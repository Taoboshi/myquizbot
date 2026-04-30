import html
import random
from datetime import datetime

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .config import BTN_TEST_MENU, RESUMABLE_MODES, TESTS
from .helpers import mode_title, seconds_to_text
from .keyboards import (
    after_finish_keyboard,
    answer_keyboard,
    find_input_keyboard,
    find_question_keyboard,
    find_results_keyboard,
    favorite_question_keyboard,
    favorites_list_keyboard,
    history_keyboard,
    attempt_detail_keyboard,
    attempt_error_detail_keyboard,
    attempt_errors_keyboard,
    profile_error_detail_keyboard,
    profile_errors_keyboard,
    learn_menu_keyboard,
    profile_keyboard,
    profile_back_keyboard,
    next_keyboard,
    public_rating_keyboard,
    question_menu_keyboard,
    question_view_keyboard,
    reset_errors_keyboard,
    session_error_keyboard,
    solve_menu_keyboard,
    start_from_number_keyboard,
    stats_keyboard,
    test_main_keyboard,
    test_select_keyboard,
)
from .keyboards import find_results_text, preview_question_text, search_question_indices
from .loader import get_questions
from .quiz import (
    add_session_wrong_answer,
    build_question_text,
    finish_attempt_if_needed,
    format_session_error_card,
    format_marked_question_text,
    my_stats_text,
    public_rating_text,
    result_text,
    wrong_index_for_question,
)
from .runtime import LAST_START_AT, USER_STATE
from .state import clear_text_waiting_state, delete_active_session, get_state, load_active_session, restore_state, save_active_session, start_quiz_mode
from .storage import (
    add_all_time_error,
    clear_all_time_errors,
    get_all_time_error_indices,
    get_answered_question_count,
    get_attempt_wrong_answers,
    get_attempt_detail,
    get_attempt_history,
    get_attempt_history_count,
    get_attempt_order,
    get_favorite_count,
    get_favorite_indices,
    get_profile_error_counts,
    get_profile_error_rows,
    db_connect,
    is_favorite_question,
    record_answer,
    record_attempt_wrong_answer,
    remove_all_time_error,
    remove_favorite_question,
    toggle_favorite_question,
    upsert_user,
)

