"""Admin callback and command handlers.

This module intentionally imports the UI/service helpers from admin_ui to keep
callback behavior compatible while splitting the former monolithic admin.py.
"""

from .admin_ui import *  # noqa: F401,F403 - compatibility split of legacy admin module
from .admin_ui import _parse_users_sort, _slug

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Админ-панель недоступна.")
        return
    await update.message.reply_text("🛠 Админ-панель", reply_markup=admin_main_keyboard())


async def admin_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Админ-панель недоступна.")
        return
    await update.message.reply_text(admin_debug_text(), reply_markup=admin_debug_keyboard())

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text("🛠 Админ-панель", reply_markup=admin_main_keyboard())


async def handle_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    sort = "recent"
    page = 0

    # Supported formats:
    # admin:users
    # admin:users:0
    # admin:users:recent
    # admin:users:recent:0
    # admin:users:result:0
    # admin:users:attempts:0
    # admin:users:errors:0
    if len(parts) >= 3:
        third = parts[2]
        if third.isdigit():
            page = int(third)
        else:
            sort = _parse_users_sort(third)

    if len(parts) >= 4 and str(parts[3]).isdigit():
        page = int(parts[3])

    message_text = admin_users_text(page, sort)
    keyboard = admin_users_keyboard(page, sort)

    try:
        await query.edit_message_text(message_text, reply_markup=keyboard)
    except Exception as exc:
        if "Message is not modified" in str(exc):
            return
        raise


async def _show_admin_users_sorted(update: Update, context: ContextTypes.DEFAULT_TYPE, sort: str) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    sort = _parse_users_sort(sort)
    page = 0
    message_text = admin_users_text(page, sort)
    keyboard = admin_users_keyboard(page, sort)

    try:
        await query.edit_message_text(message_text, reply_markup=keyboard)
    except Exception as exc:
        if "Message is not modified" in str(exc):
            return
        raise


async def handle_admin_users_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "recent")


async def handle_admin_users_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "result")


async def handle_admin_users_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "attempts")


async def handle_admin_users_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _show_admin_users_sorted(update, context, "errors")


