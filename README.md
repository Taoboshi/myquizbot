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

`validate_project.py` проверяет загрузку JSON-тестов, SQLite-схему и базовую запись статистики.

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
