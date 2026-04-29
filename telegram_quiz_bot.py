import csv
import html
import json
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from threading import Thread
from typing import Any

from flask import Flask
from telegram import BotCommand, InputFile, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quiz_progress.sqlite3"

# Лучше хранить токен в Render → Environment Variables → TELEGRAM_BOT_TOKEN.
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8643995860:AAF4I10UCVu1TBeS84bm7mTvIjoNJLtRVWk").strip()
ADMIN_IDS = {551500449}

TESTS = {
    "first_test": {
        "title": "ОЗИЗ модуль 2",
        "file": "tests/oziz_module_2.json",
    },
}

LETTERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К"]

BTN_SHOW_ANSWER = "Показать ответ"
BTN_MENU = "☰ Меню"
BTN_NEXT = "➡️ Следующий"
BTN_CONTINUE = "▶️ Продолжить"
BTN_SAVE_EXIT = "💾 Сохранить и выйти"
BTN_FINISH = "🎯 Завершить"
BTN_TEST_MENU = "🏠 К меню теста"
BTN_BACK = "⬅️ Назад"

RESUMABLE_MODES = {"normal", "random", "reverse", "from_number"}

WEB_APP = Flask(__name__)


@WEB_APP.route("/")
def home():
    return "OZIZ quiz bot is running!"


def keep_alive() -> None:
    port = int(os.environ.get("PORT", 8080))
    Thread(target=lambda: WEB_APP.run(host="0.0.0.0", port=port), daemon=True).start()


# ============================================================
# BASIC HELPERS
# ============================================================

def sep() -> str:
    return "────────────────"


def seconds_to_text(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} ч {minutes} мин {sec} сек"
    if minutes:
        return f"{minutes} мин {sec} сек"
    return f"{sec} сек"


def mode_title(mode: str | None) -> str:
    return {
        "normal": "По порядку",
        "random": "Вразброс",
        "mini": "Тренировка",
        "errors": "Разбор ошибок",
    }.get(mode or "", "Тест")


def get_admin_ids() -> set[int]:
    ids = set(ADMIN_IDS)
    raw = os.getenv("TELEGRAM_ADMIN_IDS", "") or os.getenv("TELEGRAM_ADMIN_ID", "")
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


def user_display_name(row: sqlite3.Row | dict[str, Any]) -> str:
    username = row["username"] or ""
    first = row["first_name"] or ""
    last = row["last_name"] or ""
    full = f"{first} {last}".strip()
    if username and full:
        return f"{full} (@{username})"
    if username:
        return f"@{username}"
    return full or f"ID {row['user_id']}"


# ============================================================
# TEST LOADER
# ============================================================

def normalize_question(raw: dict[str, Any], index: int) -> dict[str, Any]:
    question = raw.get("question") or raw.get("text") or raw.get("q") or raw.get("title")
    options = raw.get("options") or raw.get("answers") or raw.get("variants")

    if not question:
        raise ValueError(f"Вопрос #{index + 1}: нет текста вопроса")
    if not isinstance(options, list) or len(options) < 2:
        raise ValueError(f"Вопрос #{index + 1}: options должен быть списком минимум из 2 вариантов")

    correct = raw.get("correct_index")
    if correct is None:
        correct = raw.get("answer_index")
    if correct is None:
        correct = raw.get("correct")
    if correct is None:
        correct = raw.get("answer")

    if isinstance(correct, str):
        value = correct.strip()
        upper = value.upper()
        if upper in LETTERS:
            correct = LETTERS.index(upper)
        elif value.isdigit():
            correct = int(value)
            if correct >= 1:
                correct -= 1
        else:
            try:
                correct = options.index(value)
            except ValueError:
                found = None
                for i, option in enumerate(options):
                    if value == str(option).strip() or value in str(option):
                        found = i
                        break
                if found is None:
                    raise ValueError(f"Вопрос #{index + 1}: не удалось определить правильный ответ")
                correct = found

    if not isinstance(correct, int):
        raise ValueError(f"Вопрос #{index + 1}: correct_index должен быть числом, буквой или текстом ответа")
    if correct < 0 or correct >= len(options):
        raise ValueError(f"Вопрос #{index + 1}: correct_index вне диапазона")

    return {
        "question": str(question).strip(),
        "options": [str(option).strip() for option in options],
        "correct_index": correct,
    }