async def setup_bot_commands(app) -> None:
    await app.bot.set_my_commands([
        BotCommand("start", "Открыть меню"),
        BotCommand("tests", "Выбрать тест"),
        BotCommand("finish", "Завершить текущую попытку"),
        BotCommand("stats", "Статистика"),
        BotCommand("reset", "Сбросить текущее действие"),
        BotCommand("reset_errors", "Сбросить ошибки"),
        BotCommand("myid", "Показать Telegram ID"),
        BotCommand("admin", "Админ-панель"),
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    chat_id = update.effective_chat.id
    current = datetime.now().timestamp()

    if current - LAST_START_AT.get(chat_id, 0) < 2:
        return

    LAST_START_AT[chat_id] = current
    await update.message.reply_text("Выбери тест:", reply_markup=test_select_keyboard())

async def tests_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    await update.message.reply_text("Выбери тест:", reply_markup=test_select_keyboard())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if len(TESTS) == 1:
        test_id = next(iter(TESTS))
        await update.message.reply_text(my_stats_text(update.effective_user.id, test_id), reply_markup=stats_keyboard(test_id))
    else:
        await update.message.reply_text("Выбери тест:", reply_markup=test_select_keyboard())

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)
    if state.get("test_id") and state.get("mode") in RESUMABLE_MODES:
        delete_active_session(update.effective_user.id, state.get("test_id"))
    USER_STATE.pop(update.effective_chat.id, None)
    await update.message.reply_text("Текущее действие сброшено.", reply_markup=test_select_keyboard())

async def reset_errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if len(TESTS) == 1:
        test_id = next(iter(TESTS))
        await update.message.reply_text("Сбросить ошибки?", reply_markup=reset_errors_keyboard(test_id))
    else:
        await update.message.reply_text("Выбери тест:", reply_markup=test_select_keyboard())

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    await update.message.reply_text(f"Твой Telegram ID: {update.effective_user.id}")

def test_main_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    total = len(get_questions(test_id))
    errors = len(get_all_time_error_indices(user_id, test_id))
    return f"{title}\n\nВопросов: {total}\nОшибок для разбора: {errors}"


def learn_menu_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    total = len(get_questions(test_id))
    errors = len(get_all_time_error_indices(user_id, test_id))
    return f"📖 Учить\n{title}\n\nВопросов: {total}\nОшибок для разбора: {errors}"



def _safe_percent(correct: int | None, answered: int | None) -> int:
    answered = int(answered or 0)
    correct = int(correct or 0)
    if answered <= 0:
        return 0
    return round(correct / answered * 100)


def _profile_display_name(user) -> str:
    first = getattr(user, "first_name", None) or "Пользователь"
    last = getattr(user, "last_name", None) or ""
    return f"{first} {last}".strip()


def _profile_username(user) -> str:
    username = getattr(user, "username", None)
    return f"@{username}" if username else "username не указан"


def profile_text(user, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    total_questions = len(get_questions(test_id))

    try:
        errors_count = len(get_all_time_error_indices(user.id, test_id))
    except Exception:
        errors_count = 0

    try:
        favorites_count = get_favorite_count(user.id, test_id)
    except Exception:
        favorites_count = 0

    stats = None
    best_attempt = None
    last_attempt = None

    try:
        with db_connect() as conn:
            stats = conn.execute(
                """
                SELECT attempts_started, attempts_finished, total_answered, total_correct
                FROM user_stats
                WHERE user_id = ? AND test_id = ?
                """,
                (user.id, test_id),
            ).fetchone()

            best_attempt = conn.execute(
                """
                SELECT answered, correct
                FROM attempts
                WHERE user_id = ?
                  AND test_id = ?
                  AND finished_at IS NOT NULL
                  AND answered > 0
                ORDER BY
                    (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                    correct DESC,
                    finished_at DESC
                LIMIT 1
                """,
                (user.id, test_id),
            ).fetchone()

            last_attempt = conn.execute(
                """
                SELECT answered, correct
                FROM attempts
                WHERE user_id = ?
                  AND test_id = ?
                  AND finished_at IS NOT NULL
                  AND answered > 0
                ORDER BY finished_at DESC
                LIMIT 1
                """,
                (user.id, test_id),
            ).fetchone()
    except Exception:
        stats = None
        best_attempt = None
        last_attempt = None

    attempts_total = int(stats["attempts_started"] or 0) if stats else 0
    total_answered = int(stats["total_answered"] or 0) if stats else 0
    total_correct = int(stats["total_correct"] or 0) if stats else 0

    try:
        answered_questions = get_answered_question_count(user.id, test_id)
    except Exception:
        answered_questions = min(total_answered, total_questions)

    accuracy = _safe_percent(total_correct, total_answered)

    best_percent = _safe_percent(best_attempt["correct"], best_attempt["answered"]) if best_attempt else None
    last_percent = _safe_percent(last_attempt["correct"], last_attempt["answered"]) if last_attempt else None

    best_line = f"{best_percent}%" if best_percent is not None else "пока нет"
    last_line = f"{last_percent}%" if last_percent is not None else "пока нет"

    return (
        f"👤 Профиль\n\n"
        f"{_profile_display_name(user)}\n"
        f"{_profile_username(user)}\n\n"
        f"📚 Тест: {title}\n\n"
        f"📌 Кратко:\n"
        f"Решено вопросов: {answered_questions} из {total_questions}\n"
        f"Точность ответов: {accuracy}%\n"
        f"Ошибок: {errors_count}\n"
        f"Избранных: {favorites_count}\n"
        f"Попыток: {attempts_total}\n\n"
        f"🏆 Лучший результат: {best_line}\n"
        f"🕓 Последняя попытка: {last_line}"
    )



PROFILE_PAGE_SIZE = 10


def _format_dt(value) -> str:
    if not value:
        return "—"
    text = str(value)
    if "." in text:
        text = text.split(".", 1)[0]
    text = text.replace("T", " ")
    if "+" in text:
        text = text.split("+", 1)[0].strip()
    return text[:16]


def _short_question(test_id: str, index: int, limit: int = 90) -> str:
    question = str(get_questions(test_id)[index]["question"]).replace("\n", " ").strip()
    if len(question) > limit:
        return question[:limit].rstrip() + "…"
    return question


def _total_pages(total: int, page_size: int = PROFILE_PAGE_SIZE) -> int:
    return max(1, (total + page_size - 1) // page_size)


def _page_bounds(page: int, total: int, page_size: int = PROFILE_PAGE_SIZE) -> tuple[int, int, int]:
    pages = _total_pages(total, page_size)
    page = max(0, min(page, pages - 1))
    start = page * page_size
    end = min(total, start + page_size)
    return page, start, end


def _neighbor_indices(indices: list[int], current_index: int) -> tuple[int | None, int | None]:
    try:
        pos = indices.index(current_index)
    except ValueError:
        return None, None
    prev_index = indices[pos - 1] if pos > 0 else None
    next_index = indices[pos + 1] if pos + 1 < len(indices) else None
    return prev_index, next_index


def favorites_text(user_id: int, test_id: str, page: int) -> tuple[str, list[int], int, int]:
    indices = get_favorite_indices(user_id, test_id)
    total = len(indices)
    page, start, end = _page_bounds(page, total)
    visible = indices[start:end]
    title = TESTS[test_id]["title"]

    lines = [
        "⭐ Избранные",
        "",
        title,
        "",
        f"Всего: {total}",
    ]

    if total:
        lines.append(f"Показаны: {start + 1}–{end} из {total}")
        lines.append("")
        for item_no, index in enumerate(visible, start=start + 1):
            lines.append(f"{item_no}. Вопрос {index + 1}")
            lines.append(_short_question(test_id, index))
            lines.append("")
    else:
        lines.extend(["", "Избранных вопросов пока нет."])

    return "\n".join(lines).rstrip(), visible, page, _total_pages(total)


def favorite_question_text(test_id: str, index: int) -> str:
    title = TESTS[test_id]["title"]
    return format_marked_question_text(
        test_id,
        index,
        ["⭐ Избранный вопрос", "", f"📚 {title}", f"Вопрос {index + 1}"],
    )


def profile_errors_text(user_id: int, test_id: str, page: int) -> tuple[str, list[int], int, int]:
    rows = get_profile_error_rows(user_id, test_id)
    counts = get_profile_error_counts(user_id, test_id)
    total = len(rows)
    page, start, end = _page_bounds(page, total)
    visible_rows = rows[start:end]
    visible_indices = [int(row["question_index"]) for row in visible_rows]
    title = TESTS[test_id]["title"]

    lines = [
        "🧠 Ошибки",
        "",
        title,
        "",
        f"Всего: {counts['total']}",
        f"Не исправлено: {counts['unresolved']}",
        f"Исправлено: {counts['resolved']}",
    ]

    if total:
        lines.append("")
        lines.append(f"Показаны: {start + 1}–{end} из {total}")
        lines.append("")
        for item_no, row in enumerate(visible_rows, start=start + 1):
            index = int(row["question_index"])
            resolved = int(row.get("is_resolved") or 0) == 1
            status = "✅ Исправлена" if resolved else "❌ Не исправлена"
            lines.append(f"{item_no}. Вопрос {index + 1}")
            lines.append(_short_question(test_id, index))
            lines.append(f"Дата ошибки: {_format_dt(row.get('last_wrong_at'))}")
            lines.append(f"Статус: {status}")
            lines.append("")
    else:
        lines.extend(["", "Ошибок пока нет."])

    return "\n".join(lines).rstrip(), visible_indices, page, _total_pages(total)


def profile_error_text(user_id: int, test_id: str, index: int) -> str:
    rows = get_profile_error_rows(user_id, test_id)
    row = next((item for item in rows if int(item["question_index"]) == index), None)
    title = TESTS[test_id]["title"]

    if row:
        resolved = int(row.get("is_resolved") or 0) == 1
        status = "✅ Исправлена" if resolved else "❌ Не исправлена"
        wrong_index = row.get("last_wrong_answer_index")
        extra = [
            "🧠 Ошибка",
            "",
            f"📚 {title}",
            f"Вопрос {index + 1}",
            "",
            f"Дата ошибки: {_format_dt(row.get('last_wrong_at'))}",
            f"Статус: {status}",
        ]
    else:
        wrong_index = None
        extra = ["🧠 Ошибка", "", f"📚 {title}", f"Вопрос {index + 1}"]

    return format_marked_question_text(
        test_id,
        index,
        extra,
        selected_index=wrong_index,
        show_answer_note=wrong_index is None,
    )


def history_text(user_id: int, test_id: str, page: int) -> tuple[str, list[dict], int, int]:
    total = get_attempt_history_count(user_id, test_id)
    page, start, end = _page_bounds(page, total)
    attempts = get_attempt_history(user_id, test_id, limit=PROFILE_PAGE_SIZE, offset=start)
    title = TESTS[test_id]["title"]

    lines = [
        "📜 История",
        "",
        title,
        "",
    ]

    if not attempts:
        lines.append("Попыток пока нет.")
        return "\n".join(lines), attempts, page, _total_pages(total)

    lines.append(f"Показаны: {start + 1}–{start + len(attempts)} из {total}")
    lines.append("")

    for item_no, attempt in enumerate(attempts, start=1):
        answered = int(attempt.get("answered") or 0)
        correct = int(attempt.get("correct") or 0)
        wrong = int(attempt.get("wrong_count") or 0)
        percent = round(correct / answered * 100) if answered else 0
        lines.append(f"{item_no}. {mode_title(attempt.get('mode'))} · {percent}%")
        lines.append(f"{_format_dt(attempt.get('finished_at'))} · {answered} вопроса · {wrong} ошибок")
        lines.append("")

    return "\n".join(lines).rstrip(), attempts, page, _total_pages(total)


def attempt_detail_text(user_id: int, test_id: str, attempt_id: int) -> tuple[str, dict | None]:
    attempt = get_attempt_detail(user_id, test_id, attempt_id)
    if not attempt:
        return "Попытка не найдена.", None

    title = TESTS[test_id]["title"]
    answered = int(attempt.get("answered") or 0)
    correct = int(attempt.get("correct") or 0)
    wrong = int(attempt.get("wrong_count") or 0)
    percent = round(correct / answered * 100) if answered else 0

    lines = [
        f"📄 Попытка #{attempt_id}",
        "",
        f"📚 {title}",
        f"🎮 {mode_title(attempt.get('mode'))}",
        f"🕓 {_format_dt(attempt.get('finished_at'))}",
        f"⏱ {seconds_to_text(attempt.get('duration_seconds'))}",
        "",
        "📊 Результат:",
        f"🏆 {percent}%",
        f"✅ Правильно: {correct}",
        f"❌ Ошибок: {wrong}",
        f"📝 Решено: {answered}",
    ]

    return "\n".join(lines), attempt


def attempt_errors_text(user_id: int, test_id: str, attempt_id: int, page: int) -> tuple[str, list[int], int, int]:
    items = get_attempt_wrong_answers(user_id, test_id, attempt_id)
    indices = [int(item["question_index"]) for item in items]
    total = len(indices)
    page, start, end = _page_bounds(page, total)
    visible = indices[start:end]
    title = TESTS[test_id]["title"]

    lines = [
        "🧠 Ошибки попытки",
        "",
        f"📄 Попытка #{attempt_id}",
        title,
        "",
        f"Ошибок: {total}",
    ]

    if total:
        lines.append("")
        if total > PROFILE_PAGE_SIZE:
            lines.append(f"Показаны: {start + 1}–{end} из {total}")
            lines.append("")
        for item_no, index in enumerate(visible, start=start + 1):
            lines.append(f"{item_no}. Вопрос {index + 1}")
            lines.append(_short_question(test_id, index))
            lines.append("")
    else:
        lines.extend(["", "Ошибок в этой попытке нет."])

    return "\n".join(lines).rstrip(), visible, page, _total_pages(total)


def attempt_error_text(user_id: int, test_id: str, attempt_id: int, index: int) -> str:
    items = get_attempt_wrong_answers(user_id, test_id, attempt_id)
    item = next((entry for entry in items if int(entry["question_index"]) == index), None)
    wrong_index = item.get("wrong_answer_index") if item else None
    title = TESTS[test_id]["title"]

    return format_marked_question_text(
        test_id,
        index,
        ["🧠 Ошибка попытки", "", f"📚 {title}", f"📄 Попытка #{attempt_id}", f"Вопрос {index + 1}"],
        selected_index=wrong_index,
        show_answer_note=wrong_index is None,
    )


def get_state_or_restore(chat_id: int, user_id: int, test_id: str) -> dict:
    state = get_state(chat_id)
    if state.get("active") and state.get("test_id") == test_id:
        return state

    if not state.get("active"):
        data = load_active_session(user_id, test_id)
        if data:
            return restore_state(chat_id, data)

    return state

async def handle_learn_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)

    await query.edit_message_text(learn_menu_text(query.from_user.id, test_id), reply_markup=learn_menu_keyboard(test_id))

async def handle_tests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    await query.edit_message_text("Выбери тест:", reply_markup=test_select_keyboard())

async def handle_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)

    await query.edit_message_text(test_main_text(query.from_user.id, test_id), reply_markup=test_main_keyboard(test_id))


async def handle_my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)

    await query.edit_message_text(profile_text(query.from_user, test_id), reply_markup=profile_keyboard(test_id))



