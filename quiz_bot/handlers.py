import random
from datetime import datetime

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .config import ADMIN_IDS, BTN_TEST_MENU, RESUMABLE_MODES, TESTS
from .helpers import attempt_percent, format_moscow_datetime, mode_title, seconds_to_text, short_question_text
from .keyboards import (
    after_finish_keyboard,
    answer_keyboard,
    find_input_keyboard,
    find_question_keyboard,
    find_results_keyboard,
    learn_menu_keyboard,
    profile_keyboard,
    next_keyboard,
    public_rating_keyboard,
    question_menu_keyboard,
    question_view_keyboard,
    reset_errors_keyboard,
    session_error_keyboard,
    solve_menu_keyboard,
    start_from_number_keyboard,
    stats_keyboard,
    favorites_keyboard,
    favorite_detail_keyboard,
    profile_errors_keyboard,
    profile_error_detail_keyboard,
    history_keyboard,
    attempt_detail_keyboard,
    attempt_errors_keyboard,
    attempt_error_detail_keyboard,
    result_errors_keyboard,
    test_main_keyboard,
    test_select_keyboard,
)
from .keyboards import find_results_text, preview_question_text, search_question_indices, PAGE_SIZE
from .loader import get_questions
from .quiz import (
    add_session_wrong_answer,
    build_question_text,
    finish_attempt_if_needed,
    format_session_error_card,
    my_stats_text,
    public_rating_text,
    result_text,
    wrong_index_for_question,
)
from .runtime import LAST_START_AT, USER_STATE
from .state import clear_text_waiting_state, delete_active_session, get_state, load_active_session, restore_state, save_active_session, save_question_progress, start_quiz_mode
from .storage import (
    clear_all_time_errors,
    get_all_time_error_indices,
    get_answered_question_count,
    get_attempt_wrong_answers,
    get_attempt,
    get_attempt_order,
    list_attempts,
    list_favorites,
    favorite_count,
    is_favorite,
    set_favorite,
    toggle_favorite,
    list_profile_errors,
    get_profile_error_items,
    error_counts,
    stats_summary,
    db_connect,
    upsert_user,
)