async def handle_admin_global_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    await query.edit_message_text(
        admin_global_user_text(user_id),
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_user_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    back_page = int(parts[4])
    sort = _parse_users_sort(parts[5]) if len(parts) > 5 else "recent"
    await query.edit_message_text(
        admin_user_history_text(user_id, page),
        reply_markup=admin_user_history_keyboard(user_id, page, back_page, sort),
    )


async def handle_admin_user_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    back_page = int(parts[4])
    sort = _parse_users_sort(parts[5]) if len(parts) > 5 else "recent"
    await query.edit_message_text(
        admin_user_errors_text(user_id, page),
        reply_markup=admin_user_errors_keyboard(user_id, page, back_page, sort),
    )


async def handle_admin_user_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    back_page = int(parts[4])
    sort = _parse_users_sort(parts[5]) if len(parts) > 5 else "recent"
    await query.edit_message_text(
        admin_user_favorites_text(user_id, page),
        reply_markup=admin_user_favorites_keyboard(user_id, page, back_page, sort),
    )


async def handle_admin_export_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    path = export_user_csv(user_id)
    await query.message.reply_document(InputFile(path), caption=f"📤 Экспорт пользователя: {user_id}")
    await query.edit_message_text(
        admin_global_user_text(user_id),
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_clear_user_runtime_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    await query.edit_message_text(
        "🧹 Очистить runtime-сессии пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Это удалит только временные состояния текущих прохождений. "
        "Статистика, попытки, ошибки и избранное останутся.",
        reply_markup=admin_clear_user_runtime_confirm_keyboard(user_id, page, sort),
    )


async def handle_admin_clear_user_runtime_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    count = clear_user_runtime_sessions(user_id)
    await query.edit_message_text(
        f"✅ Runtime-сессии пользователя очищены.\n\nУдалено записей: {count}",
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_block_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    await query.edit_message_text(
        "🚫 Заблокировать пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Он не сможет пользоваться ботом, пока ты его не разблокируешь. "
        "Статистика и данные пользователя останутся.",
        reply_markup=admin_block_user_confirm_keyboard(user_id, page, sort),
    )


async def handle_admin_block_user_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    block_user(user_id, query.from_user.id, "blocked from admin panel")
    await query.edit_message_text(
        "🚫 Пользователь заблокирован.",
        reply_markup=admin_unblock_user_keyboard(user_id, page, sort),
    )


async def handle_admin_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    unblock_user(user_id)
    await query.edit_message_text(
        "✅ Пользователь разблокирован.",
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0
    await query.edit_message_text(
        admin_blocked_users_text(page),
        reply_markup=admin_blocked_users_keyboard(page),
    )


async def handle_admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    context.user_data["admin_broadcast_waiting"] = True
    context.user_data.pop("admin_broadcast_text", None)

    await query.edit_message_text(
        "📢 Рассылка\n\n"
        "Отправь следующим сообщением текст, который нужно разослать пользователям.\n\n"
        "Получатели: все незаблокированные пользователи.",
        reply_markup=admin_broadcast_cancel_keyboard(),
    )


async def handle_admin_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    subject_code_id = context.user_data.get("admin_subject_code_id")
    if subject_code_id:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "Код не может быть пустым.",
                reply_markup=admin_subject_access_keyboard(subject_code_id),
            )
            raise ApplicationHandlerStop

        context.user_data.pop("admin_subject_code_id", None)
        set_subject_access_setting(
            subject_code_id,
            "code",
            code=text,
            updated_by=user.id,
        )
        await update.message.reply_text(
            "✅ Код раздела обновлён.\n\n" + admin_subject_access_text(subject_code_id),
            reply_markup=admin_subject_access_keyboard(subject_code_id),
        )
        raise ApplicationHandlerStop

    rename_subject_id = context.user_data.get("admin_rename_subject_id")
    if rename_subject_id:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "Название раздела не может быть пустым.",
                reply_markup=admin_subject_settings_keyboard(rename_subject_id),
            )
            raise ApplicationHandlerStop

        context.user_data.pop("admin_rename_subject_id", None)
        subject_id = _slug(text)

        if subject_id != rename_subject_id and not get_tests_for_subject(rename_subject_id):
            delete_subject_setting(rename_subject_id)
            remove_subject_override(rename_subject_id)
        else:
            subject_id = rename_subject_id

        set_subject_setting(subject_id, text, emoji="", updated_by=user.id)
        add_subject_override(subject_id, text, emoji="")

        await update.message.reply_text(
            "✅ Раздел переименован.\n\n" + admin_subject_text(subject_id),
            reply_markup=admin_subject_keyboard(subject_id),
        )
        raise ApplicationHandlerStop

    if context.user_data.get("admin_add_subject_waiting"):
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "Название раздела не может быть пустым.",
                reply_markup=admin_tests_keyboard(),
            )
            raise ApplicationHandlerStop

        context.user_data.pop("admin_add_subject_waiting", None)

        subject_id = _slug(text)
        set_subject_setting(subject_id, text, emoji="", updated_by=user.id)
        add_subject_override(subject_id, text, emoji="")

        await update.message.reply_text(
            "✅ Раздел добавлен.\n\n" + admin_tests_text(),
            reply_markup=admin_tests_keyboard(),
        )
        raise ApplicationHandlerStop

    rename_test_id = context.user_data.get("admin_rename_test_id")
    if rename_test_id:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "Название не может быть пустым.",
                reply_markup=admin_test_meta_keyboard(rename_test_id),
            )
            raise ApplicationHandlerStop

        context.user_data.pop("admin_rename_test_id", None)
        current = effective_test_info(rename_test_id)
        set_test_metadata_setting(
            rename_test_id,
            title=text,
            subject_id=current.get("subject_id"),
            subject_title=current.get("subject_title"),
            subject_emoji=current.get("subject_emoji"),
            updated_by=user.id,
        )
        apply_test_metadata_override(rename_test_id, title=text)

        await update.message.reply_text(
            "✅ Название теста обновлено.\n\n" + admin_test_meta_text(rename_test_id),
            reply_markup=admin_test_meta_keyboard(rename_test_id),
        )
        raise ApplicationHandlerStop

    subject_test_id = context.user_data.get("admin_change_subject_test_id")
    if subject_test_id:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "Название раздела не может быть пустым.",
                reply_markup=admin_test_meta_keyboard(subject_test_id),
            )
            raise ApplicationHandlerStop

        context.user_data.pop("admin_change_subject_test_id", None)
        current = effective_test_info(subject_test_id)
        subject_id = _slug(text)

        set_test_metadata_setting(
            subject_test_id,
            title=current.get("title"),
            subject_id=subject_id,
            subject_title=text,
            subject_emoji=current.get("subject_emoji") or "",
            updated_by=user.id,
        )
        apply_test_metadata_override(
            subject_test_id,
            subject_id=subject_id,
            subject_title=text,
            subject_emoji=current.get("subject_emoji") or "",
        )

        await update.message.reply_text(
            "✅ Раздел теста обновлён.\n\n" + admin_test_meta_text(subject_test_id),
            reply_markup=admin_test_meta_keyboard(subject_test_id),
        )
        raise ApplicationHandlerStop

    access_code_test_id = context.user_data.get("admin_access_code_test_id")
    if access_code_test_id:
        text = (update.message.text or "").strip()
        if not text:
            await update.message.reply_text(
                "Код не может быть пустым.",
                reply_markup=admin_test_access_keyboard(access_code_test_id),
            )
            raise ApplicationHandlerStop

        context.user_data.pop("admin_access_code_test_id", None)
        set_test_access_setting(
            access_code_test_id,
            "code",
            code=text,
            updated_by=user.id,
        )
        await update.message.reply_text(
            "✅ Код доступа обновлён.\n\n" + admin_test_access_text(access_code_test_id),
            reply_markup=admin_test_access_keyboard(access_code_test_id),
        )
        raise ApplicationHandlerStop

    if not context.user_data.get("admin_broadcast_waiting"):
        return

    text = (update.message.text or "").strip()
    context.user_data["admin_broadcast_waiting"] = False

    if not text:
        await update.message.reply_text("Пустое сообщение не подходит.", reply_markup=admin_manage_keyboard())
        raise ApplicationHandlerStop

    context.user_data["admin_broadcast_text"] = text
    users_count = len(broadcast_users())

    preview = text
    if len(preview) > 1200:
        preview = preview[:1200].rstrip() + "…"

    await update.message.reply_text(
        "📢 Предпросмотр рассылки\n\n"
        f"Получателей: {users_count}\n"
        "Заблокированные пользователи не получат сообщение.\n\n"
        f"{preview}",
        reply_markup=admin_broadcast_preview_keyboard(),
    )

    raise ApplicationHandlerStop