async def handle_profile_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, page_str = query.data.split(":")
    page = int(page_str)

    text, visible, page, total_pages = favorites_text(query.from_user.id, test_id, page)
    await query.edit_message_text(text, reply_markup=favorites_list_keyboard(test_id, visible, page, total_pages))


async def handle_favorite_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, page_str, index_str = query.data.split(":")
    page = int(page_str)
    index = int(index_str)

    indices = get_favorite_indices(query.from_user.id, test_id)
    if index not in indices:
        text, visible, page, total_pages = favorites_text(query.from_user.id, test_id, page)
        await query.edit_message_text(text, reply_markup=favorites_list_keyboard(test_id, visible, page, total_pages))
        return

    prev_index, next_index = _neighbor_indices(indices, index)
    await query.edit_message_text(
        favorite_question_text(test_id, index),
        reply_markup=favorite_question_keyboard(test_id, index, page, prev_index, next_index),
        parse_mode="HTML",
    )


async def handle_favorite_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer("Убрано из избранного")
    _, test_id, page_str, index_str = query.data.split(":")
    page = int(page_str)
    index = int(index_str)

    remove_favorite_question(query.from_user.id, test_id, index)
    text, visible, page, total_pages = favorites_text(query.from_user.id, test_id, page)
    await query.edit_message_text(text, reply_markup=favorites_list_keyboard(test_id, visible, page, total_pages))