async def setup_bot_commands(app) -> None:
    user_commands = [
        BotCommand("start", "Открыть меню"),
    ]

    admin_commands = [
        BotCommand("start", "Открыть меню"),
        BotCommand("admin", "Админ-панель"),
    ]

    await app.bot.set_my_commands(user_commands)

    for admin_id in ADMIN_IDS:
        try:
            await app.bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            pass

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
    summary = stats_summary(user.id, test_id)
    errors = summary.get("errors") or {}

    answered_questions = int(summary.get("answered_questions") or 0)
    best = summary.get("best")
    latest = summary.get("latest")
    overall = summary.get("overall") or {}
    best_line = f"{_safe_percent(best.get('correct'), best.get('answered'))}%" if best else "пока нет"
    last_line = f"{_safe_percent(latest.get('correct'), latest.get('answered'))}%" if latest else "пока нет"

    return (
        f"👤 Профиль\n\n"
        f"{_profile_display_name(user)}\n"
        f"{_profile_username(user)}\n\n"
        f"📚 Тест: {title}\n\n"
        f"📌 Кратко:\n"
        f"Решено вопросов: {answered_questions} из {total_questions}\n"
        f"Ошибок: {int(errors.get('unresolved') or 0)}\n"
        f"Избранных: {int(summary.get('favorites') or 0)}\n"
        f"Попыток: {int(overall.get('attempts') or 0)}\n\n"
        f"🏆 Лучший результат: {best_line}\n"
        f"🕓 Последняя попытка: {last_line}"
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


def _question_options_text(test_id: str, question_index: int, wrong_index: int | None = None, *, show_wrong: bool = True) -> str:
    q = get_questions(test_id)[question_index]
    correct_index = int(q["correct_index"])
    lines = [f"<b>{q['question']}</b>", "", "···"]
    from .config import LETTERS
    import html
    for i, option in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""
        if i == correct_index:
            prefix = "✅ "
        elif show_wrong and wrong_index is not None and i == wrong_index and i != correct_index:
            prefix = "❌ "
        lines.append(f"{prefix}{letter}) {html.escape(str(option))}")
    if show_wrong and wrong_index is None:
        lines.append("")
        lines.append("👁 Показан ответ")
    return "\n".join(lines)


def _short_question_line(test_id: str, index: int) -> str:
    return short_question_text(get_questions(test_id)[index]["question"])


async def handle_profile_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    parts = query.data.split(":")
    test_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    items, total = list_favorites(query.from_user.id, test_id, page)
    title = TESTS[test_id]["title"]
    start = page * PAGE_SIZE
    lines = ["⭐ Избранные", "", title, "", f"Всего: {total}"]
    if total:
        lines.append(f"Показаны: {start + 1}–{start + len(items)} из {total}")
        lines.append("")
        for i, idx in enumerate(items, start=1):
            lines.append(f"{start + i}. Вопрос {idx + 1}")
            lines.append(_short_question_line(test_id, idx))
            lines.append("")
    else:
        lines.extend(["", "Избранных вопросов пока нет."])
    await query.edit_message_text("\n".join(lines).strip(), reply_markup=favorites_keyboard(test_id, items, page, total))


async def handle_favorite_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, pos_str = query.data.split(":")
    pos = int(pos_str)
    items, total = list_favorites(query.from_user.id, test_id, page=0, page_size=100000)
    if not items:
        await query.edit_message_text("Избранных вопросов пока нет.", reply_markup=profile_keyboard(test_id))
        return
    pos = max(0, min(pos, len(items) - 1))
    idx = items[pos]
    text = (
        f"⭐ Избранный вопрос\n\n"
        f"📚 {TESTS[test_id]['title']}\n"
        f"Вопрос {idx + 1}\n\n"
        f"{_question_options_text(test_id, idx, None, show_wrong=False)}"
    )
    await query.edit_message_text(text, reply_markup=favorite_detail_keyboard(test_id, pos, total, idx), parse_mode="HTML")


async def handle_profile_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    parts = query.data.split(":")
    test_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    items, total, counts = list_profile_errors(query.from_user.id, test_id, page)
    title = TESTS[test_id]["title"]
    start = page * PAGE_SIZE
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
        lines.extend(["", f"Показаны: {start + 1}–{start + len(items)} из {total}", ""])
        for i, item in enumerate(items, start=1):
            idx = int(item["question_index"])
            status = "✅ Исправлена" if int(item.get("is_resolved") or 0) else "❌ Не исправлена"
            lines.append(f"{start + i}. Вопрос {idx + 1}")
            lines.append(_short_question_line(test_id, idx))
            lines.append(f"Дата ошибки: {format_moscow_datetime(item.get('last_wrong_at'))}")
            lines.append(f"Статус: {status}")
            lines.append("")
    else:
        lines.extend(["", "Ошибок пока нет."])
    await query.edit_message_text("\n".join(lines).strip(), reply_markup=profile_errors_keyboard(test_id, items, page, total))


async def handle_profile_error_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, pos_str = query.data.split(":")
    pos = int(pos_str)
    items = get_profile_error_items(query.from_user.id, test_id)
    if not items:
        await query.edit_message_text("Ошибок пока нет.", reply_markup=profile_keyboard(test_id))
        return
    pos = max(0, min(pos, len(items) - 1))
    item = items[pos]
    idx = int(item["question_index"])
    status = "✅ Исправлена" if int(item.get("is_resolved") or 0) else "❌ Не исправлена"
    text = (
        f"🧠 Ошибка\n\n"
        f"📚 {TESTS[test_id]['title']}\n"
        f"Вопрос {idx + 1}\n\n"
        f"Дата ошибки: {format_moscow_datetime(item.get('last_wrong_at'))}\n"
        f"Статус: {status}\n\n"
        f"{_question_options_text(test_id, idx, item.get('last_wrong_answer_index'), show_wrong=True)}"
    )
    await query.edit_message_text(
        text,
        reply_markup=profile_error_detail_keyboard(test_id, pos, len(items), idx, is_favorite(query.from_user.id, test_id, idx)),
        parse_mode="HTML",
    )


async def handle_profile_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    parts = query.data.split(":")
    test_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 else 0
    attempts, total = list_attempts(query.from_user.id, test_id, page)
    start = page * PAGE_SIZE
    lines = ["📜 История попыток", "", TESTS[test_id]["title"]]
    if total:
        lines.extend(["", f"Показаны: {start + 1}–{start + len(attempts)} из {total}", ""])
        for i, a in enumerate(attempts, start=1):
            answered = int(a.get("answered") or 0)
            correct = int(a.get("correct") or 0)
            wrong = max(0, answered - correct)
            percent = _safe_percent(correct, answered)
            lines.append(f"{start + i}. {mode_title(a.get('mode'))} · {percent}%")
            lines.append(f"{format_moscow_datetime(a.get('finished_at'))} · {answered} вопроса · {wrong} ошибок")
            lines.append("")
    else:
        lines.extend(["", "Завершённых попыток пока нет."])
    await query.edit_message_text("\n".join(lines).strip(), reply_markup=history_keyboard(test_id, attempts, page, total))


async def handle_history_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, attempt_id_str, page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Попытка не найдена.", reply_markup=profile_keyboard(test_id))
        return
    wrongs = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    answered = int(attempt.get("answered") or 0)
    correct = int(attempt.get("correct") or 0)
    text = (
        f"📄 Попытка #{attempt_id}\n\n"
        f"📚 {TESTS[test_id]['title']}\n"
        f"🎮 {mode_title(attempt.get('mode'))}\n"
        f"🕓 {format_moscow_datetime(attempt.get('finished_at'))}\n"
        f"⏱ {seconds_to_text(attempt.get('duration_seconds'))}\n\n"
        f"📊 Результат:\n"
        f"🏆 {_safe_percent(correct, answered)}%\n"
        f"✅ Правильно: {correct}\n"
        f"❌ Ошибок: {max(0, answered - correct)}\n"
        f"📝 Решено: {answered}"
    )
    await query.edit_message_text(text, reply_markup=attempt_detail_keyboard(test_id, attempt_id, page, len(wrongs)))


async def handle_attempt_errors_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, attempt_id_str, page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Попытка не найдена.")
        return
    test_id = attempt["test_id"]
    all_items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    total = len(all_items)
    start = page * PAGE_SIZE
    items = all_items[start:start + PAGE_SIZE]
    lines = ["🧠 Ошибки попытки", "", f"📄 Попытка #{attempt_id}", TESTS[test_id]["title"], "", f"Ошибок: {total}"]
    if items:
        lines.append("")
        for i, item in enumerate(items, start=1):
            idx = int(item["question_index"])
            lines.append(f"{start + i}. Вопрос {idx + 1}")
            lines.append(_short_question_line(test_id, idx))
            lines.append("")
    else:
        lines.extend(["", "Ошибок в этой попытке нет."])
    await query.edit_message_text("\n".join(lines).strip(), reply_markup=attempt_errors_keyboard(test_id, attempt_id, items, page, total))


async def handle_attempt_error_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, attempt_id_str, pos_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    pos = int(pos_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Попытка не найдена.")
        return
    test_id = attempt["test_id"]
    items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    if not items:
        await query.edit_message_text("Ошибок в этой попытке нет.")
        return
    pos = max(0, min(pos, len(items) - 1))
    item = items[pos]
    idx = int(item["question_index"])
    text = (
        f"🧠 Ошибка попытки\n\n"
        f"📚 {TESTS[test_id]['title']}\n"
        f"📄 Попытка #{attempt_id}\n"
        f"Вопрос {idx + 1}\n\n"
        f"{_question_options_text(test_id, idx, item.get('wrong_answer_index'), show_wrong=True)}"
    )
    await query.edit_message_text(
        text,
        reply_markup=attempt_error_detail_keyboard(test_id, attempt_id, pos, len(items), idx, is_favorite(query.from_user.id, test_id, idx)),
        parse_mode="HTML",
    )


async def handle_repeat_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, attempt_id_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Попытка не найдена.")
        return
    answered = int(attempt.get("answered") or 0)
    order = get_attempt_order(attempt_id)[:answered]
    if not order:
        await query.answer("Для старых попыток повтор может быть недоступен", show_alert=True)
        return
    test_id = attempt["test_id"]
    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, "repeat_attempt", order)
    index = state["order"][state["pos"]]
    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index, attempt_id=state.get("attempt_id"), user_id=query.from_user.id),
        parse_mode="HTML",
    )