async def handle_admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    text = context.user_data.get("admin_broadcast_text")
    if not text:
        await query.edit_message_text("Текст рассылки не найден.", reply_markup=admin_manage_keyboard())
        return

    user_ids = broadcast_users()
    await query.edit_message_text(f"📢 Рассылка запущена.\n\nПолучателей: {len(user_ids)}")

    sent = 0
    failed = 0
    delay = float(os.getenv("BROADCAST_SEND_DELAY_SECONDS", "0.05"))

    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=text)
            sent += 1
        except Exception:
            failed += 1
        if delay > 0:
            await asyncio.sleep(delay)

    context.user_data.pop("admin_broadcast_text", None)
    context.user_data.pop("admin_broadcast_waiting", None)

    await query.message.reply_text(
        "✅ Рассылка завершена\n\n"
        f"Отправлено: {sent}\n"
        f"Ошибок: {failed}",
        reply_markup=admin_manage_keyboard(),
    )


async def handle_admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    context.user_data.pop("admin_broadcast_waiting", None)
    context.user_data.pop("admin_broadcast_text", None)
    await query.edit_message_text("Рассылка отменена.", reply_markup=admin_manage_keyboard())


async def handle_admin_reset_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    await query.edit_message_text(
        "🗑 Сбросить прогресс пользователя?\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "Будут удалены попытки, статистика, ошибки, избранное и сохранённые сессии. "
        "Сам пользователь останется в списке.\n\n"
        "Это действие нельзя отменить.",
        reply_markup=admin_reset_user_confirm_keyboard(user_id, page, sort),
    )


