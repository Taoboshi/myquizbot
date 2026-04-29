import os
from threading import Thread
from typing import Any

from flask import Flask

WEB_APP = Flask(__name__)
USER_STATE: dict[int, dict[str, Any]] = {}
LAST_START_AT: dict[int, float] = {}


@WEB_APP.route("/")
def home() -> str:
    return "OZIZ quiz bot is running!"


def keep_alive() -> None:
    port = int(os.environ.get("PORT", 8080))
    Thread(target=lambda: WEB_APP.run(host="0.0.0.0", port=port), daemon=True).start()
