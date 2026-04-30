import json
from typing import Any

from .config import RESUMABLE_MODES
from .loader import get_questions
from .runtime import USER_STATE
from .storage import db_connect, record_attempt_start

RUNTIME_MODES = set(RESUMABLE_MODES) | {"mini", "errors"}
_RUNTIME_TABLE_READY = False


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


def _ensure_runtime_sessions_table() -> None:
    global _RUNTIME_TABLE_READY

    if _RUNTIME_TABLE_READY:
        return

    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_sessions (
                user_id BIGINT NOT NULL,
                test_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, test_id, mode)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS runtime_sessions_user_test_idx
            ON runtime_sessions (user_id, test_id, updated_at)
            """
        )
        conn.commit()

    _RUNTIME_TABLE_READY = True


def _valid_session_data(data: dict[str, Any], *, runtime: bool) -> bool:
    mode = data.get("mode")
    if mode not in (RUNTIME_MODES if runtime else RESUMABLE_MODES):
        return False
    if data.get("finish_recorded"):
        return False

    order = data.get("order") or []
    pos = int(data.get("pos", 0))
    if not order or pos < 0 or pos >= len(order):
        return False

    return True


def save_runtime_session(user_id: int, state: dict[str, Any]) -> None:
    test_id = state.get("test_id")
    mode = state.get("mode")

    if not test_id or mode not in RUNTIME_MODES:
        return
    if not state.get("active"):
        return
    if state.get("finish_recorded") or not state.get("order"):
        return

    _ensure_runtime_sessions_table()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO runtime_sessions (user_id, test_id, mode, state_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, test_id, mode)
            DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, test_id, mode, json.dumps(state_for_db(state), ensure_ascii=False)),
        )
        conn.commit()


def delete_runtime_session(user_id: int, test_id: str | None, mode: str | None = None) -> None:
    if not test_id:
        return

    _ensure_runtime_sessions_table()
    with db_connect() as conn:
        if mode:
            conn.execute(
                "DELETE FROM runtime_sessions WHERE user_id = ? AND test_id = ? AND mode = ?",
                (user_id, test_id, mode),
            )
        else:
            conn.execute(
                "DELETE FROM runtime_sessions WHERE user_id = ? AND test_id = ?",
                (user_id, test_id),
            )
        conn.commit()


def _runtime_candidates(user_id: int, test_id: str) -> list[dict[str, Any]]:
    _ensure_runtime_sessions_table()
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT state_json
            FROM runtime_sessions
            WHERE user_id = ? AND test_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id, test_id),
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row["state_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if _valid_session_data(data, runtime=True):
            items.append(data)
    return items


def load_runtime_session_for_question(user_id: int, test_id: str, question_index: int) -> dict[str, Any] | None:
    for data in _runtime_candidates(user_id, test_id):
        order = data.get("order") or []
        pos = int(data.get("pos", 0))
        if pos < len(order) and int(order[pos]) == question_index:
            return data
    return None


def load_latest_runtime_session(user_id: int, test_id: str) -> dict[str, Any] | None:
    candidates = _runtime_candidates(user_id, test_id)
    return candidates[0] if candidates else None


def save_active_session(user_id: int, state: dict[str, Any]) -> None:
    test_id = state.get("test_id")
    mode = state.get("mode")

    save_runtime_session(user_id, state)

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

    if not _valid_session_data(data, runtime=False):
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
    delete_runtime_session(user_id, test_id, mode)

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
