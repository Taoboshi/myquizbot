"""Admin validation, service, access and metadata screens."""

from .admin_core import *  # noqa: F401,F403 - split from legacy admin UI module
from .admin_users import *  # noqa: F401,F403

def validate_tests_text() -> str:
    lines = ["🧪 Проверка тестов", ""]
    total_questions = 0
    total_duplicates = 0
    has_errors = False

    for test_id, info in TESTS.items():
        title = info["title"]
        lines.append(f"📚 {title}")
        lines.append(f"ID: {test_id}")

        try:
            questions = get_questions(test_id)
        except Exception as exc:
            has_errors = True
            lines.append(f"❌ Не удалось загрузить: {exc}")
            lines.append("")
            continue

        total_questions += len(questions)
        invalid_items = []
        seen: dict[str, int] = {}
        duplicates = []

        for index, question in enumerate(questions):
            q_text = str(question.get("question") or "").strip()
            options = question.get("options") or []
            correct_index = question.get("correct_index")

            problems = []
            if not q_text:
                problems.append("нет текста вопроса")
            if not isinstance(options, list) or len(options) < 2:
                problems.append("меньше 2 вариантов")
            if correct_index is None:
                problems.append("нет correct_index")
            else:
                try:
                    correct_int = int(correct_index)
                    if correct_int < 0 or correct_int >= len(options):
                        problems.append("correct_index вне диапазона")
                except (TypeError, ValueError):
                    problems.append("correct_index не число")

            normalized_question = " ".join(q_text.lower().split())
            normalized_options = "|".join(" ".join(str(option).lower().split()) for option in options)
            normalized = f"{normalized_question}||{normalized_options}||{correct_index}"
            if normalized_question:
                if normalized in seen:
                    duplicates.append((seen[normalized] + 1, index + 1))
                else:
                    seen[normalized] = index

            if problems:
                invalid_items.append((index + 1, ", ".join(problems)))

        total_duplicates += len(duplicates)

        lines.append(f"Вопросов: {len(questions)}")
        if invalid_items:
            has_errors = True
            lines.append(f"❌ Проблемных вопросов: {len(invalid_items)}")
            for num, problem in invalid_items[:10]:
                lines.append(f"• Вопрос {num}: {problem}")
            if len(invalid_items) > 10:
                lines.append(f"• ещё {len(invalid_items) - 10}")
        else:
            lines.append("✅ Структура вопросов: OK")

        if duplicates:
            lines.append(f"⚠️ Дубликатов вопросов: {len(duplicates)}")
            for first, second in duplicates[:10]:
                lines.append(f"• Вопрос {first} повторяется в вопросе {second}")
            if len(duplicates) > 10:
                lines.append(f"• ещё {len(duplicates) - 10}")
        else:
            lines.append("✅ Дубликатов не найдено")

        lines.append("")

    status = "❌ Есть проблемы" if has_errors else "✅ Критичных ошибок не найдено"
    lines.extend([
        "Итог",
        status,
        f"Тестов: {len(TESTS)}",
        f"Вопросов всего: {total_questions}",
        f"Дубликатов всего: {total_duplicates}",
    ])

    return "\n".join(lines)


def admin_clear_user_runtime_confirm_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, очистить", callback_data=f"admin:clear_user_runtime_do:{user_id}:{page}:{sort}")],
        [InlineKeyboardButton("↩️ Отмена", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")],
    ])


def clear_user_runtime_sessions(user_id: int) -> int:
    with db_connect() as conn:
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM runtime_sessions WHERE user_id = ?", (user_id,)).fetchone()
            count = int(row["c"] or 0)
            conn.execute("DELETE FROM runtime_sessions WHERE user_id = ?", (user_id,))
            conn.commit()
            return count
        except Exception:
            return 0

def admin_errors_menu_text() -> str:
    return (
        "🧠 Ошибки\n\n"
        "Здесь можно смотреть самые частые ошибки по всем тестам или отдельно по каждому тесту."
    )


