import os
from threading import Thread
from typing import Any

from flask import Flask

WEB_APP = Flask(__name__)
USER_STATE: dict[int, dict[str, Any]] = {}
LAST_START_AT: dict[int, float] = {}
_SERVER_STARTED = False


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
