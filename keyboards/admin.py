"""Клавиатуры административной панели TSPINKY GIFT."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import ApplicationRecord, GiftTierRecord, SubscriptionRecord, UserRecord


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="👥 Пользователи", callback_data="admin:users:1")
    builder.button(text="📸 Фотоотчёты", callback_data="admin:apps:pending:1")
    builder.button(text="📢 Управление каналами", callback_data="admin:channels")
    builder.button(text="🎁 Управление подарками", callback_data="admin:gifts")
    builder.button(text="⚙️ Настройки", callback_data="admin:settings")
    builder.button(text="📨 Рассылка", callback_data="admin:broadcast")
    builder.button(text="🔍 Поиск пользователя", callback_data="admin:search")
    builder.button(text="🧾 Логи действий", callback_data="admin:logs")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def admin_back_keyboard(target: str = "admin:home", label: str = "⬅️ В админ-панель") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=label, callback_data=target)
    return builder.as_markup()


def admin_cancel_fsm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить ввод", callback_data="admin:cancel_fsm")
    return builder.as_markup()


def application_moderation_keyboard(app: ApplicationRecord) -> InlineKeyboardMarkup:
    """Кнопки модерации заявки, приходящей администратору."""
    builder = InlineKeyboardBuilder()
    if app.status == "pending":
        builder.row(
            InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"admin:app_approve:{app.id}"),
            InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"admin:app_reject:{app.id}"),
        )
    elif app.status == "approved" and not app.gift_issued:
        builder.row(
            InlineKeyboardButton(text="🎁 ВЫДАТЬ ПОДАРОК", callback_data=f"admin:gift_menu:{app.id}")
        )

    builder.row(
        InlineKeyboardButton(text="👤 ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ", callback_data=f"admin:user:{app.user_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📸 К списку заявок", callback_data="admin:apps:pending:1")
    )
    return builder.as_markup()


def gift_issue_select_keyboard(app_id: int, tiers: list[GiftTierRecord]) -> InlineKeyboardMarkup:
    """Клавиатура выбора фактически выданного подарка."""
    builder = InlineKeyboardBuilder()
    for tier in tiers:
        builder.row(
            InlineKeyboardButton(
                text=f"{tier.emoji} Выдать: {tier.name}",
                callback_data=f"admin:gift_issue:{app_id}:{tier.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад к заявке", callback_data=f"admin:app_view:{app_id}"))
    return builder.as_markup()


def admin_applications_list_keyboard(
    apps: list[ApplicationRecord],
    status: str,
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    """Список заявок с фильтрами по статусу."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="• ⏳ Ожидают" if status == "pending" else "⏳ Ожидают",
            callback_data="admin:apps:pending:1",
        ),
        InlineKeyboardButton(
            text="• ✅ Одобрены" if status == "approved" else "✅ Одобрены",
            callback_data="admin:apps:approved:1",
        ),
        InlineKeyboardButton(
            text="• ❌ Отклонены" if status == "rejected" else "❌ Отклонены",
            callback_data="admin:apps:rejected:1",
        ),
    )

    for app in apps:
        gift_mark = " 🎁" if app.gift_issued else ""
        user_label = f"@{app.username}" if app.username else str(app.user_id)
        builder.row(
            InlineKeyboardButton(
                text=f"{app.application_number} • {user_label}{gift_mark}",
                callback_data=f"admin:app_view:{app.id}",
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin:apps:{status}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"Стр. {page}", callback_data="admin:noop"))
    if has_next:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin:apps:{status}:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin:home"))
    return builder.as_markup()


def admin_users_list_keyboard(users: list[UserRecord], page: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        badge = "🚫" if user.is_banned else ("✅" if user.is_counted_participant else "👤")
        label = f"@{user.username}" if user.username else user.full_name or str(user.telegram_id)
        builder.row(
            InlineKeyboardButton(
                text=f"{badge} {label} ({user.telegram_id})",
                callback_data=f"admin:user:{user.telegram_id}",
            )
        )

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"admin:users:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"Стр. {page}", callback_data="admin:noop"))
    if has_next:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin:users:{page + 1}"))
    builder.row(*nav)
    builder.row(InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin:home"))
    return builder.as_markup()


def admin_user_profile_keyboard(user: UserRecord, latest_approved_app_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if latest_approved_app_id is not None:
        builder.row(
            InlineKeyboardButton(
                text="🎁 ВЫДАТЬ ПОДАРОК",
                callback_data=f"admin:gift_menu:{latest_approved_app_id}",
            )
        )
    if user.is_banned:
        builder.row(InlineKeyboardButton(text="✅ Разблокировать", callback_data=f"admin:unban:{user.telegram_id}"))
    else:
        builder.row(InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:ban:{user.telegram_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ К пользователям", callback_data="admin:users:1"))
    builder.row(InlineKeyboardButton(text="🏠 В админ-панель", callback_data="admin:home"))
    return builder.as_markup()


def admin_channels_keyboard(subs: list[SubscriptionRecord]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sub in subs:
        state_icon = "🟢" if sub.is_active else "⚪️"
        type_icon = "📢" if sub.task_type == "channel" else "🤖"
        builder.row(
            InlineKeyboardButton(
                text=f"{state_icon} {type_icon} {sub.title}",
                callback_data=f"admin:channel_toggle:{sub.id}",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"admin:channel_del:{sub.id}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin:channel_add"))
    builder.row(InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin:home"))
    return builder.as_markup()


def admin_gifts_keyboard(tiers: list[GiftTierRecord]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tier in tiers:
        builder.row(
            InlineKeyboardButton(
                text=f"{tier.emoji} {tier.name} ({tier.target_participants} уч.)",
                callback_data=f"admin:gift_edit:{tier.id}",
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"admin:gift_del:{tier.id}"),
        )
    builder.row(InlineKeyboardButton(text="➕ Добавить подарок", callback_data="admin:gift_add"))
    builder.row(InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin:home"))
    return builder.as_markup()


def admin_settings_keyboard(promo_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_label = "⏸ Приостановить акцию" if promo_active else "▶️ Возобновить акцию"
    builder.row(InlineKeyboardButton(text=toggle_label, callback_data="admin:toggle_promo"))
    builder.row(InlineKeyboardButton(text="⏱ Изменить интервал заявок", callback_data="admin:edit_cooldown"))
    builder.row(InlineKeyboardButton(text="💬 Изменить контакт поддержки", callback_data="admin:edit_support"))
    builder.row(InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin:home"))
    return builder.as_markup()
