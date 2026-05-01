import logging
import os
import time

from telegram.error import BadRequest, Conflict
from telegram.ext import ApplicationBuilder

from .admin_routes import register_admin_handlers
from .config import get_bot_token
from .user_routes import register_user_handlers
from .handlers import setup_bot_commands
from .helpers import is_admin
from .runtime import keep_alive
from .storage import acquire_polling_lock, init_db, release_polling_lock

logger = logging.getLogger(__name__)

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
            if user_id is not None and is_admin(user_id):
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
        .token(get_bot_token(required=True))
        .post_init(setup_bot_commands)
        .concurrent_updates(int(os.getenv("BOT_CONCURRENT_UPDATES", "8")))
        .build()
    )

    register_admin_handlers(app)
    register_user_handlers(app)

    app.add_error_handler(error_handler)
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.request").setLevel(logging.WARNING)
    init_db()
    keep_alive()

    get_bot_token(required=True)

    acquire_polling_lock()
    try:
        while True:
            app = build_application()
            logger.info("Bot is running...")
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
