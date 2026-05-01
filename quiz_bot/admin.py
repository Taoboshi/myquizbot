import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes

from .config import ADMIN_USERS_PAGE_SIZE, BASE_DIR, DB_PATH, SOLUTION_MODES, TESTS
from .helpers import attempt_percent, is_admin, mode_title, seconds_to_text, sep, user_display_name
from .loader import get_questions
from .quiz import format_solution_attempt, format_training_attempt, public_rating_text
from .storage import DATABASE_URL, db_connect, get_all_time_error_indices, upsert_user

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
    rows = [[InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:test:{test_id}")] for test_id, info in TESTS.items()]
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)

def admin_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Статистика", callback_data=f"admin:test_stats:{test_id}")],
        [InlineKeyboardButton("👥 Пользователи", callback_data=f"admin:test_users:{test_id}:0")],
        [InlineKeyboardButton("🏆 Рейтинг топ-10", callback_data=f"admin:rating:{test_id}")],
        [InlineKeyboardButton("🧠 Частые ошибки", callback_data=f"admin:frequent_errors:{test_id}")],
        [InlineKeyboardButton("📤 Экспорт по тесту", callback_data=f"admin:export_test:{test_id}")],
        [InlineKeyboardButton("📚 К тестам", callback_data="admin:tests")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])