async def handle_profile_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, page_str = query.data.split(":")
    page = int(page_str)

    text, visible, page, total_pages = profile_errors_text(query.from_user.id, test_id, page)
    await query.edit_message_text(text, reply_markup=profile_errors_keyboard(test_id, visible, page, total_pages))


async def handle_profile_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, page_str, index_str = query.data.split(":")
    page = int(page_str)
    index = int(index_str)

    rows = get_profile_error_rows(query.from_user.id, test_id)
    indices = [int(row["question_index"]) for row in rows]
    prev_index, next_index = _neighbor_indices(indices, index)
    favorite = is_favorite_question(query.from_user.id, test_id, index)

    await query.edit_message_text(
        profile_error_text(query.from_user.id, test_id, index),
        reply_markup=profile_error_detail_keyboard(test_id, index, page, prev_index, next_index, favorite),
        parse_mode="HTML",
    )


async def handle_profile_error_favorite_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    _, test_id, page_str, index_str = query.data.split(":")
    page = int(page_str)
    index = int(index_str)

    is_now_favorite = toggle_favorite_question(query.from_user.id, test_id, index)
    await query.answer("Добавлено в избранное" if is_now_favorite else "Убрано из избранного")

    rows = get_profile_error_rows(query.from_user.id, test_id)
    indices = [int(row["question_index"]) for row in rows]
    prev_index, next_index = _neighbor_indices(indices, index)

    await query.edit_message_reply_markup(
        reply_markup=profile_error_detail_keyboard(test_id, index, page, prev_index, next_index, is_now_favorite)
    )