async def handle_admin_reset_user_second(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    await query.edit_message_text(
        "⚠️ Последнее подтверждение\n\n"
        f"Пользователь ID: {user_id}\n\n"
        "После нажатия кнопки ниже прогресс будет удалён полностью.",
        reply_markup=admin_reset_user_second_keyboard(user_id, page, sort),
    )


async def handle_admin_reset_user_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3])
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"
    result = reset_user_progress(user_id)

    await query.edit_message_text(
        "✅ Прогресс пользователя сброшен\n\n"
        f"Пользователь ID: {user_id}\n"
        f"Удалено попыток: {result['attempts']}\n"
        f"Строк статистики: {result['stats']}\n"
        f"Ответов по вопросам: {result['answered_questions']}\n"
        f"Ошибок: {result['errors']}\n"
        f"Избранного: {result['favorites']}\n"
        f"Сохранённых сессий: {result['active_sessions']}\n"
        f"Runtime-сессий: {result['runtime_sessions']}",
        reply_markup=admin_global_user_keyboard(user_id, page, sort),
    )


async def handle_admin_validate_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    await query.edit_message_text(
        validate_tests_text(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ К управлению", callback_data="admin:manage")],
            [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
        ]),
    )


async def handle_admin_errors_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_errors_menu_text(), reply_markup=admin_errors_menu_keyboard())


async def handle_admin_frequent_errors_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(
        admin_frequent_errors_all_text(),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧠 К ошибкам", callback_data="admin:errors")],
            [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
        ]),
    )


async def handle_admin_export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_export_menu_text(), reply_markup=admin_export_menu_keyboard())


async def handle_admin_debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_debug_text(), reply_markup=admin_debug_keyboard())


async def handle_admin_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_manage_text(), reply_markup=admin_manage_keyboard())


async def handle_admin_clear_runtime_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    await query.edit_message_text(
        "🧹 Очистить runtime-сессии?\n\n"
        "Это сбросит временные состояния текущих прохождений. "
        "Сохранённые завершённые попытки и статистика не удалятся.",
        reply_markup=admin_clear_runtime_confirm_keyboard(),
    )


async def handle_admin_clear_runtime_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    count = clear_runtime_sessions()
    await query.edit_message_text(
        f"✅ Runtime-сессии очищены.\n\nУдалено записей: {count}",
        reply_markup=admin_manage_keyboard(),
    )



async def handle_admin_noop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()


async def handle_admin_test_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":", 2)
    await query.edit_message_text(admin_test_access_text(test_id), reply_markup=admin_test_access_keyboard(test_id))


async def handle_admin_test_access_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id, page_str = query.data.split(":")
    page = int(page_str)
    await query.edit_message_text(
        admin_test_access_users_text(test_id, page),
        reply_markup=admin_test_access_users_keyboard(test_id, page),
    )


async def handle_admin_user_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    await query.edit_message_text(
        admin_user_access_text(user_id),
        reply_markup=admin_user_access_keyboard(user_id, page, sort),
    )


async def handle_admin_grant_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, test_id, page_str, sort = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    grant_user_test_access(user_id, test_id, access_source="admin", granted_by=query.from_user.id)

    await query.edit_message_text(
        f"✅ Доступ выдан.\n\n{admin_user_access_text(user_id)}",
        reply_markup=admin_user_access_keyboard(user_id, page, sort),
    )


