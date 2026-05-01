from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from .config import (
    BTN_BACK,
    BTN_CONTINUE,
    BTN_FINISH,
    BTN_MENU,
    BTN_NEXT,
    BTN_SAVE_EXIT,
    BTN_SHOW_ANSWER,
    BTN_TEST_MENU,
    FIND_PAGE_SIZE,
    LETTERS,
    RESUMABLE_MODES,
    TESTS,
)
from .access import can_view_test, is_code_locked_for_user
from .loader import get_questions, get_subject_info, get_subjects, get_tests_for_subject, test_subject_id
from .quiz import build_question_text
from .state import active_session_button_text
from .storage import is_favorite

def subject_select_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for subject_id, info in get_subjects():
        visible_tests = [
            test_id
            for test_id, _ in get_tests_for_subject(subject_id)
            if can_view_test(user_id, test_id)
        ]
        if not visible_tests:
            continue

        emoji = info.get("emoji", "📚")
        title = info.get("title", subject_id)
        rows.append([
            InlineKeyboardButton(
                f"{emoji} {title}",
                callback_data=f"subject_menu:{subject_id}",
            )
        ])

    if not rows:
        rows.append([InlineKeyboardButton("Пока нет доступных предметов", callback_data="noop")])
    return InlineKeyboardMarkup(rows)


def subject_tests_keyboard(subject_id: str, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for test_id, info in get_tests_for_subject(subject_id):
        if not can_view_test(user_id, test_id):
            continue

        is_locked = is_code_locked_for_user(user_id, test_id)
        callback = f"locked_test:{test_id}" if is_locked else f"test_menu:{test_id}"
        title = f"🔒 {info['title']}" if is_locked else info["title"]
        rows.append([
            InlineKeyboardButton(
                f"{title} — {len(get_questions(test_id))} вопросов",
                callback_data=callback,
            )
        ])

    if not rows:
        rows.append([InlineKeyboardButton("Нет доступных тестов", callback_data="noop")])

    rows.append([InlineKeyboardButton("⬅️ К предметам", callback_data="tests:menu")])
    return InlineKeyboardMarkup(rows)


def locked_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    subject_id = test_subject_id(test_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Ввести код", callback_data=f"enter_access_code:{test_id}")],
        [InlineKeyboardButton("⬅️ К тестам предмета", callback_data=f"subject_menu:{subject_id}")],
    ])


def test_select_keyboard(user_id: int | None = None) -> InlineKeyboardMarkup:
    return subject_select_keyboard(user_id or 0)

def test_main_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Учить", callback_data=f"learn_menu:{test_id}")],
        [InlineKeyboardButton("👤 Профиль", callback_data=f"my_profile:{test_id}")],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data=f"public_rating:{test_id}")],
        [InlineKeyboardButton(BTN_BACK, callback_data=f"subject_menu:{test_subject_id(test_id)}")],
    ])



def profile_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика", callback_data=f"my_stats:{test_id}")],
        [InlineKeyboardButton("⭐ Избранные вопросы", callback_data=f"profile_favorites:{test_id}")],
        [InlineKeyboardButton("🧠 Ошибки", callback_data=f"profile_errors:{test_id}")],
        [InlineKeyboardButton("📜 История попыток", callback_data=f"profile_history:{test_id}")],
        [InlineKeyboardButton(BTN_BACK, callback_data=f"test_menu:{test_id}")],
    ])


def profile_section_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(BTN_BACK, callback_data=f"my_profile:{test_id}")]])

def learn_menu_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Решать", callback_data=f"solve_menu:{test_id}")],
        [InlineKeyboardButton("⚡ Тренировка", callback_data=f"mini_start:{test_id}:10")],
        [InlineKeyboardButton("🧠 Разобрать ошибки", callback_data=f"errors_solve:{test_id}")],
        [InlineKeyboardButton("🔎 Найти вопрос", callback_data=f"find_question:{test_id}")],
        [InlineKeyboardButton("🗑 Сбросить ошибки", callback_data=f"reset_errors_confirm:{test_id}")],
        [InlineKeyboardButton(BTN_BACK, callback_data=f"test_menu:{test_id}")],
    ])

