"""Клавиатуры пользовательского интерфейса TSPINKY GIFT."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import CommentRecord
from services.subscription_checker import SubscriptionCheckReport

try:
    from aiogram.types import CopyTextButton
except ImportError:  # pragma: no cover - совместимость со старыми версиями aiogram 3.x
    CopyTextButton = None  # type: ignore[assignment]


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Получить подарок", callback_data="menu:get_gift")
    builder.button(text="📊 Моя статистика", callback_data="menu:stats")
    builder.button(text="❓ Как получить подарок", callback_data="menu:how_to")
    builder.button(text="💬 Поддержка", callback_data="menu:support")
    builder.adjust(1, 2, 1)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В главное меню", callback_data="menu:home")
    return builder.as_markup()


def subscriptions_keyboard(report: SubscriptionCheckReport, is_retry: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура обязательных заданий: показывает кнопки только для невыполненных заданий."""
    builder = InlineKeyboardBuilder()

    for item in report.items:
        if item.is_completed:
            continue
        sub = item.subscription
        builder.row(
            InlineKeyboardButton(
                text=f"{sub.button_text} • {sub.title}",
                url=sub.url,
            )
        )
        if sub.task_type == "bot":
            builder.row(
                InlineKeyboardButton(
                    text=f"✅ Я запустил {sub.title}",
                    callback_data=f"subs:confirm_bot:{sub.id}",
                )
            )

    check_text = "🔄 ПРОВЕРИТЬ ЕЩЁ РАЗ" if is_retry else "✅ ПРОВЕРИТЬ"
    builder.row(InlineKeyboardButton(text=check_text, callback_data="subs:check"))
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:home"))
    return builder.as_markup()


def stage_passed_keyboard() -> InlineKeyboardMarkup:
    """Кнопка перехода к рекламному заданию после прохождения первого этапа."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 ПЕРЕЙТИ К ЗАДАНИЮ", callback_data="task:promo")
    builder.button(text="⬅️ В главное меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def promo_task_keyboard() -> InlineKeyboardMarkup:
    """Кнопки экрана рекламного задания."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Выбрать комментарий", callback_data="comments:page:1")
    builder.button(text="🔄 Обновить прогресс", callback_data="task:promo")
    builder.button(text="⬅️ В главное меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def comments_page_keyboard(
    comments: list[CommentRecord],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Клавиатура списка комментариев с поддержкой нативного copy_text."""
    builder = InlineKeyboardBuilder()

    for comment in comments:
        if CopyTextButton is not None:
            copy_btn = InlineKeyboardButton(
                text=f"📋 СКОПИРОВАТЬ #{comment.sort_order}",
                copy_text=CopyTextButton(text=comment.text),
            )
        else:
            copy_btn = InlineKeyboardButton(
                text=f"📋 СКОПИРОВАТЬ #{comment.sort_order}",
                callback_data=f"comments:copy_fallback:{comment.id}",
            )
        select_btn = InlineKeyboardButton(
            text=f"✅ Выбрать #{comment.sort_order}",
            callback_data=f"comments:select:{comment.id}",
        )
        builder.row(copy_btn, select_btn)

    nav_buttons: list[InlineKeyboardButton] = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"comments:page:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"· {page}/{total_pages} ·", callback_data="comments:noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"comments:page:{page + 1}"))
    builder.row(*nav_buttons)

    builder.row(InlineKeyboardButton(text="⬅️ К прогрессу акции", callback_data="task:promo"))
    return builder.as_markup()


def cancel_photo_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отмены отправки фотоотчёта."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Выбрать другой комментарий", callback_data="comments:page:1")
    builder.button(text="❌ Отмена", callback_data="app:cancel")
    builder.adjust(1)
    return builder.as_markup()
