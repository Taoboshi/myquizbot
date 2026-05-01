import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "quiz_progress.sqlite3")))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

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
FULL_TEST_MODES = {"normal", "random", "reverse", "from_number"}
SOLUTION_MODES = ("normal", "random", "reverse", "from_number")
FIND_PAGE_SIZE = 10
ADMIN_USERS_PAGE_SIZE = 10

# Time display settings.
# Database timestamps are treated as UTC and shown to users/admins in this timezone.
APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"
APP_TIMEZONE_LABEL = os.getenv("APP_TIMEZONE_LABEL", "МСК").strip() or "МСК"
