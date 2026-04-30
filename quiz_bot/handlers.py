import random
from datetime import datetime

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .config import BTN_TEST_MENU, RESUMABLE_MODES, TESTS
from .helpers import mode_title
from .keyboards import (
    after_finish_keyboard,
    answer_keyboard,
    find_input_keyboard,
    find_question_keyboard,
    find_results_keyboard,
    learn_menu_keyboard,
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
from .state import (
    clear_text_waiting_state,
    delete_active_session,
    delete_runtime_session,
    get_state,
    load_active_session,
    load_latest_runtime_session,
    load_runtime_session_for_question,
    load_session_by_attempt,
    restore_state,
    save_active_session,
    save_question_progress,
    start_quiz_mode,
)
from .storage import (
    clear_all_time_errors,
    get_all_time_error_indices,
    get_attempt_wrong_answers,
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
    if state.get("test_id"):
        if state.get("mode") in RESUMABLE_MODES:
            delete_active_session(update.effective_user.id, state.get("test_id"))
        delete_runtime_session(update.effective_user.id, state.get("test_id"))
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


def _parse_attempt_id(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_answer_callback(data: str) -> tuple[int | None, str, int, int]:
    parts = data.split(":")
    if len(parts) == 5:
        return _parse_attempt_id(parts[1]), parts[2], int(parts[3]), int(parts[4])
    return None, parts[1], int(parts[2]), int(parts[3])


def _parse_question_callback(data: str) -> tuple[int | None, str, int]:
    parts = data.split(":")
    if len(parts) == 4:
        return _parse_attempt_id(parts[1]), parts[2], int(parts[3])
    return None, parts[1], int(parts[2])


def _parse_pause_callback(data: str) -> tuple[int | None, str]:
    parts = data.split(":")
    if len(parts) == 3:
        return _parse_attempt_id(parts[1]), parts[2]
    return None, parts[1]


def _parse_finish_callback(data: str) -> int | None:
    parts = data.split(":")
    if len(parts) == 2:
        return _parse_attempt_id(parts[1])
    return None


def get_state_or_restore(
    chat_id: int,
    user_id: int,
    test_id: str | None = None,
    question_index: int | None = None,
    attempt_id: int | None = None,
) -> dict:
    state = get_state(chat_id)

    if attempt_id is not None:
        if state.get("attempt_id") == attempt_id:
            return state

        data = load_session_by_attempt(user_id, attempt_id)
        if data:
            return restore_state(chat_id, data)

        return state

    if test_id and state.get("active") and state.get("test_id") == test_id:
        if question_index is None:
            return state
        order = state.get("order") or []
        pos = int(state.get("pos", 0))
        if pos < len(order) and int(order[pos]) == question_index:
            return state

    if test_id and question_index is not None:
        data = load_runtime_session_for_question(user_id, test_id, question_index)
        if data:
            return restore_state(chat_id, data)

    if test_id and not state.get("active"):
        data = load_active_session(user_id, test_id)
        if data:
            return restore_state(chat_id, data)

        data = load_latest_runtime_session(user_id, test_id)
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
        reply_markup=answer_keyboard(test_id, index, state.get("attempt_id")),
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
        reply_markup=answer_keyboard(test_id, index, state.get("attempt_id")),
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
        reply_markup=answer_keyboard(test_id, index, state.get("attempt_id")),
        parse_mode="HTML",
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    attempt_id, test_id, index, selected = _parse_answer_callback(query.data)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id, index, attempt_id)

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

        await query.edit_message_text(
            build_question_text(index, state, selected_index=selected, show_correct=True),
            parse_mode="HTML",
        )

        state["pos"] += 1
        is_finished = state["pos"] >= len(state["order"])

        if is_finished:
            state["active"] = False

        save_question_progress(
            query.from_user.id,
            state,
            index,
            True,
            save_session=not is_finished,
        )

        if is_finished:
            finish_attempt_if_needed(query.from_user.id, state)
            await query.message.reply_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state))
            return

        next_index = state["order"][state["pos"]]
        await query.message.reply_text(
            build_question_text(next_index, state),
            reply_markup=answer_keyboard(test_id, next_index, state.get("attempt_id")),
            parse_mode="HTML",
        )
        return

    add_session_wrong_answer(state, index, selected)
    state["awaiting_next"] = True
    save_question_progress(query.from_user.id, state, index, False, selected)

    await query.edit_message_text(
        build_question_text(index, state, selected_index=selected, show_correct=True),
        reply_markup=next_keyboard(test_id, index, state.get("attempt_id")),
        parse_mode="HTML",
    )

async def handle_show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    attempt_id, test_id, index = _parse_question_callback(query.data)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id, index, attempt_id)

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
        reply_markup=next_keyboard(test_id, index, state.get("attempt_id")),
        parse_mode="HTML",
    )

async def handle_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    attempt_id, test_id, index = _parse_question_callback(query.data)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id, index, attempt_id)

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
        reply_markup=answer_keyboard(test_id, next_index, state.get("attempt_id")),
        parse_mode="HTML",
    )

async def handle_question_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    attempt_id, test_id, index = _parse_question_callback(query.data)

    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id, index, attempt_id)
    await query.edit_message_reply_markup(
        reply_markup=question_menu_keyboard(test_id, index, state.get("mode"), state.get("attempt_id"))
    )

async def handle_question_continue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    attempt_id, test_id, index_from_callback = _parse_question_callback(query.data)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id, index_from_callback, attempt_id)

    if state.get("test_id") != test_id or not state.get("order") or state.get("pos", 0) >= len(state.get("order", [])):
        await query.edit_message_text("Незавершённой попытки нет.", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))
        return

    state["active"] = True
    index = state["order"][state["pos"]]

    if state.get("awaiting_next"):
        await query.edit_message_text(
            build_question_text(index, state, selected_index=wrong_index_for_question(state, index), show_correct=True),
            reply_markup=next_keyboard(test_id, index, state.get("attempt_id")),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index, state.get("attempt_id")),
        parse_mode="HTML",
    )

async def handle_pause_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    attempt_id, test_id = _parse_pause_callback(query.data)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, test_id, attempt_id=attempt_id)
    if state.get("test_id") != test_id:
        data = load_latest_runtime_session(query.from_user.id, test_id)
        if data:
            state = restore_state(query.message.chat_id, data)
        else:
            data = load_active_session(query.from_user.id, test_id)
            if data:
                state = restore_state(query.message.chat_id, data)

    if state.get("test_id") == test_id:
        mode = state.get("mode")
        state["active"] = False
        if mode in RESUMABLE_MODES:
            delete_runtime_session(query.from_user.id, test_id, mode)
            save_active_session(query.from_user.id, state)
        else:
            delete_runtime_session(query.from_user.id, test_id, mode)

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
            reply_markup=next_keyboard(test_id, index, state.get("attempt_id")),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index, state.get("attempt_id")),
        parse_mode="HTML",
    )

async def handle_finish_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    attempt_id = _parse_finish_callback(query.data)
    state = get_state_or_restore(query.message.chat_id, query.from_user.id, attempt_id=attempt_id) if attempt_id is not None else get_state(query.message.chat_id)

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
    await query.edit_message_text(build_question_text(index, state), reply_markup=answer_keyboard(test_id, index, state.get("attempt_id")), parse_mode="HTML")

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

        await update.message.reply_text(build_question_text(index, state), reply_markup=answer_keyboard(start_test_id, index, state.get("attempt_id")), parse_mode="HTML")
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
