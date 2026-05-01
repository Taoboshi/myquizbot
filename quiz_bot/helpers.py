import os
import sqlite3
from typing import Any

from .config import get_env_admin_ids

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _display_timezone() -> ZoneInfo:
    tz_name = os.getenv("APP_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Moscow")


def display_timezone_label() -> str:
    return os.getenv("APP_TIMEZONE_LABEL", "МСК").strip() or "МСК"


def format_app_datetime(value, *, with_label: bool = True) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return "—"
        raw = raw.replace("T", " ")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    dt = None
            if dt is None:
                return raw
    if dt.tzinfo is None:
        # DB timestamps are written in UTC by SQLite/PostgreSQL defaults.
        dt = dt.replace(tzinfo=timezone.utc)
    formatted = dt.astimezone(_display_timezone()).strftime("%d.%m.%Y %H:%M")
    if with_label:
        return f"{formatted} {display_timezone_label()}"
    return formatted


def format_moscow_datetime(value) -> str:
    # Backward-compatible name used by older screens.
    return format_app_datetime(value, with_label=False)


def format_display_datetime(value) -> str:
    return format_app_datetime(value, with_label=True)


def short_question_text(text: str, limit: int = 95) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


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
        "repeat_attempt": "Повтор попытки",
        "view": "Просмотр",
    }.get(mode or "", "Тест")

def get_admin_ids() -> set[int]:
    return get_env_admin_ids()

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