async def handle_profile_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, page_str = query.data.split(":")
    page = int(page_str)

    text, attempts, page, total_pages = history_text(query.from_user.id, test_id, page)
    await query.edit_message_text(text, reply_markup=history_keyboard(test_id, attempts, page, total_pages))


async def handle_profile_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, attempt_id_str, page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)

    text, attempt = attempt_detail_text(query.from_user.id, test_id, attempt_id)
    if not attempt:
        await query.edit_message_text(text, reply_markup=profile_back_keyboard(test_id))
        return

    await query.edit_message_text(
        text,
        reply_markup=attempt_detail_keyboard(test_id, attempt_id, page, int(attempt.get("wrong_count") or 0)),
    )


async def handle_repeat_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, attempt_id_str = query.data.split(":")
    attempt_id = int(attempt_id_str)

    attempt = get_attempt_detail(query.from_user.id, test_id, attempt_id)
    order = get_attempt_order(attempt)

    if not order:
        await query.edit_message_text(
            "Для этой старой попытки повтор недоступен.",
            reply_markup=profile_back_keyboard(test_id),
        )
        return

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)
    start_quiz_mode(state, query.from_user.id, test_id, "repeat", order)
    index = state["order"][state["pos"]]

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )


async def handle_attempt_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, attempt_id_str, page_str, history_page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)
    history_page = int(history_page_str)

    text, visible, page, total_pages = attempt_errors_text(query.from_user.id, test_id, attempt_id, page)
    await query.edit_message_text(
        text,
        reply_markup=attempt_errors_keyboard(test_id, attempt_id, visible, page, total_pages, history_page),
    )


async def handle_attempt_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, attempt_id_str, page_str, index_str, history_page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)
    index = int(index_str)
    history_page = int(history_page_str)

    items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    indices = [int(item["question_index"]) for item in items]
    prev_index, next_index = _neighbor_indices(indices, index)
    favorite = is_favorite_question(query.from_user.id, test_id, index)

    await query.edit_message_text(
        attempt_error_text(query.from_user.id, test_id, attempt_id, index),
        reply_markup=attempt_error_detail_keyboard(
            test_id, attempt_id, index, page, history_page, prev_index, next_index, favorite
        ),
        parse_mode="HTML",
    )


