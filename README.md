# Telegram Quiz Bot

Бот для Telegram-викторин с JSON-тестами, статистикой, ошибками, избранным, доступами и админ-панелью.

## Быстрый запуск локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполни TELEGRAM_BOT_TOKEN и TELEGRAM_ADMIN_IDS
python telegram_quiz_bot.py
```

Для локальной разработки без `DATABASE_URL` используется SQLite-файл `quiz_progress.sqlite3`. Для Render/production используй PostgreSQL/Neon через `DATABASE_URL`.

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | токен бота из BotFather |
| `TELEGRAM_ADMIN_IDS` | один или несколько Telegram ID админов через запятую |
| `DATABASE_URL` | PostgreSQL URL для production |
| `DB_PATH` | путь к SQLite-файлу, если PostgreSQL не используется |
| `APP_TIMEZONE` | таймзона отображения дат |
| `APP_TIMEZONE_LABEL` | подпись таймзоны в интерфейсе |
| `BOT_CONCURRENT_UPDATES` | параллельная обработка апдейтов |

## Тесты-вопросы

JSON-файлы лежат в папке `tests/`. Поддерживается список вопросов или объект с полем `questions`. Минимальный формат вопроса:

```json
{
  "question": "Текст вопроса",
  "options": ["A", "B", "C"],
  "correct_index": 0
}
```

Также поддерживаются алиасы `text`, `answers`, `variants`, `answer`, `correct`.

## Проверка проекта перед деплоем

```bash
python scripts/validate_project.py
python -m compileall -q quiz_bot scripts

# опционально
pip install -r requirements-dev.txt
python -m pytest -q
```

`validate_project.py` проверяет синтаксис всех Python-файлов, таблицы callback-маршрутов, загрузку JSON-тестов, SQLite-схему и базовую запись статистики.

## Структура кода

Ключевые модули:

- `quiz_bot/app.py` — сборка приложения, polling и общий обработчик ошибок.
- `quiz_bot/user_routes.py` — регистрация пользовательских команд и callback-ов.
- `quiz_bot/admin_routes.py` — регистрация админских команд, guard-ов, рассылки и callback-ов.
- `quiz_bot/admin.py` — совместимый фасад для старых импортов.
- `quiz_bot/admin_core.py` — базовые тексты, клавиатуры, сводки, экспорт и обзор тестов.
- `quiz_bot/admin_users.py` — пользователи, блокировки, рассылка и сброс прогресса.
- `quiz_bot/admin_tools.py` — сервисные экраны, доступы, метаданные тестов и разделы.
- `quiz_bot/admin_handlers.py` — Telegram-handlers админки.
- `quiz_bot/storage.py` — SQLite/PostgreSQL слой хранения.
- `quiz_bot/loader.py` — загрузка и нормализация JSON-тестов.

## Render

В `render.yaml` уже задан запуск:

```bash
python telegram_quiz_bot.py
```

Перед деплоем обязательно добавь в Render Environment Variables:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ADMIN_IDS`
- `DATABASE_URL`

Без `DATABASE_URL` Render будет использовать SQLite, что подходит только для временного теста.
