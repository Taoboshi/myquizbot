import logging
import time

from telegram.error import Conflict
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .admin import (
    admin_command,
    handle_admin_export_all,
    handle_admin_export_test,
    handle_admin_frequent_errors,
    handle_admin_menu,
    handle_admin_rating,
    handle_admin_summary,
    handle_admin_test_menu,
    handle_admin_test_stats,
    handle_admin_test_user_detail,
    handle_admin_test_users,
    handle_admin_tests,
)
from .config import BOT_TOKEN
from .handlers import (
    finish_command,
    handle_answer,
    handle_continue_session,
    handle_errors_solve,
    handle_find_by_number,
    handle_find_by_text,
    handle_find_question_menu,
    handle_find_results_page,
    handle_finish_button,
    handle_learn_menu,
    handle_mini_start,
    handle_my_profile,
    handle_my_stats,
    handle_profile_favorites,
    handle_favorite_question,
    handle_favorite_remove,
    handle_profile_errors,
    handle_profile_error,
    handle_profile_error_favorite_toggle,
    handle_profile_history,
    handle_profile_attempt,
    handle_repeat_attempt,
    handle_attempt_errors,
    handle_attempt_error,
    handle_attempt_error_favorite_toggle,
    handle_question_favorite_toggle,
    handle_next_question,
    handle_pause_to_menu,
    handle_public_rating,
    handle_question_continue,
    handle_question_menu,
    handle_repeat_session_errors,
    handle_reset_errors_confirm,
    handle_reset_errors_do,
    handle_session_error_show,
    handle_show_answer,
    handle_show_result,
    handle_solve_menu,
    handle_start_from_number_menu,
    handle_start_quiz,
    handle_test_menu,
    handle_tests_menu,
    handle_text_input,
    handle_view_question,
    myid,
    reset,
    reset_errors_command,
    setup_bot_commands,
    start,
    stats_command,
    tests_command,
)
from .runtime import keep_alive
from .storage import init_db

logger = logging.getLogger(__name__)

try:
    from .admin import admin_debug_command
except ImportError:
    admin_debug_command = None


async def error_handler(update, context) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)

    if isinstance(context.error, Conflict):
        return

    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Произошла ошибка. Нажми /start.",
            )
    except Exception:
        logger.exception("Failed to send error message to user")


