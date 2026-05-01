"""Admin user, blocking and broadcast helpers."""

from .admin_core import *  # noqa: F401,F403 - split from legacy admin UI module
from .admin_core import _percent, _safe_count

_ADMIN_TABLES_READY = False


def ensure_admin_tables() -> None:
    global _ADMIN_TABLES_READY

    if _ADMIN_TABLES_READY:
        return

    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id BIGINT PRIMARY KEY,
                blocked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                blocked_by BIGINT,
                reason TEXT
            )
            """
        )
        conn.commit()

    _ADMIN_TABLES_READY = True


def is_user_blocked(user_id: int) -> bool:
    ensure_admin_tables()
    with db_connect() as conn:
        row = conn.execute(
            "SELECT user_id FROM blocked_users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row is not None


def get_blocked_user(user_id: int):
    ensure_admin_tables()
    with db_connect() as conn:
        return conn.execute(
            """
            SELECT b.*, u.username, u.first_name, u.last_name
            FROM blocked_users b
            LEFT JOIN users u ON u.user_id = b.user_id
            WHERE b.user_id = ?
            """,
            (user_id,),
        ).fetchone()


def block_user(user_id: int, blocked_by: int, reason: str | None = None) -> None:
    ensure_admin_tables()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO blocked_users (user_id, blocked_by, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                blocked_at = CURRENT_TIMESTAMP,
                blocked_by = excluded.blocked_by,
                reason = excluded.reason
            """,
            (user_id, blocked_by, reason),
        )
        conn.commit()


def unblock_user(user_id: int) -> None:
    ensure_admin_tables()
    with db_connect() as conn:
        conn.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
        conn.commit()