def solve_menu_keyboard(test_id: str, user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    if user_id is not None:
        text = active_session_button_text(user_id, test_id)
        if text:
            rows.append([InlineKeyboardButton(f"▶️ {text}", callback_data=f"continue_session:{test_id}")])

    rows.extend([
        [
            InlineKeyboardButton("📋 По порядку", callback_data=f"start:{test_id}:normal"),
            InlineKeyboardButton("🎲 Вразброс", callback_data=f"start:{test_id}:random"),
        ],
        [
            InlineKeyboardButton("👨🏿‍🦳 С конца", callback_data=f"start:{test_id}:reverse"),
            InlineKeyboardButton("🎳 С номера", callback_data=f"start_from_number:{test_id}"),
        ],
        [InlineKeyboardButton(BTN_BACK, callback_data=f"learn_menu:{test_id}")],
    ])
    return InlineKeyboardMarkup(rows)

def _favorite_button(user_id: int | None, test_id: str, index: int) -> InlineKeyboardButton:
    if user_id is not None and is_favorite(user_id, test_id, index):
        text = "⭐ Убрать"
    else:
        text = "⭐ В избранное"
    return InlineKeyboardButton(text, callback_data=f"toggle_favorite:{test_id}:{index}")


def answer_keyboard(test_id: str, index: int, attempt_id: int | None = None, user_id: int | None = None) -> InlineKeyboardMarkup:
    q = get_questions(test_id)[index]
    buttons = []
    for i, _ in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        if attempt_id is not None:
            callback_data = f"answer:{attempt_id}:{test_id}:{index}:{i}"
        else:
            callback_data = f"answer:{test_id}:{index}:{i}"
        buttons.append(InlineKeyboardButton(f"{letter}", callback_data=callback_data))

    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if attempt_id is not None:
        rows.append([InlineKeyboardButton(BTN_SHOW_ANSWER, callback_data=f"show_answer:{attempt_id}:{test_id}:{index}")])
        rows.append([_favorite_button(user_id, test_id, index), InlineKeyboardButton(BTN_MENU, callback_data=f"question_menu:{attempt_id}:{test_id}:{index}")])
    else:
        rows.append([InlineKeyboardButton(BTN_SHOW_ANSWER, callback_data=f"show_answer:{test_id}:{index}")])
        rows.append([_favorite_button(user_id, test_id, index), InlineKeyboardButton(BTN_MENU, callback_data=f"question_menu:{test_id}:{index}")])
    return InlineKeyboardMarkup(rows)


def next_keyboard(test_id: str, index: int, attempt_id: int | None = None, user_id: int | None = None) -> InlineKeyboardMarkup:
    if attempt_id is not None:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(BTN_NEXT, callback_data=f"next_question:{attempt_id}:{test_id}:{index}")],
            [_favorite_button(user_id, test_id, index), InlineKeyboardButton(BTN_MENU, callback_data=f"question_menu:{attempt_id}:{test_id}:{index}")],
        ])

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_NEXT, callback_data=f"next_question:{test_id}:{index}")],
        [_favorite_button(user_id, test_id, index), InlineKeyboardButton(BTN_MENU, callback_data=f"question_menu:{test_id}:{index}")],
    ])