def admin_errors_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("🧠 Частые ошибки по всем тестам", callback_data="admin:frequent_errors_all")]]
    for test_id, info in TESTS.items():
        rows.append([InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:frequent_errors:{test_id}")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_frequent_errors_all_text() -> str:
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT test_id, question_index, SUM(wrong_count) AS c, COUNT(DISTINCT user_id) AS users
            FROM all_time_errors
            WHERE COALESCE(is_resolved, 0) = 0
            GROUP BY test_id, question_index
            ORDER BY c DESC
            LIMIT 15
            """
        ).fetchall()

    lines = ["🧠 Частые ошибки по всем тестам", ""]
    if not rows:
        lines.append("Ошибок пока нет.")
        return "\n".join(lines)

    for n, row in enumerate(rows, start=1):
        test_id = row["test_id"]
        title = TESTS.get(test_id, {}).get("title", test_id)
        questions = get_questions(test_id)
        question_index = int(row["question_index"])
        q = questions[question_index]["question"].replace("\n", " ")
        short = q[:90] + ("…" if len(q) > 90 else "")
        lines.append(f"{n}. {title} · вопрос {question_index + 1}")
        lines.append(f"   Ошибок: {row['c']} · пользователей: {row['users']}")
        lines.append(f"   {short}")

    return "\n".join(lines)


def admin_export_menu_text() -> str:
    return (
        "📤 Экспорт\n\n"
        "Можно выгрузить все попытки сразу или только данные конкретного теста."
    )


def admin_export_menu_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("📦 Все данные", callback_data="admin:export_all")]]
    for test_id, info in TESTS.items():
        rows.append([InlineKeyboardButton(f"📚 {info['title']}", callback_data=f"admin:export_test:{test_id}")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_debug_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin:debug")],
        [InlineKeyboardButton("⚙️ Управление", callback_data="admin:manage")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_manage_text() -> str:
    return (
        "⚙️ Сервис\n\n"
        "Здесь собраны редкие и технические действия, чтобы не перегружать главную админку."
    )


def admin_manage_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Рассылка", callback_data="admin:broadcast_start"),
            InlineKeyboardButton("📤 Экспорт", callback_data="admin:export_menu"),
        ],
        [
            InlineKeyboardButton("🧪 Проверить тесты", callback_data="admin:validate_tests"),
            InlineKeyboardButton("🐞 Debug", callback_data="admin:debug"),
        ],
        [
            InlineKeyboardButton("🚫 Заблокированные", callback_data="admin:blocked_users:0"),
            InlineKeyboardButton("🧹 Runtime", callback_data="admin:clear_runtime_confirm"),
        ],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_clear_runtime_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, очистить", callback_data="admin:clear_runtime_do")],
        [InlineKeyboardButton("↩️ Отмена", callback_data="admin:manage")],
    ])


def clear_runtime_sessions() -> int:
    with db_connect() as conn:
        try:
            row = conn.execute("SELECT COUNT(*) AS c FROM runtime_sessions").fetchone()
            count = int(row["c"] or 0)
            conn.execute("DELETE FROM runtime_sessions")
            conn.commit()
            return count
        except Exception:
            return 0



def _access_icon_for_admin(test_id: str) -> str:
    access_type = TESTS[test_id].get("access", {}).get("type", "public")
    return {
        "public": "🌍",
        "private": "🔐",
        "code": "🔑",
        "admin_only": "🙈",
    }.get(access_type, "🌍")


def admin_test_meta_text(test_id: str) -> str:
    info = effective_test_info(test_id)
    setting = get_test_metadata_setting(test_id)

    subject_id = info.get("subject_id")
    subject = get_subject_info(subject_id) if subject_id else {}
    subject_title = subject.get("title") or info.get("subject_title") or "не привязан"

    lines = [
        "⚙️ Настройки теста",
        "",
        f"Тест: {info.get('title', test_id)}",
        f"ID: {test_id}",
        f"Раздел: {subject_title}",
        "",
        "Здесь меняются название, раздел и служебные действия.",
    ]

    if setting:
        lines.extend(["", f"Изменено: {fmt_msk(setting.get('updated_at'))}"])
    else:
        lines.extend(["", "Источник: JSON / файл"])

    return "\n".join(lines)


def admin_test_meta_keyboard(test_id: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("✏️ Переименовать тест", callback_data=f"admin:set_test_title:{test_id}")],
        [InlineKeyboardButton("📁 Перенести в раздел", callback_data=f"admin:move_test_subject:{test_id}")],
    ]

    if effective_test_info(test_id).get("subject_id"):
        rows.append([InlineKeyboardButton("🧷 Открепить от раздела", callback_data=f"admin:detach_test_subject:{test_id}")])

    rows.extend([
        [
            InlineKeyboardButton("🏆 Рейтинг", callback_data=f"admin:rating:{test_id}"),
            InlineKeyboardButton("📤 Экспорт", callback_data=f"admin:export_test:{test_id}"),
        ],
        [InlineKeyboardButton("🧪 Проверить тест", callback_data=f"admin:validate_test:{test_id}")],
        [InlineKeyboardButton("↩️ К тесту", callback_data=f"admin:test:{test_id}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])
    return InlineKeyboardMarkup(rows)


def admin_move_test_subject_text(test_id: str) -> str:
    info = effective_test_info(test_id)
    subjects = get_subjects()

    lines = [
        "📁 Перенести тест",
        "",
        f"Тест: {info.get('title', test_id)}",
        "",
    ]

    if not subjects:
        lines.append("Сначала создай раздел в 📚 Контент → ➕ Добавить раздел.")
    else:
        lines.append("Выбери раздел, куда перенести тест.")

    return "\n".join(lines)


def admin_move_test_subject_keyboard(test_id: str) -> InlineKeyboardMarkup:
    rows = []

    current_subject_id = effective_test_info(test_id).get("subject_id")
    for subject_id, subject in get_subjects():
        title = subject.get("title", subject_id)
        emoji = subject.get("emoji", "")
        prefix = "✅ " if subject_id == current_subject_id else ""
        rows.append([
            InlineKeyboardButton(
                f"{prefix}{emoji} {title}",
                callback_data=f"admin:move_test_subject_do:{subject_id}:{test_id}",
            )
        ])

    rows.append([InlineKeyboardButton("➕ Добавить раздел", callback_data="admin:add_subject")])
    rows.append([InlineKeyboardButton("↩️ К настройкам теста", callback_data=f"admin:test_meta:{test_id}")])
    return InlineKeyboardMarkup(rows)

def admin_test_access_text(test_id: str) -> str:
    info = effective_test_info(test_id)
    base = TESTS[test_id]
    base_access = info.get("access", {}) or {}
    effective = effective_test_access(test_id)
    override = get_test_access_setting(test_id)

    base_type = base_access.get("type", "public")
    effective_type = effective.get("type", "public")
    code = effective.get("code") or "—"

    granted_users = list_test_access_users(test_id)
    allowed_users = base_access.get("users") or []
    try:
        allowed_users = [int(x) for x in allowed_users]
    except Exception:
        allowed_users = []

    total_with_access = len(set(granted_users) | set(allowed_users))

    source_text = "из админки" if override else "из JSON"
    lines = [
        "🔐 Доступ к тесту",
        "",
        f"📚 {info['title']}",
        f"Текущий доступ: {access_type_label(effective_type)}",
        f"Базовый доступ в JSON: {access_type_label(base_type)}",
        f"Источник настройки: {source_text}",
        f"Код доступа: {code if effective_type == 'code' else '—'}",
        f"Пользователей с доступом: {total_with_access}",
        "",
    ]

    if effective_type == "public":
        lines.extend([
            "🌍 Тест открыт всем.",
            "Ручной доступ пользователям не нужен.",
        ])
    elif effective_type == "private":
        lines.extend([
            "🔐 Приватный тест видят только админ и пользователи с доступом.",
            "Доступ можно выдать из карточки пользователя.",
        ])
    elif effective_type == "code":
        lines.extend([
            "🔑 Тест виден всем как закрытый.",
            "После правильного кода доступ сохраняется в базе.",
            "Доступ также можно выдать вручную из карточки пользователя.",
        ])
    elif effective_type == "admin_only":
        lines.extend([
            "🙈 Тест видит только админ.",
            "Обычные пользователи его не увидят.",
        ])

    if override:
        lines.extend([
            "",
            f"Изменено: {fmt_msk(override.get('updated_at'))}",
        ])

    if total_with_access:
        lines.extend(["", "👥 Пользователи с доступом:"])
        user_ids = sorted(set(granted_users) | set(allowed_users))
        with db_connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, username, first_name, last_name
                FROM users
                WHERE user_id IN ({})
                ORDER BY last_seen_at DESC
                """.format(",".join(["?"] * len(user_ids))),
                tuple(user_ids),
            ).fetchall()
        for row in rows[:15]:
            lines.append(f"• {user_display_name(row)}")
        if len(rows) > 15:
            lines.append(f"• ещё {len(rows) - 15}")

    return "\n".join(lines)


def admin_test_access_keyboard(test_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🌍 Открытый", callback_data=f"admin:set_access:{test_id}:public"),
            InlineKeyboardButton("🔐 Приватный", callback_data=f"admin:set_access:{test_id}:private"),
        ],
        [
            InlineKeyboardButton("🔑 По коду", callback_data=f"admin:set_access:{test_id}:code"),
            InlineKeyboardButton("🙈 Только админ", callback_data=f"admin:set_access:{test_id}:admin_only"),
        ],
        [InlineKeyboardButton("✏️ Изменить код", callback_data=f"admin:set_access_code:{test_id}")],
        [InlineKeyboardButton("↩️ Сбросить к JSON", callback_data=f"admin:reset_access:{test_id}")],
        [InlineKeyboardButton("👥 Пользователи с доступом", callback_data=f"admin:test_access_users:{test_id}:0")],
        [InlineKeyboardButton("📚 К тесту", callback_data=f"admin:test:{test_id}")],
        [InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")],
    ])