def admin_back_to_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 К тесту", callback_data=f"admin:test:{test_id}")],
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
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   COALESCE(s.total_answered, 0) AS answered,
                   COALESCE(s.total_correct, 0) AS correct,
                   s.last_activity_at AS last_activity_at
            FROM user_stats s
            LEFT JOIN users u ON u.user_id = s.user_id
            WHERE s.test_id = ?
            ORDER BY s.total_answered DESC, s.last_activity_at DESC
            LIMIT ? OFFSET ?
            """,
            (test_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    lines = ["👥 Пользователи", title, ""]
    if total == 0:
        lines.append("Пока нет пользователей по этому тесту.")
        return "\n".join(lines)

    start_num = offset + 1
    end_num = min(offset + len(rows), total)
    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)

    lines.append(f"{start_num}–{end_num} из {total}")
    lines.append(f"Страница {page + 1} из {total_pages}")
    lines.append("")

    for row in rows:
        answered = row["answered"] or 0
        correct = row["correct"] or 0
        percent = round(correct / answered * 100, 1) if answered else 0
        lines.append(f"• {user_display_name(row)} — {correct}/{answered} ({percent}%)")

    lines.extend(["", "Нажми кнопку ниже, чтобы открыть карточку пользователя."])
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
                   COALESCE(s.total_correct, 0) AS correct,
                   s.last_activity_at AS last_activity_at
            FROM user_stats s
            LEFT JOIN users u ON u.user_id = s.user_id
            WHERE s.test_id = ?
            ORDER BY s.total_answered DESC, s.last_activity_at DESC
            LIMIT ? OFFSET ?
            """,
            (test_id, ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    buttons = []
    user_buttons = []

    for row in rows:
        answered = row["answered"] or 0
        correct = row["correct"] or 0
        percent = round(correct / answered * 100, 1) if answered else 0
        label = f"👤 {user_display_name(row)} · {percent}%"
        if len(label) > 30:
            label = label[:27].rstrip() + "…"

        user_buttons.append(InlineKeyboardButton(label, callback_data=f"admin:user:{test_id}:{row['user_id']}:{page}"))

    for i in range(0, len(user_buttons), 2):
        buttons.append(user_buttons[i:i + 2])

    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:test_users:{test_id}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:test_users:{test_id}:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🏠 Назад к тесту", callback_data=f"admin:test:{test_id}")])
    return InlineKeyboardMarkup(buttons)

def admin_user_detail_text(test_id: str, user_id: int) -> str:
    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        stats = conn.execute("SELECT * FROM user_stats WHERE user_id = ? AND test_id = ?", (user_id, test_id)).fetchone()

        errors = conn.execute(
            """
            SELECT COUNT(*) AS active_errors, COALESCE(SUM(wrong_count), 0) AS wrong_clicks
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()

        attempt_counts = conn.execute(
            """
            SELECT
                COUNT(*) AS started_total,
                SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished_total,
                SUM(CASE WHEN mode IN (?, ?, ?, ?) AND finished_at IS NOT NULL THEN 1 ELSE 0 END) AS solution_finished,
                SUM(CASE WHEN mode = 'mini' AND finished_at IS NOT NULL THEN 1 ELSE 0 END) AS training_finished,
                SUM(CASE WHEN mode = 'errors' AND finished_at IS NOT NULL THEN 1 ELSE 0 END) AS errors_finished
            FROM attempts
            WHERE user_id = ? AND test_id = ?
            """,
            (*SOLUTION_MODES, user_id, test_id),
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
                answered DESC,
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id, *SOLUTION_MODES),
        ).fetchone()

        last_solution = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ?
              AND test_id = ?
              AND mode IN (?, ?, ?, ?)
              AND finished_at IS NOT NULL
              AND answered > 0
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (user_id, test_id, *SOLUTION_MODES),
        ).fetchone()

        best_training = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ?
              AND test_id = ?
              AND mode = 'mini'
              AND finished_at IS NOT NULL
              AND answered > 0
            ORDER BY
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                correct DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

        last_training = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ?
              AND test_id = ?
              AND mode = 'mini'
              AND finished_at IS NOT NULL
              AND answered > 0
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

    title = TESTS[test_id]["title"]

    if user:
        display_name = user_display_name(user)
        first_activity = user["first_seen_at"] or "—"
        last_activity = stats["last_activity_at"] if stats else (user["last_seen_at"] or "—")
    else:
        display_name = f"ID {user_id}"
        first_activity = "—"
        last_activity = stats["last_activity_at"] if stats else "—"

    started_total = attempt_counts["started_total"] or 0
    finished_total = attempt_counts["finished_total"] or 0
    unfinished_total = max(0, started_total - finished_total)
    solution_finished = attempt_counts["solution_finished"] or 0
    training_finished = attempt_counts["training_finished"] or 0
    errors_finished = attempt_counts["errors_finished"] or 0

    def solution_with_date(attempt: sqlite3.Row | None) -> str:
        if not attempt or not attempt["answered"]:
            return "Пока нет завершённых решений"
        percent = round(attempt["correct"] / attempt["answered"] * 100, 1)
        return (
            f"{attempt['correct']}/{attempt['answered']} — {percent}%\n"
            f"Время: {seconds_to_text(attempt['duration_seconds'])}\n"
            f"Дата: {attempt['finished_at']}"
        )

    lines = [
        "👤 Пользователь",
        "",
        f"Имя: {display_name}",
        f"ID: {user_id}",
        "",
        title,
        "",
        "🕒 Активность:",
        f"Первая: {first_activity}",
        f"Последняя: {last_activity}",
        "",
        "📌 Попытки:",
        f"Завершено: {finished_total} из {started_total}",
        f"Решение: {solution_finished}",
        f"Тренировка: {training_finished}",
        f"Разбор ошибок: {errors_finished}",
        f"Незавершённых: {unfinished_total}",
        "",
        "🏆 Лучшее решение:",
        solution_with_date(best_solution),
        "",
        "🕘 Последнее решение:",
        solution_with_date(last_solution),
        "",
        "⚡ Тренировка:",
        f"Лучшая: {format_training_attempt(best_training)}",
        f"Последняя: {format_training_attempt(last_training)}",
        f"Всего тренировок: {training_finished}",
        "",
        "🧠 Ошибки:",
        f"Активных ошибок: {errors['active_errors'] or 0}",
        f"Всего ошибочных ответов: {errors['wrong_clicks'] or 0}",
    ]

    return "\n".join(lines)

def admin_test_stats_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]
    questions_count = len(get_questions(test_id))

    with db_connect() as conn:
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

        errors = conn.execute(
            """
            SELECT COUNT(*) AS active_errors,
                   COALESCE(SUM(wrong_count), 0) AS wrong_clicks
            FROM all_time_errors
            WHERE test_id = ?
            """,
            (test_id,),
        ).fetchone()

        completed_solutions = conn.execute(
            """
            SELECT COUNT(*) AS c,
                   AVG(duration_seconds) AS avg_time
            FROM attempts
            WHERE test_id = ?
              AND mode IN (?, ?, ?, ?)
              AND finished_at IS NOT NULL
              AND answered > 0
            """,
            (test_id, *SOLUTION_MODES),
        ).fetchone()

    answered = stats["answered"] or 0
    correct = stats["correct"] or 0
    percent = round(correct / answered * 100, 1) if answered else 0

    return (
        f"📈 Статистика по тесту\n{title}\n\n"
        f"Количество вопросов: {questions_count}\n"
        f"Пользователей решали: {stats['users'] or 0}\n"
        f"Попыток начато: {stats['attempts_started'] or 0}\n"
        f"Попыток завершено: {stats['attempts_finished'] or 0}\n"
        f"Завершённых решений: {completed_solutions['c'] or 0}\n"
        f"Среднее время решения: {seconds_to_text(completed_solutions['avg_time'])}\n"
        f"Всего ответов: {answered}\n"
        f"Правильных ответов: {correct}\n"
        f"Средний процент: {percent}%\n"
        f"Активных ошибок за всё время: {errors['active_errors'] or 0}\n"
        f"Всего ошибочных ответов: {errors['wrong_clicks'] or 0}"
    )

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


def admin_summary_text() -> str:
    today_start = _today_start()

    with db_connect() as conn:
        users = _safe_count(conn, "users")
        active_today = _safe_count(conn, "users", "WHERE last_seen_at >= '%s'" % today_start)
        attempts = _safe_count(conn, "attempts")
        finished = _safe_count(conn, "attempts", "WHERE finished_at IS NOT NULL")
        attempts_today = _safe_count(conn, "attempts", "WHERE started_at >= '%s'" % today_start)
        finished_today = _safe_count(conn, "attempts", "WHERE finished_at IS NOT NULL AND finished_at >= '%s'" % today_start)
        active_sessions = _safe_count(conn, "active_sessions")
        runtime_sessions = _safe_count(conn, "runtime_sessions")
        active_errors = _safe_count(conn, "all_time_errors", "WHERE COALESCE(is_resolved, 0) = 0")
        favorites = _safe_count(conn, "favorites")

        totals = conn.execute(
            """
            SELECT COALESCE(SUM(answered), 0) AS answered,
                   COALESCE(SUM(correct), 0) AS correct
            FROM attempts
            WHERE finished_at IS NOT NULL
            """
        ).fetchone()

        last_user = conn.execute(
            """
            SELECT user_id, username, first_name, last_name, last_seen_at
            FROM users
            ORDER BY last_seen_at DESC
            LIMIT 1
            """
        ).fetchone()

    answered = int(totals["answered"] or 0) if totals else 0
    correct = int(totals["correct"] or 0) if totals else 0
    avg_percent = _percent(correct, answered)
    backend = "PostgreSQL / Neon" if DATABASE_URL else "SQLite"
    last_activity = "—"
    if last_user:
        last_activity = f"{user_display_name(last_user)} · {last_user['last_seen_at']}"

    return (
        "🛠 Админ-панель\n\n"
        "📊 Обзор\n\n"
        f"👥 Пользователей: {users or 0}\n"
        f"🟢 Активных сегодня: {active_today or 0}\n"
        f"📝 Попыток всего: {attempts or 0}\n"
        f"✅ Завершено всего: {finished or 0}\n"
        f"📅 Попыток сегодня: {attempts_today or 0}\n"
        f"🏁 Завершено сегодня: {finished_today or 0}\n\n"
        f"🎯 Средний результат: {avg_percent}%\n"
        f"🔢 Ответов в завершённых попытках: {answered}\n\n"
        f"📚 Тестов: {len(TESTS)}\n"
        f"🧠 Активных ошибок: {active_errors or 0}\n"
        f"⭐ Избранных вопросов: {favorites or 0}\n"
        f"💾 Сохранённых сессий: {active_sessions or 0}\n"
        f"🔄 Runtime-сессий: {runtime_sessions or 0}\n\n"
        f"🗄 База: {backend}\n"
        f"🕒 Последняя активность: {last_activity}"
    )

def _safe_count(conn, table_name: str, where_sql: str = "") -> int | None:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {table_name} {where_sql}").fetchone()
        return int(row["c"] or 0)
    except Exception:
        return None


def _fmt_count(value: int | None) -> str:
    return str(value) if value is not None else "—"


def admin_debug_text() -> str:
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
    ]

    if last_attempt:
        finished = last_attempt["finished_at"] or "не завершена"
        lines.extend([
            "",
            "Последняя попытка:",
            f"• test_id: {last_attempt['test_id']}",
            f"• mode: {last_attempt['mode']}",
            f"• start: {last_attempt['started_at']}",
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


def admin_users_text(page: int = 0) -> str:
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = _safe_count(conn, "users") or 0
        rows = conn.execute(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.last_seen_at,
                   COUNT(a.attempt_id) AS attempts_total,
                   SUM(CASE WHEN a.finished_at IS NOT NULL THEN 1 ELSE 0 END) AS attempts_finished,
                   COALESCE(SUM(a.answered), 0) AS answered,
                   COALESCE(SUM(a.correct), 0) AS correct
            FROM users u
            LEFT JOIN attempts a ON a.user_id = u.user_id
            GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.last_seen_at
            ORDER BY u.last_seen_at DESC
            LIMIT ? OFFSET ?
            """,
            (ADMIN_USERS_PAGE_SIZE, offset),
        ).fetchall()

    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    start_num = offset + 1 if total else 0
    end_num = min(offset + len(rows), total)

    lines = [
        "👥 Пользователи",
        "",
        f"{start_num}–{end_num} из {total}",
        f"Страница {page + 1} из {total_pages}",
        "",
    ]

    if not rows:
        lines.append("Пользователей пока нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=start_num):
        answered = int(row["answered"] or 0)
        correct = int(row["correct"] or 0)
        percent = _percent(correct, answered)
        finished = int(row["attempts_finished"] or 0)
        attempts_total = int(row["attempts_total"] or 0)
        lines.append(
            f"{n}. {user_display_name(row)} — {percent}% · "
            f"{finished}/{attempts_total} попыток · {row['last_seen_at'] or '—'}"
        )

    lines.extend(["", "Открой карточку пользователя кнопкой ниже."])
    return "\n".join(lines)


def admin_users_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE

    with db_connect() as conn:
        total = _safe_count(conn, "users") or 0
        rows = conn.execute(
            """
            SELECT user_id, username, first_name, last_name
            FROM users
            ORDER BY last_seen_at DESC
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

    total_pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:users:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:users:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(buttons)


def admin_global_user_text(user_id: int) -> str:
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

        per_tests = conn.execute(
            """
            SELECT test_id, attempts_started, attempts_finished, total_answered, total_correct, last_activity_at
            FROM user_stats
            WHERE user_id = ?
            ORDER BY last_activity_at DESC
            """,
            (user_id,),
        ).fetchall()

        favorites = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)}")
        active_errors = _safe_count(conn, "all_time_errors", f"WHERE user_id = {int(user_id)} AND COALESCE(is_resolved, 0) = 0")
        saved_sessions = _safe_count(conn, "active_sessions", f"WHERE user_id = {int(user_id)}")
        runtime_sessions = _safe_count(conn, "runtime_sessions", f"WHERE user_id = {int(user_id)}")

        last_attempts = conn.execute(
            """
            SELECT test_id, mode, started_at, finished_at, answered, correct, duration_seconds
            FROM attempts
            WHERE user_id = ?
            ORDER BY started_at DESC
            LIMIT 5
            """,
            (user_id,),
        ).fetchall()

    display_name = user_display_name(user) if user else f"ID {user_id}"
    username = f"@{user['username']}" if user and user["username"] else "—"

    attempts_total = int(totals["attempts_total"] or 0) if totals else 0
    attempts_finished = int(totals["attempts_finished"] or 0) if totals else 0
    answered = int(totals["answered"] or 0) if totals else 0
    correct = int(totals["correct"] or 0) if totals else 0
    percent = _percent(correct, answered)

    lines = [
        "👤 Карточка пользователя",
        "",
        f"Имя: {display_name}",
        f"Username: {username}",
        f"ID: {user_id}",
        f"Первый запуск: {user['first_seen_at'] if user else '—'}",
        f"Последняя активность: {user['last_seen_at'] if user else '—'}",
        "",
        "📊 Общий результат",
        f"Попыток: {attempts_finished} завершено из {attempts_total}",
        f"Правильно: {correct} из {answered}",
        f"Средний результат: {percent}%",
        "",
        "🧠 Данные",
        f"Актуальных ошибок: {active_errors or 0}",
        f"Избранных вопросов: {favorites or 0}",
        f"Сохранённых сессий: {saved_sessions or 0}",
        f"Runtime-сессий: {runtime_sessions or 0}",
    ]

    if per_tests:
        lines.extend(["", "📚 По тестам"])
        for row in per_tests:
            title = TESTS.get(row["test_id"], {}).get("title", row["test_id"])
            test_answered = int(row["total_answered"] or 0)
            test_correct = int(row["total_correct"] or 0)
            test_percent = _percent(test_correct, test_answered)
            lines.append(
                f"• {title}: {test_correct}/{test_answered} · {test_percent}% · "
                f"{int(row['attempts_finished'] or 0)} заверш."
            )

    if last_attempts:
        lines.extend(["", "🕘 Последние попытки"])
        for row in last_attempts:
            title = TESTS.get(row["test_id"], {}).get("title", row["test_id"])
            status = "завершена" if row["finished_at"] else "не завершена"
            attempt_percent_value = _percent(row["correct"], row["answered"])
            lines.append(
                f"• {title} · {mode_title(row['mode'])}: "
                f"{row['correct']}/{row['answered']} ({attempt_percent_value}%) · {status}"
            )

    return "\n".join(lines)


def admin_global_user_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📜 История", callback_data=f"admin:user_history:{user_id}:0:{page}"),
            InlineKeyboardButton("🧠 Ошибки", callback_data=f"admin:user_errors:{user_id}:0:{page}"),
        ],
        [
            InlineKeyboardButton("⭐ Избранное", callback_data=f"admin:user_favorites:{user_id}:0:{page}"),
            InlineKeyboardButton("📤 Экспорт", callback_data=f"admin:export_user:{user_id}:{page}"),
        ],
        [InlineKeyboardButton("🧹 Очистить runtime", callback_data=f"admin:clear_user_runtime_confirm:{user_id}:{page}")],
        [InlineKeyboardButton("🗑 Сбросить прогресс", callback_data=f"admin:reset_user_confirm:{user_id}:{page}")],
        [InlineKeyboardButton("👥 К пользователям", callback_data=f"admin:users:{page}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_user_back_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 К пользователю", callback_data=f"admin:global_user:{user_id}:{page}")],
        [InlineKeyboardButton("👥 К пользователям", callback_data=f"admin:users:{page}")],
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
        lines.append(f"   Старт: {row['started_at']}")

    return "\n".join(lines)


def admin_user_history_keyboard(user_id: int, page: int = 0, back_page: int = 0) -> InlineKeyboardMarkup:
    total = 0
    with db_connect() as conn:
        total = _safe_count(conn, "attempts", f"WHERE user_id = {int(user_id)}") or 0

    total_pages = _admin_user_pages(total)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:user_history:{user_id}:{page - 1}:{back_page}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:user_history:{user_id}:{page + 1}:{back_page}"))
    if nav:
        rows.append(nav)
    rows.extend(admin_user_back_keyboard(user_id, back_page).inline_keyboard)
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
        lines.append(f"   Ошибок: {row['wrong_count']} · последняя: {row['last_wrong_at']}")
        lines.append(f"   {_admin_short_text(question)}")

    return "\n".join(lines)


def admin_user_errors_keyboard(user_id: int, page: int = 0, back_page: int = 0) -> InlineKeyboardMarkup:
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
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:user_errors:{user_id}:{page - 1}:{back_page}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:user_errors:{user_id}:{page + 1}:{back_page}"))
    if nav:
        rows.append(nav)
    rows.extend(admin_user_back_keyboard(user_id, back_page).inline_keyboard)
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
        lines.append(f"   Добавлен: {row['created_at']}")
        lines.append(f"   {_admin_short_text(question)}")

    return "\n".join(lines)


def admin_user_favorites_keyboard(user_id: int, page: int = 0, back_page: int = 0) -> InlineKeyboardMarkup:
    with db_connect() as conn:
        total = _safe_count(conn, "favorites", f"WHERE user_id = {int(user_id)}") or 0

    total_pages = _admin_user_pages(total)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:user_favorites:{user_id}:{page - 1}:{back_page}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:user_favorites:{user_id}:{page + 1}:{back_page}"))
    if nav:
        rows.append(nav)
    rows.extend(admin_user_back_keyboard(user_id, back_page).inline_keyboard)
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


def admin_reset_user_confirm_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ Продолжить", callback_data=f"admin:reset_user_second:{user_id}:{page}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}")],
    ])


def admin_reset_user_second_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Да, удалить прогресс", callback_data=f"admin:reset_user_do:{user_id}:{page}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}")],
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


def admin_clear_user_runtime_confirm_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, очистить", callback_data=f"admin:clear_user_runtime_do:{user_id}:{page}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}")],
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
        "🧪 Проверка тестов — ищет ошибки в JSON и дубликаты вопросов.\n"
        "🧹 Runtime-сессии — временные состояния текущих прохождений. "
        "Их можно очистить, если после обновления кода у пользователей зависли старые состояния."
    )


def admin_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
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
    await update.message.reply_text(admin_summary_text(), reply_markup=admin_main_keyboard())


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
    await query.edit_message_text(admin_summary_text(), reply_markup=admin_main_keyboard())


async def handle_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0
    await query.edit_message_text(admin_users_text(page), reply_markup=admin_users_keyboard(page))


async def handle_admin_global_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    await query.edit_message_text(
        admin_global_user_text(int(user_id_str)),
        reply_markup=admin_global_user_keyboard(int(user_id_str), int(page_str)),
    )



async def handle_admin_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str, back_page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    back_page = int(back_page_str)
    await query.edit_message_text(
        admin_user_history_text(user_id, page),
        reply_markup=admin_user_history_keyboard(user_id, page, back_page),
    )


async def handle_admin_user_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str, back_page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    back_page = int(back_page_str)
    await query.edit_message_text(
        admin_user_errors_text(user_id, page),
        reply_markup=admin_user_errors_keyboard(user_id, page, back_page),
    )


async def handle_admin_user_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str, back_page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    back_page = int(back_page_str)
    await query.edit_message_text(
        admin_user_favorites_text(user_id, page),
        reply_markup=admin_user_favorites_keyboard(user_id, page, back_page),
    )


async def handle_admin_export_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    path = export_user_csv(user_id)
    await query.message.reply_document(InputFile(path), caption=f"📤 Экспорт пользователя: {user_id}")
    await query.edit_message_text(
        admin_global_user_text(user_id),
        reply_markup=admin_global_user_keyboard(user_id, page),
    )


async def handle_admin_clear_user_runtime_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    await query.edit_message_text(
        "🧹 Очистить runtime-сессии пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Это удалит только временные состояния текущих прохождений. "
        "Статистика, попытки, ошибки и избранное останутся.",
        reply_markup=admin_clear_user_runtime_confirm_keyboard(user_id, page),
    )


async def handle_admin_clear_user_runtime_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    count = clear_user_runtime_sessions(user_id)
    await query.edit_message_text(
        f"✅ Runtime-сессии пользователя очищены.\n\nУдалено записей: {count}",
        reply_markup=admin_global_user_keyboard(user_id, page),
    )


async def handle_admin_reset_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    await query.edit_message_text(
        "🗑 Сбросить прогресс пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Будут удалены попытки, статистика, ошибки, избранное и сохранённые сессии. "
        "Сам пользователь останется в списке.\n\n"
        "Это действие нельзя отменить.",
        reply_markup=admin_reset_user_confirm_keyboard(user_id, page),
    )


async def handle_admin_reset_user_second(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    await query.edit_message_text(
        "⚠️ Последнее подтверждение\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "После нажатия кнопки ниже прогресс будет удалён полностью.",
        reply_markup=admin_reset_user_second_keyboard(user_id, page),
    )


async def handle_admin_reset_user_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, page_str = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
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
        reply_markup=admin_global_user_keyboard(user_id, page),
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
    await query.edit_message_text("Выбери тест:", reply_markup=admin_tests_keyboard())

async def handle_admin_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(TESTS[test_id]["title"], reply_markup=admin_test_keyboard(test_id))

async def handle_admin_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_summary_text(), reply_markup=admin_main_keyboard())

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
