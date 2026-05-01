"""Compatibility facade for the admin subsystem.

The implementation is split into:
- admin_ui.py: text builders, keyboards, storage/service helpers;
- admin_handlers.py: Telegram command and callback handlers.

Imports from quiz_bot.admin are kept stable for the rest of the bot.
"""

from .admin_ui import *  # noqa: F401,F403
from .admin_handlers import *  # noqa: F401,F403