def question_menu_keyboard(test_id: str, index: int, mode: str | None = None, attempt_id: int | None = None) -> InlineKeyboardMarkup:
    if attempt_id is not None:
        continue_cb = f"question_continue:{attempt_id}:{test_id}:{index}"
        pause_cb = f"pause_to_menu:{attempt_id}:{test_id}"
        finish_cb = f"finish:{attempt_id}"
    else:
        continue_cb = f"question_continue:{test_id}:{index}"
        pause_cb = f"pause_to_menu:{test_id}"
        finish_cb = "finish"

    if mode in RESUMABLE_MODES:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(BTN_CONTINUE, callback_data=continue_cb)],
            [InlineKeyboardButton(BTN_SAVE_EXIT, callback_data=pause_cb)],
            [InlineKeyboardButton(BTN_FINISH, callback_data=finish_cb)],
        ])

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_CONTINUE, callback_data=continue_cb)],
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=pause_cb)],
    ])


def after_finish_keyboard(user_id: int, state: dict[str, Any]) -> InlineKeyboardMarkup:
    test_id = state.get("test_id")
    if not test_id:
        return InlineKeyboardMarkup([])

    rows = []
    attempt_id = state.get("attempt_id")
    if state.get("wrong_answers") and attempt_id is not None:
        rows.append([InlineKeyboardButton("🧠 Ошибки", callback_data=f"result_errors_page:{attempt_id}:0")])

    mode = state.get("mode")
    if mode == "errors":
        if state.get("wrong_answers"):
            rows.append([InlineKeyboardButton("🔁 Заново", callback_data=f"repeat_session_errors:{test_id}")])
    elif mode == "mini":
        rows.append([InlineKeyboardButton("🔁 Заново", callback_data=f"mini_start:{test_id}:10")])
    elif mode == "repeat_attempt" and attempt_id is not None:
        rows.append([InlineKeyboardButton("🔁 Заново", callback_data=f"repeat_attempt:{attempt_id}")])
    else:
        rows.append([InlineKeyboardButton("🔁 Повторить тест", callback_data=f"solve_menu:{test_id}")])

    rows.append([InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)


def session_error_keyboard(test_id: str, pos: int, total: int, attempt_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    if pos > 0:
        cb = f"result_error_show:{attempt_id}:{pos - 1}" if attempt_id is not None else f"session_error_show:{test_id}:{pos - 1}"
        rows.append([InlineKeyboardButton("⬅️ Предыдущая", callback_data=cb)])
    if pos + 1 < total:
        cb = f"result_error_show:{attempt_id}:{pos + 1}" if attempt_id is not None else f"session_error_show:{test_id}:{pos + 1}"
        rows.append([InlineKeyboardButton("➡️ Следующая", callback_data=cb)])
    if attempt_id is not None:
        rows.append([InlineKeyboardButton(BTN_BACK, callback_data=f"result_errors_page:{attempt_id}:0")])
        rows.append([InlineKeyboardButton("📋 К результату", callback_data=f"show_result_attempt:{attempt_id}")])
    else:
        rows.append([InlineKeyboardButton("📋 К результату", callback_data=f"show_result:{test_id}")])
    return InlineKeyboardMarkup(rows)


def stats_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return profile_section_keyboard(test_id)

def reset_errors_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Да, сбросить ошибки", callback_data=f"reset_errors_do:{test_id}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"learn_menu:{test_id}")],
    ])

def public_rating_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")],
    ])

def start_from_number_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_BACK, callback_data=f"solve_menu:{test_id}")],
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")],
    ])

def find_question_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔢 По номеру", callback_data=f"find_number:{test_id}"),
            InlineKeyboardButton("🔤 По содержанию", callback_data=f"find_text:{test_id}"),
        ],
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")],
    ])

def find_input_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Посмотреть другой", callback_data=f"find_question:{test_id}")],
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")],
    ])