def admin_test_access_users_text(test_id: str, page: int = 0) -> str:
    info = effective_test_info(test_id)
    access = TESTS[test_id].get("access", {}) or {}
    granted_users = list_test_access_users(test_id)
    allowed_users = access.get("users") or []
    try:
        allowed_users = [int(x) for x in allowed_users]
    except Exception:
        allowed_users = []

    user_ids = sorted(set(granted_users) | set(allowed_users))
    page = max(0, page)
    offset = page * ADMIN_USERS_PAGE_SIZE
    chunk = user_ids[offset:offset + ADMIN_USERS_PAGE_SIZE]

    lines = [
        "👥 Пользователи с доступом",
        "",
        f"📚 {info['title']}",
        f"Всего: {len(user_ids)}",
        "",
    ]

    if not chunk:
        lines.append("Пока никому не выдан доступ.")
        return "\n".join(lines)

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT user_id, username, first_name, last_name, last_seen_at
            FROM users
            WHERE user_id IN ({})
            ORDER BY last_seen_at DESC
            """.format(",".join(["?"] * len(chunk))),
            tuple(chunk),
        ).fetchall()

    by_id = {int(row["user_id"]): row for row in rows}
    for n, user_id in enumerate(chunk, start=offset + 1):
        row = by_id.get(user_id)
        name = user_display_name(row) if row else f"ID {user_id}"
        lines.append(f"{n}. {name}")

    return "\n".join(lines)


def admin_test_access_users_keyboard(test_id: str, page: int = 0) -> InlineKeyboardMarkup:
    access = TESTS[test_id].get("access", {}) or {}
    granted_users = list_test_access_users(test_id)
    allowed_users = access.get("users") or []
    try:
        allowed_users = [int(x) for x in allowed_users]
    except Exception:
        allowed_users = []

    user_ids = sorted(set(granted_users) | set(allowed_users))
    total_pages = max(1, (len(user_ids) + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)

    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin:test_access_users:{test_id}:{page - 1}"))
    if page + 1 < total_pages:
        nav.append(InlineKeyboardButton("➡️ Далее", callback_data=f"admin:test_access_users:{test_id}:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("🔐 К доступу теста", callback_data=f"admin:test_access:{test_id}")])
    rows.append([InlineKeyboardButton("📚 К тесту", callback_data=f"admin:test:{test_id}")])
    return InlineKeyboardMarkup(rows)


def admin_user_access_text(user_id: int) -> str:
    with db_connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    lines = [
        "🔐 Доступы пользователя",
        "",
        f"Пользователь: {user_display_name(user) if user else f'ID {user_id}'}",
        "",
    ]

    for subject_id, subject in get_subjects():
        subject_tests = get_tests_for_subject(subject_id)
        if not subject_tests:
            continue

        lines.append(f"{subject.get('emoji', '')} {subject.get('title', subject_id)}")
        for test_id, info in subject_tests:
            access_type = effective_access_type(test_id)
            has_access = has_user_test_access(user_id, test_id)
            built_in_users = info.get("access", {}).get("users") or []
            try:
                built_in = int(user_id) in [int(x) for x in built_in_users]
            except Exception:
                built_in = False

            if access_type == "public":
                status = "🌍 открыт всем"
            elif access_type == "admin_only":
                status = "🙈 только админ"
            elif has_access or built_in:
                status = "✅ доступ есть"
            elif access_type == "code":
                status = "🔒 по коду"
            else:
                status = "❌ доступа нет"

            lines.append(f"• {info['title']}: {status}")
        lines.append("")

    return "\n".join(lines).rstrip()


def admin_user_access_keyboard(user_id: int, page: int = 0, sort: str = "recent") -> InlineKeyboardMarkup:
    rows = []

    for subject_id, subject in get_subjects():
        for test_id, info in get_tests_for_subject(subject_id):
            access_type = effective_access_type(test_id)
            if access_type in {"public", "admin_only"}:
                continue

            has_access = has_user_test_access(user_id, test_id)
            if has_access:
                label = f"➖ Забрать: {info['title']}"
                callback = f"admin:revoke_access:{user_id}:{test_id}:{page}:{sort}"
            else:
                label = f"➕ Выдать: {info['title']}"
                callback = f"admin:grant_access:{user_id}:{test_id}:{page}:{sort}"

            if len(label) > 45:
                label = label[:42].rstrip() + "…"
            rows.append([InlineKeyboardButton(label, callback_data=callback)])

    if not rows:
        rows.append([InlineKeyboardButton("Нет закрытых тестов для управления", callback_data="admin:noop")])

    rows.append([InlineKeyboardButton("👤 К пользователю", callback_data=f"admin:global_user:{user_id}:{page}:{sort}")])
    rows.append([InlineKeyboardButton("🏠 В админку", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


