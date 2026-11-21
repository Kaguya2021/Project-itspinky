"""Обработчик экрана рекламного задания и прогресса подарков."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from database import Database
from keyboards import promo_task_keyboard, subscriptions_keyboard
from services import SubscriptionChecker
from utils import format_progress_block, format_subscription_list

router = Router(name="tasks")


@router.callback_query(F.data == "task:promo")
async def cb_promo_task(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    subscription_checker: SubscriptionChecker,
) -> None:
    """Показывает рекламное задание и актуальный прогресс акции."""
    user = callback.from_user
    if user is None:
        return
    await db.touch_user(user.id)

    # Не пускаем к рекламному заданию, если пользователь отписался от каналов
    report = await subscription_checker.check_all(bot, user.id)
    if not report.all_completed:
        status_lines = format_subscription_list(report)
        text = (
            "😏 <b>ЭЙ, А ТЫ ЧЕ ХИТРИШЬ?</b>\n\n"
            "Думаешь, можно просто нажать кнопку и получить подарок? 😂\n\n"
            "А ну быстро подписывайся на все каналы!\n\n"
            "🎁 Подарок сам себя не подарит!\n\n"
            f"<b>Список заданий:</b>\n{status_lines}"
        )
        if callback.message is not None:
            try:
                await callback.message.edit_text(text, reply_markup=subscriptions_keyboard(report, is_retry=True))
            except TelegramBadRequest:
                await callback.message.answer(text, reply_markup=subscriptions_keyboard(report, is_retry=True))
        await callback.answer("Сначала выполните все обязательные задания!", show_alert=True)
        return

    unique_count = await db.get_unique_participants_count()
    tiers = await db.list_gift_tiers(active_only=True)
    progress_block = format_progress_block(unique_count, tiers)

    text = (
        "🔥 <b>ОТЛИЧНО! ПЕРВЫЙ ЭТАП ПРОЙДЕН!</b>\n\n"
        "Теперь осталось выполнить рекламное задание.\n\n"
        "Расскажи о нашем боте в TikTok или оставь комментарий под подходящим видео.\n\n"
        "В зависимости от количества уникальных подтверждённых участников открываются разные уровни подарков.\n\n"
        f"{progress_block}\n\n"
        "<i>Учитываются только уникальные пользователи с одобренными фотоотчётами.</i>"
    )

    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=promo_task_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=promo_task_keyboard())
    await callback.answer()
