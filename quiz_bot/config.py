import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "quiz_progress.sqlite3")))


def get_bot_token(*, required: bool = False) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if required and not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def parse_int_set(raw: str | None) -> set[int]:
    result: set[int] = set()
    for part in str(raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.add(int(part))
        except ValueError:
            continue
    return result


def get_env_admin_ids() -> set[int]:
    ids: set[int] = set()
    for env_name in ("TELEGRAM_ADMIN_IDS", "TELEGRAM_ADMIN_ID", "ADMIN_IDS"):
        ids.update(parse_int_set(os.getenv(env_name)))
    return ids


# Backward-compatible constants. Runtime code should prefer get_bot_token()/get_admin_ids().
BOT_TOKEN = get_bot_token(required=False)
ADMIN_IDS = frozenset(get_env_admin_ids())

SUBJECTS = {}

TESTS = {
    "oziz_module_2": {
        "file": "tests/oziz_module_2.json",
    },
}

LETTERS = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К"]

BTN_SHOW_ANSWER = "💡 Показать ответ"
BTN_MENU = "🏛️ Меню"
BTN_NEXT = "➡️ Следующий"
BTN_CONTINUE = "▶️ Продолжить"
BTN_SAVE_EXIT = "💾 Сохранить и выйти"
BTN_FINISH = "🎯 Завершить"
BTN_TEST_MENU = "🏛️ К меню теста"
BTN_BACK = "⬅️ Назад"

RESUMABLE_MODES = {"normal", "random", "reverse", "from_number"}
FULL_TEST_MODES = {"normal", "random", "reverse", "from_number"}
SOLUTION_MODES = ("normal", "random", "reverse", "from_number")
FIND_PAGE_SIZE = 10
ADMIN_USERS_PAGE_SIZE = 10

# Time display settings.
# Database timestamps are treated as UTC and shown to users/admins in this timezone.
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
APP_TIMEZONE_LABEL = os.getenv("APP_TIMEZONE_LABEL", "МСК").strip() or "МСК"