async def handle_admin_revoke_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, user_id_str, test_id, page_str, sort = query.data.split(":")
    user_id = int(user_id_str)
    page = int(page_str)
    revoke_user_test_access(user_id, test_id)

    await query.edit_message_text(
        f"✅ Доступ забран.\n\n{admin_user_access_text(user_id)}",
        reply_markup=admin_user_access_keyboard(user_id, page, sort),
    )


async def handle_admin_set_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id, access_type = query.data.split(":")
    current_code = effective_access_code(test_id)
    set_test_access_setting(test_id, access_type, code=current_code, updated_by=query.from_user.id)

    await query.edit_message_text(
        admin_test_access_text(test_id),
        reply_markup=admin_test_access_keyboard(test_id),
    )


async def handle_admin_reset_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    reset_test_access_setting(test_id)

    await query.edit_message_text(
        admin_test_access_text(test_id),
        reply_markup=admin_test_access_keyboard(test_id),
    )


async def handle_admin_set_access_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    context.user_data["admin_access_code_test_id"] = test_id

    await query.edit_message_text(
        "✏️ Изменить код доступа\n\n"
        f"Тест: {effective_test_info(test_id)['title']}\n\n"
        "Отправь следующим сообщением новый код доступа.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:test_access:{test_id}")],
        ]),
    )


async def handle_admin_test_meta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    await query.edit_message_text(
        admin_test_meta_text(test_id),
        reply_markup=admin_test_meta_keyboard(test_id),
    )


async def handle_admin_set_test_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    context.user_data["admin_rename_test_id"] = test_id
    context.user_data.pop("admin_change_subject_test_id", None)

    await query.edit_message_text(
        "✏️ Изменить название теста\n\n"
        f"Текущее название: {effective_test_info(test_id)['title']}\n\n"
        "Отправь следующим сообщением новое название.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:test_meta:{test_id}")],
        ]),
    )


async def handle_admin_set_test_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    context.user_data["admin_change_subject_test_id"] = test_id
    context.user_data.pop("admin_rename_test_id", None)

    await query.edit_message_text(
        "📁 Изменить раздел теста\n\n"
        f"Текущий раздел: {effective_test_info(test_id).get('subject_title') or '—'}\n\n"
        "Отправь следующим сообщением новое название раздела.\n"
        "Например: Анатомия или Фармакология.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:test_meta:{test_id}")],
        ]),
    )


async def handle_admin_reset_test_meta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    reset_test_metadata_setting(test_id)

    base = TESTS[test_id]
    apply_test_metadata_override(
        test_id,
        title=base.get("title"),
        subject_id=base.get("subject_id"),
        subject_title=base.get("subject_title"),
        subject_emoji=base.get("subject_emoji"),
    )

    await query.edit_message_text(
        admin_test_meta_text(test_id),
        reply_markup=admin_test_meta_keyboard(test_id),
    )


async def handle_admin_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    await query.edit_message_text(
        admin_subject_text(subject_id),
        reply_markup=admin_subject_keyboard(subject_id),
    )


async def handle_admin_add_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    context.user_data["admin_add_subject_waiting"] = True
    context.user_data.pop("admin_rename_test_id", None)
    context.user_data.pop("admin_change_subject_test_id", None)
    context.user_data.pop("admin_access_code_test_id", None)
    context.user_data.pop("admin_rename_subject_id", None)

    await query.edit_message_text(
        "➕ Добавить раздел\n\n"
        "Отправь следующим сообщением название раздела.\n\n"
        "Например: Анатомия",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Отмена", callback_data="admin:tests")],
        ]),
    )


async def handle_admin_add_test_to_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    await query.edit_message_text(
        admin_add_test_to_subject_text(subject_id),
        reply_markup=admin_add_test_to_subject_keyboard(subject_id),
    )