async def handle_result_errors_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, attempt_id_str, page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Результат недоступен.")
        return
    test_id = attempt["test_id"]
    all_items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    total = len(all_items)
    start = page * PAGE_SIZE
    items = all_items[start:start + PAGE_SIZE]
    lines = ["🧠 Ошибки", "", f"📚 {TESTS[test_id]['title']}", f"📄 Попытка #{attempt_id}", "", f"Ошибок: {total}"]
    if items:
        lines.append("")
        for i, item in enumerate(items, start=1):
            idx = int(item["question_index"])
            lines.append(f"{start + i}. Вопрос {idx + 1}")
            lines.append(_short_question_line(test_id, idx))
            lines.append("")
    else:
        lines.extend(["", "Ошибок в этом прохождении нет."])
    await query.edit_message_text("\n".join(lines).strip(), reply_markup=result_errors_keyboard(attempt_id, items, page, total))


async def handle_result_error_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, attempt_id_str, pos_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    pos = int(pos_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Результат недоступен.")
        return
    test_id = attempt["test_id"]
    items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    if not items:
        await query.edit_message_text("Ошибок в этом прохождении нет.")
        return
    pos = max(0, min(pos, len(items) - 1))
    item = items[pos]
    idx = int(item["question_index"])
    text = (
        f"🧠 Ошибка\n\n"
        f"📚 {TESTS[test_id]['title']}\n"
        f"📄 Попытка #{attempt_id}\n"
        f"Вопрос {idx + 1}\n\n"
        f"{_question_options_text(test_id, idx, item.get('wrong_answer_index'), show_wrong=True)}"
    )
    await query.edit_message_text(text, reply_markup=session_error_keyboard(test_id, pos, len(items), attempt_id=attempt_id), parse_mode="HTML")


async def handle_show_result_attempt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, attempt_id_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    attempt = get_attempt(attempt_id)
    if not attempt or int(attempt.get("user_id") or 0) != query.from_user.id:
        await query.edit_message_text("Результат недоступен.")
        return
    test_id = attempt["test_id"]
    answered = int(attempt.get("answered") or 0)
    correct = int(attempt.get("correct") or 0)
    fake_state = {
        "test_id": test_id,
        "mode": attempt.get("mode"),
        "total": answered,
        "correct": correct,
        "order": get_attempt_order(attempt_id) or list(range(answered)),
        "wrong_answers": get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id),
        "attempt_id": attempt_id,
        "duration_seconds": attempt.get("duration_seconds"),
    }
    await query.edit_message_text(result_text(fake_state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, fake_state), parse_mode="HTML")


