import logging
import os
import time

from telegram import Update
from telegram.error import BadRequest, Conflict
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler, filters

from .admin import (
    admin_command,
    blocked_user_guard,
    handle_admin_block_user_confirm,
    handle_admin_block_user_do,
    handle_admin_blocked_users,
    handle_admin_broadcast_cancel,
    handle_admin_broadcast_send,
    handle_admin_broadcast_start,
    handle_admin_broadcast_text,
    handle_admin_clear_runtime_confirm,
    handle_admin_clear_runtime_do,
    handle_admin_debug,
    handle_admin_errors_menu,
    handle_admin_export_all,
    handle_admin_export_menu,
    handle_admin_export_test,
    handle_admin_frequent_errors,
    handle_admin_frequent_errors_all,
    handle_admin_global_user_detail,
    handle_admin_user_history,
    handle_admin_user_errors,
    handle_admin_user_favorites,
    handle_admin_export_user,
    handle_admin_clear_user_runtime_confirm,
    handle_admin_clear_user_runtime_do,
    handle_admin_reset_user_confirm,
    handle_admin_reset_user_second,
    handle_admin_reset_user_do,
    handle_admin_validate_tests,
    handle_admin_manage,
    handle_admin_menu,
    handle_admin_rating,
    handle_admin_summary,
    handle_admin_test_menu,
    handle_admin_test_overview,
    handle_admin_validate_test,
    handle_admin_test_stats,
    handle_admin_test_user_detail,
    handle_admin_test_users,
    handle_admin_unblock_user,
    handle_admin_tests,
    handle_admin_noop,
    handle_admin_test_access,
    handle_admin_test_access_users,
    handle_admin_user_access,
    handle_admin_grant_access,
    handle_admin_revoke_access,
    handle_admin_users,
    handle_admin_users_recent,
    handle_admin_users_result,
    handle_admin_users_attempts,
    handle_admin_users_errors,
)
from .config import ADMIN_IDS, BOT_TOKEN
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
    handle_next_question,
    handle_pause_to_menu,
    handle_profile_favorites,
    handle_favorite_show,
    handle_profile_errors,
    handle_profile_error_show,
    handle_profile_history,
    handle_history_attempt,
    handle_attempt_errors_page,
    handle_attempt_error_show,
    handle_repeat_attempt,
    handle_result_errors_page,
    handle_result_error_show,
    handle_show_result_attempt,
    handle_toggle_favorite,
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
from .storage import acquire_polling_lock, init_db, release_polling_lock

logger = logging.getLogger(__name__)

try:
    from .admin import admin_debug_command
except ImportError:
    admin_debug_command = None


async def error_handler(update, context) -> None:
    err = context.error

    if isinstance(err, Conflict):
        return

    if isinstance(err, BadRequest) and "Message is not modified" in str(err):
        return

    logger.exception("Unhandled bot error", exc_info=err)

    try:
        if update and update.effective_chat:
            user_id = update.effective_user.id if update.effective_user else None
            if user_id in ADMIN_IDS:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "⚠️ Ошибка в боте\n\n"
                        f"{type(err).__name__}: {err}\n\n"
                        "Пришли этот текст, если нужно исправить кнопку."
                    ),
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Произошла ошибка. Нажми /start.",
                )
    except Exception:
        logger.exception("Failed to send error message to user")