def load_tests() -> dict[str, list[dict[str, Any]]]:
    loaded = {}

    for test_id, info in list(TESTS.items()):
        path = BASE_DIR / info["file"]
        if not path.exists():
            raise FileNotFoundError(f"Не найден файл с вопросами: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        questions = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(questions, list):
            raise ValueError(f"{path}: нужен список вопросов или объект с questions")

        loaded[test_id] = [normalize_question(item, i) for i, item in enumerate(questions)]

    # Дополнительные JSON из папки tests автоматически подхватываются как отдельные тесты.
    tests_dir = BASE_DIR / "tests"
    known_paths = {str((BASE_DIR / info["file"]).resolve()) for info in TESTS.values()}

    if tests_dir.exists():
        for path in sorted(tests_dir.glob("*.json")):
            if str(path.resolve()) in known_paths:
                continue

            test_id = path.stem
            if test_id in loaded:
                continue

            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                questions = data.get("questions") if isinstance(data, dict) else data
                if not isinstance(questions, list):
                    continue

                TESTS[test_id] = {
                    "title": path.stem.replace("_", " "),
                    "file": str(path.relative_to(BASE_DIR)),
                }
                loaded[test_id] = [normalize_question(item, i) for i, item in enumerate(questions)]
            except Exception:
                # Один битый дополнительный файл не должен ломать основной бот.
                pass

    return loaded


LOADED_TESTS = load_tests()


def get_questions(test_id: str) -> list[dict[str, Any]]:
    return LOADED_TESTS[test_id]


# ============================================================
# DATABASE
# ============================================================

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db_connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                attempts_started INTEGER NOT NULL DEFAULT 0,
                attempts_finished INTEGER NOT NULL DEFAULT 0,
                total_answered INTEGER NOT NULL DEFAULT 0,
                total_correct INTEGER NOT NULL DEFAULT 0,
                last_activity_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            );

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
            );

            CREATE TABLE IF NOT EXISTS all_time_errors (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                wrong_count INTEGER NOT NULL DEFAULT 1,
                last_wrong_answer_index INTEGER,
                last_wrong_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id, question_index)
            );

            CREATE TABLE IF NOT EXISTS attempt_wrong_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id INTEGER,
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                question_index INTEGER NOT NULL,
                wrong_answer_index INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER NOT NULL,
                test_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id)
            );
            """
        )

        # Безопасные миграции для старой базы.
        for stmt in [
            "ALTER TABLE all_time_errors ADD COLUMN last_wrong_answer_index INTEGER",
            "ALTER TABLE attempts ADD COLUMN finished_by_user INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE active_sessions ADD COLUMN updated_at TEXT",
        ]:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

        conn.commit()


def upsert_user(user) -> None:
    if not user:
        return
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            (user.id, user.username, user.first_name, user.last_name),
        )
        conn.commit()


def ensure_user_stats(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_stats (user_id, test_id) VALUES (?, ?)",
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
            "INSERT INTO attempts (user_id, test_id, mode) VALUES (?, ?, ?)",
            (user_id, test_id, mode),
        )
        conn.commit()
        return int(cur.lastrowid)


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


def add_all_time_error(user_id: int, test_id: str, question_index: int, wrong_answer_index: int | None) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO all_time_errors (user_id, test_id, question_index, wrong_count, last_wrong_answer_index, last_wrong_at)
            VALUES (?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, test_id, question_index)
            DO UPDATE SET
                wrong_count = wrong_count + 1,
                last_wrong_answer_index = excluded.last_wrong_answer_index,
                last_wrong_at = CURRENT_TIMESTAMP
            """,
            (user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()


def remove_all_time_error(user_id: int, test_id: str, question_index: int) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            DELETE FROM all_time_errors
            WHERE user_id = ? AND test_id = ? AND question_index = ?
            """,
            (user_id, test_id, question_index),
        )
        conn.commit()


def clear_all_time_errors(user_id: int, test_id: str) -> None:
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM all_time_errors WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        )
        conn.commit()


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
    return [int(row["question_index"]) for row in rows]


def record_attempt_wrong_answer(
    attempt_id: int | None,
    user_id: int,
    test_id: str,
    question_index: int,
    wrong_answer_index: int | None,
) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO attempt_wrong_answers (attempt_id, user_id, test_id, question_index, wrong_answer_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (attempt_id, user_id, test_id, question_index, wrong_answer_index),
        )
        conn.commit()


def get_attempt_wrong_answers(user_id: int, test_id: str, attempt_id: int | None) -> list[dict[str, int | None]]:
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
            "question_index": int(row["question_index"]),
            "wrong_answer_index": row["wrong_answer_index"],
        }
        for row in rows
    ]


# ============================================================
# STATE + ACTIVE SESSIONS
# ============================================================

USER_STATE: dict[int, dict[str, Any]] = {}
LAST_START_AT: dict[int, float] = {}


def get_state(chat_id: int) -> dict[str, Any]:
    if chat_id not in USER_STATE:
        USER_STATE[chat_id] = {
            "test_id": None,
            "mode": None,
            "order": [],
            "pos": 0,
            "correct": 0,
            "total": 0,
            "wrong_answers": [],
            "awaiting_next": False,
            "active": False,
            "finish_recorded": False,
            "attempt_id": None,
        }
    return USER_STATE[chat_id]


def state_for_db(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "test_id": state.get("test_id"),
        "mode": state.get("mode"),
        "order": state.get("order", []),
        "pos": state.get("pos", 0),
        "correct": state.get("correct", 0),
        "total": state.get("total", 0),
        "wrong_answers": state.get("wrong_answers", []),
        "awaiting_next": state.get("awaiting_next", False),
        "active": state.get("active", False),
        "finish_recorded": state.get("finish_recorded", False),
        "attempt_id": state.get("attempt_id"),
    }


def restore_state(chat_id: int, data: dict[str, Any]) -> dict[str, Any]:
    state = get_state(chat_id)
    state.update({
        "test_id": data.get("test_id"),
        "mode": data.get("mode"),
        "order": data.get("order", []),
        "pos": data.get("pos", 0),
        "correct": data.get("correct", 0),
        "total": data.get("total", 0),
        "wrong_answers": data.get("wrong_answers", []),
        "awaiting_next": data.get("awaiting_next", False),
        "active": True,
        "finish_recorded": data.get("finish_recorded", False),
        "attempt_id": data.get("attempt_id"),
    })
    return state



def save_active_session(user_id: int, state: dict[str, Any]) -> None:
    test_id = state.get("test_id")
    mode = state.get("mode")

    # Сохраняем только последнюю попытку из кнопки "Решать".
    # Работа над ошибками и тренировка не должны её перезаписывать.
    if not test_id or mode not in RESUMABLE_MODES:
        return
    if state.get("finish_recorded") or not state.get("order"):
        return

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
            (user_id, test_id, json.dumps(state_for_db(state), ensure_ascii=False)),
        )
        conn.commit()

def delete_active_session(user_id: int, test_id: str | None) -> None:
    if not test_id:
        return
    with db_connect() as conn:
        conn.execute(
            "DELETE FROM active_sessions WHERE user_id = ? AND test_id = ?",
            (user_id, test_id),
        )
        conn.commit()



def load_active_session(user_id: int, test_id: str) -> dict[str, Any] | None:
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

    if data.get("mode") not in RESUMABLE_MODES:
        return None
    if not data.get("order") or data.get("pos", 0) >= len(data.get("order", [])):
        return None
    return data


def active_session_button_text(user_id: int, test_id: str) -> str | None:
    data = load_active_session(user_id, test_id)
    if not data:
        return None

    order = data.get("order", [])
    pos = data.get("pos", 0)
    mode = data.get("mode")

    if mode in {"from_number", "reverse"} and order and pos < len(order):
        current_question = int(order[pos]) + 1
        return f"Продолжить: вопрос {current_question} из {len(get_questions(test_id))}"

    return f"Продолжить: вопрос {pos + 1} из {len(order)}"

def start_quiz_mode(state: dict[str, Any], user_id: int, test_id: str, mode: str, order: list[int]) -> None:
    if mode in RESUMABLE_MODES:
        delete_active_session(user_id, test_id)

    state.update({
        "test_id": test_id,
        "mode": mode,
        "order": order,
        "pos": 0,
        "correct": 0,
        "total": 0,
        "wrong_answers": [],
        "awaiting_next": False,
        "active": True,
        "finish_recorded": False,
        "attempt_id": record_attempt_start(user_id, test_id, mode),
    })
    save_active_session(user_id, state)

def add_session_wrong_answer(state: dict[str, Any], question_index: int, wrong_answer_index: int | None) -> None:
    state.setdefault("wrong_answers", []).append({
        "question_index": question_index,
        "wrong_answer_index": wrong_answer_index,
    })


def wrong_index_for_question(state: dict[str, Any], question_index: int) -> int | None:
    for item in reversed(state.get("wrong_answers", [])):
        if item.get("question_index") == question_index:
            return item.get("wrong_answer_index")
    return None



def finish_attempt_if_needed(user_id: int, state: dict[str, Any], finished_by_user: bool = False) -> None:
    if state.get("finish_recorded"):
        return

    test_id = state.get("test_id")
    if not test_id:
        return

    completed_full = state.get("mode") in RESUMABLE_MODES and state.get("total", 0) == len(get_questions(test_id))

    record_attempt_finish(
        user_id=user_id,
        test_id=test_id,
        attempt_id=state.get("attempt_id"),
        answered=state.get("total", 0),
        correct=state.get("correct", 0),
        completed_full_test=completed_full,
        finished_by_user=finished_by_user,
    )
    state["finish_recorded"] = True

    if state.get("mode") in RESUMABLE_MODES:
        delete_active_session(user_id, test_id)

def build_question_text(
    index: int,
    state: dict[str, Any],
    selected_index: int | None = None,
    show_correct: bool = False,
) -> str:
    test_id = state["test_id"]
    q = get_questions(test_id)[index]
    title = html.escape(TESTS[test_id]["title"])
    mode = html.escape(mode_title(state.get("mode")))
    correct_index = int(q["correct_index"])

    lines = [
        title,
        f"{mode} · {state['pos'] + 1} из {len(state['order'])}",
        "",
        f"<b>{html.escape(q['question'])}</b>",
        "",
        "",
    ]

    for i, option in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""
        if show_correct and i == correct_index:
            prefix = "✅ "
        elif selected_index is not None and i == selected_index and i != correct_index:
            prefix = "❌ "
        lines.append(f"{prefix}{letter}) {html.escape(option)}")

    return "\n".join(lines)


def format_session_error_card(test_id: str, pos: int, items: list[dict[str, int | None]]) -> str:
    title = html.escape(TESTS[test_id]["title"])
    if not items:
        return f"Ошибок в этом решении по тесту «{title}» нет."

    item = items[pos]
    index = int(item["question_index"])
    wrong_index = item.get("wrong_answer_index")
    q = get_questions(test_id)[index]
    correct_index = int(q["correct_index"])

    lines = [
        "Ошибки этого решения",
        title,
        f"{pos + 1} из {len(items)}",
        "",
        f"<b>{html.escape(q['question'])}</b>",
        "",
        "",
    ]

    for i, option in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        prefix = ""
        if i == correct_index:
            prefix = "✅ "
        elif wrong_index is not None and i == wrong_index and i != correct_index:
            prefix = "❌ "
        lines.append(f"{prefix}{letter}) {html.escape(option)}")

    return "\n".join(lines)



def result_text(state: dict[str, Any], user_id: int, finished_by_user: bool = False) -> str:
    total = int(state.get("total", 0))
    correct = int(state.get("correct", 0))
    percent = round(correct / total * 100, 1) if total else 0
    wrong_count = len(state.get("wrong_answers", []))
    test_id = state.get("test_id")
    passed_mode = mode_title(state.get("mode"))

    if test_id:
        title = TESTS[test_id]["title"]
        all_errors = len(get_all_time_error_indices(user_id, test_id))
        total_questions = len(state.get("order", [])) or total
    else:
        title = "тест не выбран"
        all_errors = 0
        total_questions = total

    header = "⏹ Решение завершено" if finished_by_user else "🎉 Тест завершён"
    return (
        f"{header}\n\n"
        f"{title}\n"
        f"🎮 Режим: {passed_mode}\n\n"
        f"📊 Результат: {percent}%\n"
        f"📝 Решено: {total} из {total_questions}\n"
        f"❌ Ошибок в этом решении: {wrong_count}\n\n"
        f"🧠 Ошибок за всё время: {all_errors}"
    )

def format_attempt_short(attempt: sqlite3.Row | None, test_id: str | None = None) -> str:
    if not attempt or not attempt["answered"]:
        return "пока нет"

    percent = round(attempt["correct"] / attempt["answered"] * 100, 1)
    duration = seconds_to_text(attempt["duration_seconds"])
    if test_id:
        return f"{percent}% · {duration} · {attempt['answered']} из {len(get_questions(test_id))}"
    return f"{percent}% · {duration} · {attempt['answered']} вопросов"


def my_stats_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        best = conn.execute(
            """
            SELECT *
            FROM attempts
            WHERE user_id = ? AND test_id = ? AND finished_at IS NOT NULL AND answered > 0
            ORDER BY
                answered DESC,
                (CAST(correct AS REAL) / NULLIF(answered, 0)) DESC,
                duration_seconds ASC
            LIMIT 1
            """,
            (user_id, test_id),
        ).fetchone()

        last = conn.execute(
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
        f"🏆 Лучший результат:\n"
        f"{format_attempt_short(best, test_id)}\n\n"
        f"🕘 Последний результат:\n"
        f"{format_attempt_short(last, test_id)}\n\n"
        f"{sep()}\n\n"
        f"🧠 Ошибок: {errors_count}"
    )


# ============================================================
# KEYBOARDS
# ============================================================


def public_rating_text(test_id: str) -> str:
    title = TESTS[test_id]["title"]

    with db_connect() as conn:
        rows = conn.execute(
            """
            WITH ranked_attempts AS (
                SELECT
                    a.*,
                    (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) AS percent_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY a.user_id
                        ORDER BY
                            a.answered DESC,
                            (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) DESC,
                            a.duration_seconds ASC,
                            a.finished_at DESC
                    ) AS user_rank
                FROM attempts a
                WHERE a.test_id = ?
                  AND a.finished_at IS NOT NULL
                  AND a.answered > 0
                  AND a.mode IN ('normal', 'random', 'reverse', 'from_number')
            )
            SELECT r.*, u.user_id, u.username, u.first_name, u.last_name
            FROM ranked_attempts r
            LEFT JOIN users u ON u.user_id = r.user_id
            WHERE r.user_rank = 1
            ORDER BY
                r.answered DESC,
                r.percent_value DESC,
                r.duration_seconds ASC,
                r.finished_at DESC
            LIMIT 10
            """,
            (test_id,),
        ).fetchall()

    lines = [
        "🏆 Рейтинг топ-10",
        title,
        "",
    ]

    if not rows:
        lines.append("Пока нет завершённых решений.")
        return "\n".join(lines)

    seen_users: set[int] = set()
    place = 1

    for row in rows:
        user_id = int(row["user_id"])
        if user_id in seen_users:
            continue

        seen_users.add(user_id)
        percent = round((row["correct"] / row["answered"]) * 100, 1) if row["answered"] else 0
        lines.append(
            f"{place}. {user_display_name(row)} — "
            f"{row['correct']}/{row['answered']} — {percent}% · {seconds_to_text(row['duration_seconds'])}"
        )
        place += 1

    return "\n".join(lines)


def public_rating_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")],
    ])


async def handle_public_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    await query.edit_message_text(
        public_rating_text(test_id),
        reply_markup=public_rating_keyboard(test_id),
    )

def test_select_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for test_id, info in TESTS.items():
        rows.append([
            InlineKeyboardButton(
                f"📚 {info['title']} — {len(get_questions(test_id))} вопросов",
                callback_data=f"test_menu:{test_id}",
            )
        ])
    return InlineKeyboardMarkup(rows)



def test_main_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Учить", callback_data=f"learn_menu:{test_id}")],
        [InlineKeyboardButton("📊 Статистика", callback_data=f"my_stats:{test_id}")],
        [InlineKeyboardButton("🏆 Рейтинг", callback_data=f"public_rating:{test_id}")],
        [InlineKeyboardButton(BTN_BACK, callback_data="tests:menu")],
    ])


def learn_menu_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    questions_count = len(get_questions(test_id))
    errors_count = len(get_all_time_error_indices(user_id, test_id))

    return (
        f"📚 Учить\n"
        f"{title}\n\n"
        f"Вопросов: {questions_count}\n"
        f"Ошибок: {errors_count}\n\n"
        f"Выбери действие:"
    )


def learn_menu_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Решать", callback_data=f"solve_menu:{test_id}")],
        [InlineKeyboardButton("⚡ Тренировка", callback_data=f"mini_start:{test_id}:10")],
        [InlineKeyboardButton("🧠 Разобрать ошибки", callback_data=f"errors_solve:{test_id}")],
        [InlineKeyboardButton("🗑 Сбросить ошибки", callback_data=f"reset_errors_confirm:{test_id}")],
        [InlineKeyboardButton("🔎 Найти вопрос", callback_data=f"find_question:{test_id}")],
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

def answer_keyboard(test_id: str, index: int) -> InlineKeyboardMarkup:
    q = get_questions(test_id)[index]
    buttons = []
    for i, _ in enumerate(q["options"]):
        letter = LETTERS[i] if i < len(LETTERS) else str(i + 1)
        buttons.append(InlineKeyboardButton(f"{letter}", callback_data=f"answer:{test_id}:{index}:{i}"))

    if len(buttons) == 4:
        rows = [
            [buttons[0], buttons[2]],
            [buttons[1], buttons[3]],
        ]
    else:
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]

    rows.append([InlineKeyboardButton(BTN_SHOW_ANSWER, callback_data=f"show_answer:{test_id}:{index}")])
    rows.append([InlineKeyboardButton(BTN_MENU, callback_data=f"question_menu:{test_id}:{index}")])
    return InlineKeyboardMarkup(rows)


def next_keyboard(test_id: str, index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_NEXT, callback_data=f"next_question:{test_id}:{index}")],
        [InlineKeyboardButton(BTN_MENU, callback_data=f"question_menu:{test_id}:{index}")],
    ])



def question_menu_keyboard(test_id: str, index: int, mode: str | None = None) -> InlineKeyboardMarkup:
    if mode in RESUMABLE_MODES:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(BTN_CONTINUE, callback_data=f"question_continue:{test_id}:{index}")],
            [InlineKeyboardButton(BTN_SAVE_EXIT, callback_data=f"pause_to_menu:{test_id}")],
            [InlineKeyboardButton(BTN_FINISH, callback_data="finish")],
        ])

    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_CONTINUE, callback_data=f"question_continue:{test_id}:{index}")],
        [InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"pause_to_menu:{test_id}")],
    ])

def after_finish_keyboard(user_id: int, state: dict[str, Any]) -> InlineKeyboardMarkup:
    test_id = state.get("test_id")
    if not test_id:
        return InlineKeyboardMarkup([])

    if state.get("mode") == "errors":
        rows = []
        if state.get("wrong_answers"):
            rows.append([InlineKeyboardButton("🔁 Заново", callback_data=f"repeat_session_errors:{test_id}")])
        rows.append([InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")])
        return InlineKeyboardMarkup(rows)

    rows = []
    if state.get("wrong_answers"):
        rows.append([InlineKeyboardButton("👀 Посмотреть ошибки", callback_data=f"session_error_show:{test_id}:0")])
    rows.append([InlineKeyboardButton("🔁 Повторить тест", callback_data=f"solve_menu:{test_id}")])
    rows.append([InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)


def session_error_keyboard(test_id: str, pos: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if pos > 0:
        nav.append(InlineKeyboardButton("↩️ Предыдущий", callback_data=f"session_error_show:{test_id}:{pos - 1}"))
    if pos + 1 < total:
        nav.append(InlineKeyboardButton(BTN_NEXT, callback_data=f"session_error_show:{test_id}:{pos + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("📋 К результату", callback_data=f"show_result:{test_id}")])
    rows.append([InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")])
    return InlineKeyboardMarkup(rows)


def stats_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")]])



def reset_errors_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Да, сбросить ошибки", callback_data=f"reset_errors_confirm:{test_id}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"learn_menu:{test_id}")],
    ])

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
    if current - LAST_START_AT.get(chat_id, 0) < 1.5:
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


# ============================================================
# USER CALLBACKS
# ============================================================

def test_main_text(user_id: int, test_id: str) -> str:
    title = TESTS[test_id]["title"]
    total = len(get_questions(test_id))
    errors = len(get_all_time_error_indices(user_id, test_id))
    return f"{title}\n\nВопросов: {total}\nОшибок для разбора: {errors}"


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
    await query.edit_message_text(test_main_text(query.from_user.id, test_id), reply_markup=test_main_keyboard(test_id))



async def handle_learn_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")

    await query.edit_message_text(
        learn_menu_text(query.from_user.id, test_id),
        reply_markup=learn_menu_keyboard(test_id),
    )

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

    order = list(range(len(get_questions(test_id))))
    if mode == "random":
        random.shuffle(order)

    state = get_state(query.message.chat_id)
    start_quiz_mode(state, query.from_user.id, test_id, mode, order)
    index = state["order"][state["pos"]]

    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
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
        await query.edit_message_text(
            learn_menu_text(query.from_user.id, test_id),
            reply_markup=learn_menu_keyboard(test_id),
        )
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
    state = get_state(query.message.chat_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=test_select_keyboard())
        return
    if state.get("awaiting_next"):
        await query.answer("Нажми «Следующий»")
        return
    if state.get("test_id") != test_id or state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    correct_index = int(get_questions(test_id)[index]["correct_index"])
    is_correct = selected == correct_index

    record_answer(query.from_user.id, test_id, is_correct)
    state["total"] += 1

    if is_correct:
        state["correct"] += 1
        remove_all_time_error(query.from_user.id, test_id, index)

        # Старый вопрос остаётся в чате без кнопок.
        await query.edit_message_text(
            build_question_text(index, state, selected_index=selected, show_correct=True),
            parse_mode="HTML",
        )

        state["pos"] += 1

        if state["pos"] >= len(state["order"]):
            state["active"] = False
            finish_attempt_if_needed(query.from_user.id, state)
            await query.message.reply_text(
                result_text(state, query.from_user.id),
                reply_markup=after_finish_keyboard(query.from_user.id, state),
            )
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
    state = get_state(query.message.chat_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=test_select_keyboard())
        return
    if state.get("awaiting_next"):
        await query.answer("Нажми «Следующий»")
        return
    if state.get("test_id") != test_id or state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    record_answer(query.from_user.id, test_id, False)
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
    state = get_state(query.message.chat_id)

    if not state.get("active"):
        await query.edit_message_text("Этот режим уже завершён.", reply_markup=after_finish_keyboard(query.from_user.id, state))
        return
    if not state.get("awaiting_next"):
        await query.answer("Следующий вопрос уже открыт")
        return
    if state.get("test_id") != test_id or state.get("pos", 0) >= len(state.get("order", [])) or state["order"][state["pos"]] != index:
        await query.answer("Этот вопрос уже обработан")
        return

    # У старого вопроса исчезают кнопки.
    await query.edit_message_reply_markup(reply_markup=None)

    state["awaiting_next"] = False
    state["pos"] += 1

    if state["pos"] >= len(state["order"]):
        state["active"] = False
        finish_attempt_if_needed(query.from_user.id, state)
        await query.message.reply_text(
            result_text(state, query.from_user.id),
            reply_markup=after_finish_keyboard(query.from_user.id, state),
        )
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

    state = get_state(query.message.chat_id)
    await query.edit_message_reply_markup(
        reply_markup=question_menu_keyboard(test_id, int(index_str), state.get("mode"))
    )

async def handle_question_continue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, _index_str = query.data.split(":")
    state = get_state(query.message.chat_id)

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
    state = get_state(query.message.chat_id)

    if state.get("test_id") == test_id:
        state["active"] = False

        # Только попытка из "Решать" попадает в продолжение.
        # Работа над ошибками не стирает сохранённую обычную попытку.
        if state.get("mode") in RESUMABLE_MODES:
            save_active_session(query.from_user.id, state)

    await query.edit_message_text(test_main_text(query.from_user.id, test_id), reply_markup=test_main_keyboard(test_id))

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
    await query.edit_message_text(
        result_text(state, query.from_user.id, finished_by_user=True),
        reply_markup=after_finish_keyboard(query.from_user.id, state),
    )


async def finish_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    state = get_state(update.effective_chat.id)

    if not state.get("test_id"):
        await update.message.reply_text("Сейчас нет активного режима.", reply_markup=test_select_keyboard())
        return

    state["active"] = False
    state["awaiting_next"] = False
    finish_attempt_if_needed(update.effective_user.id, state, finished_by_user=True)
    await update.message.reply_text(
        result_text(state, update.effective_user.id, finished_by_user=True),
        reply_markup=after_finish_keyboard(update.effective_user.id, state),
    )


async def handle_session_error_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id, pos_str = query.data.split(":")

    state = get_state(query.message.chat_id)
    items = state.get("wrong_answers", [])
    if not items:
        items = get_attempt_wrong_answers(query.from_user.id, test_id, state.get("attempt_id"))

    if not items:
        await query.edit_message_text("Ошибок в этом решении нет.", reply_markup=test_main_keyboard(test_id))
        return

    pos = max(0, min(int(pos_str), len(items) - 1))
    await query.edit_message_text(
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
        await query.edit_message_text("Результат недоступен.", reply_markup=test_main_keyboard(test_id))
        return

    await query.edit_message_text(result_text(state, query.from_user.id), reply_markup=after_finish_keyboard(query.from_user.id, state))


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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(BTN_TEST_MENU, callback_data=f"test_menu:{test_id}")]]),
        )
        return

    start_quiz_mode(state, query.from_user.id, test_id, "errors", order)
    index = state["order"][state["pos"]]
    await query.edit_message_text(
        build_question_text(index, state),
        reply_markup=answer_keyboard(test_id, index),
        parse_mode="HTML",
    )


async def handle_my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    _, test_id = query.data.split(":")
    await query.edit_message_text(my_stats_text(query.from_user.id, test_id), reply_markup=stats_keyboard(test_id))



async def handle_reset_errors_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer("Ошибки сброшены")

    _, test_id = query.data.split(":")
    clear_all_time_errors(query.from_user.id, test_id)

    await query.edit_message_text(
        learn_menu_text(query.from_user.id, test_id),
        reply_markup=learn_menu_keyboard(test_id),
    )

def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Выбрать тест", callback_data="admin:tests")],
        [InlineKeyboardButton("📊 Общая сводка", callback_data="admin:summary")],
        [InlineKeyboardButton("📤 Экспорт всех данных", callback_data="admin:export_all")],
    ])


def admin_tests_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:test:{test_id}")] for test_id, info in TESTS.items()]
    rows.append([InlineKeyboardButton("⬅️ Назад в админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_test_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📈 Статистика по тесту", callback_data=f"admin:test_stats:{test_id}")],
        [InlineKeyboardButton("🏆 Рейтинг топ-10", callback_data=f"admin:rating:{test_id}")],
        [InlineKeyboardButton("👥 Пользователи", callback_data=f"admin:test_users:{test_id}")],
        [InlineKeyboardButton("🧠 Частые ошибки", callback_data=f"admin:frequent_errors:{test_id}")],
        [InlineKeyboardButton("📤 Экспорт по тесту", callback_data=f"admin:export_test:{test_id}")],
        [InlineKeyboardButton("⬅️ Назад к тестам", callback_data="admin:tests")],
    ])


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Нет доступа.")
        return
    await update.message.reply_text("Админ-панель", reply_markup=admin_main_keyboard())


async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    await query.edit_message_text("Админ-панель", reply_markup=admin_main_keyboard())


async def handle_admin_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    await query.edit_message_text("Выбери тест:", reply_markup=admin_tests_keyboard())


async def handle_admin_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(TESTS[test_id]["title"], reply_markup=admin_test_keyboard(test_id))


async def handle_admin_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return

    with db_connect() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        attempts = conn.execute("SELECT COUNT(*) AS c FROM attempts").fetchone()["c"]
        finished = conn.execute("SELECT COUNT(*) AS c FROM attempts WHERE finished_at IS NOT NULL").fetchone()["c"]
        answered = conn.execute("SELECT COALESCE(SUM(answered), 0) AS c FROM attempts").fetchone()["c"]

    text = (
        "📊 Общая сводка\n\n"
        f"👥 Пользователей: {users}\n"
        f"📝 Попыток начато: {attempts}\n"
        f"✅ Попыток завершено: {finished}\n"
        f"🔢 Ответов в попытках: {answered}"
    )
    await query.edit_message_text(text, reply_markup=admin_main_keyboard())


async def handle_admin_test_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    _, _, test_id = query.data.split(":")

    with db_connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT user_id) AS users,
                COUNT(*) AS attempts,
                SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished,
                COALESCE(SUM(answered), 0) AS answered,
                COALESCE(SUM(correct), 0) AS correct
            FROM attempts
            WHERE test_id = ?
            """,
            (test_id,),
        ).fetchone()

    answered = row["answered"] or 0
    correct = row["correct"] or 0
    percent = round(correct / answered * 100, 1) if answered else 0

    text = (
        f"📈 Статистика по тесту\n{TESTS[test_id]['title']}\n\n"
        f"👥 Пользователей: {row['users'] or 0}\n"
        f"📝 Попыток: {row['attempts'] or 0}\n"
        f"✅ Завершено: {row['finished'] or 0}\n"
        f"🔢 Ответов: {answered}\n"
        f"📊 Правильность: {percent}%"
    )
    await query.edit_message_text(text, reply_markup=admin_test_keyboard(test_id))


