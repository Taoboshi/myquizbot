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
from .access import access_label, access_type_label, can_view_test, effective_test_access, effective_access_type, effective_access_code, subject_access_label, subject_access_type, subject_access_code
from .loader import add_subject_override, apply_test_metadata_override, effective_test_info, get_questions, get_subject_info, get_subjects, get_tests_for_subject, get_unassigned_tests, remove_subject_override, _slug
from .quiz import format_solution_attempt, format_training_attempt, public_rating_text
from .storage import DATABASE_URL, db_connect, delete_subject_setting, get_all_time_error_indices, get_test_access_setting, get_test_metadata_setting, grant_user_test_access, has_user_test_access, list_test_access_users, list_user_test_access, reset_test_access_setting, reset_test_metadata_setting, revoke_user_test_access, set_subject_access_setting, set_subject_setting, set_test_access_setting, set_test_metadata_setting, upsert_user


def fmt_msk(value) -> str:
    return format_display_datetime(value)


def admin_overview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin:summary")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Обзор", callback_data="admin:summary")],
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="admin:users:0"),
            InlineKeyboardButton("📚 Контент", callback_data="admin:tests"),
        ],
        [
            InlineKeyboardButton("🧠 Ошибки", callback_data="admin:errors"),
            InlineKeyboardButton("⚙️ Сервис", callback_data="admin:manage"),
        ],
    ])

def subject_button_title(info: dict, subject_id: str = "") -> str:
    emoji = (info.get("emoji") or "").strip()
    title = info.get("title") or subject_id
    return f"{emoji} {title}" if emoji else str(title)



def admin_tests_text() -> str:
    subjects = get_subjects()
    tests_count = len(TESTS)

    lines = [
        "📚 Контент",
        "",
        f"Разделов: {len(subjects)}",
        f"Тестов: {tests_count}",
        "",
        "Здесь создаются разделы и раскладываются тесты.",
    ]

    return "\n".join(lines)


def admin_tests_keyboard() -> InlineKeyboardMarkup:
    rows = []

    for subject_id, info in get_subjects():
        tests_count = len(get_tests_for_subject(subject_id))
        emoji = info.get("emoji", "")
        title = info.get("title", subject_id)
        rows.append([
            InlineKeyboardButton(
                f"{subject_button_title(info, subject_id)} ({tests_count})",
                callback_data=f"admin:subject:{subject_id}",
            )
        ])

    rows.append([InlineKeyboardButton("➕ Добавить раздел", callback_data="admin:add_subject")])
    rows.append([InlineKeyboardButton("🧪 Проверить тесты", callback_data="admin:validate_tests")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_subject_text(subject_id: str) -> str:
    info = get_subject_info(subject_id)
    tests = get_tests_for_subject(subject_id)

    lines = [
        subject_button_title(info, subject_id),
        "",
        f"Тестов в разделе: {len(tests)}",
        "",
    ]

    if tests:
        lines.append("Выбери тест или добавь новый.")
    else:
        lines.append("Раздел пустой. Можно добавить тест или удалить раздел.")

    return "\n".join(lines)


def admin_subject_keyboard(subject_id: str) -> InlineKeyboardMarkup:
    rows = []

    for test_id, info in get_tests_for_subject(subject_id):
        title = info.get("title", test_id)
        if len(title) > 45:
            title = title[:42].rstrip() + "…"
        rows.append([
            InlineKeyboardButton(
                f"📚 {title}",
                callback_data=f"admin:test:{test_id}",
            )
        ])

    rows.append([InlineKeyboardButton("➕ Добавить тест", callback_data=f"admin:add_test_to_subject:{subject_id}")])
    rows.append([InlineKeyboardButton("⚙️ Настройки раздела", callback_data=f"admin:subject_settings:{subject_id}")])
    rows.append([InlineKeyboardButton("📚 К разделам", callback_data="admin:tests")])
    return InlineKeyboardMarkup(rows)


def admin_subject_access_text(subject_id: str) -> str:
    info = get_subject_info(subject_id)
    title = subject_button_title(info, subject_id)
    access_type = subject_access_type(subject_id)
    code = subject_access_code(subject_id)

    lines = [
        "🔐 Доступ к разделу",
        "",
        f"Раздел: {title}",
        f"Текущий доступ: {access_type_label(access_type)}",
        f"Код доступа: {code if access_type == 'code' else '—'}",
        "",
    ]

    if access_type == "public":
        lines.append("Раздел открыт всем.")
    elif access_type == "private":
        lines.append("Раздел видят только пользователи с доступом.")
    elif access_type == "code":
        lines.append("Раздел виден с замком и открывается по коду.")
    elif access_type == "admin_only":
        lines.append("Раздел видит только админ.")

    return "\n".join(lines)


def admin_subject_access_keyboard(subject_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 Открытый", callback_data=f"admin:set_subject_access:{subject_id}:public"),
            InlineKeyboardButton("🔐 Приватный", callback_data=f"admin:set_subject_access:{subject_id}:private"),
        ],
        [
            InlineKeyboardButton("🔑 По коду", callback_data=f"admin:set_subject_access:{subject_id}:code"),
            InlineKeyboardButton("🙈 Только админ", callback_data=f"admin:set_subject_access:{subject_id}:admin_only"),
        ],
        [InlineKeyboardButton("✏️ Изменить код", callback_data=f"admin:set_subject_code:{subject_id}")],
        [InlineKeyboardButton("↩️ К настройкам раздела", callback_data=f"admin:subject_settings:{subject_id}")],
    ])