async def handle_attempt_error_favorite_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    _, test_id, attempt_id_str, page_str, index_str, history_page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)
    index = int(index_str)
    history_page = int(history_page_str)

    is_now_favorite = toggle_favorite_question(query.from_user.id, test_id, index)
    await query.answer("Добавлено в избранное" if is_now_favorite else "Убрано из избранного")

    items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    indices = [int(item["question_index"]) for item in items]
    prev_index, next_index = _neighbor_indices(indices, index)

    await query.edit_message_reply_markup(
        reply_markup=attempt_error_detail_keyboard(
            test_id, attempt_id, index, page, history_page, prev_index, next_index, is_now_favorite
        )
    )


async def handle_question_favorite_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    _, test_id, index_str = query.data.split(":")
    index = int(index_str)

    is_now_favorite = toggle_favorite_question(query.from_user.id, test_id, index)
    await query.answer("Добавлено в избранное" if is_now_favorite else "Убрано из избранного")

    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)
    await query.edit_message_reply_markup(
        reply_markup=question_menu_keyboard(test_id, index, state.get("mode"), is_favorite=is_now_favorite)
    )

async def handle_solve_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    state["pending_start_from_number_test_id"] = None

    await query.edit_message_text("📝 Решать\n\nВыбери режим:", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))

async def handle_start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, mode = query.data.split(":")

    order = list(range(len(get_questions(test_id))))
    if mode == "random":
        random.shuffle(order)
    elif mode == "reverse":
        order = list(reversed(order))

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)

    start_quiz_mode(state, query.from_user.id, test_id, mode, order)
    index = state["order"][state["pos"]]

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_start_from_number_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)
    state["pending_start_from_number_test_id"] = test_id

    await query.edit_message_text(
        f"🎳 С номера\n\nВведи номер вопроса от 1 до {len(get_questions(test_id))}.",
        reply_markup=start_from_number_keyboard(test_id),
    )

async def handle_mini_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, _count = query.data.split(":")

    order = list(range(len(get_questions(test_id))))
    random.shuffle(order)
    order = order[:min(10, len(order))]

    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, "mini", order)
    index = state["order"][state["pos"]]

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_errors_solve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    order = get_all_time_error_indices(query.from_user.id, test_id)
    if not order:
        await query.answer("Ошибок для разбора нет")
        await query.edit_message_text(learn_menu_text(query.from_user.id, test_id), reply_markup=learn_menu_keyboard(test_id))
        return

    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, "errors", order)
    index = state["order"][state["pos"]]

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, index_str, answer_str = query.data.split(":")
    index = int(index_str)
    selected = int(answer_str)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))
        return
    if state.get("awaiting_next"):
        await query.answer("Нажми «Следующий»")
        return
    if state.get("test_id") != test_id or state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    correct_index = int(get_questions(test_id)[index]["correct_index"])
    is_correct = selected == correct_index

    record_answer(query.from_user.id, test_id, is_correct, index)
    state["total"] += 1

    if is_correct:
        state["correct"] += 1
        remove_all_time_error(query.from_user.id, test_id, index)

        await query.edit_message_text(
            build_question_text(index, state, selected_index=selected, show_correct=True),
            parse_mode="HTML",
        )

        state["pos"] += 1

        if state["pos"] >= len(state["order"]):
            state["active"] = False
            finish_attempt_if_needed(query.from_user.id, state)
            await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state))
            return

        save_active_session(query.from_user.id, state)
        next_index = state["order"][state["pos"]]
        await query.message.reply_text(
            build_question_text(next_index, state),
            reply_markup=answer_keyboard(test_id, next_index),
            parse_mode="HTML",
        )
        return

    add_session_wrong_answer(state, index, selected)
    record_attempt_wrong_answer(state.get("attempt_id"), query.from_user.id, test_id, index, selected)
    add_all_time_error(query.from_user.id, test_id, index, selected)
    state["awaiting_next"] = True
    save_active_session(query.from_user.id, state)

    await query.edit_message_text(
        build_question_text(index, state, selected_index=selected, show_correct=True),
        reply_markup=next_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))
        return
    if state.get("awaiting_next"):
        await query.answer("Нажми «Следующий»")
        return
    if state.get("test_id") != test_id or state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    record_answer(query.from_user.id, test_id, False, index)
    state["total"] += 1
    add_session_wrong_answer(state, index, None)
    record_attempt_wrong_answer(state.get("attempt_id"), query.from_user.id, test_id, index, None)
    add_all_time_error(query.from_user.id, test_id, index, None)
    state["awaiting_next"] = True
    save_active_session(query.from_user.id, state)

    await query.edit_message_text(
        build_question_text(index, state, selected_index=None, show_correct=True),
        reply_markup=next_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))
        return
    if not state.get("awaiting_next"):
        await query.answer("Следующий вопрос уже открыт")
        return
    if state.get("test_id") != test_id or state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    await query.edit_message_reply_markup(reply_markup=None)

    state["awaiting_next"] = False
    state["pos"] += 1

    if state["pos"] >= len(state["order"]):
        state["active"] = False
        finish_attempt_if_needed(query.from_user.id, state)
        await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state))
        return

    save_active_session(query.from_user.id, state)
    next_index = state["order"][state["pos"]]
    await query.message.reply_text(
        build_question_text(next_index, state),
        reply_markup=answer_keyboard(test_id, next_index),
        parse_mode="HTML",
    )