async def handle_admin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    _, _, test_id = query.data.split(":")

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT a.*, u.username, u.first_name, u.last_name
            FROM attempts a
            LEFT JOIN users u ON u.user_id = a.user_id
            WHERE a.test_id = ? AND a.finished_at IS NOT NULL AND a.answered > 0
            ORDER BY
                a.answered DESC,
                (CAST(a.correct AS REAL) / NULLIF(a.answered, 0)) DESC,
                a.duration_seconds ASC
            LIMIT 10
            """,
            (test_id,),
        ).fetchall()

    lines = [f"🏆 Рейтинг топ-10\n{TESTS[test_id]['title']}\n"]
    if not rows:
        lines.append("Пока нет результатов.")
    else:
        for n, row in enumerate(rows, start=1):
            percent = round(row["correct"] / row["answered"] * 100, 1)
            lines.append(
                f"{n}. {user_display_name(row)} — {percent}% · "
                f"{seconds_to_text(row['duration_seconds'])} · {row['answered']} из {len(get_questions(test_id))}"
            )

    await query.edit_message_text("\n".join(lines), reply_markup=admin_test_keyboard(test_id))


async def handle_admin_test_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    _, _, test_id = query.data.split(":")

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT u.*
            FROM users u
            JOIN attempts a ON a.user_id = u.user_id
            WHERE a.test_id = ?
            ORDER BY u.last_seen_at DESC
            LIMIT 30
            """,
            (test_id,),
        ).fetchall()

    lines = [f"👥 Пользователи\n{TESTS[test_id]['title']}\n"]
    if not rows:
        lines.append("Пока нет пользователей.")
    else:
        for row in rows:
            lines.append(f"• {user_display_name(row)} — ID {row['user_id']}")

    await query.edit_message_text("\n".join(lines), reply_markup=admin_test_keyboard(test_id))


