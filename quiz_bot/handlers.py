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
    learn_menu_keyboard,
    profile_keyboard,
    profile_attempt_detail_keyboard,
    profile_history_keyboard,
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
    get_user_attempt_detail,
    get_user_attempt_history,
    db_connect,
    record_answer,
    record_attempt_wrong_answer,
    remove_all_time_error,
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
        f"Ошибок для разбора: {errors_count}\n"
        f"Попыток всего: {attempts_total}\n\n"
        f"🏆 Лучший результат: {best_line}\n"
        f"🕓 Последняя попытка: {last_line}"
    )




def _format_datetime_for_profile(value) -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")

    text = str(value).strip()
    if not text:
        return "—"

    normalized = text.replace("T", " ").replace("Z", "")
    if "+" in normalized:
        normalized = normalized.split("+", 1)[0].strip()
    if "." in normalized:
        normalized = normalized.split(".", 1)[0].strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(normalized, fmt).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            pass

    return text[:16]


def _attempt_percent(attempt: dict) -> int:
    answered = int(attempt.get("answered") or 0)
    correct = int(attempt.get("correct") or 0)
    if answered <= 0:
        return 0
    return round(correct / answered * 100)


def _mode_label(mode: str | None) -> str:
    emoji = {
        "normal": "📝",
        "random": "🎲",
        "reverse": "↩️",
        "from_number": "🎳",
        "mini": "⚡",
        "errors": "🧠",
    }.get(mode or "", "📝")
    return f"{emoji} {mode_title(mode)}"


def profile_history_text(user_id: int, test_id: str, page: int = 0) -> tuple[str, list[dict], int]:
    title = TESTS[test_id]["title"]
    page_size = 10
    attempts, total = get_user_attempt_history(user_id, test_id, page=page, page_size=page_size)

    if not attempts:
        return (
            f"📜 История попыток\n\n"
            f"{title}\n\n"
            f"Пока нет завершённых попыток.",
            attempts,
            total,
        )

    start = page * page_size
    end = start + len(attempts)
    lines = [
        "📜 История попыток",
        "",
        title,
        "",
        f"Показаны: {start + 1}–{end} из {total}",
        "",
    ]

    for i, attempt in enumerate(attempts, start=start + 1):
        percent = _attempt_percent(attempt)
        answered = int(attempt.get("answered") or 0)
        correct = int(attempt.get("correct") or 0)
        wrong_count = int(attempt.get("wrong_count") or max(0, answered - correct))
        date = _format_datetime_for_profile(attempt.get("finished_at") or attempt.get("started_at"))

        lines.extend([
            f"{i}. {_mode_label(attempt.get('mode'))}",
            date,
            f"Результат: {percent}%",
            f"Вопросов: {answered}",
            f"Ошибок: {wrong_count}",
            "",
        ])

    lines.append("Нажми номер попытки, чтобы открыть подробности.")
    return "\n".join(lines).rstrip(), attempts, total


def profile_attempt_detail_text(user_id: int, test_id: str, attempt_id: int) -> str:
    title = TESTS[test_id]["title"]
    attempt = get_user_attempt_detail(user_id, test_id, attempt_id)
    if not attempt:
        return (
            f"📄 Попытка\n\n"
            f"{title}\n\n"
            f"Попытка не найдена или уже недоступна."
        )

    answered = int(attempt.get("answered") or 0)
    correct = int(attempt.get("correct") or 0)
    wrong_count = int(attempt.get("wrong_count") or max(0, answered - correct))
    percent = _attempt_percent(attempt)
    date = _format_datetime_for_profile(attempt.get("finished_at") or attempt.get("started_at"))
    duration = seconds_to_text(attempt.get("duration_seconds"))

    wrong_answers = attempt.get("wrong_answers") or []
    wrong_numbers = []
    for item in wrong_answers:
        try:
            wrong_numbers.append(str(int(item["question_index"]) + 1))
        except (TypeError, ValueError, KeyError):
            pass

    lines = [
        f"📄 Попытка #{attempt_id}",
        "",
        f"📚 {title}",
        f"🎮 Режим: {mode_title(attempt.get('mode'))}",
        f"🕓 Дата: {date}",
        f"⏱ Время: {duration}",
        "",
        "📊 Результат",
        f"🏆 {percent}%",
        f"✅ Правильно: {correct}",
        f"❌ Ошибок: {wrong_count}",
        f"📝 Решено: {answered}",
    ]

    if int(attempt.get("finished_by_user") or 0):
        lines.append("⏹ Завершена вручную")

    lines.append("")
    if wrong_numbers:
        preview = ", ".join(wrong_numbers[:30])
        if len(wrong_numbers) > 30:
            preview += f" и ещё {len(wrong_numbers) - 30}"
        lines.append("🧠 Ошибки в этой попытке:")
        lines.append(preview)
    else:
        lines.append("🧠 Ошибок в этой попытке нет.")

    return "\n".join(lines)

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


async def handle_profile_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    action, test_id = query.data.split(":", 1)

    titles = {
        "profile_favorites": "⭐ Избранные вопросы",
        "profile_errors": "🧠 Ошибки",
    }
    title = titles.get(action, "Раздел профиля")

    await query.edit_message_text(
        f"{title}\n\nРаздел скоро будет добавлен.",
        reply_markup=profile_keyboard(test_id),
    )

async def handle_profile_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    parts = query.data.split(":")
    test_id = parts[1]
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    text, attempts, total = profile_history_text(query.from_user.id, test_id, page)
    await query.edit_message_text(
        text,
        reply_markup=profile_history_keyboard(test_id, attempts, page, total),
    )


async def handle_profile_attempt_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, attempt_id_str, page_str = query.data.split(":")
    attempt_id = int(attempt_id_str)
    page = int(page_str) if page_str.isdigit() else 0

    await query.edit_message_text(
        profile_attempt_detail_text(query.from_user.id, test_id, attempt_id),
        reply_markup=profile_attempt_detail_keyboard(test_id, page),
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
