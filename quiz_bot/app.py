import logging
import time

from telegram import Update
from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from . import admin as admin_handlers
from . import handlers as user_handlers
from .config import BOT_TOKEN
from .runtime import keep_alive
from .storage import init_db

try:
    from .storage import acquire_polling_lock, release_polling_lock
except Exception:  # pragma: no cover
    def acquire_polling_lock() -> None:
        return None

    def release_polling_lock() -> None:
        return None


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log callback/command errors and show a short message to the user."""
    logger.exception("Unhandled Telegram update error", exc_info=context.error)

    if not isinstance(update, Update):
        return

    query = update.callback_query
    if query:
        try:
            await query.answer("Произошла ошибка. Нажми /start.", show_alert=True)
        except Exception:
            logger.exception("Failed to answer callback after error")
        return

    message = update.effective_message
    if message:
        try:
            await message.reply_text("Произошла ошибка. Нажми /start.")
        except Exception:
            logger.exception("Failed to send error message")


def _add_optional_command(app, command: str, module, func_name: str) -> None:
    func = getattr(module, func_name, None)
    if func is not None:
        app.add_handler(CommandHandler(command, func))


def _add_optional_callback(app, module, func_name: str, pattern: str) -> None:
    func = getattr(module, func_name, None)
    if func is not None:
        app.add_handler(CallbackQueryHandler(func, pattern=pattern))


def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(user_handlers.setup_bot_commands).build()

    # Commands
    app.add_handler(CommandHandler("start", user_handlers.start))
    app.add_handler(CommandHandler("tests", user_handlers.tests_command))
    app.add_handler(CommandHandler("finish", user_handlers.finish_command))
    app.add_handler(CommandHandler("stats", user_handlers.stats_command))
    app.add_handler(CommandHandler("reset", user_handlers.reset))
    app.add_handler(CommandHandler("reset_errors", user_handlers.reset_errors_command))
    app.add_handler(CommandHandler("myid", user_handlers.myid))
    app.add_handler(CommandHandler("admin", admin_handlers.admin_command))
    _add_optional_command(app, "admin_debug", admin_handlers, "admin_debug_command")
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_handlers.handle_text_input))

    # User callbacks
    app.add_handler(CallbackQueryHandler(user_handlers.handle_tests_menu, pattern=r"^tests:menu$"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_test_menu, pattern=r"^test_menu:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_learn_menu, pattern=r"^learn_menu:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_solve_menu, pattern=r"^solve_menu:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_start_quiz, pattern=r"^start:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_start_from_number_menu, pattern=r"^start_from_number:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_mini_start, pattern=r"^mini_start:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_errors_solve, pattern=r"^errors_solve:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_find_question_menu, pattern=r"^find_question:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_find_by_number, pattern=r"^find_number:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_find_by_text, pattern=r"^find_text:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_view_question, pattern=r"^view_question:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_find_results_page, pattern=r"^find_results_page:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_answer, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_show_answer, pattern=r"^show_answer:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_next_question, pattern=r"^next_question:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_question_menu, pattern=r"^question_menu:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_question_continue, pattern=r"^question_continue:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_pause_to_menu, pattern=r"^pause_to_menu:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_continue_session, pattern=r"^continue_session:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_finish_button, pattern=r"^finish$"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_session_error_show, pattern=r"^session_error_show:"))
    _add_optional_callback(app, user_handlers, "handle_session_error_detail", r"^session_error_detail:")
    app.add_handler(CallbackQueryHandler(user_handlers.handle_show_result, pattern=r"^show_result:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_repeat_session_errors, pattern=r"^repeat_session_errors:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_my_stats, pattern=r"^my_stats:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_public_rating, pattern=r"^public_rating:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_reset_errors_confirm, pattern=r"^reset_errors_confirm:"))
    app.add_handler(CallbackQueryHandler(user_handlers.handle_reset_errors_do, pattern=r"^reset_errors_do:"))

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_menu, pattern=r"^admin:menu$"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_tests, pattern=r"^admin:tests$"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_test_menu, pattern=r"^admin:test:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_summary, pattern=r"^admin:summary$"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_test_stats, pattern=r"^admin:test_stats:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_rating, pattern=r"^admin:rating:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_test_users, pattern=r"^admin:test_users:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_test_user_detail, pattern=r"^admin:user:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_test_user_detail, pattern=r"^admin:test_user:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_frequent_errors, pattern=r"^admin:frequent_errors:"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_export_all, pattern=r"^admin:export_all$"))
    app.add_handler(CallbackQueryHandler(admin_handlers.handle_admin_export_test, pattern=r"^admin:export_test:"))

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    init_db()
    keep_alive()

    if not BOT_TOKEN:
        raise RuntimeError("Не найден токен. Добавь TELEGRAM_BOT_TOKEN в Render Environment.")

    while True:
        acquire_polling_lock()
        app = build_application()
        print("Bot is running...")
        try:
            app.run_polling()
            break
        except Conflict:
            print("Telegram polling conflict: another bot instance is still running. Waiting 15 seconds...")
            time.sleep(15)
        finally:
            release_polling_lock()