def question_view_keyboard(test_id: str, index: int) -> InlineKeyboardMarkup:
    total = len(get_questions(test_id))
    nav_row = []
    if index > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"view_question:{test_id}:{index - 1}"))
    if index + 1 < total:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"view_question:{test_id}:{index + 1}"))

    rows = []
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton("🔎 Посмотреть другой", callback_data=f"find_question:{test_id}")])
    rows.append([InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)

def preview_question_text(test_id: str, index: int) -> str:
    total = len(get_questions(test_id))
    state = {
        "test_id": test_id,
        "mode": "view",
        "order": list(range(total)),
        "pos": index,
    }
    return build_question_text(index, state, selected_index=-1, show_correct=True)

def search_question_indices(test_id: str, query_text: str) -> list[int]:
    query_text = query_text.strip().casefold()
    if not query_text:
        return []

    words = [word for word in query_text.split() if word]
    results: list[tuple[int, int]] = []

    for index, question in enumerate(get_questions(test_id)):
        question_text = str(question["question"]).casefold()
        options_text = " ".join(str(option) for option in question["options"]).casefold()
        combined = f"{question_text} {options_text}"

        score = 0
        if query_text in question_text:
            score += 100
        elif query_text in combined:
            score += 60

        for word in words:
            if word in question_text:
                score += 10
            elif word in combined:
                score += 3

        if score > 0:
            results.append((score, index))

    results.sort(key=lambda item: (-item[0], item[1]))
    return [index for _score, index in results]

def find_results_text(test_id: str, query_text: str, indices: list[int], page: int = 0) -> str:
    total = len(indices)
    total_pages = max(1, (total + FIND_PAGE_SIZE - 1) // FIND_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * FIND_PAGE_SIZE
    visible = indices[start:start + FIND_PAGE_SIZE]

    lines = [
        "🔤 Найденные вопросы",
        f"Запрос: {query_text}",
        "",
        f"{start + 1}–{start + len(visible)} из {total}",
        f"Страница {page + 1} из {total_pages}",
        "",
    ]

    for index in visible:
        question_text = str(get_questions(test_id)[index]["question"]).replace("\n", " ")
        if len(question_text) > 95:
            question_text = question_text[:95].rstrip() + "…"
        lines.append(f"{index + 1}. {question_text}")

    return "\n".join(lines)

def find_results_keyboard(test_id: str, indices: list[int], page: int = 0) -> InlineKeyboardMarkup:
    total = len(indices)
    total_pages = max(1, (total + FIND_PAGE_SIZE - 1) // FIND_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * FIND_PAGE_SIZE
    visible = indices[start:start + FIND_PAGE_SIZE]

    number_buttons = [
        InlineKeyboardButton(str(index + 1), callback_data=f"view_question:{test_id}:{index}")
        for index in visible
    ]
    rows = [number_buttons[i:i + 5] for i in range(0, len(number_buttons), 5)]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"find_results_page:{test_id}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"find_results_page:{test_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🔎 Посмотреть другой", callback_data=f"find_question:{test_id}")])
    rows.append([InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"learn_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)


PAGE_SIZE = 5


def _number_rows(items: list[tuple[str, str]], per_row: int = 5) -> list[list[InlineKeyboardButton]]:
    buttons = [InlineKeyboardButton(text, callback_data=cb) for text, cb in items]
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def profile_list_keyboard(test_id: str, prefix: str, page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"{prefix}:{test_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"{prefix}:{test_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def favorites_keyboard(test_id: str, indices: list[int], page: int, total: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    rows = _number_rows([(str(index + 1), f"favorite_show:{test_id}:{start + i}") for i, index in enumerate(indices)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"profile_favorites:{test_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"profile_favorites:{test_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def favorite_detail_keyboard(test_id: str, pos: int, total: int, question_index: int) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if pos > 0:
        nav.append(InlineKeyboardButton("⬅️ Предыдущий", callback_data=f"favorite_show:{test_id}:{pos - 1}"))
    if pos + 1 < total:
        nav.append(InlineKeyboardButton("➡️ Следующий", callback_data=f"favorite_show:{test_id}:{pos + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⭐ Убрать из избранного", callback_data=f"toggle_favorite:{test_id}:{question_index}")])
    rows.append([InlineKeyboardButton(BTN_BACK, callback_data=f"profile_favorites:{test_id}:{pos // PAGE_SIZE}")])
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def profile_errors_keyboard(test_id: str, items: list[dict[str, Any]], page: int, total: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    rows = _number_rows([(str(int(item["question_index"]) + 1), f"profile_error_show:{test_id}:{start + i}") for i, item in enumerate(items)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"profile_errors:{test_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"profile_errors:{test_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def profile_error_detail_keyboard(test_id: str, pos: int, total: int, question_index: int, fav: bool) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if pos > 0:
        nav.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"profile_error_show:{test_id}:{pos - 1}"))
    if pos + 1 < total:
        nav.append(InlineKeyboardButton("➡️ Следующая", callback_data=f"profile_error_show:{test_id}:{pos + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⭐ Убрать из избранного" if fav else "⭐ В избранное", callback_data=f"toggle_favorite:{test_id}:{question_index}")])
    rows.append([InlineKeyboardButton(BTN_BACK, callback_data=f"profile_errors:{test_id}:{pos // PAGE_SIZE}")])
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def history_keyboard(test_id: str, attempts: list[dict[str, Any]], page: int, total: int) -> InlineKeyboardMarkup:
    rows = _number_rows([(str(page * PAGE_SIZE + i + 1), f"history_attempt:{test_id}:{int(a['attempt_id'])}:{page}") for i, a in enumerate(attempts)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"profile_history:{test_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"profile_history:{test_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def attempt_detail_keyboard(test_id: str, attempt_id: int, page: int, wrong_count: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🔁 Пройти заново", callback_data=f"repeat_attempt:{attempt_id}")]]
    if wrong_count:
        rows.append([InlineKeyboardButton("🧠 Ошибки попытки", callback_data=f"attempt_errors_page:{attempt_id}:0")])
    rows.append([InlineKeyboardButton(BTN_BACK, callback_data=f"profile_history:{test_id}:{page}")])
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def attempt_errors_keyboard(test_id: str, attempt_id: int, items: list[dict[str, Any]], page: int, total: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    rows = _number_rows([(str(int(item["question_index"]) + 1), f"attempt_error_show:{attempt_id}:{start + i}") for i, item in enumerate(items)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"attempt_errors_page:{attempt_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"attempt_errors_page:{attempt_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(BTN_BACK, callback_data=f"history_attempt:{test_id}:{attempt_id}:0")])
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def attempt_error_detail_keyboard(test_id: str, attempt_id: int, pos: int, total: int, question_index: int, fav: bool) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if pos > 0:
        nav.append(InlineKeyboardButton("⬅️ Предыдущая", callback_data=f"attempt_error_show:{attempt_id}:{pos - 1}"))
    if pos + 1 < total:
        nav.append(InlineKeyboardButton("➡️ Следующая", callback_data=f"attempt_error_show:{attempt_id}:{pos + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⭐ Убрать из избранного" if fav else "⭐ В избранное", callback_data=f"toggle_favorite:{test_id}:{question_index}")])
    rows.append([InlineKeyboardButton(BTN_BACK, callback_data=f"attempt_errors_page:{attempt_id}:{pos // PAGE_SIZE}")])
    rows.append([InlineKeyboardButton("👤 В профиль", callback_data=f"my_profile:{test_id}")])
    return InlineKeyboardMarkup(rows)


def result_errors_keyboard(attempt_id: int, items: list[dict[str, Any]], page: int, total: int) -> InlineKeyboardMarkup:
    start = page * PAGE_SIZE
    rows = _number_rows([(str(int(item["question_index"]) + 1), f"result_error_show:{attempt_id}:{start + i}") for i, item in enumerate(items)])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"result_errors_page:{attempt_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"result_errors_page:{attempt_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("📋 К результату", callback_data=f"show_result_attempt:{attempt_id}")])
    return InlineKeyboardMarkup(rows)