async def handle_admin_frequent_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    _, _, test_id = query.data.split(":")

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

    lines = [f"🧠 Частые ошибки\n{TESTS[test_id]['title']}\n"]
    if not rows:
        lines.append("Ошибок пока нет.")
    else:
        questions = get_questions(test_id)
        for n, row in enumerate(rows, start=1):
            q = questions[int(row["question_index"])]["question"]
            short = q[:120] + ("…" if len(q) > 120 else "")
            lines.append(f"{n}. {row['c']} раз — {short}")

    await query.edit_message_text("\n".join(lines), reply_markup=admin_test_keyboard(test_id))


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


async def handle_admin_export_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    path = export_csv(None)
    await query.message.reply_document(InputFile(path), caption="📤 Экспорт всех данных")


async def handle_admin_export_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return
    _, _, test_id = query.data.split(":")
    path = export_csv(test_id)
    await query.message.reply_document(InputFile(path), caption=f"📤 Экспорт по тесту: {TESTS[test_id]['title']}")


# ============================================================
# APP
# ============================================================

def main() -> None:
    init_db()
    keep_alive()

    if not BOT_TOKEN:
        raise RuntimeError("Не найден токен. Добавь TELEGRAM_BOT_TOKEN в Render или впиши BOT_TOKEN в код.")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_bot_commands).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tests", tests_command))
    app.add_handler(CommandHandler("finish", finish_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("reset_errors", reset_errors_command))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_command))

    # User callbacks
    app.add_handler(CallbackQueryHandler(handle_tests_menu, pattern=r"^tests:menu$"))
    app.add_handler(CallbackQueryHandler(handle_test_menu, pattern=r"^test_menu:"))
    app.add_handler(CallbackQueryHandler(handle_learn_menu, pattern=r"^learn_menu:"))
    app.add_handler(CallbackQueryHandler(handle_solve_menu, pattern=r"^solve_menu:"))
    app.add_handler(CallbackQueryHandler(handle_start_quiz, pattern=r"^start:"))
    app.add_handler(CallbackQueryHandler(handle_mini_start, pattern=r"^mini_start:"))
    app.add_handler(CallbackQueryHandler(handle_errors_solve, pattern=r"^errors_solve:"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(handle_show_answer, pattern=r"^show_answer:"))
    app.add_handler(CallbackQueryHandler(handle_next_question, pattern=r"^next_question:"))
    app.add_handler(CallbackQueryHandler(handle_question_menu, pattern=r"^question_menu:"))
    app.add_handler(CallbackQueryHandler(handle_question_continue, pattern=r"^question_continue:"))
    app.add_handler(CallbackQueryHandler(handle_pause_to_menu, pattern=r"^pause_to_menu:"))
    app.add_handler(CallbackQueryHandler(handle_continue_session, pattern=r"^continue_session:"))
    app.add_handler(CallbackQueryHandler(handle_finish_button, pattern=r"^finish$"))
    app.add_handler(CallbackQueryHandler(handle_session_error_show, pattern=r"^session_error_show:"))
    app.add_handler(CallbackQueryHandler(handle_show_result, pattern=r"^show_result:"))
    app.add_handler(CallbackQueryHandler(handle_repeat_session_errors, pattern=r"^repeat_session_errors:"))
    app.add_handler(CallbackQueryHandler(handle_my_stats, pattern=r"^my_stats:"))
    app.add_handler(CallbackQueryHandler(handle_public_rating, pattern=r"^public_rating:"))
    app.add_handler(CallbackQueryHandler(handle_reset_errors_confirm, pattern=r"^reset_errors_confirm:"))

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(handle_admin_menu, pattern=r"^admin:menu$"))
    app.add_handler(CallbackQueryHandler(handle_admin_tests, pattern=r"^admin:tests$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_menu, pattern=r"^admin:test:"))
    app.add_handler(CallbackQueryHandler(handle_admin_summary, pattern=r"^admin:summary$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_stats, pattern=r"^admin:test_stats:"))
    app.add_handler(CallbackQueryHandler(handle_admin_rating, pattern=r"^admin:rating:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_users, pattern=r"^admin:test_users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_frequent_errors, pattern=r"^admin:frequent_errors:"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_all, pattern=r"^admin:export_all$"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_test, pattern=r"^admin:export_test:"))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
