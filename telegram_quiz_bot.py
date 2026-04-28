import csv
import html
import json
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Thread

from flask import Flask

from telegram import BotCommand, InputFile, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quiz_progress.sqlite3"

# ----------------------------
# НАСТРОЙКИ
# ----------------------------
# Токен вставлен прямо в код для удобства.
# Если перевыпустишь токен в BotFather, замени его здесь.
BOT_TOKEN = "8643995860:AAGeJHU66x1uPVHFF19nZEc2N0qpt_LrWNI"

# Впиши сюда свой Telegram ID, чтобы работала админ-панель.
# Узнать ID можно командой /myid.
# Пример: ADMIN_IDS = {551500449}
ADMIN_IDS = set()

# Мини-веб-сервер для Render / UptimeRobot.
# Он нужен, чтобы внешний сервис мог пинговать бота по ссылке.
WEB_APP = Flask(__name__)

@WEB_APP.route("/")
def home():
    return "OZIZ bot is running!"

def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    thread = Thread(
        target=lambda: WEB_APP.run(host="0.0.0.0", port=port),
        daemon=True,
    )
    thread.start()


LETTERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З"]

def sep() -> str:
    return "────────────────"

def mode_title(mode: str | None) -> str:
    return {
        "normal": "По порядку",
        "random": "Вразброс",
        "mini": "Тренировка",
        "errors": "Разбор ошибок",
    }.get(mode or "", "Тест")

def format_attempt_short(attempt) -> str:
    if not attempt or not attempt["answered"]:
        return "пока нет"
    percent = round(attempt["correct"] / attempt["answered"] * 100, 1)
    return f"{percent}% · {seconds_to_text(attempt['duration_seconds'])}"


# Чтобы потом добавить новый тест:
# 1) положи рядом новый JSON с вопросами
# 2) добавь новую строку в TESTS
# 3) меню выбора теста появится автоматически
TESTS = {
    "first_test": {
        "title": "ОЗИЗ модуль 2",
        "file": "tests/oziz_module_2.json",
    },
}

LOADED_TESTS = {}
for test_id, info in TESTS.items():
    with (BASE_DIR / info["file"]).open("r", encoding="utf-8") as f:
        LOADED_TESTS[test_id] = json.load(f)


USER_STATE = {}


def get_questions(test_id: str) -> list[dict]:
    return LOADED_TESTS[test_id]


def seconds_to_text(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} ч {minutes} мин {sec} сек"
    if minutes:
        return f"{minutes} мин {sec} сек"
    return f"{sec} сек"


def get_admin_ids() -> set[int]:
    ids = set(ADMIN_IDS)

    raw = os.getenv("TELEGRAM_ADMIN_ID", "").strip()
    if not raw:
        raw = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()

    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))

    return ids


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