def broadcast_users() -> list[int]:
    ensure_admin_tables()
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT u.user_id
            FROM users u
            LEFT JOIN blocked_users b ON b.user_id = u.user_id
            WHERE b.user_id IS NULL
            ORDER BY u.last_seen_at DESC
            """
        ).fetchall()
    return [int(row["user_id"]) for row in rows]


async def blocked_user_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or is_admin(user.id):
        return

    if not is_user_blocked(user.id):
        return

    if update.callback_query:
        await update.callback_query.answer("Доступ к боту ограничен.", show_alert=True)
    elif update.message:
        await update.message.reply_text("Доступ к боту ограничен.")

    raise ApplicationHandlerStop


def _parse_users_sort(value: str | None) -> str:
    allowed = {"recent", "result", "attempts", "errors"}
    return value if value in allowed else "recent"


def _users_sort_title(sort: str) -> str:
    return {
        "recent": "последняя активность",
        "result": "лучший средний результат",
        "attempts": "больше всего попыток",
        "errors": "больше всего ошибок",
    }.get(sort, "последняя активность")


def _users_order_sql(sort: str) -> str:
    if sort == "result":
        return "percent DESC, finished_attempts DESC, u.last_seen_at DESC"
    if sort == "attempts":
        return "attempts_total DESC, u.last_seen_at DESC"
    if sort == "errors":
        return "active_errors DESC, u.last_seen_at DESC"
    return "u.last_seen_at DESC"


def _users_query(sort: str) -> str:
    order_sql = _users_order_sql(sort)
    return f"""
        SELECT
            u.user_id,
            u.username,
            u.first_name,
            u.last_name,
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
            CASE WHEN b.user_id IS NULL THEN 0 ELSE 1 END AS is_blocked
        FROM users u
        LEFT JOIN attempts a ON a.user_id = u.user_id
        LEFT JOIN all_time_errors e
            ON e.user_id = u.user_id AND COALESCE(e.is_resolved, 0) = 0
        LEFT JOIN favorites f ON f.user_id = u.user_id
        LEFT JOIN blocked_users b ON b.user_id = u.user_id
        GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.last_seen_at, b.user_id
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """


def admin_users_text(page: int = 0, sort: str = "recent") -> str:
    ensure_admin_tables()
    sort = _parse_users_sort(sort)
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = _safe_count(conn, "users") or 0
        rows = conn.execute(_users_query(sort), (ADMIN_USERS_PAGE_SIZE, offset)).fetchall()

    total_pages = _admin_user_pages(total)
    start_num = offset + 1 if total else 0
    end_num = min(offset + len(rows), total)

    lines = [
        "👥 Пользователи",
        "",
        f"Показано: {start_num}–{end_num} из {total}",
        f"Сортировка: {_users_sort_title(sort)}",
        "",
    ]

    if not rows:
        lines.append("Пользователей пока нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=start_num):
        name = user_display_name(row)
        percent = float(row["percent"] or 0)
        answered = int(row["answered"] or 0)
        correct = int(row["correct"] or 0)
        attempts_total = int(row["attempts_total"] or 0)
        finished_attempts = int(row["finished_attempts"] or 0)
        active_errors = int(row["active_errors"] or 0)
        favorites = int(row["favorites"] or 0)
        blocked = " 🚫" if int(row["is_blocked"] or 0) else ""

        lines.append(f"{n}. {name}{blocked}")
        lines.append(f"   🎯 {percent}% · ✅ {correct}/{answered}")
        lines.append(f"   📝 попытки: {finished_attempts}/{attempts_total} · 🧠 ошибки: {active_errors} · ⭐ {favorites}")
        lines.append(f"   🕒 {fmt_msk(row['last_seen_at'])}")

    lines.extend([
        "",
        "Подсказка:",
        "🎯 — средний результат по всем ответам",
        "🧠 — активные ошибки пользователя",
    ])
    return "\n".join(lines)


def admin_users_keyboard(page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    ensure_admin_tables()
    sort = _parse_users_sort(sort)
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = _safe_count(conn, "users") or 0
        rows = conn.execute(_users_query(sort), (ADMIN_USERS_PAGE_SIZE, offset)).fetchall()

    buttons = []
    for row in rows:
        name = user_display_name(row)
        percent = float(row["percent"] or 0)
        label = f"{'🚫 ' if int(row['is_blocked'] or 0) else '👤 '}{name} · {percent}%"
        if len(label) > 38:
            label = label[:35].rstrip() + "…"
        buttons.append([InlineKeyboardButton(label, callback_data=f"admin:global_user:{row['user_id']}:{page}:{sort}")])

    buttons.extend([
        [
            InlineKeyboardButton("🕒 Активность", callback_data="admin:users:recent:0"),
            InlineKeyboardButton("🎯 Результат", callback_data="admin:users:result:0"),
        ],
        [
            InlineKeyboardButton("📝 Попытки", callback_data="admin:users:attempts:0"),
            InlineKeyboardButton("🧠 Ошибки", callback_data="admin:users:errors:0"),
        ],
    ])

    total_pages = _admin_user_pages(total)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:users:{sort}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:users:{sort}:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(buttons)


def _attempt_row_text(row) -> str:
    if not row:
        return "пока нет"
    answered = int(row["answered"] or 0)
    correct = int(row["correct"] or 0)
    percent = _percent(correct, answered)
    status = "завершена" if row["finished_at"] else "не завершена"
    return (
        f"{correct}/{answered} · {percent}% · {status}\n"
        f"Время: {seconds_to_text(row['duration_seconds'])}\n"
        f"Дата: {fmt_msk(row['started_at'])}"
    )


def admin_global_user_text(user_id: int) -> str:
    ensure_admin_tables()

    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

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
            (user_id,),
        ).fetchone()

        best_attempt = conn.execute(
            """
            SELECT test_id, mode, started_at, finished_at, duration_seconds, answered, correct
            FROM attempts
            WHERE user_id = ? AND finished_at IS NOT NULL AND answered > 0
            ORDER BY (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC, answered DESC, duration_seconds ASC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        last_attempt = conn.execute(
            """
            SELECT test_id, mode, started_at, finished_at, duration_seconds, answered, correct
            FROM attempts
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        per_tests = conn.execute(
            """
            SELECT test_id, attempts_started, attempts_finished, total_answered, total_correct, last_activity_at
            FROM user_stats
            WHERE user_id = ?
            ORDER BY last_activity_at DESC
            """,
            (user_id,),
        ).fetchall()

        favorites = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)}") or 0
        active_errors = _safe_count(conn, "all_time_errors", f"WHERE user_id = {int(user_id)} AND COALESCE(is_resolved, 0) = 0") or 0
        saved_sessions = _safe_count(conn, "active_sessions", f"WHERE user_id = {int(user_id)}") or 0
        runtime_sessions = _safe_count(conn, "runtime_sessions", f"WHERE user_id = {int(user_id)}") or 0
        blocked = conn.execute("SELECT * FROM blocked_users WHERE user_id = ?", (user_id,)).fetchone()

    display_name = user_display_name(user) if user else f"ID {user_id}"
    username = f"@{user['username']}" if user and user["username"] else "—"
    status = "🚫 заблокирован" if blocked else "🟢 активен"

    attempts_total = int(totals["attempts_total"] or 0) if totals else 0
    attempts_finished = int(totals["attempts_finished"] or 0) if totals else 0
    answered = int(totals["answered"] or 0) if totals else 0
    correct = int(totals["correct"] or 0) if totals else 0
    percent = _percent(correct, answered)
    unfinished = max(0, attempts_total - attempts_finished)

    lines = [
        "👤 Пользователь",
        "",
        f"{display_name}",
        f"Username: {username}",
        f"ID: {user_id}",
        f"Статус: {status}",
        f"Последняя активность: {fmt_msk(user['last_seen_at']) if user else '—'}",
    ]

    if blocked:
        lines.extend([
            f"Заблокирован: {fmt_msk(blocked['blocked_at'])}",
            f"Причина: {blocked['reason'] or '—'}",
        ])

    lines.extend([
        "",
        "📊 Учебная статистика",
        f"🎯 Средний результат: {percent}%",
        f"✅ Правильно: {correct} из {answered}",
        f"📝 Попытки: {attempts_finished} завершено из {attempts_total}",
        f"⏳ Незавершённых: {unfinished}",
        "",
        "🧠 Работа с вопросами",
        f"Активных ошибок: {active_errors}",
        f"Избранных вопросов: {favorites}",
        "",
        "💾 Сессии",
        f"Сохранённых: {saved_sessions}",
        f"Runtime: {runtime_sessions}",
    ])

    if best_attempt:
        title = TESTS.get(best_attempt["test_id"], {}).get("title", best_attempt["test_id"])
        lines.extend([
            "",
            "🏆 Лучший результат",
            f"{title} · {mode_title(best_attempt['mode'])}",
            _attempt_row_text(best_attempt),
        ])

    if last_attempt:
        title = TESTS.get(last_attempt["test_id"], {}).get("title", last_attempt["test_id"])
        lines.extend([
            "",
            "🕘 Последняя попытка",
            f"{title} · {mode_title(last_attempt['mode'])}",
            _attempt_row_text(last_attempt),
        ])

    if per_tests:
        lines.extend(["", "📚 По тестам"])
        for row in per_tests:
            title = TESTS.get(row["test_id"], {}).get("title", row["test_id"])
            test_answered = int(row["total_answered"] or 0)
            test_correct = int(row["total_correct"] or 0)
            test_percent = _percent(test_correct, test_answered)
            lines.append(
                f"• {title}: {test_percent}% · {test_correct}/{test_answered} · "
                f"{int(row['attempts_finished'] or 0)} заверш."
            )

    return "\n".join(lines)


def admin_global_user_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    sort = _parse_users_sort(sort)
    rows = [
        [
            InlineKeyboardButton("📜 История", callback_data=f"admin:user_history:{user_id}:0:{page}:{sort}"),
            InlineKeyboardButton("🧠 Ошибки", callback_data=f"admin:user_errors:{user_id}:0:{page}:{sort}"),
        ],
        [
            InlineKeyboardButton("⭐ Избранное", callback_data=f"admin:user_favorites:{user_id}:0:{page}:{sort}"),
            InlineKeyboardButton("🔐 Доступы", callback_data=f"admin:user_access:{user_id}:{page}:{sort}"),
        ],
        [
            InlineKeyboardButton("📤 Экспорт", callback_data=f"admin:export_user:{user_id}:{page}:{sort}"),
            InlineKeyboardButton("⚙️ Управление", callback_data=f"admin:user_manage:{user_id}:{page}:{sort}"),
        ],
        [InlineKeyboardButton("👥 К пользователям", callback_data=f"admin:users:{sort}:{page}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ]
    return InlineKeyboardMarkup(rows)


def admin_user_manage_text(user_id: int) -> str:
    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    status = "🚫 заблокирован" if is_user_blocked(user_id) else "🟢 активен"

    return "\n".join([
        "⚙️ Управление пользователем",
        "",
        f"Пользователь: {user_display_name(user) if user else f'ID {user_id}'}",
        f"Статус: {status}",
        "",
        "Эти действия меняют состояние пользователя.",
    ])


def admin_user_manage_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    sort = _parse_users_sort(sort)
    rows = []

    if is_user_blocked(user_id):
        rows.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"admin:unblock_user:{user_id}:{page}:{sort}")])
    else:
        rows.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"admin:block_user_confirm:{user_id}:{page}:{sort}")])

    rows.extend([
        [InlineKeyboardButton("🧹 Очистить runtime", callback_data=f"admin:clear_user_runtime_confirm:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("🗑 Сбросить прогресс", callback_data=f"admin:reset_user_confirm:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("👤 К пользователю", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
    ])
    return InlineKeyboardMarkup(rows)

def admin_user_back_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    sort = _parse_users_sort(sort)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 К пользователю", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("👥 К пользователям", callback_data=f"admin:users:{sort}:{page}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def _admin_short_text(value: str | None, limit: int = 95) -> str:
    text = (value or "").replace("\n", " ").strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _admin_user_pages(total: int) -> int:
    return max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)


def admin_user_history_text(user_id: int, page: int = 0) -> str:
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        total = _safe_count(conn, "attempts", f"WHERE user_id = {int(user_id)}") or 0
        rows = conn.execute(
            """
            SELECT attempt_id, test_id, mode, started_at, finished_at,
                   duration_seconds, answered, correct, completed_full_test, finished_by_user
            FROM attempts
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    display_name = user_display_name(user) if user else f"ID {user_id}"
    total_pages = _admin_user_pages(total)

    lines = [
        "📜 История попыток",
        "",
        f"Пользователь: {display_name}",
        f"Страница {page + 1} из {total_pages}",
        "",
    ]

    if not rows:
        lines.append("Попыток пока нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=offset + 1):
        title = TESTS.get(row["test_id"], {}).get("title", row["test_id"])
        answered = int(row["answered"] or 0)
        correct = int(row["correct"] or 0)
        percent = _percent(correct, answered)
        status = "✅ завершена" if row["finished_at"] else "⏳ не завершена"
        finish_reason = " · остановлена" if row["finished_by_user"] else ""
        lines.append(f"{n}. {title}")
        lines.append(f"   {mode_title(row['mode'])} · {status}{finish_reason}")
        lines.append(f"   Результат: {correct}/{answered} · {percent}%")
        lines.append(f"   Время: {seconds_to_text(row['duration_seconds'])}")
        lines.append(f"   Старт: {fmt_msk(row['started_at'])}")

    return "\n".join(lines)


def admin_user_history_keyboard(user_id: int, page: int = 0, back_page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    total = 0
    with db_connect() as conn:
        total = _safe_count(conn, "attempts", f"WHERE user_id = {int(user_id)}") or 0

    total_pages = _admin_user_pages(total)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:user_history:{user_id}:{page - 1}:{back_page}:{sort}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:user_history:{user_id}:{page + 1}:{back_page}:{sort}"))
    if nav:
        rows.append(nav)
    rows.extend(admin_user_back_keyboard(user_id, back_page, sort).inline_keyboard)
    return InlineKeyboardMarkup(rows)


def admin_user_errors_text(user_id: int, page: int = 0) -> str:
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        total = _safe_count(
            conn,
            "all_time_errors",
            f"WHERE user_id = {int(user_id)} AND COALESCE(is_resolved, 0) = 0",
        ) or 0
        rows = conn.execute(
            """
            SELECT test_id, question_index, wrong_count, last_wrong_answer_index, last_wrong_at
            FROM all_time_errors
            WHERE user_id = ? AND COALESCE(is_resolved, 0) = 0
            ORDER BY wrong_count DESC, last_wrong_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    display_name = user_display_name(user) if user else f"ID {user_id}"
    total_pages = _admin_user_pages(total)

    lines = [
        "🧠 Ошибки пользователя",
        "",
        f"Пользователь: {display_name}",
        f"Активных ошибок: {total}",
        f"Страница {page + 1} из {total_pages}",
        "",
    ]

    if not rows:
        lines.append("Активных ошибок нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=offset + 1):
        test_id = row["test_id"]
        title = TESTS.get(test_id, {}).get("title", test_id)
        question_index = int(row["question_index"])
        try:
            question = get_questions(test_id)[question_index]["question"]
        except Exception:
            question = "Вопрос не найден"
        lines.append(f"{n}. {title} · вопрос {question_index + 1}")
        lines.append(f"   Ошибок: {row['wrong_count']} · последняя: {fmt_msk(row['last_wrong_at'])}")
        lines.append(f"   {_admin_short_text(question)}")

    return "\n".join(lines)


def admin_user_errors_keyboard(user_id: int, page: int = 0, back_page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    with db_connect() as conn:
        total = _safe_count(
            conn,
            "all_time_errors",
            f"WHERE user_id = {int(user_id)} AND COALESCE(is_resolved, 0) = 0",
        ) or 0

    total_pages = _admin_user_pages(total)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:user_errors:{user_id}:{page - 1}:{back_page}:{sort}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:user_errors:{user_id}:{page + 1}:{back_page}:{sort}"))
    if nav:
        rows.append(nav)
    rows.extend(admin_user_back_keyboard(user_id, back_page, sort).inline_keyboard)
    return InlineKeyboardMarkup(rows)


def admin_user_favorites_text(user_id: int, page: int = 0) -> str:
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        total = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)}") or 0
        rows = conn.execute(
            """
            SELECT test_id, question_index, created_at
            FROM favorites
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    display_name = user_display_name(user) if user else f"ID {user_id}"
    total_pages = _admin_user_pages(total)

    lines = [
        "⭐ Избранные вопросы",
        "",
        f"Пользователь: {display_name}",
        f"Всего: {total}",
        f"Страница {page + 1} из {total_pages}",
        "",
    ]

    if not rows:
        lines.append("Избранных вопросов нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=offset + 1):
        test_id = row["test_id"]
        title = TESTS.get(test_id, {}).get("title", test_id)
        question_index = int(row["question_index"])
        try:
            question = get_questions(test_id)[question_index]["question"]
        except Exception:
            question = "Вопрос не найден"
        lines.append(f"{n}. {title} · вопрос {question_index + 1}")
        lines.append(f"   Добавлен: {fmt_msk(row['created_at'])}")
        lines.append(f"   {_admin_short_text(question)}")

    return "\n".join(lines)


def admin_user_favorites_keyboard(user_id: int, page: int = 0, back_page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    with db_connect() as conn:
        total = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)}") or 0

    total_pages = _admin_user_pages(total)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:user_favorites:{user_id}:{page - 1}:{back_page}:{sort}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:user_favorites:{user_id}:{page + 1}:{back_page}:{sort}"))
    if nav:
        rows.append(nav)
    rows.extend(admin_user_back_keyboard(user_id, back_page, sort).inline_keyboard)
    return InlineKeyboardMarkup(rows)


def export_user_csv(user_id: int) -> Path:
    path = BASE_DIR / f"quiz_export_user_{user_id}.csv"

    with db_connect() as conn, path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempt_id", "user_id", "name", "test_id", "mode", "started_at", "finished_at",
            "duration_seconds", "answered", "correct", "completed_full_test", "finished_by_user",
        ])

        rows = conn.execute(
            """
            SELECT a.*, u.username, u.first_name, u.last_name
            FROM attempts a
            LEFT JOIN users u ON u.user_id = a.user_id
            WHERE a.user_id = ?
            ORDER BY a.started_at DESC
            """,
            (user_id,),
        ).fetchall()

        for row in rows:
            writer.writerow([
                row["attempt_id"], row["user_id"], user_display_name(row), row["test_id"], row["mode"],
                row["started_at"], row["finished_at"], row["duration_seconds"], row["answered"], row["correct"],
                row["completed_full_test"], row["finished_by_user"],
            ])

    return path


def admin_block_user_confirm_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Да, заблокировать", callback_data=f"admin:block_user_do:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
    ])


def admin_unblock_user_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 К пользователю", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("🚫 Заблокированные", callback_data="admin:blocked_users:0")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_blocked_users_text(page: int = 0) -> str:
    ensure_admin_tables()
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = _safe_count(conn, "blocked_users") or 0
        rows = conn.execute(
            """
            SELECT b.user_id, b.blocked_at, b.reason, u.username, u.first_name, u.last_name
            FROM blocked_users b
            LEFT JOIN users u ON u.user_id = b.user_id
            ORDER BY b.blocked_at DESC
            LIMIT ? OFFSET ?
            """,
            (ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    total_pages = _admin_user_pages(total)
    lines = [
        "🚫 Заблокированные пользователи",
        "",
        f"Всего: {total}",
        f"Страница {page + 1} из {total_pages}",
        "",
    ]

    if not rows:
        lines.append("Заблокированных пользователей нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=offset + 1):
        lines.append(f"{n}. {user_display_name(row)}")
        lines.append(f"   ID: {row['user_id']}")
        lines.append(f"   Заблокирован: {fmt_msk(row['blocked_at'])}")
        if row["reason"]:
            lines.append(f"   Причина: {row['reason']}")

    return "\n".join(lines)


def admin_blocked_users_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    ensure_admin_tables()
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = _safe_count(conn, "blocked_users") or 0
        rows = conn.execute(
            """
            SELECT b.user_id, u.username, u.first_name, u.last_name
            FROM blocked_users b
            LEFT JOIN users u ON u.user_id = b.user_id
            ORDER BY b.blocked_at DESC
            LIMIT ? OFFSET ?
            """,
            (ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    buttons = []
    for row in rows:
        label = f"👤 {user_display_name(row)}"
        if len(label) > 34:
            label = label[:31].rstrip() + "…"
        buttons.append([InlineKeyboardButton(label, callback_data=f"admin:global_user:{row['user_id']}:{page}")])

    total_pages = _admin_user_pages(total)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:blocked_users:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:blocked_users:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("⚙️ К управлению", callback_data="admin:manage")])
    buttons.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(buttons)


def admin_broadcast_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Отправить всем", callback_data="admin:broadcast_send")],
        [InlineKeyboardButton("↩️ Отмена", callback_data="admin:broadcast_cancel")],
    ])


def admin_broadcast_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("↩️ Отмена", callback_data="admin:broadcast_cancel")],
    ])


