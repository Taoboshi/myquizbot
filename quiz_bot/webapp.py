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
    is_user_rating_hidden,
    mark_all_time_error_resolved,
    record_attempt_finish,
    reset_user_rating,
    set_subject_setting,
    set_test_metadata_setting,
    set_user_rating_hidden,
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


def create_webapp() -> Any:
    """Create and return a configured Flask application instance."""
    from flask import Flask
    app = Flask(__name__)
    register_webapp_routes(app)
    return app


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
                return f.read(), 200, {
                    "Content-Type": "text/html; charset=utf-8",
                    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
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

        is_hidden_in_rating = False
        if user_id:
            try:
                is_hidden_in_rating = is_user_rating_hidden(int(user_id))
            except Exception:
                pass

        return jsonify({
            "is_admin": is_admin,
            "is_hidden_in_rating": is_hidden_in_rating,
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
                          AND a.user_id NOT IN (
                              SELECT user_id FROM users WHERE is_hidden_in_rating = 1
                          )
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
                        WHERE finished_at IS NOT NULL
                          AND answered > 0
                          AND user_id NOT IN (
                              SELECT user_id FROM users WHERE is_hidden_in_rating = 1
                          )
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

    @app.route("/api/user/toggle_rating_visibility", methods=["POST"])
    def api_toggle_rating_visibility():
        payload = request.get_json(silent=True) or {}
        user_id = payload.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "invalid user_id"}), 400

        is_hidden = bool(payload.get("is_hidden", False))
        set_user_rating_hidden(uid, is_hidden)
        return jsonify({"success": True, "is_hidden": is_hidden})

    @app.route("/api/user/reset_rating", methods=["POST"])
    def api_reset_rating():
        payload = request.get_json(silent=True) or {}
        user_id = payload.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not user_id:
            return jsonify({"error": "user_id required"}), 400
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return jsonify({"error": "invalid user_id"}), 400

        res = reset_user_rating(uid)
        return jsonify({"success": True, "deleted_attempts": res.get("attempts", 0)})

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

        from .config import SUBJECTS
        from .storage import clear_cache, get_subject_setting
        subj_info = (get_subject_setting(subject_id) if get_subject_setting else None) or SUBJECTS.get(subject_id) or {}
        subj_title = subj_info.get("title", "")
        subj_emoji = subj_info.get("emoji", "")

        set_test_metadata_setting(test_id, subject_id=subject_id, subject_title=subj_title, subject_emoji=subj_emoji, updated_by=int(user_id or 0))
        if test_id in TESTS:
            TESTS[test_id]["subject_id"] = subject_id
            TESTS[test_id]["subject_title"] = subj_title
            TESTS[test_id]["subject_emoji"] = subj_emoji
        clear_cache()
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
        if test_id in TESTS:
            TESTS[test_id]["subject_id"] = "default"
            TESTS[test_id]["subject_title"] = ""
            TESTS[test_id]["subject_emoji"] = ""
        from .storage import clear_cache
        clear_cache()
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

        for t_id in list(TESTS.keys()):
            info = effective_test_info(t_id)
            if info.get("subject_id") == sub_id:
                set_test_metadata_setting(t_id, subject_id="default", updated_by=int(user_id or 0))
                TESTS[t_id]["subject_id"] = "default"
                TESTS[t_id]["subject_title"] = ""
                TESTS[t_id]["subject_emoji"] = ""

        delete_subject_setting(sub_id)
        from .storage import clear_cache
        clear_cache()
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

        from .admin_users import ensure_admin_tables
        ensure_admin_tables()

        tab = request.args.get("tab", "all").strip().lower()
        search = request.args.get("search", "").strip().lower()
        sort = request.args.get("sort", "recent").strip().lower()

        sql = """
            SELECT
                u.user_id,
                u.username,
                u.first_name,
                u.last_name,
                u.first_seen_at AS created_at,
                u.last_seen_at,
                COUNT(DISTINCT a.attempt_id) AS attempts_total,
                SUM(CASE WHEN a.finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished_attempts,
                COALESCE(SUM(a.answered), 0) AS answered,
                COALESCE(SUM(a.correct), 0) AS correct,
                CASE
                    WHEN COALESCE(SUM(a.answered), 0) > 0
                    THEN ROUND(COALESCE(SUM(a.correct), 0) * 100.0 / COALESCE(SUM(a.answered), 0), 1)
                    ELSE 0
                END AS percent,
                COUNT(DISTINCT e.question_index) AS active_errors,
                COUNT(DISTINCT f.question_index) AS favorites,
                CASE WHEN b.user_id IS NULL THEN 0 ELSE 1 END AS is_blocked,
                b.blocked_at,
                b.reason AS blocked_reason
            FROM users u
            LEFT JOIN attempts a ON a.user_id = u.user_id
            LEFT JOIN all_time_errors e
                ON e.user_id = u.user_id AND COALESCE(e.is_resolved, 0) = 0
            LEFT JOIN favorites f ON f.user_id = u.user_id
            LEFT JOIN blocked_users b ON b.user_id = u.user_id
            GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.first_seen_at, u.last_seen_at, b.user_id, b.blocked_at, b.reason
        """

        with db_connect() as conn:
            raw_rows = conn.execute(sql).fetchall()

        items = []
        for r in raw_rows:
            d = dict(r)
            name = f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip() or d.get('username') or f"ID {d['user_id']}"
            item = {
                "user_id": d["user_id"],
                "name": name,
                "username": d.get("username") or "",
                "first_name": d.get("first_name") or "",
                "last_name": d.get("last_name") or "",
                "created_at": d.get("created_at") or "",
                "last_seen_at": d.get("last_seen_at") or d.get("created_at") or "",
                "attempts_count": int(d.get("attempts_total") or 0),
                "finished_count": int(d.get("finished_attempts") or 0),
                "answered_count": int(d.get("answered") or 0),
                "correct_count": int(d.get("correct") or 0),
                "accuracy": float(d.get("percent") or 0),
                "active_errors": int(d.get("active_errors") or 0),
                "favorites_count": int(d.get("favorites") or 0),
                "is_blocked": bool(d.get("is_blocked")),
                "blocked_at": d.get("blocked_at") or "",
                "blocked_reason": d.get("blocked_reason") or "",
            }

            if search:
                target_str = f"{item['name']} {item['username']} {item['user_id']}".lower()
                if search not in target_str:
                    continue

            if tab == "blocked" and not item["is_blocked"]:
                continue
            if tab == "active" and item["attempts_count"] == 0 and not item["last_seen_at"]:
                continue
            if tab == "with_attempts" and item["attempts_count"] == 0:
                continue

            items.append(item)

        if sort == "accuracy":
            items.sort(key=lambda x: (x["accuracy"], x["correct_count"]), reverse=True)
        elif sort == "attempts":
            items.sort(key=lambda x: (x["attempts_count"], x["finished_count"]), reverse=True)
        elif sort == "errors":
            items.sort(key=lambda x: x["active_errors"], reverse=True)
        else:
            items.sort(key=lambda x: str(x.get("last_seen_at") or x.get("created_at") or ""), reverse=True)

        return jsonify({"success": True, "users": items, "items": items, "total_count": len(items)})

    @app.route("/api/admin/user/detail", methods=["GET"])
    def api_admin_user_detail():
        user_id = request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        target_uid = request.args.get("target_user_id")
        if not target_uid:
            return jsonify({"error": "target_user_id required"}), 400

        try:
            target_uid_int = int(target_uid)
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid target_user_id"}), 400

        from .admin_users import ensure_admin_tables
        ensure_admin_tables()

        with db_connect() as conn:
            u_row = conn.execute("SELECT * FROM users WHERE user_id = ?", (target_uid_int,)).fetchone()
            b_row = conn.execute("SELECT * FROM blocked_users WHERE user_id = ?", (target_uid_int,)).fetchone()

            totals = conn.execute(
                """
                SELECT COUNT(*) AS attempts_total,
                       SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS attempts_finished,
                       COALESCE(SUM(answered), 0) AS answered,
                       COALESCE(SUM(correct), 0) AS correct,
                       MAX(started_at) AS last_attempt_at
                FROM attempts
                WHERE user_id = ?
                """,
                (target_uid_int,),
            ).fetchone()

            attempts_rows = conn.execute(
                """
                SELECT attempt_id, test_id, mode, started_at, finished_at, duration_seconds, answered, correct
                FROM attempts
                WHERE user_id = ?
                ORDER BY started_at DESC
                LIMIT 30
                """,
                (target_uid_int,),
            ).fetchall()

            errors_rows = conn.execute(
                """
                SELECT test_id, question_index, wrong_count, last_wrong_at
                FROM all_time_errors
                WHERE user_id = ? AND COALESCE(is_resolved, 0) = 0
                ORDER BY wrong_count DESC, last_wrong_at DESC
                LIMIT 30
                """,
                (target_uid_int,),
            ).fetchall()

            fav_count = conn.execute("SELECT COUNT(*) FROM favorites WHERE user_id = ?", (target_uid_int,)).fetchone()[0]

        user_info = {
            "user_id": target_uid_int,
            "name": f"{u_row['first_name'] or ''} {u_row['last_name'] or ''}".strip() if u_row else f"ID {target_uid_int}",
            "username": u_row["username"] if u_row and u_row["username"] else "",
            "first_name": u_row["first_name"] if u_row and u_row["first_name"] else "",
            "last_name": u_row["last_name"] if u_row and u_row["last_name"] else "",
            "created_at": u_row["first_seen_at"] if u_row and u_row["first_seen_at"] else "",
            "last_seen_at": u_row["last_seen_at"] if u_row and u_row["last_seen_at"] else "",
            "is_blocked": b_row is not None,
            "blocked_at": b_row["blocked_at"] if b_row and b_row["blocked_at"] else "",
            "blocked_reason": b_row["reason"] if b_row and b_row["reason"] else "",
        }

        ans_tot = int(totals["answered"] or 0) if totals else 0
        cor_tot = int(totals["correct"] or 0) if totals else 0
        acc = round((cor_tot * 100.0 / ans_tot), 1) if ans_tot > 0 else 0.0

        stats_info = {
            "attempts_total": int(totals["attempts_total"] or 0) if totals else 0,
            "attempts_finished": int(totals["attempts_finished"] or 0) if totals else 0,
            "answered": ans_tot,
            "correct": cor_tot,
            "percent": acc,
            "active_errors": len(errors_rows),
            "favorites": fav_count,
        }

        attempts_list = []
        for a in attempts_rows:
            t_id = a["test_id"]
            ans = int(a["answered"] or 0)
            cor = int(a["correct"] or 0)
            attempts_list.append({
                "attempt_id": a["attempt_id"],
                "test_id": t_id,
                "test_title": effective_test_info(t_id).get("title", t_id),
                "mode": a["mode"] or "exam",
                "started_at": a["started_at"] or "",
                "finished_at": a["finished_at"] or "",
                "duration_seconds": int(a["duration_seconds"] or 0),
                "answered": ans,
                "correct": cor,
                "percent": round((cor * 100.0 / ans), 1) if ans > 0 else 0,
            })

        errors_list = []
        for e in errors_rows:
            t_id = e["test_id"]
            q_idx = int(e["question_index"] or 0)
            t_qs = LOADED_TESTS.get(t_id, [])
            q_text = t_qs[q_idx]["question"] if q_idx < len(t_qs) else f"Вопрос #{q_idx+1}"
            errors_list.append({
                "test_id": t_id,
                "test_title": effective_test_info(t_id).get("title", t_id),
                "question_index": q_idx + 1,
                "question_text": q_text,
                "wrong_count": int(e["wrong_count"] or 1),
            })

        return jsonify({
            "success": True,
            "user": user_info,
            "stats": stats_info,
            "attempts": attempts_list,
            "errors": errors_list,
        })

    @app.route("/api/admin/user/block", methods=["POST"])
    def api_admin_user_block():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        target_uid = data.get("target_user_id")
        reason = data.get("reason", "").strip() or "Ограничение доступа администратором"
        if not target_uid:
            return jsonify({"error": "target_user_id required"}), 400

        from .admin_users import block_user
        block_user(int(target_uid), int(user_id or 0), reason)
        return jsonify({"success": True, "target_user_id": target_uid, "is_blocked": True})

    @app.route("/api/admin/user/unblock", methods=["POST"])
    def api_admin_user_unblock():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        target_uid = data.get("target_user_id")
        if not target_uid:
            return jsonify({"error": "target_user_id required"}), 400

        from .admin_users import unblock_user
        unblock_user(int(target_uid))
        return jsonify({"success": True, "target_user_id": target_uid, "is_blocked": False})

    @app.route("/api/admin/user/send_message", methods=["POST"])
    def api_admin_user_send_message():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id") or request.args.get("user_id") or request.headers.get("X-Telegram-User-Id")
        if not is_admin_user(user_id):
            return jsonify({"error": "Forbidden"}), 403

        target_uid = data.get("target_user_id")
        text = data.get("text", "").strip()
        if not target_uid or not text:
            return jsonify({"error": "target_user_id and text required"}), 400

        bot_token = get_bot_token()
        if not bot_token:
            return jsonify({
                "success": True,
                "simulation": True,
                "message": "Локальный режим: бот-токен не настроен, сообщение сымитировано.",
            })

        import asyncio
        from telegram import Bot

        async def _send_direct():
            bot = Bot(bot_token)
            await bot.send_message(chat_id=int(target_uid), text=text, parse_mode="HTML")

        try:
            asyncio.run(_send_direct())
            return jsonify({"success": True, "sent": True})
        except Exception as e:
            logger.warning("Failed to send message to user %s: %s", target_uid, e)
            return jsonify({"error": f"Ошибка отправки: {str(e)}"}), 500

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

        from .admin_users import reset_user_progress
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