def user_display_name(row: sqlite3.Row | dict) -> str:
    first = row["first_name"] or ""
    last = row["last_name"] or ""
    username = row["username"] or ""

    full = f"{first} {last}".strip()
    if username and full:
        return f"{full} (@{username})"
    if username:
        return f"@{username}"
    return full or f"ID {row['user_id']}"


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS all_time_errors (
            user_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            wrong_count INTEGER NOT NULL DEFAULT 1,
            last_wrong_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, test_id, question_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hard_questions (
            user_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, test_id, question_index)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            attempts_started INTEGER NOT NULL DEFAULT 0,
            attempts_finished INTEGER NOT NULL DEFAULT 0,
            total_answered INTEGER NOT NULL DEFAULT 0,
            total_correct INTEGER NOT NULL DEFAULT 0,
            last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, test_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attempts (
            attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            duration_seconds INTEGER,
            answered INTEGER NOT NULL DEFAULT 0,
            correct INTEGER NOT NULL DEFAULT 0,
            completed_full_test INTEGER NOT NULL DEFAULT 0,
            finished_by_user INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS active_sessions (
            user_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, test_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attempt_wrong_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER,
            user_id INTEGER NOT NULL,
            test_id TEXT NOT NULL,
            question_index INTEGER NOT NULL,
            wrong_answer_index INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    try:
        conn.execute("ALTER TABLE all_time_errors ADD COLUMN last_wrong_answer_index INTEGER")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    return conn


def upsert_user(user) -> None:
    if user is None:
        return

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, first_seen_at, last_seen_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (
                user.id,
                user.username,
                user.first_name,
                user.last_name,
            ),
        )
        conn.commit()


def ensure_user_stats(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO user_stats (user_id, test_id, attempts_started, attempts_finished, total_answered, total_correct, last_activity_at)
            VALUES (?, ?, 0, 0, 0, 0, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, test_id)
            DO NOTHING
            """,
            (user_id, test_id),
        )
        conn.commit()


def record_attempt_start(user_id: int, test_id: str, mode: str) -> int:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET attempts_started = attempts_started + 1,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        )
        cur = conn.execute(
            """
            INSERT INTO attempts (user_id, test_id, mode, started_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, test_id, mode),
        )
        conn.commit()
        return int(cur.lastrowid)


def record_attempt_finish(
    user_id: int,
    test_id: str,
    attempt_id: int | None,
    answered: int,
    correct: int,
    completed_full_test: bool,
    finished_by_user: bool,
) -> None:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET attempts_finished = attempts_finished + 1,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        )

        if attempt_id is not None:
            conn.execute(
                """
                UPDATE attempts
                SET finished_at = CURRENT_TIMESTAMP,
                    duration_seconds = CAST((julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 86400 AS INTEGER),
                    answered = ?,
                    correct = ?,
                    completed_full_test = ?,
                    finished_by_user = ?
                WHERE attempt_id = ?
                """,
                (
                    answered,
                    correct,
                    1 if completed_full_test else 0,
                    1 if finished_by_user else 0,
                    attempt_id,
                ),
            )
        conn.commit()


def record_answer(user_id: int, test_id: str, is_correct: bool) -> None:
    ensure_user_stats(user_id, test_id)
    with db_connect() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET total_answered = total_answered + 1,
                total_correct = total_correct + ?,
                last_activity_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND test_id = ?
            """,
            (1 if is_correct else 0, user_id, test_id),
        )
        conn.commit()



def add_all_time_error(user_id: int, test_id: str, question_index: int, wrong_answer_index: int | None = None) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO all_time_errors (user_id, test_id, question_index, wrong_count, last_wrong_at, last_wrong_answer_index)
            VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(user_id, test_id, question_index)
            DO UPDATE SET
                wrong_count = wrong_count + 1,
                last_wrong_at = CURRENT_TIMESTAMP,
                last_wrong_answer_index = excluded.last_wrong_answer_index
            """,
            (user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()

def remove_all_time_error(user_id: int, test_id: str, question_index: int) -> None:
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM all_time_errors WHERE user_id = ? AND test_id = ? AND question_index = ?",
            (user_id, test_id, question_index),
        )
        conn.commit()



def save_active_session(user_id: int, state: dict) -> None:
    test_id = state.get("test_id")
    if not test_id or not state.get("order"):
        return

    data = {
        "test_id": test_id,
        "order": state.get("order", []),
        "pos": state.get("pos", 0),
        "correct": state.get("correct", 0),
        "total": state.get("total", 0),
        "wrong_indices": state.get("wrong_indices", []),
        "wrong_answers": state.get("wrong_answers", []),
        "mode": state.get("mode"),
        "finish_recorded": state.get("finish_recorded", False),
        "attempt_id": state.get("attempt_id"),
        "awaiting_next": state.get("awaiting_next", False),
    }

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO active_sessions (user_id, test_id, state_json, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, test_id)
            DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, test_id, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()


def load_active_session(user_id: int, test_id: str) -> dict | None:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT state_json
            FROM active_sessions
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()

    if not row:
        return None

    try:
        data = json.loads(row["state_json"])
    except json.JSONDecodeError:
        return None

    if not data.get("order"):
        return None

    return data


def delete_active_session(user_id: int, test_id: str | None) -> None:
    if not test_id:
        return

    with db_connect() as conn:
        conn.execute(
            "DELETE FROM active_sessions WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        )
        conn.commit()


def restore_state_from_session(chat_id: int, session: dict) -> dict:
    state = get_state(chat_id)
    state["test_id"] = session["test_id"]
    state["order"] = session.get("order", [])
    state["pos"] = session.get("pos", 0)
    state["correct"] = session.get("correct", 0)
    state["total"] = session.get("total", 0)
    state["wrong_indices"] = session.get("wrong_indices", [])
    state["wrong_answers"] = session.get("wrong_answers", [])
    state["mode"] = session.get("mode")
    state["active"] = True
    state["finish_recorded"] = session.get("finish_recorded", False)
    state["attempt_id"] = session.get("attempt_id")
    state["awaiting_next"] = session.get("awaiting_next", False)
    return state


def active_session_button_text(user_id: int, test_id: str) -> str | None:
    session = load_active_session(user_id, test_id)
    if not session:
        return None

    order = session.get("order", [])
    pos = session.get("pos", 0)
    if not order or pos >= len(order):
        return None

    return f"Продолжить: вопрос {pos + 1} из {len(order)}"


def record_attempt_wrong_answer(
    user_id: int,
    test_id: str,
    attempt_id: int | None,
    question_index: int,
    wrong_answer_index: int | None,
) -> None:
    if attempt_id is None:
        return

    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO attempt_wrong_answers (attempt_id, user_id, test_id, question_index, wrong_answer_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (attempt_id, user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()


def get_attempt_wrong_answers(user_id: int, test_id: str, attempt_id: int | None) -> list[dict]:
    if attempt_id is None:
        return []

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, wrong_answer_index
            FROM attempt_wrong_answers
            WHERE user_id = ? AND test_id = ? AND attempt_id = ?
            ORDER BY id ASC
            """,
            (user_id, test_id, attempt_id),
        ).fetchall()

    return [
        {
            "question_index": row["question_index"],
            "wrong_answer_index": row["wrong_answer_index"],
        }
        for row in rows
    ]

def get_all_time_error_indices(user_id: int, test_id: str) -> list[int]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            ORDER BY last_wrong_at DESC
            """,
            (user_id, test_id),
        ).fetchall()
    return [row["question_index"] for row in rows]


def add_hard_question(user_id: int, test_id: str, question_index: int) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO hard_questions (user_id, test_id, question_index, added_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, test_id, question_index)
            DO UPDATE SET added_at = CURRENT_TIMESTAMP
            """,
            (user_id, test_id, question_index),
        )
        conn.commit()


def remove_hard_question(user_id: int, test_id: str, question_index: int) -> None:
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM hard_questions WHERE user_id = ? AND test_id = ? AND question_index = ?",
            (user_id, test_id, question_index),
        )
        conn.commit()


def clear_hard_questions(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM hard_questions WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        )
        conn.commit()


def clear_all_time_errors(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM all_time_errors WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        )
        conn.commit()


def get_hard_question_indices(user_id: int, test_id: str) -> list[int]:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index
            FROM hard_questions
            WHERE user_id = ? AND test_id = ?
            ORDER BY added_at DESC
            """,
            (user_id, test_id),
        ).fetchall()
    return [row["question_index"] for row in rows]


def get_hard_count(user_id: int, test_id: str) -> int:
    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM hard_questions
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()
    return row["c"] or 0




def get_state(chat_id: int) -> dict:
    if chat_id not in USER_STATE:
        USER_STATE[chat_id] = {
            "test_id": None,
            "order": [],
            "pos": 0,
            "correct": 0,
            "total": 0,
            "wrong_indices": [],
            "wrong_answers": [],
            "mode": None,
            "active": False,
            "finish_recorded": False,
            "attempt_id": None,
            "awaiting_next": False,
        }
    return USER_STATE[chat_id]

def test_select_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for test_id, info in TESTS.items():
        count = len(get_questions(test_id))
        rows.append([
            InlineKeyboardButton(
                f"{info['title']} — {count} вопросов",
                callback_data=f"test_menu:{test_id}",
            )
        ])
    return InlineKeyboardMarkup(rows)



def test_main_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Решать", callback_data=f"solve_menu:{test_id}")],
        [InlineKeyboardButton("⚡ Тренировка", callback_data=f"mini_start:{test_id}:10")],
        [InlineKeyboardButton("🧠 Разобрать ошибки", callback_data=f"errors_solve:{test_id}")],
        [InlineKeyboardButton("📊 Статистика", callback_data=f"my_stats:{test_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="tests:menu")],
    ])


def test_main_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    questions_count = len(get_questions(test_id))
    errors_count = len(get_all_time_error_indices(user_id, test_id))

    return (
        f"{title}\n\n"
        f"Вопросов: {questions_count}\n"
        f"Ошибок: {errors_count}\n\n"
        f"Выбери режим:"
    )

def study_menu_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Учить все вопросы", callback_data=f"study_start:{test_id}:all")],
        [InlineKeyboardButton("Сложные вопросы", callback_data=f"hard_menu:{test_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"test_menu:{test_id}")],
    ])


def hard_menu_keyboard(test_id: str, hard_count: int) -> InlineKeyboardMarkup:
    rows = []
    if hard_count:
        rows.append([InlineKeyboardButton("Учить сложные вопросы", callback_data=f"study_start:{test_id}:hard")])
        rows.append([InlineKeyboardButton("Сбросить сложные", callback_data=f"hard_clear:{test_id}")])
    else:
        rows.append([InlineKeyboardButton("Учить все вопросы", callback_data=f"study_start:{test_id}:all")])
    rows.append([InlineKeyboardButton("Назад к учёбе", callback_data=f"study_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)




def solve_menu_keyboard(test_id: str, user_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []

    if user_id is not None:
        continue_text = active_session_button_text(user_id, test_id)
        if continue_text:
            rows.append([InlineKeyboardButton(f"▶️ {continue_text}", callback_data=f"continue_session:{test_id}")])

    rows.extend([
        [InlineKeyboardButton("🧭 По порядку", callback_data=f"start:{test_id}:normal")],
        [InlineKeyboardButton("🔀 Вразброс", callback_data=f"start:{test_id}:random")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"test_menu:{test_id}")],
    ])

    return InlineKeyboardMarkup(rows)

def mini_menu_keyboard(test_id: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("10 случайных вопросов", callback_data=f"mini_start:{test_id}:10")],
        [InlineKeyboardButton("Назад", callback_data=f"test_menu:{test_id}")],
    ])


def errors_menu_keyboard(test_id: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Разобрать ошибки", callback_data=f"errors_solve:{test_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"test_menu:{test_id}")],
    ])



def after_finish_keyboard(user_id: int, state: dict) -> InlineKeyboardMarkup:
    test_id = state.get("test_id")
    rows = []

    if test_id:
        attempt_id = state.get("attempt_id")
        has_session_errors = bool(state.get("wrong_answers"))
        if attempt_id is not None:
            has_session_errors = has_session_errors or bool(get_attempt_wrong_answers(user_id, test_id, attempt_id))

        if has_session_errors and attempt_id is not None:
            rows.append([InlineKeyboardButton("👀 Показать ошибки", callback_data=f"session_error_show:{test_id}:{attempt_id}:0")])
        elif has_session_errors:
            rows.append([InlineKeyboardButton("👀 Показать ошибки", callback_data=f"session_error_show:{test_id}:0")])

        rows.append([InlineKeyboardButton("🔁 Повторить тест", callback_data=f"solve_menu:{test_id}")])
        rows.append([InlineKeyboardButton("🏠 К меню теста", callback_data=f"test_menu:{test_id}")])

    return InlineKeyboardMarkup(rows)

def study_keyboard(test_id: str, index: int, shown: bool) -> InlineKeyboardMarkup:
    rows = []
    if not shown:
        rows.append([InlineKeyboardButton("Показать ответ", callback_data=f"study_show:{test_id}:{index}")])
    rows.append([
        InlineKeyboardButton("Знаю", callback_data=f"study_know:{test_id}:{index}"),
        InlineKeyboardButton("Не знаю", callback_data=f"study_dont:{test_id}:{index}"),
    ])
    rows.append([InlineKeyboardButton("Закончить", callback_data="finish")])
    return InlineKeyboardMarkup(rows)


def correct_answer_text(test_id: str, index: int) -> str:
    q = get_questions(test_id)[index]
    ci = q["correct_index"]
    letter = LETTERS[ci] if ci < len(LETTERS) else str(ci + 1)
    return f"{letter}) {q['options'][ci]}"


def build_study_text(index: int, state: dict, shown: bool = False) -> str:
    test_id = state["test_id"]
    q = get_questions(test_id)[index]
    title = TESTS[test_id]["title"]

    if state.get("mode") == "study_hard":
        header = f"{title} | Учить сложные: {state['pos'] + 1}/{len(state['order'])}"
    else:
        header = f"{title} | Учить: {state['pos'] + 1}/{len(state['order'])}"

    text = f"{header}\n\nВопрос:\n{q['question']}"
    if shown:
        text += f"\n\nОтвет:\n{correct_answer_text(test_id, index)}"
    return text





def build_question_text(
    index: int,
    state: dict,
    selected_index: int | None = None,
    show_correct: bool = False,
) -> str:
    test_id = state["test_id"]
    q = get_questions(test_id)[index]
    test_title = html.escape(TESTS[test_id]["title"])
    correct_index = q["correct_index"]

    header = f"{test_title}\n{html.escape(mode_title(state.get('mode')))} · {state['pos'] + 1} из {len(state['order'])}"

    lines = [
        header,
        "",
        "🟦 Вопрос",
        "",
        f"<b>{html.escape(str(q['question']))}</b>",
        "",
        sep(),
        "",
        "⬜ Ответы",
        "",
    ]

    for i, opt in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""

        if show_correct and i == correct_index:
            prefix = "✅ "
        elif selected_index is not None and i == selected_index and i != correct_index:
            prefix = "❌ "

        lines.append(f"{prefix}{letter}) {html.escape(str(opt))}")

    return "\n".join(lines)


def build_answer_keyboard(test_id: str, index: int) -> InlineKeyboardMarkup:
    q = get_questions(test_id)[index]
    answer_buttons = []

    for i, _ in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        answer_buttons.append(
            InlineKeyboardButton(f"Ответ {letter}", callback_data=f"answer:{test_id}:{index}:{i}")
        )

    rows = [answer_buttons[i:i + 2] for i in range(0, len(answer_buttons), 2)]
    rows.append([InlineKeyboardButton("Показать ответ", callback_data=f"show_answer:{test_id}:{index}")])
    rows.append([InlineKeyboardButton("Завершить", callback_data=f"question_menu:{test_id}:{index}")])
    return InlineKeyboardMarkup(rows)

async def send_current_question(message, state: dict) -> None:
    test_id = state["test_id"]
    index = state["order"][state["pos"]]
    await message.reply_text(
        build_question_text(index, state),
        reply_markup=build_answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def send_current_study_card(message, state: dict) -> None:
    test_id = state["test_id"]
    index = state["order"][state["pos"]]
    state["study_answer_shown"] = False
    await message.reply_text(
        build_study_text(index, state, shown=False),
        reply_markup=study_keyboard(test_id, index, shown=False),
    )




def start_quiz_mode(state: dict, user_id: int, test_id: str, mode: str, order: list[int]) -> None:
    state["test_id"] = test_id
    state["order"] = order
    state["pos"] = 0
    state["correct"] = 0
    state["total"] = 0
    state["wrong_indices"] = []
    state["wrong_answers"] = []
    state["mode"] = mode
    state["active"] = True
    state["finish_recorded"] = False
    state["attempt_id"] = record_attempt_start(user_id, test_id, mode)
    state["awaiting_next"] = False
    save_active_session(user_id, state)

def start_study_mode(state: dict, test_id: str, mode: str, order: list[int]) -> None:
    state["test_id"] = test_id
    state["order"] = order
    state["pos"] = 0
    state["correct"] = 0
    state["total"] = 0
    state["wrong_indices"] = []
    state["mode"] = mode
    state["active"] = True
    state["finish_recorded"] = True
    state["attempt_id"] = None
    state["study_answer_shown"] = False


def mark_finished_if_needed(user_id: int, state: dict, completed_full_test: bool, finished_by_user: bool) -> None:
    if state.get("test_id") and not state.get("finish_recorded") and state.get("attempt_id") is not None:
        record_attempt_finish(
            user_id=user_id,
            test_id=state["test_id"],
            attempt_id=state.get("attempt_id"),
            answered=state["total"],
            correct=state["correct"],
            completed_full_test=completed_full_test,
            finished_by_user=finished_by_user,
        )
        state["finish_recorded"] = True



def result_text(state: dict, user_id: int, finished_by_user: bool = False) -> str:
    total = state["total"]
    correct = state["correct"]
    percent = round(correct / total * 100, 1) if total else 0
    wrong_count = len(state.get("wrong_answers", []))

    if state.get("test_id"):
        test_title = TESTS[state["test_id"]]["title"]
        all_time_count = len(get_all_time_error_indices(user_id, state["test_id"]))
    else:
        test_title = "тест не выбран"
        all_time_count = 0

    title = "Решение завершено" if finished_by_user else "Тест завершён"
    return (
        f"{title}\n\n"
        f"{test_title}\n\n"
        f"Результат: {percent}%\n"
        f"Решено: {total}\n"
        f"Ошибок в этом решении: {wrong_count}\n\n"
        f"Ошибок за всё время: {all_time_count}"
    )



def build_all_errors_text(user_id: int, test_id: str) -> list[str]:
    title = html.escape(TESTS[test_id]["title"])

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index, last_wrong_answer_index
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            ORDER BY last_wrong_at DESC
            """,
            (user_id, test_id),
        ).fetchall()

    if not rows:
        return [f"Ошибок по тесту «{title}» нет."]

    chunks = []
    current = f"Ошибки — {title}\n\n"

    for n, row in enumerate(rows, start=1):
        index = row["question_index"]
        wrong_index = row["last_wrong_answer_index"]
        q = get_questions(test_id)[index]
        correct_index = q["correct_index"]

        lines = [
            f"{n}. 🟦 Вопрос",
            "",
            f"<b>{html.escape(str(q['question']))}</b>",
            "",
            sep(),
            "",
            "⬜ Ответы",
            "",
        ]

        for i, opt in enumerate(q["options"]):
            letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
            prefix = ""

            if i == correct_index:
                prefix = "✅ "
            elif wrong_index is not None and i == wrong_index and i != correct_index:
                prefix = "❌ "

            lines.append(f"{prefix}{letter}) {html.escape(str(opt))}")

        item = "\n".join(lines) + "\n\n"

        if len(current) + len(item) > 3900:
            chunks.append(current.rstrip())
            current = ""

        current += item

    if current.strip():
        chunks.append(current.rstrip())

    return chunks

def format_session_error_card(state: dict, test_id: str, pos: int, items: list[dict] | None = None) -> str:
    if items is None:
        items = state.get("wrong_answers", [])

    title = html.escape(TESTS[test_id]["title"])

    if not items:
        return f"Ошибок в этом решении по тесту «{title}» нет."

    item = items[pos]
    index = item["question_index"]
    wrong_index = item.get("wrong_answer_index")
    q = get_questions(test_id)[index]
    correct_index = q["correct_index"]

    lines = [
        "Ошибки этого решения",
        title,
        f"{pos + 1} из {len(items)}",
        "",
        "🟦 Вопрос",
        "",
        f"<b>{html.escape(str(q['question']))}</b>",
        "",
        sep(),
        "",
        "⬜ Ответы",
        "",
    ]

    for i, opt in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""

        if i == correct_index:
            prefix = "✅ "
        elif wrong_index is not None and i == wrong_index and i != correct_index:
            prefix = "❌ "

        lines.append(f"{prefix}{letter}) {html.escape(str(opt))}")

    return "\n".join(lines)


def session_error_keyboard(test_id: str, pos: int, total: int, attempt_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []

    if pos + 1 < total:
        if attempt_id is not None:
            rows.append([InlineKeyboardButton("➡️ Следующий", callback_data=f"session_error_show:{test_id}:{attempt_id}:{pos + 1}")])
        else:
            rows.append([InlineKeyboardButton("➡️ Следующий", callback_data=f"session_error_show:{test_id}:{pos + 1}")])

    rows.append([InlineKeyboardButton("📋 К результату", callback_data=f"show_result:{test_id}")])
    rows.append([InlineKeyboardButton("🏠 К меню теста", callback_data=f"test_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)

async def send_all_errors_list(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, test_id: str) -> None:
    chunks = build_all_errors_text(user_id, test_id)

    for chunk in chunks:
        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")

    await context.bot.send_message(
        chat_id=chat_id,
        text="Выбери следующее действие:",
        reply_markup=errors_menu_keyboard(test_id, user_id),
    )



def my_stats_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        best_full_attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND completed_full_test = 1 AND answered > 0
            ORDER BY
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

        last_attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL AND answered > 0
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

    errors_count = len(get_all_time_error_indices(user_id, test_id))

    return (
        f"📊 Статистика\n"
        f"{title}\n\n"
        f"{sep()}\n\n"
        f"Лучший результат:\n"
        f"{format_attempt_short(best_full_attempt)}\n\n"
        f"Последний результат:\n"
        f"{format_attempt_short(last_attempt)}\n\n"
        f"{sep()}\n\n"
        f"Ошибок: {errors_count}"
    )

def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Выбрать тест", callback_data="admin:tests")],
        [InlineKeyboardButton("Общая сводка", callback_data="admin:summary")],
        [InlineKeyboardButton("Экспорт всех данных", callback_data="admin:export_all")],
    ])


def admin_test_select_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for test_id, info in TESTS.items():
        rows.append([
            InlineKeyboardButton(
                f"{info['title']} — {len(get_questions(test_id))} вопросов",
                callback_data=f"admin:test:{test_id}",
            )
        ])
    rows.append([InlineKeyboardButton("Назад в админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Статистика по тесту", callback_data=f"admin:test_stats:{test_id}")],
        [InlineKeyboardButton("Рейтинг топ-10", callback_data=f"admin:rating:{test_id}")],
        [InlineKeyboardButton("Пользователи", callback_data=f"admin:test_users:{test_id}")],
        [InlineKeyboardButton("Частые ошибки", callback_data=f"admin:frequent_errors:{test_id}")],
        [InlineKeyboardButton("Экспорт по тесту", callback_data=f"admin:export_test:{test_id}")],
        [InlineKeyboardButton("Назад", callback_data="admin:tests")],
    ])


def admin_back_to_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Назад к тесту", callback_data=f"admin:test:{test_id}")],
        [InlineKeyboardButton("Назад к тестам", callback_data="admin:tests")],
    ])


def admin_test_users_keyboard(test_id: str) -> InlineKeyboardMarkup:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT u.user_id, u.username, u.first_name, u.last_name,
                   s.total_answered AS answered,
                   s.total_correct AS correct,
                   s.last_activity_at AS last_activity_at
            FROM user_stats s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.test_id = ?
            ORDER BY s.total_answered DESC, s.last_activity_at DESC
            LIMIT 40
            """,
            (test_id,),
        ).fetchall()

    buttons = []
    for row in rows:
        answered = row["answered"] or 0
        correct = row["correct"] or 0
        percent = round(correct / answered * 100, 1) if answered else 0
        name = user_display_name(row)
        buttons.append([
            InlineKeyboardButton(
                f"{name} — {correct}/{answered} ({percent}%)",
                callback_data=f"admin:test_user:{test_id}:{row['user_id']}",
            )
        ])

    buttons.append([InlineKeyboardButton("Назад к тесту", callback_data=f"admin:test:{test_id}")])
    return InlineKeyboardMarkup(buttons)


def admin_summary_text() -> str:
    with db_connect() as conn:
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        total_answered = conn.execute("SELECT COALESCE(SUM(total_answered), 0) AS c FROM user_stats").fetchone()["c"]
        total_correct = conn.execute("SELECT COALESCE(SUM(total_correct), 0) AS c FROM user_stats").fetchone()["c"]
        total_errors = conn.execute("SELECT COUNT(*) AS c FROM all_time_errors").fetchone()["c"]
        total_hard = conn.execute("SELECT COUNT(*) AS c FROM hard_questions").fetchone()["c"]
        total_tests = len(TESTS)

    percent = round(total_correct / total_answered * 100, 1) if total_answered else 0

    return (
        "Общая сводка\n\n"
        f"Всего пользователей: {total_users}\n"
        f"Всего тестов: {total_tests}\n"
        f"Всего ответов: {total_answered}\n"
        f"Правильных ответов: {total_correct}\n"
        f"Общий процент: {percent}%\n"
        f"Активных ошибок за всё время: {total_errors}\n"
        f"Сложных вопросов у пользователей: {total_hard}"
    )


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

        hard = conn.execute(
            """
            SELECT COUNT(*) AS hard_count
            FROM hard_questions
            WHERE test_id = ?
            """,
            (test_id,),
        ).fetchone()

        completed_attempts = conn.execute(
            """
            SELECT COUNT(*) AS c,
                   AVG(duration_seconds) AS avg_time
            FROM attempts
            WHERE test_id = ? AND completed_full_test = 1
            """,
            (test_id,),
        ).fetchone()

    answered = stats["answered"] or 0
    correct = stats["correct"] or 0
    percent = round(correct / answered * 100, 1) if answered else 0

    return (
        f"Статистика по тесту — {title}\n\n"
        f"Количество вопросов: {questions_count}\n"
        f"Пользователей решали: {stats['users'] or 0}\n"
        f"Попыток начато: {stats['attempts_started'] or 0}\n"
        f"Попыток завершено: {stats['attempts_finished'] or 0}\n"
        f"Полных прохождений: {completed_attempts['c'] or 0}\n"
        f"Среднее время полного прохождения: {seconds_to_text(completed_attempts['avg_time'])}\n"
        f"Всего ответов: {answered}\n"
        f"Правильных ответов: {correct}\n"
        f"Средний процент: {percent}%\n"
        f"Активных ошибок за всё время: {errors['active_errors'] or 0}\n"
        f"Сложных вопросов у пользователей: {hard['hard_count'] or 0}\n"
        f"Всего ошибочных ответов: {errors['wrong_clicks'] or 0}"
    )


def admin_rating_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        rows = conn.execute(
            """
            WITH best_attempts AS (
                SELECT
                    a.*,
                    (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) AS percent_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.user_id
                        ORDER BY
                            (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) DESC,
                            a.duration_seconds ASC
                    ) AS rn
                FROM attempts a
                WHERE a.test_id = ?
                  AND a.completed_full_test = 1
                  AND a.answered > 0
            )
            SELECT b.*, u.username, u.first_name, u.last_name
            FROM best_attempts b
            JOIN users u ON u.user_id = b.user_id
            WHERE b.rn = 1
            ORDER BY b.percent_value DESC, b.duration_seconds ASC
            LIMIT 10
            """,
            (test_id,),
        ).fetchall()

    lines = [
        f"Рейтинг — {title}",
        "",
        "Правило: выше процент правильных; при равенстве выше тот, кто быстрее.",
        "В рейтинг попадают только полные прохождения теста.",
        "",
    ]

    if not rows:
        lines.append("Пока нет полных прохождений.")
        return "\n".join(lines)

    for i, row in enumerate(rows, start=1):
        percent = round((row["correct"] / row["answered"]) * 100, 1) if row["answered"] else 0
        lines.append(
            f"{i}. {user_display_name(row)} — {percent}% — {seconds_to_text(row['duration_seconds'])}"
        )

    return "\n".join(lines)


def admin_test_users_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]
    return f"Пользователи — {title}\n\nВыбери пользователя:"