def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(setup_bot_commands).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tests", tests_command))
    app.add_handler(CommandHandler("finish", finish_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("reset_errors", reset_errors_command))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("admin", admin_command))
    if admin_debug_command is not None:
        app.add_handler(CommandHandler("admin_debug", admin_debug_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    # User callbacks
    app.add_handler(CallbackQueryHandler(handle_tests_menu, pattern=r"^tests:menu$"))
    app.add_handler(CallbackQueryHandler(handle_test_menu, pattern=r"^test_menu:"))
    app.add_handler(CallbackQueryHandler(handle_learn_menu, pattern=r"^learn_menu:"))
    app.add_handler(CallbackQueryHandler(handle_my_profile, pattern=r"^my_profile:"))
    app.add_handler(CallbackQueryHandler(handle_profile_favorites, pattern=r"^profile_favorites:"))
    app.add_handler(CallbackQueryHandler(handle_favorite_question, pattern=r"^favorite_question:"))
    app.add_handler(CallbackQueryHandler(handle_favorite_remove, pattern=r"^favorite_remove:"))
    app.add_handler(CallbackQueryHandler(handle_profile_errors, pattern=r"^profile_errors:"))
    app.add_handler(CallbackQueryHandler(handle_profile_error, pattern=r"^profile_error:"))
    app.add_handler(CallbackQueryHandler(handle_profile_error_favorite_toggle, pattern=r"^profile_error_favorite_toggle:"))
    app.add_handler(CallbackQueryHandler(handle_profile_history, pattern=r"^profile_history:"))
    app.add_handler(CallbackQueryHandler(handle_profile_attempt, pattern=r"^profile_attempt:"))
    app.add_handler(CallbackQueryHandler(handle_repeat_attempt, pattern=r"^repeat_attempt:"))
    app.add_handler(CallbackQueryHandler(handle_attempt_errors, pattern=r"^attempt_errors:"))
    app.add_handler(CallbackQueryHandler(handle_attempt_error, pattern=r"^attempt_error:"))
    app.add_handler(CallbackQueryHandler(handle_attempt_error_favorite_toggle, pattern=r"^attempt_error_favorite_toggle:"))
    app.add_handler(CallbackQueryHandler(handle_question_favorite_toggle, pattern=r"^question_favorite_toggle:"))
    app.add_handler(CallbackQueryHandler(handle_solve_menu, pattern=r"^solve_menu:"))
    app.add_handler(CallbackQueryHandler(handle_start_quiz, pattern=r"^start:"))
    app.add_handler(CallbackQueryHandler(handle_start_from_number_menu, pattern=r"^start_from_number:"))
    app.add_handler(CallbackQueryHandler(handle_mini_start, pattern=r"^mini_start:"))
    app.add_handler(CallbackQueryHandler(handle_errors_solve, pattern=r"^errors_solve:"))
    app.add_handler(CallbackQueryHandler(handle_find_question_menu, pattern=r"^find_question:"))
    app.add_handler(CallbackQueryHandler(handle_find_by_number, pattern=r"^find_number:"))
    app.add_handler(CallbackQueryHandler(handle_find_by_text, pattern=r"^find_text:"))
    app.add_handler(CallbackQueryHandler(handle_view_question, pattern=r"^view_question:"))
    app.add_handler(CallbackQueryHandler(handle_find_results_page, pattern=r"^find_results_page:"))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^answer:"))
    app.add_handler(CallbackQueryHandler(handle_show_answer, pattern=r"^show_answer:"))
    app.add_handler(CallbackQueryHandler(handle_next_question, pattern=r"^next_question:"))
    app.add_handler(CallbackQueryHandler(handle_question_menu, pattern=r"^question_menu:"))
    app.add_handler(CallbackQueryHandler(handle_question_continue, pattern=r"^question_continue:"))
    app.add_handler(CallbackQueryHandler(handle_pause_to_menu, pattern=r"^pause_to_menu:"))
    app.add_handler(CallbackQueryHandler(handle_continue_session, pattern=r"^continue_session:"))
    app.add_handler(CallbackQueryHandler(handle_finish_button, pattern=r"^finish$"))
    app.add_handler(CallbackQueryHandler(handle_session_error_show, pattern=r"^session_error_show:"))
    app.add_handler(CallbackQueryHandler(handle_session_error_show, pattern=r"^session_errors:"))
    app.add_handler(CallbackQueryHandler(handle_show_result, pattern=r"^show_result:"))
    app.add_handler(CallbackQueryHandler(handle_repeat_session_errors, pattern=r"^repeat_session_errors:"))
    app.add_handler(CallbackQueryHandler(handle_my_stats, pattern=r"^my_stats:"))
    app.add_handler(CallbackQueryHandler(handle_public_rating, pattern=r"^public_rating:"))
    app.add_handler(CallbackQueryHandler(handle_reset_errors_confirm, pattern=r"^reset_errors_confirm:"))
    app.add_handler(CallbackQueryHandler(handle_reset_errors_do, pattern=r"^reset_errors_do:"))

    # Admin callbacks
    app.add_handler(CallbackQueryHandler(handle_admin_menu, pattern=r"^admin:menu$"))
    app.add_handler(CallbackQueryHandler(handle_admin_tests, pattern=r"^admin:tests$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_menu, pattern=r"^admin:test:"))
    app.add_handler(CallbackQueryHandler(handle_admin_summary, pattern=r"^admin:summary$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_stats, pattern=r"^admin:test_stats:"))
    app.add_handler(CallbackQueryHandler(handle_admin_rating, pattern=r"^admin:rating:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_users, pattern=r"^admin:test_users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_user_detail, pattern=r"^admin:user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_user_detail, pattern=r"^admin:test_user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_frequent_errors, pattern=r"^admin:frequent_errors:"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_all, pattern=r"^admin:export_all$"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_test, pattern=r"^admin:export_test:"))

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)
    init_db()
    keep_alive()

    if not BOT_TOKEN:
        raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в Render Environment Variables.")

    while True:
        app = build_application()
        print("Bot is running...")
        try:
            app.run_polling()
            break
        except Conflict:
            logger.warning(
                "Telegram polling conflict: another bot instance is still running. Waiting 15 seconds..."
            )
            time.sleep(15)