async def handle_admin_assign_test_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id, test_id = query.data.split(":", 3)

    subject = get_subject_info(subject_id)
    current = effective_test_info(test_id)

    set_test_metadata_setting(
        test_id,
        title=current.get("title"),
        subject_id=subject_id,
        subject_title=subject.get("title", subject_id),
        subject_emoji=subject.get("emoji", ""),
        updated_by=query.from_user.id,
    )
    apply_test_metadata_override(
        test_id,
        subject_id=subject_id,
        subject_title=subject.get("title", subject_id),
        subject_emoji=subject.get("emoji", ""),
    )

    await query.edit_message_text(
        "✅ Тест добавлен в раздел.\n\n" + admin_subject_text(subject_id),
        reply_markup=admin_subject_keyboard(subject_id),
    )



async def handle_admin_subject_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    await query.edit_message_text(
        admin_subject_access_text(subject_id),
        reply_markup=admin_subject_access_keyboard(subject_id),
    )


async def handle_admin_set_subject_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id, access_type = query.data.split(":", 3)
    current_code = subject_access_code(subject_id)
    set_subject_access_setting(subject_id, access_type, code=current_code, updated_by=query.from_user.id)

    await query.edit_message_text(
        admin_subject_access_text(subject_id),
        reply_markup=admin_subject_access_keyboard(subject_id),
    )


async def handle_admin_set_subject_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    context.user_data["admin_subject_code_id"] = subject_id

    await query.edit_message_text(
        "✏️ Изменить код раздела\n\n"
        f"Раздел: {subject_button_title(get_subject_info(subject_id), subject_id)}\n\n"
        "Отправь следующим сообщением новый код доступа.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:subject_access:{subject_id}")],
        ]),
    )


async def handle_admin_subject_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    await query.edit_message_text(
        admin_subject_settings_text(subject_id),
        reply_markup=admin_subject_settings_keyboard(subject_id),
    )


async def handle_admin_rename_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    context.user_data["admin_rename_subject_id"] = subject_id

    info = get_subject_info(subject_id)
    await query.edit_message_text(
        "✏️ Переименовать раздел\n\n"
        f"Сейчас: {info.get('title', subject_id)}\n\n"
        "Отправь следующим сообщением новое название.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:subject_settings:{subject_id}")],
        ]),
    )


async def handle_admin_delete_subject_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    tests = get_tests_for_subject(subject_id)
    if tests:
        await query.edit_message_text(
            "Раздел нельзя удалить, пока в нём есть тесты.\n\n"
            "Сначала открепи или перенеси тесты.",
            reply_markup=admin_subject_settings_keyboard(subject_id),
        )
        return

    info = get_subject_info(subject_id)
    await query.edit_message_text(
        "🗑 Удалить раздел?\n\n"
        f"Раздел: {info.get('title', subject_id)}\n\n"
        "Это удалит только сам раздел. Тесты не удаляются.",
        reply_markup=admin_delete_subject_confirm_keyboard(subject_id),
    )


async def handle_admin_delete_subject_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id = query.data.split(":", 2)
    if get_tests_for_subject(subject_id):
        await query.edit_message_text(
            "Раздел не удалён: в нём есть тесты.",
            reply_markup=admin_subject_settings_keyboard(subject_id),
        )
        return

    delete_subject_setting(subject_id)
    remove_subject_override(subject_id)

    await query.edit_message_text(
        "✅ Раздел удалён.\n\n" + admin_tests_text(),
        reply_markup=admin_tests_keyboard(),
    )


async def handle_admin_move_test_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":", 2)
    await query.edit_message_text(
        admin_move_test_subject_text(test_id),
        reply_markup=admin_move_test_subject_keyboard(test_id),
    )


