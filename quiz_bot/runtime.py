import os
from threading import Thread
from typing import Any

from flask import Flask

import time

WEB_APP = Flask(__name__)
USER_STATE: dict[int, dict[str, Any]] = {}
USER_STATE_LAST_ACCESSED: dict[int, float] = {}
LAST_START_AT: dict[int, float] = {}
_SERVER_STARTED = False

STATE_TTL_SECONDS = int(os.getenv("USER_STATE_TTL_SECONDS", "86400"))  # 24 hours


def touch_user_state(chat_id: int) -> None:
    USER_STATE_LAST_ACCESSED[chat_id] = time.time()


def cleanup_expired_user_state() -> int:
    """Removes in-memory states that have been inactive longer than STATE_TTL_SECONDS."""
    now = time.time()
    expired = [
        cid for cid, last_time in list(USER_STATE_LAST_ACCESSED.items())
        if now - last_time > STATE_TTL_SECONDS
    ]
    for cid in expired:
        USER_STATE.pop(cid, None)
        USER_STATE_LAST_ACCESSED.pop(cid, None)
        LAST_START_AT.pop(cid, None)
    return len(expired)


@WEB_APP.route("/")
def home() -> str:
    return "OZIZ quiz bot is running!"


@WEB_APP.route("/healthz")
def healthz() -> tuple[str, int]:
    return "ok", 200


def keep_alive() -> None:
    global _SERVER_STARTED

    if _SERVER_STARTED:
        return

    port = int(os.environ.get("PORT", 8080))
    thread = Thread(
        target=lambda: WEB_APP.run(
            host="0.0.0.0",
            port=port,
            use_reloader=False,
        ),
        daemon=True,
    )
    thread.start()
    _SERVER_STARTED = True