def build_application():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(setup_bot_commands)
        .concurrent_updates(int(os.getenv("BOT_CONCURRENT_UPDATES", "8")))
        .build()
    )

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
    app.add_handler(TypeHandler(Update, blocked_user_guard), group=-2)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_broadcast_text), group=-1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    # User callbacks
    app.add_handler(CallbackQueryHandler(handle_tests_menu, pattern=r"^tests:menu$"))
    app.add_handler(CallbackQueryHandler(handle_test_menu, pattern=r"^test_menu:"))
    app.add_handler(CallbackQueryHandler(handle_learn_menu, pattern=r"^learn_menu:"))
    app.add_handler(CallbackQueryHandler(handle_my_profile, pattern=r"^my_profile:"))
    app.add_handler(CallbackQueryHandler(handle_profile_favorites, pattern=r"^profile_favorites:"))
    app.add_handler(CallbackQueryHandler(handle_favorite_show, pattern=r"^favorite_show:"))
    app.add_handler(CallbackQueryHandler(handle_profile_errors, pattern=r"^profile_errors:"))
    app.add_handler(CallbackQueryHandler(handle_profile_error_show, pattern=r"^profile_error_show:"))
    app.add_handler(CallbackQueryHandler(handle_profile_history, pattern=r"^profile_history:"))
    app.add_handler(CallbackQueryHandler(handle_history_attempt, pattern=r"^history_attempt:"))
    app.add_handler(CallbackQueryHandler(handle_attempt_errors_page, pattern=r"^attempt_errors_page:"))
    app.add_handler(CallbackQueryHandler(handle_attempt_error_show, pattern=r"^attempt_error_show:"))
    app.add_handler(CallbackQueryHandler(handle_repeat_attempt, pattern=r"^repeat_attempt:"))
    app.add_handler(CallbackQueryHandler(handle_result_errors_page, pattern=r"^result_errors_page:"))
    app.add_handler(CallbackQueryHandler(handle_result_error_show, pattern=r"^result_error_show:"))
    app.add_handler(CallbackQueryHandler(handle_show_result_attempt, pattern=r"^show_result_attempt:"))
    app.add_handler(CallbackQueryHandler(handle_toggle_favorite, pattern=r"^toggle_favorite:"))
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
    app.add_handler(CallbackQueryHandler(handle_admin_summary, pattern=r"^admin:summary$"))
    app.add_handler(CallbackQueryHandler(handle_admin_users_recent, pattern=r"^admin:users:recent:0$"))
    app.add_handler(CallbackQueryHandler(handle_admin_users_result, pattern=r"^admin:users:result:0$"))
    app.add_handler(CallbackQueryHandler(handle_admin_users_attempts, pattern=r"^admin:users:attempts:0$"))
    app.add_handler(CallbackQueryHandler(handle_admin_users_errors, pattern=r"^admin:users:errors:0$"))
    app.add_handler(CallbackQueryHandler(handle_admin_users, pattern=r"^admin:users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_global_user_detail, pattern=r"^admin:global_user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_block_user_confirm, pattern=r"^admin:block_user_confirm:"))
    app.add_handler(CallbackQueryHandler(handle_admin_block_user_do, pattern=r"^admin:block_user_do:"))
    app.add_handler(CallbackQueryHandler(handle_admin_unblock_user, pattern=r"^admin:unblock_user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_blocked_users, pattern=r"^admin:blocked_users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_broadcast_start, pattern=r"^admin:broadcast_start$"))
    app.add_handler(CallbackQueryHandler(handle_admin_broadcast_send, pattern=r"^admin:broadcast_send$"))
    app.add_handler(CallbackQueryHandler(handle_admin_broadcast_cancel, pattern=r"^admin:broadcast_cancel$"))
    app.add_handler(CallbackQueryHandler(handle_admin_user_history, pattern=r"^admin:user_history:"))
    app.add_handler(CallbackQueryHandler(handle_admin_user_errors, pattern=r"^admin:user_errors:"))
    app.add_handler(CallbackQueryHandler(handle_admin_user_favorites, pattern=r"^admin:user_favorites:"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_user, pattern=r"^admin:export_user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_clear_user_runtime_confirm, pattern=r"^admin:clear_user_runtime_confirm:"))
    app.add_handler(CallbackQueryHandler(handle_admin_clear_user_runtime_do, pattern=r"^admin:clear_user_runtime_do:"))
    app.add_handler(CallbackQueryHandler(handle_admin_reset_user_confirm, pattern=r"^admin:reset_user_confirm:"))
    app.add_handler(CallbackQueryHandler(handle_admin_reset_user_second, pattern=r"^admin:reset_user_second:"))
    app.add_handler(CallbackQueryHandler(handle_admin_reset_user_do, pattern=r"^admin:reset_user_do:"))
    app.add_handler(CallbackQueryHandler(handle_admin_validate_tests, pattern=r"^admin:validate_tests$"))
    app.add_handler(CallbackQueryHandler(handle_admin_tests, pattern=r"^admin:tests$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_overview, pattern=r"^admin:test_overview:"))
    app.add_handler(CallbackQueryHandler(handle_admin_validate_test, pattern=r"^admin:validate_test:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_stats, pattern=r"^admin:test_stats:"))
    app.add_handler(CallbackQueryHandler(handle_admin_rating, pattern=r"^admin:rating:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_users, pattern=r"^admin:test_users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_user_detail, pattern=r"^admin:user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_user_detail, pattern=r"^admin:test_user:"))
    app.add_handler(CallbackQueryHandler(handle_admin_errors_menu, pattern=r"^admin:errors$"))
    app.add_handler(CallbackQueryHandler(handle_admin_frequent_errors_all, pattern=r"^admin:frequent_errors_all$"))
    app.add_handler(CallbackQueryHandler(handle_admin_frequent_errors, pattern=r"^admin:frequent_errors:"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_menu, pattern=r"^admin:export_menu$"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_all, pattern=r"^admin:export_all$"))
    app.add_handler(CallbackQueryHandler(handle_admin_export_test, pattern=r"^admin:export_test:"))
    app.add_handler(CallbackQueryHandler(handle_admin_debug, pattern=r"^admin:debug$"))
    app.add_handler(CallbackQueryHandler(handle_admin_manage, pattern=r"^admin:manage$"))
    app.add_handler(CallbackQueryHandler(handle_admin_clear_runtime_confirm, pattern=r"^admin:clear_runtime_confirm$"))
    app.add_handler(CallbackQueryHandler(handle_admin_clear_runtime_do, pattern=r"^admin:clear_runtime_do$"))
    app.add_handler(CallbackQueryHandler(handle_admin_noop, pattern=r"^admin:noop$"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_access_users, pattern=r"^admin:test_access_users:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_access, pattern=r"^admin:test_access:"))
    app.add_handler(CallbackQueryHandler(handle_admin_user_access, pattern=r"^admin:user_access:"))
    app.add_handler(CallbackQueryHandler(handle_admin_grant_access, pattern=r"^admin:grant_access:"))
    app.add_handler(CallbackQueryHandler(handle_admin_revoke_access, pattern=r"^admin:revoke_access:"))
    app.add_handler(CallbackQueryHandler(handle_admin_test_menu, pattern=r"^admin:test:"))

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

    acquire_polling_lock()
    try:
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
    finally:
        release_polling_lock()