async def handle_admin_move_test_subject_do(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, subject_id, test_id = query.data.split(":", 3)

    subject = get_subject_info(subject_id)
    current = effective_test_info(test_id)

    set_test_metadata_setting(
        test_id,
        title=current.get("title"),
        subject_id=subject_id,
        subject_title=subject.get("title", subject_id),
        subject_emoji=subject.get("emoji", ""),
        updated_by=query.from_user.id,
    )
    apply_test_metadata_override(
        test_id,
        subject_id=subject_id,
        subject_title=subject.get("title", subject_id),
        subject_emoji=subject.get("emoji", ""),
    )

    await query.edit_message_text(
        "✅ Тест перенесён.\n\n" + admin_test_meta_text(test_id),
        reply_markup=admin_test_meta_keyboard(test_id),
    )


async def handle_admin_detach_test_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":", 2)
    current = effective_test_info(test_id)

    set_test_metadata_setting(
        test_id,
        title=current.get("title"),
        subject_id="unassigned",
        subject_title="",
        subject_emoji="",
        updated_by=query.from_user.id,
    )
    apply_test_metadata_override(
        test_id,
        subject_id="unassigned",
        subject_title="",
        subject_emoji="",
    )

    await query.edit_message_text(
        "✅ Тест откреплён от раздела.\n\n"
        "Теперь он появится в списке непривязанных тестов.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 К разделам", callback_data="admin:tests")],
            [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
        ]),
    )


async def handle_admin_user_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    user_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0
    sort = _parse_users_sort(parts[4]) if len(parts) > 4 else "recent"

    await query.edit_message_text(
        admin_user_manage_text(user_id),
        reply_markup=admin_user_manage_keyboard(user_id, page, sort),
    )


async def handle_admin_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(admin_tests_text(), reply_markup=admin_tests_keyboard())

async def handle_admin_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    title = effective_test_info(test_id)["title"]
    questions_count = len(get_questions(test_id))
    await query.edit_message_text(
        f"📚 {title}\n\nВопросов: {questions_count}\n\nВыбери действие:",
        reply_markup=admin_test_keyboard(test_id),
    )

async def handle_admin_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    await query.edit_message_text(safe_admin_summary_text(), reply_markup=admin_overview_keyboard())

async def handle_admin_test_overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_test_overview_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))


async def handle_admin_validate_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    _, _, test_id = query.data.split(":")
    await query.edit_message_text(validate_single_test_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))


async def handle_admin_test_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_test_stats_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))

async def handle_admin_rating(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_rating_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))

async def handle_admin_test_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    if len(parts) >= 4:
        _, _, test_id, page_str = parts
        page = int(page_str)
    else:
        _, _, test_id = parts
        page = 0

    await query.edit_message_text(admin_test_users_text(test_id, page), reply_markup=admin_test_users_keyboard(test_id, page))

async def handle_admin_test_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return

    parts = query.data.split(":")
    page = 0

    if len(parts) == 5 and parts[1] == "user":
        _, _, test_id, user_id_str, page_str = parts
        page = int(page_str)
    elif len(parts) == 4 and parts[1] == "user":
        _, _, test_id, user_id_str = parts
    else:
        _, _, test_id, user_id_str = parts

    user_id = int(user_id_str)

    await query.edit_message_text(
        admin_user_detail_text(test_id, user_id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад к пользователям", callback_data=f"admin:test_users:{test_id}:{page}")],
            [InlineKeyboardButton("🏠 Назад к тесту", callback_data=f"admin:test:{test_id}")],
        ]),
    )

async def handle_admin_frequent_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    await query.edit_message_text(admin_frequent_errors_text(test_id), reply_markup=admin_back_to_test_keyboard(test_id))

async def handle_admin_export_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    path = export_csv(None)
    await query.message.reply_document(InputFile(path), caption="📤 Экспорт всех данных")
    await query.edit_message_text(admin_export_menu_text(), reply_markup=admin_export_menu_keyboard())

async def handle_admin_export_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    upsert_user(query.from_user)
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Админ-панель недоступна.")
        return
    _, _, test_id = query.data.split(":")
    path = export_csv(test_id)
    await query.message.reply_document(InputFile(path), caption=f"📤 Экспорт по тесту: {effective_test_info(test_id)['title']}")
    await query.edit_message_text(admin_export_menu_text(), reply_markup=admin_export_menu_keyboard())