def admin_user_detail_text(test_id: str, user_id: int) -> str:
    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

        stats = conn.execute(
            """
            SELECT *
            FROM user_stats
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()

        errors = conn.execute(
            """
            SELECT COUNT(*) AS active_errors, COALESCE(SUM(wrong_count), 0) AS wrong_clicks
            FROM all_time_errors
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()

        hard = conn.execute(
            """
            SELECT COUNT(*) AS hard_count
            FROM hard_questions
            WHERE user_id = ? AND test_id = ?
            """,
            (user_id, test_id),
        ).fetchone()

        best_attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND answered > 0 AND finished_at IS NOT NULL
            ORDER BY
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

        best_full_attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND completed_full_test = 1 AND answered > 0
            ORDER BY
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

        last_attempt = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

    if not user:
        return "Пользователь не найден."

    title = TESTS[test_id]["title"]

    if not stats:
        return (
            f"Пользователь: {user_display_name(user)}\n"
            f"Тест: {title}\n\n"
            "Этот пользователь ещё не решал выбранный тест."
        )

    answered = stats["total_answered"] or 0
    correct = stats["total_correct"] or 0
    percent = round(correct / answered * 100, 1) if answered else 0

    lines = [
        "Карточка пользователя",
        "",
        f"Имя: {user_display_name(user)}",
        f"Telegram ID: {user_id}",
        f"Тест: {title}",
        "",
        f"Попыток начато: {stats['attempts_started']}",
        f"Попыток завершено: {stats['attempts_finished']}",
        f"Всего ответов: {answered}",
        f"Правильно: {correct}",
        f"Процент по всем ответам: {percent}%",
        f"Активных ошибок: {errors['active_errors'] or 0}",
        f"Сложных вопросов: {hard['hard_count'] or 0}",
        f"Всего ошибочных ответов: {errors['wrong_clicks'] or 0}",
        f"Последняя активность: {stats['last_activity_at']}",
    ]

    if best_attempt:
        best_percent = round(best_attempt["correct"] / best_attempt["answered"] * 100, 1) if best_attempt["answered"] else 0
        full_mark = "да" if best_attempt["completed_full_test"] else "нет"
        finish_type = "закончил сам" if best_attempt["finished_by_user"] else "дошёл до конца"

        lines.extend([
            "",
            "Лучшая попытка:",
            f"Результат: {best_attempt['correct']}/{best_attempt['answered']} — {best_percent}%",
            f"Время: {seconds_to_text(best_attempt['duration_seconds'])}",
            f"Полный тест: {full_mark}",
            f"Завершение: {finish_type}",
            f"Дата: {best_attempt['finished_at']}",
        ])

    if best_full_attempt:
        full_percent = round(best_full_attempt["correct"] / best_full_attempt["answered"] * 100, 1) if best_full_attempt["answered"] else 0
        lines.extend([
            "",
            "Лучшее полное прохождение:",
            f"Результат: {best_full_attempt['correct']}/{best_full_attempt['answered']} — {full_percent}%",
            f"Время: {seconds_to_text(best_full_attempt['duration_seconds'])}",
            f"Дата: {best_full_attempt['finished_at']}",
        ])

    if last_attempt:
        last_percent = round(last_attempt["correct"] / last_attempt["answered"] * 100, 1) if last_attempt["answered"] else 0
        lines.extend([
            "",
            "Последняя попытка:",
            f"Результат: {last_attempt['correct']}/{last_attempt['answered']} — {last_percent}%",
            f"Время: {seconds_to_text(last_attempt['duration_seconds'])}",
            f"Дата: {last_attempt['finished_at']}",
        ])

    return "\n".join(lines)


def admin_frequent_errors_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT question_index,
                   COUNT(DISTINCT user_id) AS users_wrong,
                   COALESCE(SUM(wrong_count), 0) AS wrong_clicks
            FROM all_time_errors
            WHERE test_id = ?
            GROUP BY question_index
            ORDER BY users_wrong DESC, wrong_clicks DESC
            LIMIT 10
            """,
            (test_id,),
        ).fetchall()

    lines = [f"Частые ошибки — {title}", ""]

    if not rows:
        lines.append("Сохранённых ошибок пока нет.")
        return "\n".join(lines)

    for i, row in enumerate(rows, start=1):
        index = row["question_index"]
        q = get_questions(test_id)[index]
        question = q["question"]
        if len(question) > 180:
            question = question[:177] + "..."

        lines.extend([
            f"{i}. {question}",
            f"Ошиблись пользователей: {row['users_wrong']}",
            f"Всего ошибочных ответов: {row['wrong_clicks']}",
            f"Правильный ответ: {correct_answer_text(test_id, index)}",
            "",
        ])

    return "\n".join(lines).rstrip()


def write_stats_csv(out_path: Path, rows: list[sqlite3.Row]) -> None:
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "user_id",
            "username",
            "first_name",
            "last_name",
            "first_seen_at",
            "last_seen_at",
            "test_id",
            "test_title",
            "attempts_started",
            "attempts_finished",
            "total_answered",
            "total_correct",
            "percent",
            "active_errors",
            "hard_questions",
            "wrong_clicks",
        ])

        for row in rows:
            answered = row["total_answered"] or 0
            correct = row["total_correct"] or 0
            percent = round(correct / answered * 100, 1) if answered else 0
            test_title = TESTS.get(row["test_id"], {}).get("title", row["test_id"]) if row["test_id"] else ""

            writer.writerow([
                row["user_id"],
                row["username"] or "",
                row["first_name"] or "",
                row["last_name"] or "",
                row["first_seen_at"] or "",
                row["last_seen_at"] or "",
                row["test_id"] or "",
                test_title,
                row["attempts_started"] or 0,
                row["attempts_finished"] or 0,
                answered,
                correct,
                percent,
                row["active_errors"] or 0,
                row["hard_questions"] or 0,
                row["wrong_clicks"] or 0,
            ])


def create_all_stats_csv() -> Path:
    out_path = BASE_DIR / f"admin_all_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                u.user_id,
                u.username,
                u.first_name,
                u.last_name,
                u.first_seen_at,
                u.last_seen_at,
                s.test_id,
                s.attempts_started,
                s.attempts_finished,
                s.total_answered,
                s.total_correct,
                COALESCE(e.active_errors, 0) AS active_errors,
                COALESCE(h.hard_questions, 0) AS hard_questions,
                COALESCE(e.wrong_clicks, 0) AS wrong_clicks
            FROM users u
            LEFT JOIN user_stats s ON s.user_id = u.user_id
            LEFT JOIN (
                SELECT user_id, test_id, COUNT(*) AS active_errors, SUM(wrong_count) AS wrong_clicks
                FROM all_time_errors
                GROUP BY user_id, test_id
            ) e ON e.user_id = u.user_id AND e.test_id = s.test_id
            LEFT JOIN (
                SELECT user_id, test_id, COUNT(*) AS hard_questions
                FROM hard_questions
                GROUP BY user_id, test_id
            ) h ON h.user_id = u.user_id AND h.test_id = s.test_id
            ORDER BY u.last_seen_at DESC, s.total_answered DESC
            """
        ).fetchall()

    write_stats_csv(out_path, rows)
    return out_path