def admin_subject_settings_text(subject_id: str) -> str:
    info = get_subject_info(subject_id)
    tests = get_tests_for_subject(subject_id)
    title = info.get("title", subject_id)
    emoji = info.get("emoji", "")

    lines = [
        "⚙️ Настройки раздела",
        "",
        subject_button_title(info, subject_id),
        f"Тестов внутри: {len(tests)}",
        f"Доступ: {subject_access_label(subject_id)}",
        "",
        "Здесь можно переименовать, удалить раздел или настроить доступ.",
    ]

    if tests:
        lines.extend([
            "",
            "Удалить раздел можно только когда в нём нет тестов.",
            "Сначала открепи или перенеси тесты.",
        ])

    return "\n".join(lines)


def admin_subject_settings_keyboard(subject_id: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("✏️ Переименовать раздел", callback_data=f"admin:rename_subject:{subject_id}")],
        [InlineKeyboardButton("🔐 Доступ к разделу", callback_data=f"admin:subject_access:{subject_id}")],
    ]

    if get_tests_for_subject(subject_id):
        rows.append([InlineKeyboardButton("🧷 Сначала открепи тесты", callback_data=f"admin:subject:{subject_id}")])
    else:
        rows.append([InlineKeyboardButton("🗑 Удалить раздел", callback_data=f"admin:delete_subject_confirm:{subject_id}")])

    rows.append([InlineKeyboardButton("↩️ К разделу", callback_data=f"admin:subject:{subject_id}")])
    rows.append([InlineKeyboardButton("📚 К разделам", callback_data="admin:tests")])
    return InlineKeyboardMarkup(rows)


def admin_delete_subject_confirm_keyboard(subject_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Да, удалить раздел", callback_data=f"admin:delete_subject_do:{subject_id}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:subject_settings:{subject_id}")],
    ])


def admin_add_test_to_subject_text(subject_id: str) -> str:
    subject = get_subject_info(subject_id)
    tests = get_unassigned_tests()

    lines = [
        "➕ Добавить тест",
        "",
        f"Раздел: {subject_button_title(subject, subject_id)}",
        "",
    ]

    if not tests:
        lines.extend([
            "Непривязанных тестов нет.",
            "",
            "Положи JSON-файл в папку tests без subject/раздела и перезапусти Render.",
        ])
    else:
        lines.append("Выбери тест из папки tests, который ещё не привязан к разделу.")

    return "\n".join(lines)


def admin_add_test_to_subject_keyboard(subject_id: str) -> InlineKeyboardMarkup:
    rows = []

    for test_id, info in get_unassigned_tests():
        title = info.get("title", test_id)
        if len(title) > 44:
            title = title[:41].rstrip() + "…"
        rows.append([
            InlineKeyboardButton(
                f"📄 {title}",
                callback_data=f"admin:assign_test_subject:{subject_id}:{test_id}",
            )
        ])

    rows.append([InlineKeyboardButton("↩️ К разделу", callback_data=f"admin:subject:{subject_id}")])
    rows.append([InlineKeyboardButton("📚 К разделам", callback_data="admin:tests")])
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
        [
            InlineKeyboardButton("🔐 Доступ", callback_data=f"admin:test_access:{test_id}"),
            InlineKeyboardButton("✏️ Название/раздел", callback_data=f"admin:test_meta:{test_id}"),
        ],
        [InlineKeyboardButton("🧪 Проверить тест", callback_data=f"admin:validate_test:{test_id}")],
        [InlineKeyboardButton("📚 К тестам", callback_data="admin:tests")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])

def admin_back_to_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 К тесту", callback_data=f"admin:test:{test_id}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])

def admin_test_users_text(test_id: str, page: int = 0) -> str:
    title = effective_test_info(test_id)["title"]
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
    title = effective_test_info(test_id)["title"]

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
    title = effective_test_info(test_id)["title"]
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

    return "\n".join(lines)


def admin_test_stats_text(test_id: str) -> str:
    return admin_test_overview_text(test_id)


def validate_single_test_text(test_id: str) -> str:
    info = TESTS[test_id]
    title = info["title"]

    lines = ["🧪 Проверка теста", "", f"📚 {title}", f"ID: {test_id}", ""]

    try:
        questions = get_questions(test_id)
    except Exception as exc:
        return "\n".join(lines + [f"❌ Не удалось загрузить: {type(exc).__name__}: {exc}"])

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

        normalized_question = " ".join(q_text.lower().split())
        normalized_options = "|".join(" ".join(str(option).lower().split()) for option in options)
        normalized = f"{normalized_question}||{normalized_options}||{correct_index}"
        if normalized_question:
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

    return "\n".join(lines)

def admin_rating_text(test_id: str) -> str:
    return public_rating_text(test_id)

def admin_frequent_errors_text(test_id: str) -> str:
    title = effective_test_info(test_id)["title"]

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
    from .admin_users import ensure_admin_tables
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
            f"Ошибка: {type(exc).__name__}: {exc}\n\n"
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
    from .admin_users import ensure_admin_tables
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


