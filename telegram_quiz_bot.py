import json
import os
import sqlite3
import html
from pathlib import Path
from threading import Thread
from flask import Flask # Библиотека для веб-сервера
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes

# --- 1. Настройка "Анти-сна" для Render ---
app = Flask('')

@app.route('/')
def home():
    return "Бот работает!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- 2. Настройки бота ---
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "quiz_progress.sqlite3"

def load_available_tests():
    tests = {}
    for file in BASE_DIR.glob("*.json"):
        try:
            with file.open("r", encoding="utf-8") as f:
                data = json.load(f)
                test_id = file.stem
                tests[test_id] = {
                    "title": test_id.replace("_", " ").capitalize(),
                    "data": data
                }
        except Exception as e:
            print(f"Ошибка загрузки {file.name}: {e}")
    return tests

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS results (user_id INTEGER, test_id TEXT, score INTEGER, total INTEGER, end_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tests = load_available_tests()
    keyboard = []
    for tid, info in tests.items():
        keyboard.append([InlineKeyboardButton(info["title"], callback_query_data=f"select_test:{tid}")])
    
    if not keyboard:
        await update.message.reply_text("❌ JSON файлы не найдены!")
        return
    await update.message.reply_text("Выберите тест:", reply_markup=InlineKeyboardMarkup(keyboard))

# --- 3. ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    
    # Сначала запускаем веб-сервер "будильник"
    print("Запуск системы анти-сна...")
    keep_alive()
    
    # Затем запускаем самого бота
    TOKEN = "8643995860:AAFLNEOyxmZ_6pW189R59A8vI8D73pS0Z9A"
    print("Запуск Telegram бота...")
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    # Здесь бот начинает "слушать" Telegram и блокирует дальнейшее выполнение кода
    application.run_polling()