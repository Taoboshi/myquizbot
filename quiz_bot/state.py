import json
from typing import Any

from .config import RESUMABLE_MODES
from .loader import get_questions
from .runtime import USER_STATE
from .storage import db_connect, record_attempt_start

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
            "pending_start_from_number_test_id": None,
            "find_mode": None,
            "find_test_id": None,
            "find_query": None,
            "find_result_indices": None,
        }
    return USER_STATE[chat_id]

def clear_text_waiting_state(state: dict[str, Any]) -> None:
    state["pending_start_from_number_test_id"] = None
    state["find_mode"] = None
    state["find_test_id"] = None

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
        conn.execute("DELETE FROM active_sessions WHERE user_id = ? AND test_id = ?", (user_id, test_id))
        conn.commit()

def load_active_session(user_id: int, test_id: str) -> dict[str, Any] | None:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT state_json FROM active_sessions WHERE user_id = ? AND test_id = ?",
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
        "pending_start_from_number_test_id": None,
        "find_mode": None,
    })
    save_active_session(user_id, state)