async def handle_question_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, index_str = query.data.split(":")

    index = int(index_str)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)
    favorite = is_favorite_question(query.from_user.id, test_id, index)
    await query.edit_message_reply_markup(
        reply_markup=question_menu_keyboard(test_id, index, state.get("mode"), is_favorite=favorite)
    )

async def handle_question_continue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, _index_str = query.data.split(":")
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)

    if state.get("test_id") != test_id or not state.get("order") or state.get("pos", 0) >= len(state.get("order", [])):
        await query.edit_message_text("Незавершённой попытки нет.", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))
        return

    state["active"] = True
    index = state["order"][state["pos"]]

    if state.get("awaiting_next"):
        await query.edit_message_text(
            build_question_text(index, state, selected_index=wrong_index_for_question(state, index), show_correct=True),
            reply_markup=next_keyboard(test_id, index),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_pause_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)

    if state.get("test_id") == test_id:
        state["active"] = False
        if state.get("mode") in RESUMABLE_MODES:
            save_active_session(query.from_user.id, state)

    await query.edit_message_text(learn_menu_text(query.from_user.id, test_id), reply_markup=learn_menu_keyboard(test_id))

async def handle_continue_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    data = load_active_session(query.from_user.id, test_id)
    if not data:
        await query.edit_message_text("Незавершённой попытки нет.", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))
        return

    state = restore_state(query.message.chat_id, data)
    index = state["order"][state["pos"]]

    if state.get("awaiting_next"):
        await query.edit_message_text(
            build_question_text(index, state, selected_index=wrong_index_for_question(state, index), show_correct=True),
            reply_markup=next_keyboard(test_id, index),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_finish_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    state = get_state(query.message.chat_id)

    if not state.get("test_id"):
        await query.edit_message_text("Сейчас нет активного режима.", reply_markup=test_select_keyboard())
        return

    state["active"] = False
    state["awaiting_next"] = False
    finish_attempt_if_needed(query.from_user.id, state, finished_by_user=True)
    await query.edit_message_text(result_text(state, query.from_user.id, finished_by_user=True), reply_markup=after_finish_keyboard(query.from_user.id, state))

async def finish_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)

    if not state.get("test_id"):
        await update.message.reply_text("Сейчас нет активного режима.", reply_markup=test_select_keyboard())
        return

    state["active"] = False
    state["awaiting_next"] = False
    finish_attempt_if_needed(update.effective_user.id, state, finished_by_user=True)
    await update.message.reply_text(result_text(state, update.effective_user.id, finished_by_user=True), reply_markup=after_finish_keyboard(update.effective_user.id, state))

async def handle_session_error_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, pos_str = query.data.split(":")
    pos = int(pos_str)

    state = get_state(query.message.chat_id)
    items = state.get("wrong_answers", [])
    if not items:
        items = get_attempt_wrong_answers(query.from_user.id, test_id, state.get("attempt_id"))

    if not items:
        await query.edit_message_text("Ошибок в этом решении нет.", reply_markup=learn_menu_keyboard(test_id))
        return

    pos = max(0, min(pos, len(items) - 1))
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(
        format_session_error_card(test_id, pos, items),
        reply_markup=session_error_keyboard(test_id, pos, len(items)),
        parse_mode="HTML",
    )

async def handle_show_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    state = get_state(query.message.chat_id)

    if state.get("test_id") != test_id:
        await query.edit_message_text("Результат недоступен.", reply_markup=learn_menu_keyboard(test_id))
        return

    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state))

async def handle_repeat_session_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    state = get_state(query.message.chat_id)

    order = []
    seen = set()
    for item in state.get("wrong_answers", []):
        idx = item.get("question_index")
        if idx is not None and idx not in seen:
            order.append(idx)
            seen.add(idx)

    if not order:
        await query.edit_message_text(
            "Ошибок после работы над ошибками нет.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")]]),
        )
        return

    start_quiz_mode(state, query.from_user.id, test_id, "errors", order)
    index = state["order"][state["pos"]]
    await query.edit_message_text(build_question_text(index, state), reply_markup=answer_keyboard(test_id, index), parse_mode="HTML")