def create_test_stats_csv(test_id: str) -> Path:
    safe_test_id = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in test_id)
    out_path = BASE_DIR / f"admin_{safe_test_id}_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                u.user_id,
                u.username,
                u.first_name,
                u.last_name,
                u.first_seen_at,
                u.last_seen_at,
                s.test_id,
                s.attempts_started,
                s.attempts_finished,
                s.total_answered,
                s.total_correct,
                COALESCE(e.active_errors, 0) AS active_errors,
                COALESCE(h.hard_questions, 0) AS hard_questions,
                COALESCE(e.wrong_clicks, 0) AS wrong_clicks
            FROM user_stats s
            JOIN users u ON u.user_id = s.user_id
            LEFT JOIN (
                SELECT user_id, test_id, COUNT(*) AS active_errors, SUM(wrong_count) AS wrong_clicks
                FROM all_time_errors
                WHERE test_id = ?
                GROUP BY user_id, test_id
            ) e ON e.user_id = s.user_id AND e.test_id = s.test_id
            LEFT JOIN (
                SELECT user_id, test_id, COUNT(*) AS hard_questions
                FROM hard_questions
                WHERE test_id = ?
                GROUP BY user_id, test_id
            ) h ON h.user_id = s.user_id AND h.test_id = s.test_id
            WHERE s.test_id = ?
            ORDER BY s.total_answered DESC
            """,
            (test_id, test_id, test_id),
        ).fetchall()

    write_stats_csv(out_path, rows)
    return out_path


# ---------- User commands ----------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    await update.message.reply_text("Выбери тест:", reply_markup=test_select_keyboard())

async def tests_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    await update.message.reply_text("Выбери тест:", reply_markup=test_select_keyboard())


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    await update.message.reply_text(f"Твой Telegram ID: {update.effective_user.id}")


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)

    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "Админ-панель недоступна.\n\n"
            f"Твой Telegram ID: {update.effective_user.id}\n"
            "Чтобы включить доступ, добавь этот ID в TELEGRAM_ADMIN_ID при запуске бота."
        )
        return

    await update.message.reply_text("Админ-панель:", reply_markup=admin_main_keyboard())



async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)
    if state.get("test_id"):
        await update.message.reply_text(my_stats_text(update.effective_user.id, state["test_id"]))
    else:
        await update.message.reply_text("Сначала выбери тест через /start.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)
    if state.get("test_id"):
        delete_active_session(update.effective_user.id, state.get("test_id"))
    USER_STATE.pop(update.effective_chat.id, None)
    await update.message.reply_text(
        "Текущее действие сброшено. Ошибки за всё время не удалены.",
        reply_markup=test_select_keyboard(),
    )

async def finish_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)
    if not state.get("active"):
        await update.message.reply_text("Сейчас нет активного режима.", reply_markup=test_select_keyboard())
        return

    test_id = state.get("test_id")
    state["active"] = False
    state["awaiting_next"] = False
    mark_finished_if_needed(update.effective_user.id, state, completed_full_test=False, finished_by_user=True)
    delete_active_session(update.effective_user.id, test_id)

    await update.message.reply_text(
        result_text(state, update.effective_user.id, finished_by_user=True),
        reply_markup=after_finish_keyboard(update.effective_user.id, state),
    )

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
    state["test_id"] = test_id

    await query.edit_message_text(
        test_main_text(query.from_user.id, test_id),
        reply_markup=test_main_keyboard(test_id),
    )

async def handle_study_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    await query.edit_message_text(
        "Учить тест\n\nВыбери режим:",
        reply_markup=study_menu_keyboard(test_id),
    )


async def handle_hard_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    hard_count = get_hard_count(query.from_user.id, test_id)
    text = (
        f"Сложные вопросы\n\n"
        f"Сейчас в списке: {hard_count}\n\n"
        f"Сюда попадают вопросы, где ты нажал «Не знаю» в режиме учёбы."
    )
    await query.edit_message_text(text, reply_markup=hard_menu_keyboard(test_id, hard_count))


async def handle_hard_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    clear_hard_questions(query.from_user.id, test_id)
    await query.edit_message_text(
        "Сложные вопросы сброшены.",
        reply_markup=hard_menu_keyboard(test_id, 0),
    )


async def handle_study_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, study_type = query.data.split(":")
    state = get_state(query.message.chat_id)

    if study_type == "hard":
        order = get_hard_question_indices(query.from_user.id, test_id)
        if not order:
            await query.edit_message_text(
                "Сложных вопросов пока нет.\n\nОтмечай их кнопкой «Не знаю» во время учёбы.",
                reply_markup=hard_menu_keyboard(test_id, 0),
            )
            return
        mode = "study_hard"
    else:
        order = list(range(len(get_questions(test_id))))
        mode = "study"

    start_study_mode(state, test_id, mode, order)
    index = state["order"][state["pos"]]
    await query.edit_message_text(
        build_study_text(index, state, shown=False),
        reply_markup=study_keyboard(test_id, index, shown=False),
    )


async def handle_study_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state(query.message.chat_id)
    state["study_answer_shown"] = True

    await query.edit_message_text(
        build_study_text(index, state, shown=True),
        reply_markup=study_keyboard(test_id, index, shown=True),
    )


async def handle_study_mark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    action, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state(query.message.chat_id)

    if action == "study_know":
        remove_hard_question(query.from_user.id, test_id, index)
        result = "✅ Отмечено: знаю. Убрано из сложных."
    else:
        add_hard_question(query.from_user.id, test_id, index)
        result = "🟡 Отмечено: не знаю. Добавлено в сложные."

    await query.edit_message_text(
        build_study_text(index, state, shown=True) + "\n\n" + result
    )

    state["pos"] += 1
    if state["pos"] >= len(state["order"]):
        state["active"] = False
        await query.message.reply_text(
            result_text(state, query.from_user.id),
            reply_markup=after_finish_keyboard(query.from_user.id, state),
        )
        return

    await send_current_study_card(query.message, state)




async def handle_solve_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    await query.edit_message_text("📝 Решать\n\nВыбери режим:", reply_markup=solve_menu_keyboard(test_id, query.from_user.id))


async def handle_start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, mode = query.data.split(":")
    questions = get_questions(test_id)
    order = list(range(len(questions)))
    if mode == "random":
        random.shuffle(order)

    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, mode, order)
    index = state["order"][state["pos"]]

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=build_answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_mini_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    await query.edit_message_text(
        "⚡ Тренировка\n\n10 случайных вопросов.",
        reply_markup=mini_menu_keyboard(test_id, query.from_user.id),
    )



async def handle_mini_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, _mini_type = query.data.split(":")
    questions = get_questions(test_id)

    order = list(range(len(questions)))
    random.shuffle(order)
    order = order[:min(10, len(order))]

    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, "mini", order)
    index = state["order"][state["pos"]]
    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=build_answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_errors_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    error_count = len(get_all_time_error_indices(query.from_user.id, test_id))
    text = (
        f"Работа над ошибками\n\n"
        f"Ошибок за всё время: {error_count}"
    )
    await query.edit_message_text(text, reply_markup=errors_menu_keyboard(test_id, query.from_user.id))




async def handle_errors_solve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    order = get_all_time_error_indices(query.from_user.id, test_id)
    if not order:
        await query.edit_message_text(
            "Ошибок за всё время нет.",
            reply_markup=test_main_keyboard(test_id),
        )
        return

    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, "errors", order)
    index = state["order"][state["pos"]]
    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=build_answer_keyboard(test_id, index),
        parse_mode="HTML",
    )

async def handle_errors_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    clear_all_time_errors(query.from_user.id, test_id)
    await query.edit_message_text(
        "Мои ошибки за всё время сброшены.",
        reply_markup=errors_menu_keyboard(test_id, query.from_user.id),
    )


async def handle_all_errors_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, _, test_id = query.data.split(":")
    await query.edit_message_text("Показываю ошибки за всё время в формате «вопрос → ответ».")
    await send_all_errors_list(context, query.message.chat_id, query.from_user.id, test_id)




async def handle_my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    await query.edit_message_text(
        my_stats_text(query.from_user.id, test_id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 К меню теста", callback_data=f"test_menu:{test_id}")],
        ]),
    )

async def handle_finish_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    state = get_state(query.message.chat_id)
    if not state.get("active"):
        await query.edit_message_text("Сейчас нет активного режима.", reply_markup=test_select_keyboard())
        return

    test_id = state.get("test_id")
    state["active"] = False
    state["awaiting_next"] = False
    mark_finished_if_needed(query.from_user.id, state, completed_full_test=False, finished_by_user=True)
    delete_active_session(query.from_user.id, test_id)

    await query.edit_message_text(
        result_text(state, query.from_user.id, finished_by_user=True),
        reply_markup=after_finish_keyboard(query.from_user.id, state),
    )

def add_session_wrong_answer(state: dict, question_index: int, wrong_answer_index: int | None) -> None:
    state.setdefault("wrong_answers", []).append({
        "question_index": question_index,
        "wrong_answer_index": wrong_answer_index,
    })
    if question_index not in state["wrong_indices"]:
        state["wrong_indices"].append(question_index)




def next_after_pause_keyboard(test_id: str, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Следующий", callback_data=f"next_question:{test_id}:{index}")],
        [InlineKeyboardButton("Завершить", callback_data=f"question_menu:{test_id}:{index}")],
    ])

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    state = get_state(query.message.chat_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=test_select_keyboard())
        return

    _, test_id, index_str, answer_str = query.data.split(":")
    index = int(index_str)
    selected = int(answer_str)

    if state.get("awaiting_next"):
        await query.answer("Нажми «Следующий»")
        return

    if state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    q = get_questions(test_id)[index]
    correct_index = q["correct_index"]

    is_correct = selected == correct_index
    record_answer(query.from_user.id, test_id, is_correct)

    state["total"] += 1

    if is_correct:
        state["correct"] += 1
        remove_all_time_error(query.from_user.id, test_id, index)

        await query.edit_message_text(
            text=build_question_text(index, state, selected_index=selected, show_correct=True),
            parse_mode="HTML",
        )

        state["pos"] += 1

        if state["pos"] >= len(state["order"]):
            state["active"] = False
            completed_full_test = state.get("mode") in {"normal", "random"} and state["total"] == len(get_questions(test_id))
            mark_finished_if_needed(
                query.from_user.id,
                state,
                completed_full_test=completed_full_test,
                finished_by_user=False,
            )
            delete_active_session(query.from_user.id, test_id)

            await query.message.reply_text(
                result_text(state, query.from_user.id),
                reply_markup=after_finish_keyboard(query.from_user.id, state),
            )
            return

        save_active_session(query.from_user.id, state)
        next_index = state["order"][state["pos"]]
        await query.message.reply_text(
            build_question_text(next_index, state),
            reply_markup=build_answer_keyboard(test_id, next_index),
            parse_mode="HTML",
        )
        return

    add_session_wrong_answer(state, index, selected)
    record_attempt_wrong_answer(query.from_user.id, test_id, state.get("attempt_id"), index, selected)
    add_all_time_error(query.from_user.id, test_id, index, selected)
    state["awaiting_next"] = True
    save_active_session(query.from_user.id, state)

    await query.edit_message_text(
        text=build_question_text(index, state, selected_index=selected, show_correct=True),
        reply_markup=next_after_pause_keyboard(test_id, index),
        parse_mode="HTML",
    )


async def handle_show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    state = get_state(query.message.chat_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=test_select_keyboard())
        return

    _, test_id, index_str = query.data.split(":")
    index = int(index_str)

    if state.get("awaiting_next"):
        await query.answer("Нажми «Следующий»")
        return

    if state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    record_answer(query.from_user.id, test_id, False)
    state["total"] += 1
    add_session_wrong_answer(state, index, None)
    record_attempt_wrong_answer(query.from_user.id, test_id, state.get("attempt_id"), index, None)
    add_all_time_error(query.from_user.id, test_id, index, None)
    state["awaiting_next"] = True
    save_active_session(query.from_user.id, state)

    await query.edit_message_text(
        text=build_question_text(index, state, selected_index=None, show_correct=True),
        reply_markup=next_after_pause_keyboard(test_id, index),
        parse_mode="HTML",
    )


async def handle_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state(query.message.chat_id)

    if not state.get("active"):
        await query.edit_message_text(
            "Этот режим уже завершён.",
            reply_markup=after_finish_keyboard(query.from_user.id, state),
        )
        return

    if not state.get("awaiting_next"):
        await query.answer("Следующий вопрос уже открыт")
        return

    if state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    state["awaiting_next"] = False
    state["pos"] += 1

    if state["pos"] >= len(state["order"]):
        state["active"] = False
        completed_full_test = state.get("mode") in {"normal", "random"} and state["total"] == len(get_questions(test_id))
        mark_finished_if_needed(
            query.from_user.id,
            state,
            completed_full_test=completed_full_test,
            finished_by_user=False,
        )
        delete_active_session(query.from_user.id, test_id)

        await query.edit_message_text(
            result_text(state, query.from_user.id),
            reply_markup=after_finish_keyboard(query.from_user.id, state),
        )
        return

    save_active_session(query.from_user.id, state)
    next_index = state["order"][state["pos"]]
    await query.edit_message_text(
        build_question_text(next_index, state),
        reply_markup=build_answer_keyboard(test_id, next_index),
        parse_mode="HTML",
    )


async def handle_session_error_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    parts = query.data.split(":")
    state = get_state(query.message.chat_id)

    if len(parts) == 4:
        _, test_id, attempt_id_str, pos_str = parts
        attempt_id = int(attempt_id_str)
        pos = int(pos_str)
        items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)
    else:
        _, test_id, pos_str = parts
        attempt_id = state.get("attempt_id")
        pos = int(pos_str)
        items = state.get("wrong_answers", [])
        if not items and attempt_id is not None:
            items = get_attempt_wrong_answers(query.from_user.id, test_id, attempt_id)

    if not items:
        if not state.get("test_id"):
            state["test_id"] = test_id
        await query.edit_message_text(
            "Ошибок в этом решении нет.",
            reply_markup=after_finish_keyboard(query.from_user.id, state),
        )
        return

    pos = max(0, min(pos, len(items) - 1))
    await query.edit_message_text(
        format_session_error_card(state, test_id, pos, items=items),
        reply_markup=session_error_keyboard(test_id, pos, len(items), attempt_id=attempt_id),
        parse_mode="HTML",
    )

async def handle_show_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    state = get_state(query.message.chat_id)
    if not state.get("test_id"):
        state["test_id"] = test_id

    await query.edit_message_text(
        result_text(state, query.from_user.id),
        reply_markup=after_finish_keyboard(query.from_user.id, state),
    )



def reset_errors_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Да, сбросить ошибки", callback_data=f"reset_errors_confirm:{test_id}")],
        [InlineKeyboardButton("Отмена", callback_data=f"test_menu:{test_id}")],
    ])


async def reset_errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)

    state = get_state(update.effective_chat.id)
    test_id = state.get("test_id")

    if not test_id:
        await update.message.reply_text(
            "Сначала выбери тест через /start.",
            reply_markup=test_select_keyboard(),
        )
        return

    error_count = len(get_all_time_error_indices(update.effective_user.id, test_id))
    title = TESTS[test_id]["title"]

    if not error_count:
        await update.message.reply_text(
            f"Ошибок по тесту «{title}» нет.",
            reply_markup=test_main_keyboard(test_id),
        )
        return

    await update.message.reply_text(
        f"Сброс ошибок\n\n"
        f"{title}\n\n"
        f"Ошибок сейчас: {error_count}\n\n"
        f"Точно сбросить ошибки по этому тесту?",
        reply_markup=reset_errors_keyboard(test_id),
    )


async def handle_reset_errors_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    clear_all_time_errors(query.from_user.id, test_id)

    await query.edit_message_text(
        "Ошибки сброшены.",
        reply_markup=test_main_keyboard(test_id),
    )


async def handle_pause_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    state = get_state(query.message.chat_id)

    if state.get("test_id") == test_id and state.get("order"):
        save_active_session(query.from_user.id, state)
        state["active"] = False

    await query.edit_message_text(
        test_main_text(query.from_user.id, test_id),
        reply_markup=test_main_keyboard(test_id),
    )


async def handle_continue_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, test_id = query.data.split(":")
    session = load_active_session(query.from_user.id, test_id)

    if not session:
        await query.edit_message_text(
            "Незавершённой попытки нет.",
            reply_markup=solve_menu_keyboard(test_id, query.from_user.id),
        )
        return

    state = restore_state_from_session(query.message.chat_id, session)

    if state["pos"] >= len(state["order"]):
        delete_active_session(query.from_user.id, test_id)
        await query.edit_message_text(
            "Незавершённой попытки нет.",
            reply_markup=solve_menu_keyboard(test_id, query.from_user.id),
        )
        return

    index = state["order"][state["pos"]]

    if state.get("awaiting_next"):
        wrong_index = None
        for item in reversed(state.get("wrong_answers", [])):
            if item.get("question_index") == index:
                wrong_index = item.get("wrong_answer_index")
                break

        await query.edit_message_text(
            build_question_text(index, state, selected_index=wrong_index, show_correct=True),
            reply_markup=next_after_pause_keyboard(test_id, index),
            parse_mode="HTML",
        )
        return

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=build_answer_keyboard(test_id, index),
        parse_mode="HTML",
    )



def question_menu_keyboard(test_id: str, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Завершить попытку", callback_data="finish")],
        [InlineKeyboardButton("Сохранить и выйти", callback_data=f"pause_to_menu:{test_id}")],
        [InlineKeyboardButton("Продолжить", callback_data=f"question_continue:{test_id}:{index}")],
    ])

async def handle_question_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state(query.message.chat_id)

    if state.get("test_id") == test_id and state.get("order"):
        save_active_session(query.from_user.id, state)

    await query.edit_message_text(
        "Что сделать с попыткой?",
        reply_markup=question_menu_keyboard(test_id, index),
    )


async def handle_question_continue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    _, _, test_id, index_str = query.data.split(":")
    index = int(index_str)
    state = get_state(query.message.chat_id)

    if not state.get("active"):
        session = load_active_session(query.from_user.id, test_id)
        if session:
            state = restore_state_from_session(query.message.chat_id, session)
        else:
            await query.edit_message_text(
                "Незавершённой попытки нет.",
                reply_markup=solve_menu_keyboard(test_id, query.from_user.id),
            )
            return

    if state.get("awaiting_next"):
        wrong_index = None
        for item in reversed(state.get("wrong_answers", [])):
            if item.get("question_index") == index:
                wrong_index = item.get("wrong_answer_index")
                break

        await query.edit_message_text(
            build_question_text(index, state, selected_index=wrong_index, show_correct=True),
            reply_markup=next_after_pause_keyboard(test_id, index),
            parse_mode="HTML",
        )
        return

    if state.get("pos", 0) < len(state.get("order", [])):
        current_index = state["order"][state["pos"]]
    else:
        current_index = index

    await query.edit_message_text(
        build_question_text(current_index, state),
        reply_markup=build_answer_keyboard(test_id, current_index),
        parse_mode="HTML",
    )

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    await query.edit_message_text("Админ-панель:", reply_markup=admin_main_keyboard())


async def handle_admin_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    await query.edit_message_text("Выбери тест для админ-статистики:", reply_markup=admin_test_select_keyboard())


async def handle_admin_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    title = TESTS[test_id]["title"]
    count = len(get_questions(test_id))

    await query.edit_message_text(
        f"{title}\nВопросов: {count}\n\nВыбери раздел:",
        reply_markup=admin_test_keyboard(test_id),
    )


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

    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_test_users_text(test_id), reply_markup=admin_test_users_keyboard(test_id))


async def handle_admin_test_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id, user_id_str = query.data.split(":")
    user_id = int(user_id_str)

    await query.edit_message_text(
        admin_user_detail_text(test_id, user_id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад к пользователям", callback_data=f"admin:test_users:{test_id}")],
            [InlineKeyboardButton("Назад к тесту", callback_data=f"admin:test:{test_id}")],
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

    csv_path = create_all_stats_csv()

    await query.message.reply_document(
        document=InputFile(csv_path),
        filename=csv_path.name,
        caption="Экспорт всех данных CSV"
    )

    await query.edit_message_text("CSV-экспорт всех данных отправлен.", reply_markup=admin_main_keyboard())


async def handle_admin_export_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    csv_path = create_test_stats_csv(test_id)

    await query.message.reply_document(
        document=InputFile(csv_path),
        filename=csv_path.name,
        caption=f"Экспорт по тесту: {TESTS[test_id]['title']}"
    )

    await query.edit_message_text("CSV-экспорт по тесту отправлен.", reply_markup=admin_test_keyboard(test_id))



async def setup_bot_commands(application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "открыть бота"),
        BotCommand("stats", "моя статистика"),
        BotCommand("myid", "узнать Telegram ID"),
        BotCommand("admin", "админ-панель"),
        BotCommand("reset", "сбросить текущее действие"),
        BotCommand("reset_errors", "сбросить ошибки"),
    ])


def main() -> None:
    db_connect()
    keep_alive()

    token = BOT_TOKEN.strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Не найден токен. Впиши его в BOT_TOKEN в начале файла telegram_quiz_bot.py."
        )

    app = ApplicationBuilder().token(token).post_init(setup_bot_commands).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tests", tests_command))
    app.add_handler(CommandHandler("finish", finish_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("reset_errors", reset_errors_command))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_command))

    # User navigation
    app.add_handler(CallbackQueryHandler(handle_tests_menu, pattern=r"^tests:menu$"))
    app.add_handler(CallbackQueryHandler(handle_test_menu, pattern=r"^test_menu:"))
    app.add_handler(CallbackQueryHandler(handle_solve_menu, pattern=r"^solve_menu:"))
    app.add_handler(CallbackQueryHandler(handle_start_quiz, pattern=r"^start:"))
    app.add_handler(CallbackQueryHandler(handle_mini_menu, pattern=r"^mini_menu:"))
    app.add_handler(CallbackQueryHandler(handle_mini_start, pattern=r"^mini_start:"))
    app.add_handler(CallbackQueryHandler(handle_errors_solve, pattern=r"^errors_solve:"))
    app.add_handler(CallbackQueryHandler(handle_my_stats, pattern=r"^my_stats:"))
    app.add_handler(CallbackQueryHandler(handle_finish_button, pattern=r"^finish$"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(handle_show_answer, pattern=r"^show_answer:"))
    app.add_handler(CallbackQueryHandler(handle_next_question, pattern=r"^next_question:"))
    app.add_handler(CallbackQueryHandler(handle_question_menu, pattern=r"^question_menu:"))
    app.add_handler(CallbackQueryHandler(handle_question_continue, pattern=r"^question_continue:"))
    app.add_handler(CallbackQueryHandler(handle_pause_to_menu, pattern=r"^pause_to_menu:"))
    app.add_handler(CallbackQueryHandler(handle_continue_session, pattern=r"^continue_session:"))
    app.add_handler(CallbackQueryHandler(handle_session_error_show, pattern=r"^session_error_show:"))
    app.add_handler(CallbackQueryHandler(handle_show_result, pattern=r"^show_result:"))
    app.add_handler(CallbackQueryHandler(handle_reset_errors_confirm, pattern=r"^reset_errors_confirm:"))

    # Admin navigation
    app.add_handler(CallbackQueryHandler(handle_admin_menu, pattern=r"^admin:menu$"))
    app.add_handler(CallbackQueryHandler(handle_admin_tests, pattern=r"^admin:tests$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_menu, pattern=r"^admin:test:"))
    app.add_handler(CallbackQueryHandler(handle_admin_summary, pattern=r"^admin:summary$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_stats, pattern=r"^admin:test_stats:"))
    app.add_handler(CallbackQueryHandler(handle_admin_rating, pattern=r"^admin:rating:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_users, pattern=r"^admin:test_users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_user_detail, pattern=r"^admin:test_user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_frequent_errors, pattern=r"^admin:frequent_errors:"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_all, pattern=r"^admin:export_all$"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_test, pattern=r"^admin:export_test:"))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
