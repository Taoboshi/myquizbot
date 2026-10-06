"""Flask web application and REST API for ohTest Telegram Mini App."""

import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import ADMIN_IDS, BASE_DIR, TESTS, get_bot_token, get_env_admin_ids
from .loader import (
    LOADED_TESTS,
    effective_test_info,
    get_questions,
    get_subjects,
    get_tests_for_subject,
    get_unassigned_tests,
    load_tests,
)
from .storage import (
    DATABASE_URL,
    add_all_time_error,
    clear_all_time_errors,
    db_connect,
    delete_subject_setting,
    ensure_user_stats,
    get_all_time_error_indices,
    mark_all_time_error_resolved,
    record_attempt_finish,
    set_subject_setting,
    set_test_metadata_setting,
    toggle_favorite,
    upsert_user,
)

logger = logging.getLogger(__name__)


def is_admin_user(user_id: Any) -> bool:
    admin_ids = get_env_admin_ids() or ADMIN_IDS
    if not admin_ids:
        # If no admin IDs configured yet in environment, allow access so the project owner is not locked out
        return True
    if not user_id:
        return False
    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        return False
    return uid in admin_ids


def register_webapp_routes(app: Any) -> None:
    """Register all Mini App frontend and API routes on the Flask app."""
    if not hasattr(app, "route"):
        return

    from flask import jsonify, request

    @app.route("/app")
    @app.route("/ohtest")
    def serve_mini_app():
        index_file = Path(__file__).resolve().parent / "web" / "index.html"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
        return "ohTest Mini App is starting up...", 200

    @app.route("/api/bootstrap", methods=["GET", "POST"])
    def api_bootstrap():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if user_id:
            try:
                uid = int(user_id)
                u_name = request.args.get("name") or ""
                u_uname = request.args.get("username") or ""
                u_fname = request.args.get("first_name") or u_name or f"User {uid}"
                u_lname = request.args.get("last_name") or ""

                class _WebUser:
                    def __init__(self, u_id, uname, fname, lname):
                        self.id = u_id
                        self.username = uname
                        self.first_name = fname
                        self.last_name = lname

                upsert_user(_WebUser(uid, u_uname, u_fname, u_lname))
            except Exception as e:
                logger.warning("Failed to auto-upsert web user %s: %s", user_id, e)

        is_admin = is_admin_user(user_id)

        from .access import effective_test_access

        subjects_data = []
        for s_id, s_info in get_subjects():
            tests_list = []
            for t_id, t_info in get_tests_for_subject(s_id):
                info = effective_test_info(t_id)
                acc = effective_test_access(t_id)
                acc_type = acc.get("type", "public")
                acc_code = acc.get("code", "")
                tests_list.append({
                    "id": t_id,
                    "title": info.get("title", t_id),
                    "questions_count": len(LOADED_TESTS.get(t_id, [])),
                    "description": info.get("description", ""),
                    "access_type": acc_type,
                    "access_code": acc_code if is_admin else "",
                })
            subjects_data.append({
                "id": s_id,
                "title": s_info.get("title", s_id),
                "emoji": s_info.get("emoji", "📚"),
                "tests": tests_list,
                "tests_count": len(tests_list),
            })

        unassigned_data = []
        for t_id, t_info in get_unassigned_tests():
            info = effective_test_info(t_id)
            acc = effective_test_access(t_id)
            acc_type = acc.get("type", "public")
            acc_code = acc.get("code", "")
            unassigned_data.append({
                "id": t_id,
                "title": info.get("title", t_id),
                "questions_count": len(LOADED_TESTS.get(t_id, [])),
                "file": t_info.get("file", ""),
                "access_type": acc_type,
                "access_code": acc_code if is_admin else "",
            })

        return jsonify({
            "is_admin": is_admin,
            "subjects": subjects_data,
            "unassigned_tests": unassigned_data,
            "total_loaded_tests": len(LOADED_TESTS),
        })

    @app.route("/api/tests/<test_id>", methods=["GET"])
    def api_test_detail(test_id: str):
        if test_id not in LOADED_TESTS:
            return jsonify({"error": "Test not found"}), 404

        info = effective_test_info(test_id)
        raw_qs = LOADED_TESTS[test_id]
        clean_qs = []
        for i, q in enumerate(raw_qs):
            correct_idx = q.get("correct_index")
            if correct_idx is None:
                correct_idx = q.get("correct", 0)
            try:
                correct_idx = int(correct_idx)
            except (ValueError, TypeError):
                correct_idx = 0

            options = [str(opt).strip() for opt in q.get("options", [])]
            if correct_idx >= len(options):
                correct_idx = 0

            clean_qs.append({
                "id": i + 1,
                "question": q.get("question", "").strip(),
                "options": options,
                "correct": correct_idx,
                "explanation": q.get("explanation") or (f"Правильный ответ: {options[correct_idx]}" if options else ""),
            })

        from .access import effective_test_access
        acc = effective_test_access(test_id)

        return jsonify({
            "id": test_id,
            "title": info.get("title", test_id),
            "subject_id": info.get("subject_id", "default"),
            "subject_title": info.get("subject_title", ""),
            "questions_count": len(clean_qs),
            "questions": clean_qs,
            "access_type": acc.get("type", "public"),
        })

    @app.route("/api/rating", methods=["GET"])
    def api_rating():
        test_id = request.args.get("test_id")
        subject_id = request.args.get("subject_id")

        target_test_ids = []
        if test_id and test_id not in ("all", ""):
            target_test_ids = [test_id]
        elif subject_id and subject_id not in ("all", ""):
            target_test_ids = [t_id for t_id, _ in get_tests_for_subject(subject_id)]

        with db_connect() as conn:
            if target_test_ids:
                placeholders = ",".join(["?"] * len(target_test_ids))
                rows = conn.execute(
                    f"""
                    WITH ranked_attempts AS (
                        SELECT
                            a.*,
                            (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) AS percent_value,
                            ROW_NUMBER() OVER (
                                PARTITION BY a.user_id
                                ORDER BY
                                    a.answered DESC,
                                    (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) DESC,
                                    a.duration_seconds ASC,
                                    a.finished_at DESC
                            ) AS user_rank
                        FROM attempts a
                        WHERE a.test_id IN ({placeholders})
                          AND a.finished_at IS NOT NULL
                          AND a.answered > 0
                    )
                    SELECT r.*, u.user_id, u.username, u.first_name, u.last_name
                    FROM ranked_attempts r
                    LEFT JOIN users u ON u.user_id = r.user_id
                    WHERE r.user_rank = 1
                    ORDER BY
                        r.answered DESC,
                        r.percent_value DESC,
                        r.duration_seconds ASC
                    LIMIT 20
                    """,
                    tuple(target_test_ids),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    WITH user_scores AS (
                        SELECT
                            user_id,
                            COUNT(*) as attempts_count,
                            SUM(correct) as total_correct,
                            SUM(answered) as total_answered,
                            AVG(CAST(correct AS REAL) / NULLIF(answered, 0)) * 100 as avg_pct
                        FROM attempts
                        WHERE finished_at IS NOT NULL AND answered > 0
                        GROUP BY user_id
                    )
                    SELECT s.*, u.username, u.first_name, u.last_name
                    FROM user_scores s
                    LEFT JOIN users u ON u.user_id = s.user_id
                    ORDER BY s.total_correct DESC, s.avg_pct DESC
                    LIMIT 20
                    """
                ).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            name = f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip() or d.get('username') or f"Пользователь {d.get('user_id')}"
            
            raw_pct = d.get("percent_value")
            if raw_pct is None:
                raw_pct = d.get("avg_pct")
            pct_val = 0
            if raw_pct is not None:
                try:
                    num = float(raw_pct)
                    if "percent_value" in d and num <= 1.0:
                        num = num * 100.0
                    pct_val = round(num)
                except (ValueError, TypeError):
                    pct_val = 0

            score_val = d.get("correct") if "correct" in d and d.get("correct") is not None else d.get("total_correct", 0)
            total_val = d.get("answered") if "answered" in d and d.get("answered") is not None else d.get("total_answered", 0)
            dur_val = d.get("duration_seconds", 0) or 0

            items.append({
                "user_id": int(d.get("user_id") or 0),
                "name": str(name),
                "username": str(d.get("username") or ""),
                "score": int(score_val or 0),
                "total": int(total_val or 0),
                "percent": int(pct_val),
                "duration": int(dur_val),
            })

        return jsonify({
            "items": items,
            "subject_id": subject_id or "all",
            "test_id": test_id or "all",
        })

    @app.route("/api/attempts/record", methods=["POST"])
    def api_record_attempt():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or 9990001
        test_id = data.get("test_id")
        correct = int(data.get("correct", 0))
        answered = int(data.get("answered", 0))
        duration = int(data.get("duration", 0))
        mode = data.get("mode", "normal")
        wrong_questions = data.get("wrong_questions", [])

        if not test_id:
            return jsonify({"error": "test_id required"}), 400

        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "invalid user_id"}), 400

        # Ensure user row exists
        with db_connect() as conn:
            user_row = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)).fetchone()
            if not user_row:
                conn.execute(
                    "INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
                    (uid, data.get("first_name", f"User {uid}"), data.get("username", "")),
                )

            # Record attempt
            if DATABASE_URL:
                cur = conn.execute(
                    """
                    INSERT INTO attempts (user_id, test_id, mode, answered, correct, duration_seconds, completed_full_test, finished_by_user, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP)
                    RETURNING attempt_id
                    """,
                    (uid, test_id, mode, answered, correct, duration),
                )
                attempt_id = cur.fetchone()["attempt_id"]
            else:
                cur = conn.execute(
                    """
                    INSERT INTO attempts (user_id, test_id, mode, answered, correct, duration_seconds, completed_full_test, finished_by_user, finished_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, 1, CURRENT_TIMESTAMP)
                    """,
                    (uid, test_id, mode, answered, correct, duration),
                )
                attempt_id = cur.lastrowid

            ensure_user_stats(uid, test_id)
            conn.execute(
                """
                UPDATE user_stats
                SET attempts_started = attempts_started + 1,
                    attempts_finished = attempts_finished + 1,
                    last_activity_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND test_id = ?
                """,
                (uid, test_id),
            )
            conn.commit()

        # Record wrong answers
        for q_idx in wrong_questions:
            try:
                add_all_time_error(uid, test_id, int(q_idx) - 1, None)
            except Exception:
                pass

        return jsonify({"success": True, "attempt_id": attempt_id})

    @app.route("/api/errors/record", methods=["POST"])
    def api_record_single_error():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or 9990001
        test_id = data.get("test_id")
        question_id = data.get("question_id")
        user_answer = data.get("user_answer")

        if not test_id or question_id is None:
            return jsonify({"error": "test_id and question_id required"}), 400

        try:
            uid = int(user_id)
            qid = int(question_id)
            add_all_time_error(uid, test_id, qid - 1, user_answer)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        return jsonify({"success": True, "recorded": qid})

    @app.route("/api/errors/resolve", methods=["POST"])
    def api_resolve_error():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id")
        test_id = data.get("test_id")
        question_id = data.get("question_id")

        if not user_id or not test_id or question_id is None:
            return jsonify({"error": "user_id, test_id and question_id required"}), 400

        try:
            uid = int(user_id)
            qid = int(question_id)
            mark_all_time_error_resolved(uid, test_id, qid - 1)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        return jsonify({"success": True, "resolved": qid})

    @app.route("/api/errors/clear", methods=["POST"])
    def api_clear_errors():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id")
        test_id = data.get("test_id")

        if not user_id or not test_id:
            return jsonify({"error": "user_id and test_id required"}), 400

        try:
            uid = int(user_id)
            clear_all_time_errors(uid, test_id)
        except Exception as e:
            return jsonify({"error": str(e)}), 400

        return jsonify({"success": True, "cleared": test_id})

    @app.route("/api/user/state", methods=["GET"])
    def api_user_state():
        user_id = request.args.get("user_id")
        test_id = request.args.get("test_id")

        if not user_id or not test_id:
            return jsonify({"error": "user_id and test_id required"}), 400

        try:
            uid = int(user_id)
            err_indices = get_all_time_error_indices(uid, test_id)
            # convert 0-based question_index to 1-based question id
            error_ids = [i + 1 for i in err_indices]
            with db_connect() as conn:
                fav_rows = conn.execute(
                    "SELECT question_index FROM favorites WHERE user_id = ? AND test_id = ? AND is_favorite = 1",
                    (uid, test_id),
                ).fetchall()
            favorite_ids = [r["question_index"] + 1 for r in fav_rows]
            return jsonify({"test_id": test_id, "errors": error_ids, "favorites": favorite_ids})
        except Exception as e:
            return jsonify({"errors": [], "favorites": []})

    # ==========================================
    # ADMIN API ENDPOINTS
    # ==========================================

    @app.route("/api/admin/overview", methods=["GET"])
    def api_admin_overview():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        with db_connect() as conn:
            users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            attempts_count = conn.execute("SELECT COUNT(*) FROM attempts WHERE finished_at IS NOT NULL").fetchone()[0]

        return jsonify({
            "users_count": users_count,
            "attempts_count": attempts_count,
            "tests_count": len(LOADED_TESTS),
            "subjects_count": len(get_subjects()),
            "unassigned_count": len(get_unassigned_tests()),
        })

    @app.route("/api/admin/unassigned", methods=["GET"])
    def api_admin_unassigned():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        items = []
        for t_id, t_info in get_unassigned_tests():
            info = effective_test_info(t_id)
            items.append({
                "id": t_id,
                "title": info.get("title", t_id),
                "questions_count": len(LOADED_TESTS.get(t_id, [])),
                "file": t_info.get("file", ""),
            })
        return jsonify({"items": items})

    @app.route("/api/admin/assign_test", methods=["POST"])
    def api_admin_assign_test():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        test_id = data.get("test_id")
        subject_id = data.get("subject_id")

        if not test_id or not subject_id:
            return jsonify({"error": "test_id and subject_id required"}), 400

        set_test_metadata_setting(test_id, subject_id=subject_id, updated_by=int(user_id or 0))
        return jsonify({"success": True, "test_id": test_id, "subject_id": subject_id})

    @app.route("/api/admin/unlink_test", methods=["POST"])
    def api_admin_unlink_test():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        test_id = data.get("test_id")
        if not test_id:
            return jsonify({"error": "test_id required"}), 400

        set_test_metadata_setting(test_id, subject_id="default", updated_by=int(user_id or 0))
        return jsonify({"success": True, "unlinked_id": test_id})

    @app.route("/api/admin/add_subject", methods=["POST"])
    def api_admin_add_subject():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        sub_id = data.get("id") or data.get("title", "").strip().lower().replace(" ", "_")
        title = data.get("title", "").strip()
        emoji = data.get("emoji", "📚").strip()

        if not sub_id or not title:
            return jsonify({"error": "id and title required"}), 400

        set_subject_setting(sub_id, title=title, emoji=emoji, updated_by=int(user_id or 0))
        return jsonify({"success": True, "subject_id": sub_id, "title": title})

    @app.route("/api/admin/edit_subject", methods=["POST"])
    def api_admin_edit_subject():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        sub_id = data.get("id")
        title = data.get("title", "").strip()
        emoji = data.get("emoji", "📚").strip()

        if not sub_id or not title:
            return jsonify({"error": "id and title required"}), 400

        set_subject_setting(sub_id, title=title, emoji=emoji, updated_by=int(user_id or 0))
        return jsonify({"success": True, "subject_id": sub_id, "title": title, "emoji": emoji})

    @app.route("/api/admin/delete_subject", methods=["POST"])
    def api_admin_delete_subject():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        sub_id = data.get("id")
        if not sub_id:
            return jsonify({"error": "id required"}), 400

        delete_subject_setting(sub_id)
        return jsonify({"success": True, "deleted_id": sub_id})

    @app.route("/api/admin/frequent_errors", methods=["GET"])
    def api_admin_frequent_errors():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        with db_connect() as conn:
            rows = conn.execute(
                """
                SELECT test_id, question_index, SUM(wrong_count) AS c, COUNT(DISTINCT user_id) AS users
                FROM all_time_errors
                WHERE COALESCE(is_resolved, 0) = 0
                GROUP BY test_id, question_index
                ORDER BY c DESC
                LIMIT 20
                """
            ).fetchall()

        items = []
        for r in rows:
            t_id = r["test_id"]
            q_idx = int(r["question_index"])
            t_qs = LOADED_TESTS.get(t_id, [])
            q_text = t_qs[q_idx]["question"] if q_idx < len(t_qs) else f"Вопрос #{q_idx+1}"
            items.append({
                "test_id": t_id,
                "test_title": effective_test_info(t_id).get("title", t_id),
                "question_index": q_idx + 1,
                "question_text": q_text,
                "error_count": r["c"],
                "users_count": r["users"],
            })
        return jsonify({"items": items})

    @app.route("/api/admin/users", methods=["GET"])
    def api_admin_users():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        with db_connect() as conn:
            rows = conn.execute(
                """
                SELECT u.user_id, u.username, u.first_name, u.last_name, u.first_seen_at as created_at,
                       COUNT(a.attempt_id) as attempts_count
                FROM users u
                LEFT JOIN attempts a ON a.user_id = u.user_id
                GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.first_seen_at
                ORDER BY u.first_seen_at DESC
                LIMIT 100
                """
            ).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            items.append({
                "user_id": d["user_id"],
                "name": f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip() or d.get('username') or f"ID {d['user_id']}",
                "username": d.get("username") or "",
                "created_at": d.get("created_at") or "",
                "attempts_count": d.get("attempts_count") or 0,
            })
        return jsonify({"items": items})

    @app.route("/api/admin/broadcast", methods=["POST"])
    def api_admin_broadcast():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(force=True) or {}
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "text required"}), 400

        bot_token = get_bot_token()
        if not bot_token:
            return jsonify({
                "success": True,
                "message": "Локальный режим: бот-токен не настроен, рассылка симулирована.",
                "sent_count": 0,
            })

        import asyncio
        from telegram import Bot

        async def _send_all():
            bot = Bot(bot_token)
            sent = 0
            with db_connect() as conn:
                u_rows = conn.execute("SELECT user_id FROM users").fetchall()
            for row in u_rows:
                try:
                    await bot.send_message(chat_id=row["user_id"], text=text, parse_mode="HTML")
                    sent += 1
                except Exception as e:
                    logger.warning("Broadcast failed for %s: %s", row["user_id"], e)
            return sent

        sent_count = asyncio.run(_send_all())
        return jsonify({"success": True, "sent_count": sent_count})

    @app.route("/api/admin/upload_test", methods=["POST"])
    def api_admin_upload_test():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        filename = None
        data = None

        if "file" in request.files:
            file = request.files["file"]
            filename = file.filename
            data = json.load(file)
        elif request.is_json:
            json_body = request.get_json()
            filename = json_body.get("filename")
            data = json_body.get("data")

        if not filename or not data:
            return jsonify({"error": "No file or data provided"}), 400

        # Validate structure
        questions = data.get("questions")
        if not isinstance(questions, list) or len(questions) == 0:
            return jsonify({"error": "JSON must contain non-empty 'questions' list"}), 400

        # Rule: Do not assign subject automatically, keep unassigned!
        data.pop("subject", None)
        data.pop("subject_id", None)

        safe_name = Path(filename).stem.strip().lower().replace(" ", "_")
        target_path = BASE_DIR / "tests" / f"{safe_name}.json"
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Reload tests in memory
        load_tests()

        return jsonify({
            "success": True,
            "test_id": safe_name,
            "title": data.get("title", safe_name),
            "questions_count": len(questions),
        })

    @app.route("/api/admin/tests", methods=["GET"])
    def api_admin_tests():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        from .access import effective_test_access
        items = []
        for t_id, qs in LOADED_TESTS.items():
            info = effective_test_info(t_id)
            acc = effective_test_access(t_id)
            items.append({
                "id": t_id,
                "title": info.get("title", t_id),
                "subject_id": info.get("subject_id", "default"),
                "subject_title": info.get("subject_title", "Не привязан"),
                "questions_count": len(qs),
                "file": TESTS.get(t_id, {}).get("file", ""),
                "access_type": acc.get("type", "public"),
                "access_code": acc.get("code", ""),
            })
        return jsonify({"items": items})

    @app.route("/api/admin/rename_test", methods=["POST"])
    def api_admin_rename_test():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(force=True) or {}
        test_id = data.get("test_id")
        title = data.get("title", "").strip()
        if not test_id or not title:
            return jsonify({"error": "test_id and title required"}), 400

        set_test_metadata_setting(test_id, title=title, updated_by=int(user_id or 0))
        return jsonify({"success": True, "test_id": test_id, "title": title})

    @app.route("/api/admin/delete_test", methods=["POST"])
    def api_admin_delete_test():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(force=True) or {}
        test_id = data.get("test_id")
        if not test_id:
            return jsonify({"error": "test_id required"}), 400

        # Delete file if exists
        file_path = BASE_DIR / "tests" / f"{test_id}.json"
        if file_path.exists():
            try:
                os.remove(file_path)
            except Exception:
                pass
        LOADED_TESTS.pop(test_id, None)
        return jsonify({"success": True, "deleted_id": test_id})

    @app.route("/api/admin/set_test_access", methods=["POST"])
    def api_admin_set_test_access():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(force=True) or {}
        test_id = data.get("test_id")
        access_type = data.get("access_type", "public")
        code = data.get("code", "")
        if not test_id:
            return jsonify({"error": "test_id required"}), 400

        from .storage import set_test_access_setting
        uid_int = int(user_id) if user_id and str(user_id).isdigit() else None
        set_test_access_setting(test_id, access_type, code=code, updated_by=uid_int)

        from .access import effective_test_access
        new_acc = effective_test_access(test_id)
        return jsonify({
            "success": True,
            "test_id": test_id,
            "access_type": new_acc.get("type", "public"),
            "access_code": new_acc.get("code", ""),
        })

    @app.route("/api/admin/reset_test_access", methods=["POST"])
    def api_admin_reset_test_access():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(force=True) or {}
        test_id = data.get("test_id")
        if not test_id:
            return jsonify({"error": "test_id required"}), 400

        from .storage import reset_test_access_setting
        reset_test_access_setting(test_id)

        from .access import effective_test_access
        new_acc = effective_test_access(test_id)
        return jsonify({
            "success": True,
            "test_id": test_id,
            "access_type": new_acc.get("type", "public"),
            "access_code": new_acc.get("code", ""),
        })

    @app.route("/api/tests/verify_code", methods=["POST"])
    def api_verify_test_code():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.headers.get("X-Telegram-User-Id")
        test_id = data.get("test_id")
        code = str(data.get("code", "")).strip()

        if not test_id or not code:
            return jsonify({"success": False, "error": "test_id and code required"}), 400

        from .access import effective_access_code, grant_user_test_access
        expected = effective_access_code(test_id)
        if not expected or expected.casefold() != code.casefold():
            return jsonify({"success": False, "error": "Неверный код доступа"}), 403

        if user_id and str(user_id).isdigit():
            try:
                grant_user_test_access(int(user_id), test_id, access_source="code")
            except Exception:
                pass

        return jsonify({"success": True, "test_id": test_id})

    @app.route("/api/admin/reset_user", methods=["POST"])
    def api_admin_reset_user():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        data = request.get_json(force=True) or {}
        target_uid = data.get("target_user_id")
        if not target_uid:
            return jsonify({"error": "target_user_id required"}), 400

        from .storage import reset_user_progress
        reset_user_progress(int(target_uid))
        return jsonify({"success": True, "target_user_id": target_uid})

    @app.route("/api/support/feedback", methods=["POST"])
    def api_support_feedback():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.headers.get("X-Telegram-User-Id")
        message = data.get("message", "").strip()
        contact = data.get("contact", "").strip()
        fb_type = data.get("type", "feedback").strip()
        test_id = data.get("test_id", "")
        question_id = data.get("question_id", "")
        if not message:
            return jsonify({"error": "Message required"}), 400

        try:
            from .storage import save_support_feedback
            uid_int = int(user_id) if user_id and str(user_id).isdigit() else None
            save_support_feedback(
                user_id=uid_int,
                contact=contact,
                fb_type=fb_type,
                message=message,
                test_id=test_id
            )
        except Exception as e:
            logger.warning("Failed to save feedback to db: %s", e)

        # Notify Telegram Admin if BOT_TOKEN and admin ids exist
        try:
            token = get_bot_token(required=False)
            admin_ids = get_env_admin_ids()
            if token and admin_ids:
                import urllib.request
                import json as py_json
                text = (
                    f"📩 <b>Новое обращение в поддержку ohTest!</b>\n"
                    f"👤 <b>Пользователь:</b> {user_id or '—'}\n"
                    f"📱 <b>Контакт:</b> {contact or '@issdm'}\n"
                    f"🏷️ <b>Тип:</b> {fb_type}\n"
                    f"📚 <b>Тест:</b> {test_id or '—'}\n\n"
                    f"💬 <b>Текст:</b>\n{message}"
                )
                for aid in admin_ids:
                    try:
                        url = f"https://api.telegram.org/bot{token}/sendMessage"
                        payload = py_json.dumps({"chat_id": aid, "text": text, "parse_mode": "HTML"}).encode("utf-8")
                        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                        urllib.request.urlopen(req, timeout=3)
                    except Exception:
                        pass
        except Exception:
            pass

        return jsonify({"success": True, "message": "Feedback received"})

    @app.route("/api/admin/feedback", methods=["GET"])
    def api_admin_feedback():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        from .storage import list_support_feedback
        return jsonify({"items": list_support_feedback(limit=50)})



