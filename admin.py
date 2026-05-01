import asyncio
import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from .config import ADMIN_USERS_PAGE_SIZE, BASE_DIR, DB_PATH, SOLUTION_MODES, TESTS
from .helpers import attempt_percent, format_display_datetime, is_admin, mode_title, seconds_to_text, sep, user_display_name
from .loader import get_questions
from .quiz import format_solution_attempt, format_training_attempt, public_rating_text
from .storage import DATABASE_URL, db_connect, get_all_time_error_indices, upsert_user


def fmt_msk(value) -> str:
    return format_display_datetime(value)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Обзор", callback_data="admin:summary")],
        [InlineKeyboardButton("👥 Пользователи", callback_data="admin:users:0")],
        [InlineKeyboardButton("📚 Тесты", callback_data="admin:tests")],
        [InlineKeyboardButton("🧠 Ошибки", callback_data="admin:errors")],
        [InlineKeyboardButton("📤 Экспорт", callback_data="admin:export_menu")],
        [InlineKeyboardButton("🐞 Debug", callback_data="admin:debug")],
        [InlineKeyboardButton("⚙️ Управление", callback_data="admin:manage")],
    ])

def admin_tests_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for test_id, info in TESTS.items():
        rows.append([InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:test:{test_id}")])
    rows.append([InlineKeyboardButton("🧪 Проверить все тесты", callback_data="admin:validate_tests")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)

def admin_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Обзор теста", callback_data=f"admin:test_overview:{test_id}")],
        [
            InlineKeyboardButton("👥 Пользователи", callback_data=f"admin:test_users:{test_id}:0"),
            InlineKeyboardButton("🏆 Рейтинг", callback_data=f"admin:rating:{test_id}"),
        ],
        [
            InlineKeyboardButton("🧠 Ошибки", callback_data=f"admin:frequent_errors:{test_id}"),
            InlineKeyboardButton("📤 Экспорт", callback_data=f"admin:export_test:{test_id}"),
        ],
        [InlineKeyboardButton("🧪 Проверить тест", callback_data=f"admin:validate_test:{test_id}")],
        [InlineKeyboardButton("📚 К тестам", callback_data="admin:tests")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])

def admin_back_to_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 К тесту", callback_data=f"admin:test:{test_id}")],
        [InlineKeyboardButton("📚 К тестам", callback_data="admin:tests")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])

def admin_test_users_text(test_id: str, page: int = 0) -> str:
    title = TESTS[test_id]["title"]
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM user_stats WHERE test_id = ?", (test_id,)).fetchone()["c"] or 0
        rows = conn.execute(
            """
            SELECT
                u.user_id,
                u.username,
                u.first_name,
                u.last_name,
                u.last_seen_at,
                COALESCE(s.attempts_started, 0) AS attempts_started,
                COALESCE(s.attempts_finished, 0) AS attempts_finished,
                COALESCE(s.total_answered, 0) AS answered,
                COALESCE(s.total_correct, 0) AS correct,
                s.last_activity_at AS last_activity_at,
                COUNT(DISTINCT e.question_index) AS active_errors,
                COUNT(DISTINCT f.question_index) AS favorites
            FROM user_stats s
            LEFT JOIN users u ON u.user_id = s.user_id
            LEFT JOIN all_time_errors e
                ON e.user_id = s.user_id
               AND e.test_id = s.test_id
               AND COALESCE(e.is_resolved, 0) = 0
            LEFT JOIN favorites f
                ON f.user_id = s.user_id
               AND f.test_id = s.test_id
            WHERE s.test_id = ?
            GROUP BY
                u.user_id, u.username, u.first_name, u.last_name, u.last_seen_at,
                s.attempts_started, s.attempts_finished, s.total_answered,
                s.total_correct, s.last_activity_at
            ORDER BY s.last_activity_at DESC, s.total_answered DESC
            LIMIT ? OFFSET ?
            """,
            (test_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    total_pages = _admin_user_pages(total)
    start_num = offset + 1 if total else 0
    end_num = min(offset + len(rows), total)

    lines = [
        "👥 Пользователи теста",
        "",
        f"📚 {title}",
        f"Показано: {start_num}–{end_num} из {total}",
        "",
    ]

    if total == 0:
        lines.append("Пока нет пользователей по этому тесту.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=start_num):
        answered = int(row["answered"] or 0)
        correct = int(row["correct"] or 0)
        percent = _percent(correct, answered)
        started = int(row["attempts_started"] or 0)
        finished = int(row["attempts_finished"] or 0)
        active_errors = int(row["active_errors"] or 0)
        favorites = int(row["favorites"] or 0)

        lines.append(f"{n}. {user_display_name(row)}")
        lines.append(f"   🎯 {percent}% · ✅ {correct}/{answered}")
        lines.append(f"   📝 попытки: {finished}/{started} · 🧠 ошибки: {active_errors} · ⭐ {favorites}")
        lines.append(f"   🕒 {fmt_msk(row['last_activity_at'] or row['last_seen_at'])}")

    return "\n".join(lines)


def admin_test_users_keyboard(test_id: str, page: int = 0) -> InlineKeyboardMarkup:
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM user_stats WHERE test_id = ?", (test_id,)).fetchone()["c"] or 0
        rows = conn.execute(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   COALESCE(s.total_answered, 0) AS answered,
                   COALESCE(s.total_correct, 0) AS correct
            FROM user_stats s
            LEFT JOIN users u ON u.user_id = s.user_id
            WHERE s.test_id = ?
            ORDER BY s.last_activity_at DESC, s.total_answered DESC
            LIMIT ? OFFSET ?
            """,
            (test_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    buttons = []
    for row in rows:
        answered = int(row["answered"] or 0)
        correct = int(row["correct"] or 0)
        percent = _percent(correct, answered)
        label = f"👤 {user_display_name(row)} · {percent}%"
        if len(label) > 38:
            label = label[:35].rstrip() + "…"
        buttons.append([InlineKeyboardButton(label, callback_data=f"admin:user:{test_id}:{row['user_id']}:{page}")])

    total_pages = _admin_user_pages(total)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:test_users:{test_id}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:test_users:{test_id}:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("📚 К тесту", callback_data=f"admin:test:{test_id}")])
    buttons.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(buttons)

def admin_user_detail_text(test_id: str, user_id: int) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        stats = conn.execute("SELECT * FROM user_stats WHERE user_id = ? AND test_id = ?", (user_id, test_id)).fetchone()

        errors = conn.execute(
            """
            SELECT COUNT(*) AS active_errors, COALESCE(SUM(wrong_count), 0) AS wrong_clicks
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ? AND COALESCE(is_resolved, 0) = 0
            """,
            (user_id, test_id),
        ).fetchone()

        favorites = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)} AND test_id = '{test_id}'") or 0
        saved_sessions = _safe_count(conn, "active_sessions", f"WHERE user_id = {int(user_id)} AND test_id = '{test_id}'") or 0

        attempts = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished,
                   SUM(CASE WHEN finished_at IS NULL THEN 1 ELSE 0 END) AS unfinished
            FROM attempts
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()

        best_solution = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ?
              AND test_id = ?
              AND mode IN (?, ?, ?, ?)
              AND finished_at IS NOT NULL
              AND answered > 0
            ORDER BY
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                answered DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id, *SOLUTION_MODES),
        ).fetchone()

        last_attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

    display_name = user_display_name(user) if user else f"ID {user_id}"
    username = f"@{user['username']}" if user and user["username"] else "—"

    answered = int(stats["total_answered"] or 0) if stats else 0
    correct = int(stats["total_correct"] or 0) if stats else 0
    percent = _percent(correct, answered)
    started = int(stats["attempts_started"] or 0) if stats else 0
    finished = int(stats["attempts_finished"] or 0) if stats else 0
    unfinished = int(attempts["unfinished"] or 0) if attempts else 0
    active_errors = int(errors["active_errors"] or 0) if errors else 0
    wrong_clicks = int(errors["wrong_clicks"] or 0) if errors else 0

    lines = [
        "👤 Пользователь в тесте",
        "",
        f"{display_name}",
        f"Username: {username}",
        f"ID: {user_id}",
        "",
        f"📚 {title}",
        "",
        "📊 Результат",
        f"🎯 Средний результат: {percent}%",
        f"✅ Правильно: {correct} из {answered}",
        f"📝 Попытки: {finished} завершено из {started}",
        f"⏳ Незавершённых: {unfinished}",
        "",
        "🧠 Ошибки и вопросы",
        f"Активных ошибок: {active_errors}",
        f"Всего ошибочных ответов: {wrong_clicks}",
        f"Избранных вопросов: {favorites}",
        f"Сохранённых сессий: {saved_sessions}",
    ]

    if best_solution:
        lines.extend([
            "",
            "🏆 Лучшее решение",
            _attempt_row_text(best_solution),
        ])

    if last_attempt:
        lines.extend([
            "",
            "🕘 Последняя попытка",
            f"{mode_title(last_attempt['mode'])}",
            _attempt_row_text(last_attempt),
        ])

    return "\n".join(lines)

def admin_test_overview_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]
    questions_count = len(get_questions(test_id))

    with db_connect() as conn:
        stats = None
        errors = None
        completed_solutions = None
        modes = []

        try:
            stats = conn.execute(
                """
                SELECT COUNT(DISTINCT user_id) AS users,
                       COALESCE(SUM(attempts_started), 0) AS attempts_started,
                       COALESCE(SUM(attempts_finished), 0) AS attempts_finished,
                       COALESCE(SUM(total_answered), 0) AS answered,
                       COALESCE(SUM(total_correct), 0) AS correct
                FROM user_stats
                WHERE test_id = ?
                """,
                (test_id,),
            ).fetchone()
        except Exception:
            _rollback_if_possible(conn)

        try:
            errors = conn.execute(
                """
                SELECT COUNT(*) AS active_errors,
                       COALESCE(SUM(wrong_count), 0) AS wrong_clicks
                FROM all_time_errors
                WHERE test_id = ? AND COALESCE(is_resolved, 0) = 0
                """,
                (test_id,),
            ).fetchone()
        except Exception:
            _rollback_if_possible(conn)

        try:
            completed_solutions = conn.execute(
                """
                SELECT COUNT(*) AS c,
                       AVG(duration_seconds) AS avg_time,
                       MIN(duration_seconds) AS best_time
                FROM attempts
                WHERE test_id = ?
                  AND mode IN (?, ?, ?, ?)
                  AND finished_at IS NOT NULL
                  AND answered > 0
                """,
                (test_id, *SOLUTION_MODES),
            ).fetchone()
        except Exception:
            _rollback_if_possible(conn)

        try:
            modes = conn.execute(
                """
                SELECT mode,
                       COUNT(*) AS attempts,
                       SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished,
                       COALESCE(SUM(answered), 0) AS answered,
                       COALESCE(SUM(correct), 0) AS correct
                FROM attempts
                WHERE test_id = ?
                GROUP BY mode
                ORDER BY attempts DESC
                """,
                (test_id,),
            ).fetchall()
        except Exception:
            _rollback_if_possible(conn)

    users = int(stats["users"] or 0) if stats else 0
    attempts_started = int(stats["attempts_started"] or 0) if stats else 0
    attempts_finished = int(stats["attempts_finished"] or 0) if stats else 0
    answered = int(stats["answered"] or 0) if stats else 0
    correct = int(stats["correct"] or 0) if stats else 0
    percent = _percent(correct, answered)

    active_errors = int(errors["active_errors"] or 0) if errors else 0
    wrong_clicks = int(errors["wrong_clicks"] or 0) if errors else 0

    completed_count = int(completed_solutions["c"] or 0) if completed_solutions else 0
    avg_time = completed_solutions["avg_time"] if completed_solutions else None
    best_time = completed_solutions["best_time"] if completed_solutions else None

    completion_percent = _percent(attempts_finished, attempts_started)

    lines = [
        "📊 Обзор теста",
        "",
        f"📚 {title}",
        f"Вопросов: {questions_count}",
        "",
        "👥 Пользователи",
        f"Решали тест: {users}",
        f"Попыток начато: {attempts_started}",
        f"Попыток завершено: {attempts_finished} ({completion_percent}%)",
        "",
        "🎯 Результаты",
        f"Правильно: {correct} из {answered}",
        f"Средний результат: {percent}%",
        f"Завершённых полных решений: {completed_count}",
        f"Среднее время: {seconds_to_text(avg_time)}",
        f"Лучшее время: {seconds_to_text(best_time)}",
        "",
        "🧠 Ошибки",
        f"Активных ошибочных вопросов: {active_errors}",
        f"Всего ошибочных ответов: {wrong_clicks}",
    ]

    if modes:
        lines.extend(["", "🎮 По режимам"])
        for row in modes:
            mode_answered = int(row["answered"] or 0)
            mode_correct = int(row["correct"] or 0)
            mode_percent = _percent(mode_correct, mode_answered)
            lines.append(
                f"• {mode_title(row['mode'])}: "
                f"{int(row['finished'] or 0)}/{int(row['attempts'] or 0)} заверш. · "
                f"{mode_percent}%"
            )

    return "\\n".join(lines)


def admin_test_stats_text(test_id: str) -> str:
    return admin_test_overview_text(test_id)


def validate_single_test_text(test_id: str) -> str:
    info = TESTS[test_id]
    title = info["title"]

    lines = ["🧪 Проверка теста", "", f"📚 {title}", f"ID: {test_id}", ""]

    try:
        questions = get_questions(test_id)
    except Exception as exc:
        return "\\n".join(lines + [f"❌ Не удалось загрузить: {type(exc).__name__}: {exc}"])

    invalid_items = []
    seen: dict[str, int] = {}
    duplicates = []

    for index, question in enumerate(questions):
        q_text = str(question.get("question") or "").strip()
        options = question.get("options") or []
        correct_index = question.get("correct_index")

        problems = []
        if not q_text:
            problems.append("нет текста вопроса")
        if not isinstance(options, list) or len(options) < 2:
            problems.append("меньше 2 вариантов")
        if correct_index is None:
            problems.append("нет correct_index")
        else:
            try:
                correct_int = int(correct_index)
                if correct_int < 0 or correct_int >= len(options):
                    problems.append("correct_index вне диапазона")
            except (TypeError, ValueError):
                problems.append("correct_index не число")

        normalized = " ".join(q_text.lower().split())
        if normalized:
            if normalized in seen:
                duplicates.append((seen[normalized] + 1, index + 1))
            else:
                seen[normalized] = index

        if problems:
            invalid_items.append((index + 1, ", ".join(problems)))

    lines.append(f"Вопросов: {len(questions)}")

    if invalid_items:
        lines.append(f"❌ Проблемных вопросов: {len(invalid_items)}")
        for num, problem in invalid_items[:15]:
            lines.append(f"• Вопрос {num}: {problem}")
        if len(invalid_items) > 15:
            lines.append(f"• ещё {len(invalid_items) - 15}")
    else:
        lines.append("✅ Структура вопросов: OK")

    if duplicates:
        lines.append(f"⚠️ Дубликатов: {len(duplicates)}")
        for first, second in duplicates[:15]:
            lines.append(f"• Вопрос {first} повторяется в вопросе {second}")
        if len(duplicates) > 15:
            lines.append(f"• ещё {len(duplicates) - 15}")
    else:
        lines.append("✅ Дубликатов не найдено")

    return "\\n".join(lines)

def admin_rating_text(test_id: str) -> str:
    return public_rating_text(test_id)

def admin_frequent_errors_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, SUM(wrong_count) AS c
            FROM all_time_errors
            WHERE test_id = ?
            GROUP BY question_index
            ORDER BY c DESC
            LIMIT 10
            """,
            (test_id,),
        ).fetchall()

    lines = [f"🧠 Частые ошибки\n{title}\n"]
    if not rows:
        lines.append("Ошибок пока нет.")
        return "\n".join(lines)

    questions = get_questions(test_id)
    for n, row in enumerate(rows, start=1):
        q = questions[int(row["question_index"])]["question"].replace("\n", " ")
        short = q[:120] + ("…" if len(q) > 120 else "")
        lines.append(f"{n}. {row['c']} раз — {short}")

    return "\n".join(lines)

def _today_start() -> str:
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def _percent(correct: int | float | None, total: int | float | None) -> float:
    total = total or 0
    if not total:
        return 0.0
    return round(float(correct or 0) / float(total) * 100, 1)


def _safe_scalar(conn, sql: str, params: tuple = (), default=0):
    try:
        row = conn.execute(sql, params).fetchone()
        if not row:
            return default
        # sqlite.Row and psycopg dict_row both support keys
        value = row[0] if not hasattr(row, "keys") else next(iter(dict(row).values()))
        return default if value is None else value
    except Exception:
        _rollback_if_possible(conn)
        return default


def admin_summary_text() -> str:
    ensure_admin_tables()

    backend = "PostgreSQL / Neon" if DATABASE_URL else "SQLite"

    with db_connect() as conn:
        users = _safe_count(conn, "users") or 0
        attempts = _safe_count(conn, "attempts") or 0
        finished = _safe_count(conn, "attempts", "WHERE finished_at IS NOT NULL") or 0
        active_sessions = _safe_count(conn, "active_sessions") or 0
        runtime_sessions = _safe_count(conn, "runtime_sessions") or 0
        active_errors = _safe_count(conn, "all_time_errors", "WHERE COALESCE(is_resolved, 0) = 0") or 0
        favorites = _safe_count(conn, "favorites") or 0
        blocked_users = _safe_count(conn, "blocked_users") or 0

        totals = None
        try:
            totals = conn.execute(
                """
                SELECT COALESCE(SUM(answered), 0) AS answered,
                       COALESCE(SUM(correct), 0) AS correct
                FROM attempts
                WHERE finished_at IS NOT NULL
                """
            ).fetchone()
        except Exception:
            _rollback_if_possible(conn)

        last_user = None
        try:
            last_user = conn.execute(
                """
                SELECT user_id, username, first_name, last_name, last_seen_at
                FROM users
                ORDER BY last_seen_at DESC
                LIMIT 1
                """
            ).fetchone()
        except Exception:
            _rollback_if_possible(conn)

    answered = int(totals["answered"] or 0) if totals else 0
    correct = int(totals["correct"] or 0) if totals else 0
    avg_percent = _percent(correct, answered)
    broadcast_recipients = max(0, users - blocked_users)

    last_activity = "—"
    if last_user:
        last_activity = f"{user_display_name(last_user)} · {fmt_msk(last_user['last_seen_at'])}"

    return (
        "📊 Обзор\n\n"
        f"👥 Пользователей: {users}\n"
        f"🚫 Заблокированных: {blocked_users}\n"
        f"📢 Получателей рассылки: {broadcast_recipients}\n\n"
        f"📝 Попыток всего: {attempts}\n"
        f"✅ Завершено: {finished}\n"
        f"🎯 Средний результат: {avg_percent}%\n"
        f"🔢 Ответов: {answered}\n\n"
        f"📚 Тестов: {len(TESTS)}\n"
        f"🧠 Активных ошибок: {active_errors}\n"
        f"⭐ Избранных вопросов: {favorites}\n\n"
        f"💾 Сохранённых сессий: {active_sessions}\n"
        f"🔄 Runtime-сессий: {runtime_sessions}\n"
        f"🗄 База: {backend}\n\n"
        f"🕒 Последняя активность:\n{last_activity}"
    )

def safe_admin_summary_text() -> str:
    try:
        return admin_summary_text()
    except Exception as exc:
        return (
            "📊 Обзор\n\n"
            "⚠️ Обзор не загрузился.\n"
            f"Ошибка: {type(exc).__name__}: {exc}\\n\\n"
            "Открой 🐞 Debug или пришли этот текст."
        )


def _rollback_if_possible(conn) -> None:
    try:
        if hasattr(conn, "rollback"):
            conn.rollback()
        elif hasattr(conn, "conn") and hasattr(conn.conn, "rollback"):
            conn.conn.rollback()
    except Exception:
        pass


def _table_exists_for_admin(conn, table_name: str) -> bool:
    try:
        if DATABASE_URL:
            row = conn.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = ?
                ) AS exists
                """,
                (table_name,),
            ).fetchone()
            return bool(row["exists"])
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return row is not None
    except Exception:
        _rollback_if_possible(conn)
        return False


def _safe_count(conn, table_name: str, where_sql: str = "") -> int | None:
    try:
        if not _table_exists_for_admin(conn, table_name):
            return 0
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {table_name} {where_sql}").fetchone()
        return int(row["c"] or 0)
    except Exception:
        _rollback_if_possible(conn)
        return None


def _fmt_count(value: int | None) -> str:
    return str(value) if value is not None else "—"


def admin_debug_text() -> str:
    ensure_admin_tables()
    backend = "PostgreSQL / Neon" if DATABASE_URL else "SQLite"
    db_place = "DATABASE_URL" if DATABASE_URL else str(DB_PATH)

    with db_connect() as conn:
        users = _safe_count(conn, "users")
        user_stats = _safe_count(conn, "user_stats")
        attempts = _safe_count(conn, "attempts")
        finished_attempts = _safe_count(conn, "attempts", "WHERE finished_at IS NOT NULL")
        active_sessions = _safe_count(conn, "active_sessions")
        runtime_sessions = _safe_count(conn, "runtime_sessions")
        all_time_errors = _safe_count(conn, "all_time_errors")
        attempt_wrong_answers = _safe_count(conn, "attempt_wrong_answers")
        blocked_users = _safe_count(conn, "blocked_users")

        try:
            last_attempt = conn.execute(
                """
                SELECT test_id, mode, started_at, finished_at
                FROM attempts
                ORDER BY attempt_id DESC
                LIMIT 1
                """
            ).fetchone()
        except Exception:
            last_attempt = None

    test_lines = []
    for test_id, info in TESTS.items():
        try:
            count = len(get_questions(test_id))
        except Exception:
            count = "ошибка загрузки"
        test_lines.append(f"• {info['title']} ({test_id}) — {count}")

    lines = [
        "🛠 Admin debug",
        "",
        f"База: {backend}",
        f"Путь/переменная: {db_place}",
        f"DATABASE_URL: {'есть' if DATABASE_URL else 'нет'}",
        "",
        f"Тестов загружено: {len(TESTS)}",
        *test_lines,
        "",
        f"👥 users: {_fmt_count(users)}",
        f"📊 user_stats: {_fmt_count(user_stats)}",
        f"📝 attempts: {_fmt_count(attempts)}",
        f"✅ finished attempts: {_fmt_count(finished_attempts)}",
        f"💾 active_sessions: {_fmt_count(active_sessions)}",
        f"🔄 runtime_sessions: {_fmt_count(runtime_sessions)}",
        f"🧠 all_time_errors: {_fmt_count(all_time_errors)}",
        f"❌ attempt_wrong_answers: {_fmt_count(attempt_wrong_answers)}",
        f"🚫 blocked_users: {_fmt_count(blocked_users)}",
    ]

    if last_attempt:
        finished = fmt_msk(last_attempt["finished_at"]) if last_attempt["finished_at"] else "не завершена"
        lines.extend([
            "",
            "Последняя попытка:",
            f"• test_id: {last_attempt['test_id']}",
            f"• mode: {last_attempt['mode']}",
            f"• start: {fmt_msk(last_attempt['started_at'])}",
            f"• finish: {finished}",
        ])

    return "\n".join(lines)

def export_csv(test_id: str | None = None) -> Path:
    suffix = test_id or "all"
    path = BASE_DIR / f"quiz_export_{suffix}.csv"

    with db_connect() as conn, path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attempt_id", "user_id", "name", "test_id", "mode", "started_at", "finished_at",
            "duration_seconds", "answered", "correct", "completed_full_test", "finished_by_user",
        ])

        if test_id:
            rows = conn.execute(
                """
                SELECT a.*, u.username, u.first_name, u.last_name
                FROM attempts a
                LEFT JOIN users u ON u.user_id = a.user_id
                WHERE a.test_id = ?
                ORDER BY a.started_at DESC
                """,
                (test_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT a.*, u.username, u.first_name, u.last_name
                FROM attempts a
                LEFT JOIN users u ON u.user_id = a.user_id
                ORDER BY a.started_at DESC
                """
            ).fetchall()

        for row in rows:
            writer.writerow([
                row["attempt_id"], row["user_id"], user_display_name(row), row["test_id"], row["mode"],
                row["started_at"], row["finished_at"], row["duration_seconds"], row["answered"], row["correct"],
                row["completed_full_test"], row["finished_by_user"],
            ])

    return path


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
        f"{correct}/{answered} · {percent}% · {status}\\n"
        f"Время: {seconds_to_text(row['duration_seconds'])}\\n"
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
            InlineKeyboardButton("📤 Экспорт", callback_data=f"admin:export_user:{user_id}:{page}:{sort}"),
        ],
    ]

    if is_user_blocked(user_id):
        rows.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"admin:unblock_user:{user_id}:{page}:{sort}")])
    else:
        rows.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"admin:block_user_confirm:{user_id}:{page}:{sort}")])

    rows.extend([
        [InlineKeyboardButton("🧹 Очистить runtime", callback_data=f"admin:clear_user_runtime_confirm:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("🗑 Сбросить прогресс", callback_data=f"admin:reset_user_confirm:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("👥 К пользователям", callback_data=f"admin:users:{sort}:{page}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
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


def validate_tests_text() -> str:
    lines = ["🧪 Проверка тестов", ""]
    total_questions = 0
    total_duplicates = 0
    has_errors = False

    for test_id, info in TESTS.items():
        title = info["title"]
        lines.append(f"📚 {title}")
        lines.append(f"ID: {test_id}")

        try:
            questions = get_questions(test_id)
        except Exception as exc:
            has_errors = True
            lines.append(f"❌ Не удалось загрузить: {exc}")
            lines.append("")
            continue

        total_questions += len(questions)
        invalid_items = []
        seen: dict[str, int] = {}
        duplicates = []

        for index, question in enumerate(questions):
            q_text = str(question.get("question") or "").strip()
            options = question.get("options") or []
            correct_index = question.get("correct_index")

            problems = []
            if not q_text:
                problems.append("нет текста вопроса")
            if not isinstance(options, list) or len(options) < 2:
                problems.append("меньше 2 вариантов")
            if correct_index is None:
                problems.append("нет correct_index")
            else:
                try:
                    correct_int = int(correct_index)
                    if correct_int < 0 or correct_int >= len(options):
                        problems.append("correct_index вне диапазона")
                except (TypeError, ValueError):
                    problems.append("correct_index не число")

            normalized = " ".join(q_text.lower().split())
            if normalized:
                if normalized in seen:
                    duplicates.append((seen[normalized] + 1, index + 1))
                else:
                    seen[normalized] = index

            if problems:
                invalid_items.append((index + 1, ", ".join(problems)))

        total_duplicates += len(duplicates)

        lines.append(f"Вопросов: {len(questions)}")
        if invalid_items:
            has_errors = True
            lines.append(f"❌ Проблемных вопросов: {len(invalid_items)}")
            for num, problem in invalid_items[:10]:
                lines.append(f"• Вопрос {num}: {problem}")
            if len(invalid_items) > 10:
                lines.append(f"• ещё {len(invalid_items) - 10}")
        else:
            lines.append("✅ Структура вопросов: OK")

        if duplicates:
            lines.append(f"⚠️ Дубликатов вопросов: {len(duplicates)}")
            for first, second in duplicates[:10]:
                lines.append(f"• Вопрос {first} повторяется в вопросе {second}")
            if len(duplicates) > 10:
                lines.append(f"• ещё {len(duplicates) - 10}")
        else:
            lines.append("✅ Дубликатов не найдено")

        lines.append("")

    status = "❌ Есть проблемы" if has_errors else "✅ Критичных ошибок не найдено"
    lines.extend([
        "Итог",
        status,
        f"Тестов: {len(TESTS)}",
        f"Вопросов всего: {total_questions}",
        f"Дубликатов всего: {total_duplicates}",
    ])

    return "\n".join(lines)


def admin_clear_user_runtime_confirm_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, очистить", callback_data=f"admin:clear_user_runtime_do:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
    ])


def clear_user_runtime_sessions(user_id: int) -> int:
    with db_connect() as conn:
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM runtime_sessions WHERE user_id = ?", (user_id,)).fetchone()
            count = int(row["c"] or 0)
            conn.execute("DELETE FROM runtime_sessions WHERE user_id = ?", (user_id,))
            conn.commit()
            return count
        except Exception:
            return 0

def admin_errors_menu_text() -> str:
    return (
        "🧠 Ошибки\n\n"
        "Здесь можно смотреть самые частые ошибки по всем тестам или отдельно по каждому тесту."
    )


def admin_errors_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🧠 Частые ошибки по всем тестам", callback_data="admin:frequent_errors_all")]]
    for test_id, info in TESTS.items():
        rows.append([InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:frequent_errors:{test_id}")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_frequent_errors_all_text() -> str:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT test_id, question_index, SUM(wrong_count) AS c, COUNT(DISTINCT user_id) AS users
            FROM all_time_errors
            WHERE COALESCE(is_resolved, 0) = 0
            GROUP BY test_id, question_index
            ORDER BY c DESC
            LIMIT 15
            """
        ).fetchall()

    lines = ["🧠 Частые ошибки по всем тестам", ""]
    if not rows:
        lines.append("Ошибок пока нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=1):
        test_id = row["test_id"]
        title = TESTS.get(test_id, {}).get("title", test_id)
        questions = get_questions(test_id)
        question_index = int(row["question_index"])
        q = questions[question_index]["question"].replace("\n", " ")
        short = q[:90] + ("…" if len(q) > 90 else "")
        lines.append(f"{n}. {title} · вопрос {question_index + 1}")
        lines.append(f"   Ошибок: {row['c']} · пользователей: {row['users']}")
        lines.append(f"   {short}")

    return "\n".join(lines)


def admin_export_menu_text() -> str:
    return (
        "📤 Экспорт\n\n"
        "Можно выгрузить все попытки сразу или только данные конкретного теста."
    )


def admin_export_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("📦 Все данные", callback_data="admin:export_all")]]
    for test_id, info in TESTS.items():
        rows.append([InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:export_test:{test_id}")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_debug_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin:debug")],
        [InlineKeyboardButton("⚙️ Управление", callback_data="admin:manage")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_manage_text() -> str:
    return (
        "⚙️ Управление\n\n"
        "Действия здесь меняют состояние бота. Опасные операции требуют подтверждения.\n\n"
        "📢 Рассылка — отправить сообщение всем незаблокированным пользователям.\n"
        "🚫 Заблокированные — список пользователей с ограниченным доступом.\n"
        "🧪 Проверка тестов — ищет ошибки в JSON и дубликаты вопросов.\n"
        "🧹 Runtime-сессии — временные состояния текущих прохождений."
    )


def admin_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("🚫 Заблокированные", callback_data="admin:blocked_users:0")],
        [InlineKeyboardButton("🧪 Проверить тесты", callback_data="admin:validate_tests")],
        [InlineKeyboardButton("🧹 Очистить runtime-сессии", callback_data="admin:clear_runtime_confirm")],
        [InlineKeyboardButton("🐞 Debug", callback_data="admin:debug")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_clear_runtime_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, очистить", callback_data="admin:clear_runtime_do")],
        [InlineKeyboardButton("↩️ Отмена", callback_data="admin:manage")],
    ])


def clear_runtime_sessions() -> int:
    with db_connect() as conn:
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM runtime_sessions").fetchone()
            count = int(row["c"] or 0)
            conn.execute("DELETE FROM runtime_sessions")
            conn.commit()
            return count
        except Exception:
            return 0


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Админ-панель недоступна.")
        return
    await update.message.reply_text("🛠 Админ-панель", reply_markup=admin_main_keyboard())


async def admin_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Админ-панель недоступна.")
        return
    await update.message.reply_text(admin_debug_text(), reply_markup=admin_debug_keyboard())

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text("🛠 Админ-панель", reply_markup=admin_main_keyboard())


async def handle_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    sort = "recent"
    page = 0

    # Supported formats:
    # admin:users
    # admin:users:0
    # admin:users:recent
    # admin:users:recent:0
    # admin:users:result:0
    # admin:users:attempts:0
    # admin:users:errors:0
    if len(parts) >= 3:
        third = parts[2]
        if third.isdigit():
            page = int(third)
        else:
            sort = _parse_users_sort(third)

    if len(parts) >= 4 and str(parts[3]).isdigit():
        page = int(parts[3])

    message_text = admin_users_text(page, sort)
    keyboard = admin_users_keyboard(page, sort)

    try:
        await query.edit_message_text(message_text, reply_markup=keyboard)
    except Exception as exc:
        if "Message is not modified" in str(exc):
            return
        raise


async def _show_admin_users_sorted(update: Update, context: ContextTypes.DEFAULT_TYPE, sort: str) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    sort = _parse_users_sort(sort)
    page = 0
    message_text = admin_users_text(page, sort)
    keyboard = admin_users_keyboard(page, sort)

    try:
        await query.edit_message_text(message_text, reply_markup=keyboard)
    except Exception as exc:
        if "Message is not modified" in str(exc):
            return
        raise


async def handle_admin_users_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "recent")


async def handle_admin_users_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "result")


async def handle_admin_users_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "attempts")


async def handle_admin_users_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "errors")


async def handle_admin_global_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    await query.edit_message_text(
        admin_global_user_text(user_id),
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    back_page = int(parts[4])
    sort = _parse_users_sort(parts[5]) if len(parts) > 5 else "recent"
    await query.edit_message_text(
        admin_user_history_text(user_id, page),
        reply_markup=admin_user_history_keyboard(user_id, page, back_page, sort),
    )


async def handle_admin_user_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    back_page = int(parts[4])
    sort = _parse_users_sort(parts[5]) if len(parts) > 5 else "recent"
    await query.edit_message_text(
        admin_user_errors_text(user_id, page),
        reply_markup=admin_user_errors_keyboard(user_id, page, back_page, sort),
    )


async def handle_admin_user_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    back_page = int(parts[4])
    sort = _parse_users_sort(parts[5]) if len(parts) > 5 else "recent"
    await query.edit_message_text(
        admin_user_favorites_text(user_id, page),
        reply_markup=admin_user_favorites_keyboard(user_id, page, back_page, sort),
    )


async def handle_admin_export_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    path = export_user_csv(user_id)
    await query.message.reply_document(InputFile(path), caption=f"📤 Экспорт пользователя: {user_id}")
    await query.edit_message_text(
        admin_global_user_text(user_id),
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_clear_user_runtime_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    await query.edit_message_text(
        "🧹 Очистить runtime-сессии пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Это удалит только временные состояния текущих прохождений. "
        "Статистика, попытки, ошибки и избранное останутся.",
        reply_markup=admin_clear_user_runtime_confirm_keyboard(user_id, page, sort),
    )


async def handle_admin_clear_user_runtime_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    count = clear_user_runtime_sessions(user_id)
    await query.edit_message_text(
        f"✅ Runtime-сессии пользователя очищены.\n\nУдалено записей: {count}",
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_block_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    await query.edit_message_text(
        "🚫 Заблокировать пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Он не сможет пользоваться ботом, пока ты его не разблокируешь. "
        "Статистика и данные пользователя останутся.",
        reply_markup=admin_block_user_confirm_keyboard(user_id, page, sort),
    )


async def handle_admin_block_user_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    block_user(user_id, query.from_user.id, "blocked from admin panel")
    await query.edit_message_text(
        "🚫 Пользователь заблокирован.",
        reply_markup=admin_unblock_user_keyboard(user_id, page, sort),
    )


async def handle_admin_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    unblock_user(user_id)
    await query.edit_message_text(
        "✅ Пользователь разблокирован.",
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0
    await query.edit_message_text(
        admin_blocked_users_text(page),
        reply_markup=admin_blocked_users_keyboard(page),
    )


async def handle_admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    context.user_data["admin_broadcast_waiting"] = True
    context.user_data.pop("admin_broadcast_text", None)

    await query.edit_message_text(
        "📢 Рассылка\n\n"
        "Отправь следующим сообщением текст, который нужно разослать пользователям.\n\n"
        "Получатели: все незаблокированные пользователи.",
        reply_markup=admin_broadcast_cancel_keyboard(),
    )


async def handle_admin_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id):
        return
    if not context.user_data.get("admin_broadcast_waiting"):
        return

    text = (update.message.text or "").strip()
    context.user_data["admin_broadcast_waiting"] = False

    if not text:
        await update.message.reply_text("Пустое сообщение не подходит.", reply_markup=admin_manage_keyboard())
        raise ApplicationHandlerStop

    context.user_data["admin_broadcast_text"] = text
    users_count = len(broadcast_users())

    preview = text
    if len(preview) > 1200:
        preview = preview[:1200].rstrip() + "…"

    await update.message.reply_text(
        "📢 Предпросмотр рассылки\n\n"
        f"Получателей: {users_count}\n"
        "Заблокированные пользователи не получат сообщение.\n\n"
        f"{preview}",
        reply_markup=admin_broadcast_preview_keyboard(),
    )

    raise ApplicationHandlerStop


async def handle_admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    text = context.user_data.get("admin_broadcast_text")
    if not text:
        await query.edit_message_text("Текст рассылки не найден.", reply_markup=admin_manage_keyboard())
        return

    user_ids = broadcast_users()
    await query.edit_message_text(f"📢 Рассылка запущена.\n\nПолучателей: {len(user_ids)}")

    sent = 0
    failed = 0
    delay = float(os.getenv("BROADCAST_SEND_DELAY_SECONDS", "0.05"))

    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception:
            failed += 1
        if delay > 0:
            await asyncio.sleep(delay)

    context.user_data.pop("admin_broadcast_text", None)
    context.user_data.pop("admin_broadcast_waiting", None)

    await query.message.reply_text(
        "✅ Рассылка завершена\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}",
        reply_markup=admin_manage_keyboard(),
    )


async def handle_admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    context.user_data.pop("admin_broadcast_waiting", None)
    context.user_data.pop("admin_broadcast_text", None)
    await query.edit_message_text("Рассылка отменена.", reply_markup=admin_manage_keyboard())


async def handle_admin_reset_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    await query.edit_message_text(
        "🗑 Сбросить прогресс пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Будут удалены попытки, статистика, ошибки, избранное и сохранённые сессии. "
        "Сам пользователь останется в списке.\n\n"
        "Это действие нельзя отменить.",
        reply_markup=admin_reset_user_confirm_keyboard(user_id, page, sort),
    )


async def handle_admin_reset_user_second(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    await query.edit_message_text(
        "⚠️ Последнее подтверждение\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "После нажатия кнопки ниже прогресс будет удалён полностью.",
        reply_markup=admin_reset_user_second_keyboard(user_id, page, sort),
    )


async def handle_admin_reset_user_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    result = reset_user_progress(user_id)

    await query.edit_message_text(
        "✅ Прогресс пользователя сброшен\n\n"
        f"Пользователь ID: {user_id}\n"
        f"Удалено попыток: {result['attempts']}\n"
        f"Строк статистики: {result['stats']}\n"
        f"Ответов по вопросам: {result['answered_questions']}\n"
        f"Ошибок: {result['errors']}\n"
        f"Избранного: {result['favorites']}\n"
        f"Сохранённых сессий: {result['active_sessions']}\n"
        f"Runtime-сессий: {result['runtime_sessions']}",
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_validate_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    await query.edit_message_text(
        validate_tests_text(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ К управлению", callback_data="admin:manage")],
            [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
        ]),
    )


async def handle_admin_errors_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_errors_menu_text(), reply_markup=admin_errors_menu_keyboard())


async def handle_admin_frequent_errors_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(
        admin_frequent_errors_all_text(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 К ошибкам", callback_data="admin:errors")],
            [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
        ]),
    )


async def handle_admin_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_export_menu_text(), reply_markup=admin_export_menu_keyboard())


async def handle_admin_debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_debug_text(), reply_markup=admin_debug_keyboard())


async def handle_admin_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_manage_text(), reply_markup=admin_manage_keyboard())


async def handle_admin_clear_runtime_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    await query.edit_message_text(
        "🧹 Очистить runtime-сессии?\n\n"
        "Это сбросит временные состояния текущих прохождений. "
        "Сохранённые завершённые попытки и статистика не удалятся.",
        reply_markup=admin_clear_runtime_confirm_keyboard(),
    )


async def handle_admin_clear_runtime_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    count = clear_runtime_sessions()
    await query.edit_message_text(
        f"✅ Runtime-сессии очищены.\n\nУдалено записей: {count}",
        reply_markup=admin_manage_keyboard(),
    )


async def handle_admin_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text("📚 Тесты\n\nВыбери тест для просмотра статистики и действий.", reply_markup=admin_tests_keyboard())

async def handle_admin_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    title = TESTS[test_id]["title"]
    questions_count = len(get_questions(test_id))
    await query.edit_message_text(
        f"📚 {title}\n\nВопросов: {questions_count}\n\nВыбери действие:",
        reply_markup=admin_test_keyboard(test_id),
    )

async def handle_admin_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(safe_admin_summary_text(), reply_markup=admin_main_keyboard())

async def handle_admin_test_overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_test_overview_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))


async def handle_admin_validate_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    await query.edit_message_text(validate_single_test_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))


async def handle_admin_test_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_test_stats_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))

async def handle_admin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_rating_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))

async def handle_admin_test_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    if len(parts) >= 4:
        _, _, test_id, page_str = parts
        page = int(page_str)
    else:
        _, _, test_id = parts
        page = 0

    await query.edit_message_text(admin_test_users_text(test_id, page), reply_markup=admin_test_users_keyboard(test_id, page))

async def handle_admin_test_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    page = 0

    if len(parts) == 5 and parts[1] == "user":
        _, _, test_id, user_id_str, page_str = parts
        page = int(page_str)
    elif len(parts) == 4 and parts[1] == "user":
        _, _, test_id, user_id_str = parts
    else:
        _, _, test_id, user_id_str = parts

    user_id = int(user_id_str)

    await query.edit_message_text(
        admin_user_detail_text(test_id, user_id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад к пользователям", callback_data=f"admin:test_users:{test_id}:{page}")],
            [InlineKeyboardButton("🏠 Назад к тесту", callback_data=f"admin:test:{test_id}")],
        ]),
    )

async def handle_admin_frequent_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_frequent_errors_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))

async def handle_admin_export_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    path = export_csv(None)
    await query.message.reply_document(InputFile(path), caption="📤 Экспорт всех данных")
    await query.edit_message_text(admin_export_menu_text(), reply_markup=admin_export_menu_keyboard())

async def handle_admin_export_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    path = export_csv(test_id)
    await query.message.reply_document(InputFile(path), caption=f"📤 Экспорт по тесту: {TESTS[test_id]['title']}")
    await query.edit_message_text(admin_export_menu_text(), reply_markup=admin_export_menu_keyboard())
