"""Обработчики обязательных заданий и реальной проверки подписок."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from database import Database
from keyboards import stage_passed_keyboard, subscriptions_keyboard
from services import SubscriptionChecker
from utils import format_subscription_list

router = Router(name="subscriptions")

SUCCESS_TEXT = (
    "🎉 <b>ВОТ ТЕПЕРЬ ДРУГОЕ ДЕЛО!</b>\n\n"
    "Все обязательные задания успешно выполнены!\n\n"
    "Ты прошёл первый этап получения подарка!"
)


def _build_initial_tasks_text(status_lines: str, has_bot_task: bool) -> str:
    bot_notice = (
        "\n\n⚠️ <i>Примечание: Telegram Bot API не позволяет напрямую проверить запуск стороннего бота. "
        "После запуска нажмите кнопку подтверждения под заданием (при подключённой общей базе проверка "
        "выполняется автоматически).</i>"
        if has_bot_task
        else ""
    )
    return (
        "✨ <b>ОБЯЗАТЕЛЬНЫЕ ЗАДАНИЯ</b>\n\n"
        "Перед получением подарка выполни задания ниже и нажми <b>«✅ ПРОВЕРИТЬ»</b>.\n\n"
        f"<b>Список заданий:</b>\n{status_lines}"
        f"{bot_notice}"
    )


def _build_failed_check_text(status_lines: str, has_uncompleted_bot: bool) -> str:
    bot_warning = (
        "\n\n⚠️ <i>Подтверждение запуска стороннего бота является честным подтверждением пользователя "
        "и не гарантирует запуск без общей базы данных.</i>"
        if has_uncompleted_bot
        else ""
    )
    return (
        "😏 <b>ЭЙ, А ТЫ ЧЕ ХИТРИШЬ?</b>\n\n"
        "Думаешь, можно просто нажать кнопку и получить подарок? 😂\n\n"
        "А ну быстро подписывайся на все каналы!\n\n"
        "🎁 Подарок сам себя не подарит!\n\n"
        f"<b>Список заданий:</b>\n{status_lines}"
        f"{bot_warning}"
    )


@router.callback_query(F.data == "menu:get_gift")
async def cb_get_gift(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    subscription_checker: SubscriptionChecker,
) -> None:
    """Открывает этап обязательных заданий с актуальными статусами."""
    user = callback.from_user
    if user is None:
        return
    await db.upsert_user(user.id, user.username, user.full_name)

    report = await subscription_checker.check_all(bot, user.id)
    if report.all_completed:
        if callback.message is not None:
            try:
                await callback.message.edit_text(SUCCESS_TEXT, reply_markup=stage_passed_keyboard())
            except TelegramBadRequest:
                await callback.message.answer(SUCCESS_TEXT, reply_markup=stage_passed_keyboard())
        await callback.answer("Все обязательные задания уже выполнены!")
        return

    status_lines = format_subscription_list(report)
    has_bot_task = any(i.subscription.task_type == "bot" and not i.is_completed for i in report.items)
    text = _build_initial_tasks_text(status_lines, has_bot_task)
    kb = subscriptions_keyboard(report, is_retry=False)

    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("subs:confirm_bot:"))
async def cb_confirm_partner_bot(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    subscription_checker: SubscriptionChecker,
) -> None:
    """Честное подтверждение запуска третьего бота с предупреждением."""
    user = callback.from_user
    if user is None or not callback.data:
        return

    try:
        sub_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный идентификатор задания.", show_alert=True)
        return

    sub = await db.get_subscription(sub_id)
    if sub is None or sub.task_type != "bot":
        await callback.answer("Задание не найдено.", show_alert=True)
        return

    await db.set_bot_task_confirmed(user.id, True, "honest_confirmation")
    await db.save_task_status(user.id, sub.id, True, "honest_confirmation")

    report = await subscription_checker.check_all(bot, user.id)
    if report.all_completed:
        if callback.message is not None:
            try:
                await callback.message.edit_text(SUCCESS_TEXT, reply_markup=stage_passed_keyboard())
            except TelegramBadRequest:
                await callback.message.answer(SUCCESS_TEXT, reply_markup=stage_passed_keyboard())
        await callback.answer(
            "Подтверждение принято (не гарантирует запуск без общей БД). Все задания выполнены!",
            show_alert=True,
        )
        return

    status_lines = format_subscription_list(report)
    text = _build_initial_tasks_text(status_lines, has_bot_task=False)
    kb = subscriptions_keyboard(report, is_retry=False)
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=kb)
    await callback.answer(
        "Запуск отмечен (честное подтверждение, не гарантирует запуск). Теперь проверьте подписки на каналы.",
        show_alert=True,
    )


@router.callback_query(F.data == "subs:check")
async def cb_check_subscriptions(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    subscription_checker: SubscriptionChecker,
) -> None:
    """Реально проверяет каждый канал отдельно через getChatMember."""
    user = callback.from_user
    if user is None:
        return
    await db.touch_user(user.id)

    report = await subscription_checker.check_all(bot, user.id)
    if report.all_completed:
        if callback.message is not None:
            try:
                await callback.message.edit_text(SUCCESS_TEXT, reply_markup=stage_passed_keyboard())
            except TelegramBadRequest:
                await callback.message.answer(SUCCESS_TEXT, reply_markup=stage_passed_keyboard())
        await callback.answer("🎉 Проверка пройдена!")
        return

    status_lines = format_subscription_list(report)
    has_uncompleted_bot = any(i.subscription.task_type == "bot" and not i.is_completed for i in report.items)
    text = _build_failed_check_text(status_lines, has_uncompleted_bot)
    kb = subscriptions_keyboard(report, is_retry=True)

    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass
    await callback.answer("Не все обязательные задания выполнены!", show_alert=False)
