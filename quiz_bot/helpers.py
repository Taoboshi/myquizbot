import os
import sqlite3
from typing import Any

from .config import ADMIN_IDS

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
        "reverse": "С конца",
        "from_number": "С номера",
        "mini": "Тренировка",
        "errors": "Разбор ошибок",
        "view": "Просмотр",
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
    user_id = row["user_id"]
    username = (row["username"] or "").strip()
    first = (row["first_name"] or "").strip()
    last = (row["last_name"] or "").strip()

    name_parts = [part for part in [first, last] if part and part != "*"]
    full = " ".join(name_parts).strip()

    if username and full:
        return f"{full} (@{username})"
    if username:
        return f"@{username}"
    if full:
        return full
    return f"Без имени — ID {user_id}"

def attempt_percent(attempt: sqlite3.Row | None) -> float:
    if not attempt or not attempt["answered"]:
        return 0.0
    return round(attempt["correct"] / attempt["answered"] * 100, 1)