async def handle_toggle_favorite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    value = toggle_favorite(query.from_user.id, test_id, index)
    await query.answer("Добавлено в избранное" if value else "Убрано из избранного")

    state = get_state(query.message.chat_id)
    try:
        if state.get("test_id") == test_id and state.get("active") and state.get("order") and state.get("pos", 0) < len(state.get("order", [])) and state["order"][state["pos"]] == index:
            if state.get("awaiting_next"):
                await query.edit_message_reply_markup(reply_markup=next_keyboard(test_id, index, user_id=query.from_user.id))
            else:
                await query.edit_message_reply_markup(reply_markup=answer_keyboard(test_id, index, user_id=query.from_user.id))
        else:
            rows = []
            for row in (query.message.reply_markup.inline_keyboard if query.message.reply_markup else []):
                new_row = []
                for btn in row:
                    if btn.callback_data == query.data:
                        new_row.append(InlineKeyboardButton("⭐ Убрать из избранного" if value else "⭐ В избранное", callback_data=query.data))
                    else:
                        new_row.append(btn)
                rows.append(new_row)
            if rows:
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))
    except Exception:
        pass

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
        reply_markup=answer_keyboard(test_id, index, user_id=query.from_user.id),
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
        reply_markup=answer_keyboard(test_id, index, user_id=query.from_user.id),
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
        reply_markup=answer_keyboard(test_id, index, user_id=query.from_user.id),
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

    state["total"] += 1

    if is_correct:
        state["correct"] += 1
        answered_text = build_question_text(index, state, selected_index=selected, show_correct=True)
        state["pos"] += 1

        if state["pos"] >= len(state["order"]):
            state["active"] = False
            save_question_progress(query.from_user.id, state, index, True, save_session=False)
            finish_attempt_if_needed(query.from_user.id, state)
            await query.edit_message_text(
                answered_text,
                parse_mode="HTML",
            )
            await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state), parse_mode="HTML")
            return

        save_question_progress(query.from_user.id, state, index, True)
        next_index = state["order"][state["pos"]]
        await query.edit_message_text(
            answered_text,
            parse_mode="HTML",
        )
        await query.message.reply_text(
            build_question_text(next_index, state),
            reply_markup=answer_keyboard(test_id, next_index, user_id=query.from_user.id),
            parse_mode="HTML",
        )
        return

    add_session_wrong_answer(state, index, selected)
    state["awaiting_next"] = True
    save_question_progress(query.from_user.id, state, index, False, selected)

    await query.edit_message_text(
        build_question_text(index, state, selected_index=selected, show_correct=True),
        reply_markup=next_keyboard(test_id, index, user_id=query.from_user.id),
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

    state["total"] += 1
    add_session_wrong_answer(state, index, None)
    state["awaiting_next"] = True
    save_question_progress(query.from_user.id, state, index, False, None)

    await query.edit_message_text(
        build_question_text(index, state, selected_index=None, show_correct=True),
        reply_markup=next_keyboard(test_id, index, user_id=query.from_user.id),
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
        await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state), parse_mode="HTML")
        return

    save_active_session(query.from_user.id, state)
    next_index = state["order"][state["pos"]]
    await query.message.reply_text(
        build_question_text(next_index, state),
        reply_markup=answer_keyboard(test_id, next_index, user_id=query.from_user.id),
        parse_mode="HTML",
    )

