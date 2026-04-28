Telegram-бот ОЗИЗ модуль 2 — готовая версия для локального запуска / Render

Что внутри:
- telegram_quiz_bot.py — полный код бота
- questions_first_test_corrected.json — 203 вопроса
- requirements.txt — зависимости
- render.yaml — конфиг для Render
- CHANGES_RU.txt — список изменений

Важно:
- Токен вставлен прямо в telegram_quiz_bot.py в переменную BOT_TOKEN.
- Для админ-панели впиши свой Telegram ID в ADMIN_IDS в начале telegram_quiz_bot.py.
  Пример:
  ADMIN_IDS = {123456789}

Как узнать Telegram ID:
1. Запусти бота.
2. Напиши ему /myid.
3. Скопируй число.
4. Вставь его в ADMIN_IDS.
5. Перезапусти бота.

Локальный запуск на Windows:
1. Открой PowerShell в папке с ботом.
2. Установи зависимости:
   pip install -r requirements.txt
3. Запусти:
   python telegram_quiz_bot.py

Запуск на Render через GitHub:
1. Загрузи эти файлы в GitHub-репозиторий.
2. В Render создай New Web Service.
3. Подключи GitHub-репозиторий.
4. Build Command:
   pip install -r requirements.txt
5. Start Command:
   python telegram_quiz_bot.py

Для UptimeRobot:
- После запуска Render даст ссылку вида https://....onrender.com
- Добавь эту ссылку в UptimeRobot как HTTP monitor.
- Бот отвечает на главной странице текстом:
  OZIZ bot is running!

Функции бота:
- Учить тест
- Сложные вопросы
- Решать тест по порядку / вразброс
- Мини-тренировка 10/20/50 вопросов
- Только сложные / только ошибки
- Работа над ошибками
- Моя статистика
- Админ-панель
- Рейтинг топ-10
- Частые ошибки
- Экспорт CSV
