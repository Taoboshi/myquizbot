import os
import time
from threading import Thread
from typing import Any

try:
    from flask import Flask
    WEB_APP = Flask(__name__)
except ImportError:
    Flask = None

    class _DummyApp:
        def route(self, *args, **kwargs):
            return lambda fn: fn

        def run(self, *args, **kwargs):
            pass

    WEB_APP = _DummyApp()
USER_STATE: dict[int, dict[str, Any]] = {}
USER_STATE_LAST_ACCESSED: dict[int, float] = {}
LAST_START_AT: dict[int, float] = {}
LAST_CALLBACK_AT: dict[tuple[int, str], float] = {}
_SERVER_STARTED = False

import hashlib

STATE_TTL_SECONDS = int(os.getenv("USER_STATE_TTL_SECONDS", "86400"))  # 24 hours
CALLBACK_DEBOUNCE_SECONDS = float(os.getenv("CALLBACK_DEBOUNCE_SECONDS", "0.35"))

_CALLBACK_STORE: dict[str, str] = {}
_CALLBACK_STORE_ORDER: list[str] = []
_MAX_CALLBACK_STORE = 1000


def safe_callback(data: str) -> str:
    """Ensure callback_data is <= 64 bytes for Telegram inline buttons.
    If longer, store full data and return a compact token 'cbe:<hash>'.
    """
    if not data:
        return ""
    data_bytes = str(data).encode("utf-8")
    if len(data_bytes) <= 64:
        return str(data)

    token_hash = hashlib.sha256(data_bytes).hexdigest()[:12]
    token = f"cbe:{token_hash}"
    if token not in _CALLBACK_STORE:
        _CALLBACK_STORE[token] = str(data)
        _CALLBACK_STORE_ORDER.append(token)
        if len(_CALLBACK_STORE_ORDER) > _MAX_CALLBACK_STORE:
            oldest = _CALLBACK_STORE_ORDER.pop(0)
            _CALLBACK_STORE.pop(oldest, None)
        try:
            from .storage import save_callback_cache
            save_callback_cache(token, str(data))
        except Exception:
            pass
    return token


def unpack_callback(data: str) -> str:
    """If callback is a packed token 'cbe:<hash>', retrieve the original callback data."""
    if data and data.startswith("cbe:"):
        res = _CALLBACK_STORE.get(data)
        if not res:
            try:
                from .storage import get_callback_cache
                res = get_callback_cache(data)
                if res:
                    _CALLBACK_STORE[data] = res
            except Exception:
                pass
        return res or data
    return data


def is_duplicate_callback(user_id: int, callback_data: str) -> bool:
    """Return True if user pressed the exact same callback within debounce threshold."""
    now = time.time()
    key = (user_id, callback_data)
    last = LAST_CALLBACK_AT.get(key, 0.0)
    if now - last < CALLBACK_DEBOUNCE_SECONDS:
        return True
    LAST_CALLBACK_AT[key] = now
    # Periodic small cleanup of old debounce keys if dictionary grows
    if len(LAST_CALLBACK_AT) > 5000:
        threshold = now - 10.0
        to_del = [k for k, t in LAST_CALLBACK_AT.items() if t < threshold]
        for k in to_del:
            LAST_CALLBACK_AT.pop(k, None)
    return False


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
