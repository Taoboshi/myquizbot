"""Paginated Mini App user management. All actions use verified admin identity."""

import asyncio
import time
from datetime import datetime, timedelta, timezone

from flask import jsonify, request

from . import storage
from .admin_users import block_user, ensure_admin_tables, unblock_user
from .config import ADMIN_IDS, get_bot_token, get_env_admin_ids
from .loader import LOADED_TESTS


def ensure_people_tables():
    ensure_admin_tables()
    with storage.db_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS admin_user_notes (
            user_id BIGINT PRIMARY KEY, note TEXT NOT NULL, updated_by BIGINT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS admin_user_messages (
            message_id TEXT PRIMARY KEY, user_id BIGINT NOT NULL, sent_by BIGINT NOT NULL,
            text TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_progress_resets (
            user_id BIGINT NOT NULL, test_id TEXT NOT NULL, kind TEXT NOT NULL,
            version TEXT NOT NULL, PRIMARY KEY(user_id, test_id, kind))""")
        conn.execute("CREATE INDEX IF NOT EXISTS admin_messages_user ON admin_user_messages(user_id, created_at)")
        conn.commit()


def reset_markers(user_id):
    ensure_people_tables()
    with storage.db_connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT test_id, kind, version FROM user_progress_resets WHERE user_id = ?", (user_id,)
        ).fetchall()]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _page():
    try:
        page = int(request.args.get("page", 0))
        if page < 0 or page > 100000:
            raise ValueError()
        return page
    except ValueError:
        raise ValueError("Некорректная страница") from None


def _user_dict(row):
    data = dict(row)
    telegram_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")]))
    data["telegram_name"] = telegram_name
    data["name"] = data.get("profile_name") or telegram_name or data.get("username") or str(data["user_id"])
    data["avatar"] = data.get("profile_avatar") or ""
    until = data.get("blocked_until")
    data["is_blocked"] = bool(data.get("blocked_at") and (not until or str(until) > str(_now())))
    for key in ["created_at", "last_seen_at", "blocked_at", "blocked_until"]:
        if data.get(key) is not None:
            data[key] = str(data[key])
    return data


def people_list():
    ensure_people_tables()
    page = _page()
    query = request.args.get("search", "").strip()[:100]
    tab = request.args.get("tab", "all")
    where, params = [], []
    if query:
        where.append("LOWER(COALESCE(u.profile_name,'') || ' ' || COALESCE(u.first_name,'') || ' ' || COALESCE(u.last_name,'') || ' ' || COALESCE(u.username,'') || ' ' || CAST(u.user_id AS TEXT)) LIKE ? ESCAPE '!'")
        literal = query.lower().lstrip('@').replace('!', '!!').replace('%', '!%').replace('_', '!_')
        params.append("%" + literal + "%")
    if tab in {"active7", "active30", "inactive30", "active"}:
        threshold = _now() - timedelta(days=7 if tab in {"active7", "active"} else 30)
        where.append("COALESCE(u.last_seen_at,u.first_seen_at) " + ("<" if tab == "inactive30" else ">=") + " ?")
        params.append(str(threshold))
    if tab == "blocked":
        where.append("b.user_id IS NOT NULL AND (b.blocked_until IS NULL OR b.blocked_until > ?)")
        params.append(str(_now()))
    if tab == "with_attempts":
        where.append("EXISTS (SELECT 1 FROM attempts a WHERE a.user_id=u.user_id)")
    if tab == "with_access":
        where.append("EXISTS (SELECT 1 FROM user_test_access x WHERE x.user_id=u.user_id)")
    clause = " WHERE " + " AND ".join(where) if where else ""
    order = {"accuracy": "accuracy DESC", "attempts": "attempts_count DESC", "errors": "active_errors DESC"}.get(request.args.get("sort"), "u.last_seen_at DESC")
    source = " FROM users u LEFT JOIN blocked_users b ON b.user_id=u.user_id"
    with storage.db_connect() as conn:
        if not storage.DATABASE_URL:
            conn.create_function('LOWER', 1, lambda text: str(text).lower() if text is not None else None)
        total = conn.execute("SELECT COUNT(*) AS c" + source + clause, tuple(params)).fetchone()["c"]
        rows = conn.execute("""SELECT u.user_id, u.username, u.first_name, u.last_name,
            u.profile_name, u.profile_avatar, u.first_seen_at AS created_at, u.last_seen_at,
            b.blocked_at, b.blocked_until, b.reason AS blocked_reason,
            (SELECT COUNT(*) FROM attempts a WHERE a.user_id=u.user_id) AS attempts_count,
            (SELECT COUNT(*) FROM all_time_errors e WHERE e.user_id=u.user_id AND COALESCE(e.is_resolved,0)=0) AS active_errors,
            (SELECT COUNT(*) FROM user_test_access x WHERE x.user_id=u.user_id) AS access_count,
            (SELECT CASE WHEN SUM(a.answered)>0 THEN ROUND(SUM(a.correct)*100.0/SUM(a.answered),1) ELSE 0 END FROM attempts a WHERE a.user_id=u.user_id) AS accuracy
            """ + source + clause + f" ORDER BY {order}, u.user_id DESC LIMIT ? OFFSET ?", tuple(params + [25, page * 25])).fetchall()
    return {"items": [_user_dict(row) for row in rows], "total": total, "page": page, "has_more": (page + 1) * 25 < total}


def people_detail(uid):
    from .loader import effective_test_info
    ensure_people_tables()
    page = _page()
    test_id = request.args.get("test_id", "")
    filter_sql = " AND test_id = ?" if test_id else ""
    params = (uid, test_id) if test_id else (uid,)
    try:
        days = int(request.args.get("days", 0))
        if days not in {0, 7, 30}:
            raise ValueError()
    except ValueError:
        raise ValueError("Некорректный период") from None
    attempt_filter, error_filter = filter_sql, filter_sql
    if days:
        attempt_filter += " AND started_at >= ?"
        error_filter += " AND last_wrong_at >= ?"
        params += (str(_now() - timedelta(days=days)),)
    with storage.db_connect() as conn:
        user = conn.execute("""SELECT u.*, u.first_seen_at AS created_at, b.blocked_at,
            b.blocked_until, b.reason AS blocked_reason FROM users u
            LEFT JOIN blocked_users b ON b.user_id=u.user_id WHERE u.user_id=?""", (uid,)).fetchone()
        if not user:
            return None
        totals = conn.execute("""SELECT COUNT(*) AS attempts_total,
            COALESCE(SUM(answered),0) AS answered, COALESCE(SUM(correct),0) AS correct,
            SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished
            FROM attempts WHERE user_id=?""" + attempt_filter, params).fetchone()
        errors_count = conn.execute("SELECT COUNT(*) AS c FROM all_time_errors WHERE user_id=? AND COALESCE(is_resolved,0)=0" + error_filter, params).fetchone()["c"]
        attempts = conn.execute("SELECT * FROM attempts WHERE user_id=?" + attempt_filter + " ORDER BY started_at DESC, attempt_id DESC LIMIT 25 OFFSET ?", params + (page * 25,)).fetchall()
        errors = conn.execute("SELECT * FROM all_time_errors WHERE user_id=? AND COALESCE(is_resolved,0)=0" + error_filter + " ORDER BY last_wrong_at DESC, test_id, question_index LIMIT 25 OFFSET ?", params + (page * 25,)).fetchall()
        accesses = conn.execute("SELECT * FROM user_test_access WHERE user_id=? ORDER BY granted_at DESC", (uid,)).fetchall()
        note = conn.execute("SELECT * FROM admin_user_notes WHERE user_id=?", (uid,)).fetchone()
        messages = conn.execute("SELECT * FROM admin_user_messages WHERE user_id=? ORDER BY created_at DESC, message_id DESC LIMIT 25 OFFSET ?", (uid, page * 25)).fetchall()
        message_count = conn.execute("SELECT COUNT(*) AS c FROM admin_user_messages WHERE user_id=?", (uid,)).fetchone()["c"]
        test_rows = conn.execute("SELECT DISTINCT test_id FROM attempts WHERE user_id=? UNION SELECT DISTINCT test_id FROM all_time_errors WHERE user_id=?", (uid, uid)).fetchall()
    def titled(rows):
        items = []
        for row in rows:
            test_id = row["test_id"]
            try:
                title = effective_test_info(test_id).get("title", test_id)
            except KeyError:
                title = test_id
            items.append({**dict(row), "test_title": title})
        return items
    error_items = titled(errors)
    for item in error_items:
        questions = LOADED_TESTS.get(item["test_id"], [])
        index = int(item["question_index"])
        item["question_text"] = questions[index]["question"] if 0 <= index < len(questions) else "Вопрос удалён"
    return {"user": _user_dict(user), "stats": {**dict(totals), "active_errors": errors_count},
            "attempts": titled(attempts), "errors": error_items, "access": titled(accesses),
            "tests": titled(test_rows), "note": dict(note) if note else {}, "messages": [dict(row) for row in messages],
            "message_count": message_count, "page": page}


def reset_progress(uid, kind, test_id=""):
    # A marker invalidates old device copies on the next authenticated sync.
    kinds = {"history", "errors", "favorites", "all"}
    if kind not in kinds:
        raise ValueError("Неизвестный вид сброса")
    clause = " WHERE user_id=?" + (" AND test_id=?" if test_id else "")
    params = (uid, test_id) if test_id else (uid,)
    tables = []
    if kind in {"history", "all"}:
        tables += ["attempt_wrong_answers", "attempts", "user_stats", "user_answered_questions", "active_sessions", "runtime_sessions"]
    if kind in {"errors", "all"}:
        tables.append("all_time_errors")
    if kind in {"favorites", "all"}:
        tables.append("favorites")
    with storage.db_connect() as conn:
        for table in tables:
            if table == "runtime_sessions" and not storage._table_exists(conn, table):
                continue
            conn.execute(f"DELETE FROM {table}" + clause, params)
        conn.execute("""INSERT INTO user_progress_resets(user_id,test_id,kind,version) VALUES(?,?,?,?)
            ON CONFLICT(user_id,test_id,kind) DO UPDATE SET version=excluded.version""", (uid, test_id, kind, str(time.time_ns())))
        conn.commit()


def register_people_routes(app):
    from .webapp import authenticated_user_id, is_admin_user

    @app.route("/api/admin/people")
    def admin_people():
        if not is_admin_user():
            return jsonify({"error": "Forbidden"}), 403
        try:
            return jsonify(people_list())
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    @app.route("/api/admin/people/<int:uid>")
    def admin_person(uid):
        if not is_admin_user():
            return jsonify({"error": "Forbidden"}), 403
        try:
            data = people_detail(uid)
            return jsonify(data) if data else (jsonify({"error": "Пользователь не найден"}), 404)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    @app.route("/api/admin/people/<int:uid>/action", methods=["POST"])
    def admin_person_action(uid):
        if not is_admin_user():
            return jsonify({"error": "Forbidden"}), 403
        ensure_people_tables()
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Некорректные данные"}), 400
        with storage.db_connect() as conn:
            if not conn.execute("SELECT user_id FROM users WHERE user_id=?", (uid,)).fetchone():
                return jsonify({"error": "Пользователь не найден"}), 404
        actor = authenticated_user_id()
        action = payload.get("action")
        try:
            if action in {"block", "unblock"}:
                if uid == actor or uid in (get_env_admin_ids() or ADMIN_IDS):
                    raise ValueError("Нельзя блокировать администратора")
                if action == "block":
                    reason = payload.get("reason", "")
                    days = payload.get("days", 0)
                    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500 or type(days) is not int or days not in {0, 1, 7, 30}:
                        raise ValueError("Укажите причину и допустимый срок")
                    until = str(_now() + timedelta(days=days)) if days else None
                    block_user(uid, actor, reason.strip(), until)
                else:
                    unblock_user(uid)
            elif action == "note":
                text = payload.get("text", "")
                if not isinstance(text, str) or len(text) > 5000:
                    raise ValueError("Заметка должна быть не длиннее 5000 символов")
                with storage.db_connect() as conn:
                    conn.execute("""INSERT INTO admin_user_notes(user_id,note,updated_by) VALUES(?,?,?)
                        ON CONFLICT(user_id) DO UPDATE SET note=excluded.note, updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP""", (uid, text.strip(), actor))
                    conn.commit()
            elif action in {"grant", "revoke", "reset"}:
                test_id = payload.get("test_id", "")
                if not isinstance(test_id, str) or (test_id and test_id not in LOADED_TESTS):
                    raise ValueError("Тест не найден")
                if action == "reset":
                    if payload.get("confirmed") is not True:
                        raise ValueError("Подтвердите сброс")
                    reset_progress(uid, payload.get("kind"), test_id)
                elif not test_id:
                    raise ValueError("Выберите тест")
                elif action == "grant":
                    from .access import effective_access_type
                    if effective_access_type(test_id) == "admin_only":
                        raise ValueError("Этот тест доступен только администраторам")
                    storage.grant_user_test_access(uid, test_id, "admin", actor)
                else:
                    storage.revoke_user_test_access(uid, test_id)
            elif action == "message":
                text = payload.get("text", "")
                if not isinstance(text, str) or not text.strip() or len(text) > 4096:
                    raise ValueError("Сообщение должно содержать от 1 до 4096 символов")
                token = get_bot_token(required=False)
                status, error = "sent", ""
                if not token:
                    status, error = "failed", "Бот не настроен. Сообщение не отправлено."
                else:
                    from telegram import Bot
                    async def send():
                        async with Bot(token) as bot:
                            await bot.send_message(chat_id=uid, text=text.strip())
                    try:
                        asyncio.run(send())
                    except Exception:
                        status, error = "failed", "Telegram не принял сообщение. Пользователь мог заблокировать бота."
                with storage.db_connect() as conn:
                    conn.execute("INSERT INTO admin_user_messages(message_id,user_id,sent_by,text,status,error) VALUES(?,?,?,?,?,?)", (str(time.time_ns()), uid, actor, text.strip(), status, error))
                    conn.commit()
                return jsonify({"success": status == "sent", "error": error}), 200 if status == "sent" else 502
            else:
                raise ValueError("Неизвестное действие")
        except (ValueError, TypeError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"success": True})