async def handle_my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    await query.edit_message_text(my_stats_text(query.from_user.id, test_id), reply_markup=stats_keyboard(test_id))

async def handle_public_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    await query.edit_message_text(public_rating_text(test_id), reply_markup=public_rating_keyboard(test_id))

async def handle_reset_errors_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    await query.edit_message_text("Сбросить ошибки?", reply_markup=reset_errors_keyboard(test_id))

async def handle_reset_errors_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer("Ошибки сброшены")
    _, test_id = query.data.split(":")
    clear_all_time_errors(query.from_user.id, test_id)
    await query.edit_message_text(learn_menu_text(query.from_user.id, test_id), reply_markup=learn_menu_keyboard(test_id))

async def handle_find_question_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)
    state["find_test_id"] = test_id
    state["find_query"] = None
    state["find_result_indices"] = None

    await query.edit_message_text("🔎 Найти вопрос\n\nКак искать?", reply_markup=find_question_keyboard(test_id))

async def handle_find_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)
    state["find_mode"] = "number"
    state["find_test_id"] = test_id

    await query.edit_message_text(
        f"🔢 По номеру\n\nВведи номер вопроса от 1 до {len(get_questions(test_id))}.",
        reply_markup=find_input_keyboard(test_id),
    )

async def handle_find_by_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    state = get_state(query.message.chat_id)
    clear_text_waiting_state(state)
    state["find_mode"] = "text"
    state["find_test_id"] = test_id

    await query.edit_message_text("🔤 По содержанию\n\nВведи слово или фразу из вопроса.", reply_markup=find_input_keyboard(test_id))

async def handle_view_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, index_str = query.data.split(":")
    index = max(0, min(int(index_str), len(get_questions(test_id)) - 1))

    state = get_state(query.message.chat_id)
    state["find_mode"] = None
    state["find_test_id"] = test_id

    await query.edit_message_text(
        preview_question_text(test_id, index),
        reply_markup=question_view_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_find_results_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, page_str = query.data.split(":")
    page = int(page_str)

    state = get_state(query.message.chat_id)
    query_text = state.get("find_query")
    indices = state.get("find_result_indices")

    if not query_text or not indices:
        await query.edit_message_text("Результаты поиска устарели. Запусти поиск заново.", reply_markup=find_question_keyboard(test_id))
        return

    await query.edit_message_text(find_results_text(test_id, query_text, indices, page), reply_markup=find_results_keyboard(test_id, indices, page))

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)
    text = (update.message.text or "").strip()

    start_test_id = state.get("pending_start_from_number_test_id")
    if start_test_id:
        total_questions = len(get_questions(start_test_id))

        if not text.isdigit():
            await update.message.reply_text(f"Введи номер вопроса числом от 1 до {total_questions}.", reply_markup=start_from_number_keyboard(start_test_id))
            return

        start_number = int(text)
        if start_number < 1 or start_number > total_questions:
            await update.message.reply_text(
                f"Номер должен быть от 1 до {total_questions}. Введи номер вопроса ещё раз.",
                reply_markup=start_from_number_keyboard(start_test_id),
            )
            return

        state["pending_start_from_number_test_id"] = None
        order = list(range(start_number - 1, total_questions))
        start_quiz_mode(state, update.effective_user.id, start_test_id, "from_number", order)
        index = state["order"][state["pos"]]

        await update.message.reply_text(build_question_text(index, state), reply_markup=answer_keyboard(start_test_id, index), parse_mode="HTML")
        return

    find_mode = state.get("find_mode")
    test_id = state.get("find_test_id")
    if find_mode not in {"number", "text"} or not test_id:
        return

    total = len(get_questions(test_id))

    if find_mode == "number":
        if not text.isdigit():
            await update.message.reply_text(f"Введи номер вопроса числом от 1 до {total}.", reply_markup=find_input_keyboard(test_id))
            return

        index = int(text) - 1
        if index < 0 or index >= total:
            await update.message.reply_text(
                f"Номер должен быть от 1 до {total}. Введи номер вопроса ещё раз.",
                reply_markup=find_input_keyboard(test_id),
            )
            return

        state["find_mode"] = None
        await update.message.reply_text(preview_question_text(test_id, index), reply_markup=question_view_keyboard(test_id, index), parse_mode="HTML")
        return

    indices = search_question_indices(test_id, text)
    if not indices:
        await update.message.reply_text("Ничего не найдено. Введи другое слово или фразу.", reply_markup=find_input_keyboard(test_id))
        return

    state["find_mode"] = None
    state["find_query"] = text
    state["find_result_indices"] = indices

    await update.message.reply_text(find_results_text(test_id, text, indices, page=0), reply_markup=find_results_keyboard(test_id, indices, page=0))