async def handle_question_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, index_str = query.data.split(":")

    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id)
    await query.edit_message_reply_markup(
        reply_markup=question_menu_keyboard(test_id, int(index_str), state.get("mode"))
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
            reply_markup=next_keyboard(test_id, index, user_id=query.from_user.id),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index, user_id=query.from_user.id),
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
            reply_markup=next_keyboard(test_id, index, user_id=query.from_user.id),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index, user_id=query.from_user.id),
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
    await query.edit_message_text(result_text(state, query.from_user.id, finished_by_user=True), reply_markup=after_finish_keyboard(query.from_user.id, state), parse_mode="HTML")

async def finish_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)

    if not state.get("test_id"):
        await update.message.reply_text("Сейчас нет активного режима.", reply_markup=test_select_keyboard())
        return

    state["active"] = False
    state["awaiting_next"] = False
    finish_attempt_if_needed(update.effective_user.id, state, finished_by_user=True)
    await update.message.reply_text(result_text(state, update.effective_user.id, finished_by_user=True), reply_markup=after_finish_keyboard(update.effective_user.id, state), parse_mode="HTML")

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
    await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state), parse_mode="HTML")

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
    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index, attempt_id=state.get("attempt_id"), user_id=query.from_user.id),
        parse_mode="HTML",
    )

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

        await update.message.reply_text(build_question_text(index, state), reply_markup=answer_keyboard(start_test_id, index, user_id=update.effective_user.id), parse_mode="HTML")
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