def admin_reset_user_confirm_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ Продолжить", callback_data=f"admin:reset_user_second:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
    ])


def admin_reset_user_second_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Да, удалить прогресс", callback_data=f"admin:reset_user_do:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
    ])


def reset_user_progress(user_id: int) -> dict[str, int]:
    with db_connect() as conn:
        attempt_row = conn.execute(
            "SELECT COUNT(*) AS c FROM attempts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        attempts_count = int(attempt_row["c"] or 0)

        stats_count = _safe_count(conn, "user_stats", f"WHERE user_id = {int(user_id)}") or 0
        answered_count = _safe_count(conn, "user_answered_questions", f"WHERE user_id = {int(user_id)}") or 0
        errors_count = _safe_count(conn, "all_time_errors", f"WHERE user_id = {int(user_id)}") or 0
        favorites_count = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)}") or 0
        active_count = _safe_count(conn, "active_sessions", f"WHERE user_id = {int(user_id)}") or 0
        runtime_count = _safe_count(conn, "runtime_sessions", f"WHERE user_id = {int(user_id)}") or 0

        conn.execute(
            """
            DELETE FROM attempt_wrong_answers
            WHERE user_id = ?
               OR attempt_id IN (
                    SELECT attempt_id FROM attempts WHERE user_id = ?
               )
            """,
            (user_id, user_id),
        )
        conn.execute("DELETE FROM attempts WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_answered_questions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM all_time_errors WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM favorites WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))

        try:
            conn.execute("DELETE FROM runtime_sessions WHERE user_id = ?", (user_id,))
        except Exception:
            pass

        conn.commit()

    return {
        "attempts": attempts_count,
        "stats": stats_count,
        "answered_questions": answered_count,
        "errors": errors_count,
        "favorites": favorites_count,
        "active_sessions": active_count,
        "runtime_sessions": runtime_count,
    }


