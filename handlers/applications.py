"""Обработчик приёма фотоотчётов от пользователей и отправки их администратору."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import BotConfig
from database import Database
from handlers.comments import ApplicationStates
from keyboards import application_moderation_keyboard, main_menu_keyboard
from services import ApplicationService
from utils import format_application_admin_caption

logger = logging.getLogger(__name__)
router = Router(name="applications")


@router.callback_query(F.data == "app:cancel")
async def cb_cancel_application(callback: CallbackQuery, state: FSMContext) -> None:
    """Отменяет ожидание фотоотчёта и возвращает в главное меню."""
    await state.clear()
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                "Отправка фотоотчёта отменена. Вы вернулись в главное меню.",
                reply_markup=main_menu_keyboard(),
            )
        except TelegramBadRequest:
            await callback.message.answer(
                "Отправка фотоотчёта отменена. Вы вернулись в главное меню.",
                reply_markup=main_menu_keyboard(),
            )
    await callback.answer()


@router.message(ApplicationStates.waiting_for_photo, F.photo)
async def handle_photo_report(
    message: Message,
    bot: Bot,
    db: Database,
    config: BotConfig,
    application_service: ApplicationService,
    state: FSMContext,
) -> None:
    """Принимает фотоотчёт, сохраняет заявку и пересылает администратору."""
    user = message.from_user
    if user is None or not message.photo:
        return

    await db.upsert_user(user.id, user.username, user.full_name)
    data = await state.get_data()
    comment_id = data.get("comment_id")
    comment_text = str(data.get("comment_text", "")).strip()

    if not comment_text:
        await state.clear()
        await message.answer(
            "⚠️ Не выбран комментарий. Нажмите «🎁 Получить подарок» и выберите текст заново.",
            reply_markup=main_menu_keyboard(),
        )
        return

    best_photo = message.photo[-1]
    result = await application_service.submit_photo_report(
        bot=bot,
        user_id=user.id,
        username=user.username,
        comment_id=comment_id,
        comment_text=comment_text,
        photo_file_id=best_photo.file_id,
        photo_file_unique_id=best_photo.file_unique_id,
    )

    if not result.success or result.application is None:
        await message.answer(
            result.error_message or "❌ Не удалось принять фотоотчёт.",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    app = result.application
    await state.clear()

    # Отправляем фотоотчёт главному администратору
    caption = format_application_admin_caption(app)
    try:
        admin_msg = await bot.send_photo(
            chat_id=config.admin_id,
            photo=app.photo_file_id,
            caption=caption,
            reply_markup=application_moderation_keyboard(app),
        )
        await db.set_application_admin_message(app.id, admin_msg.message_id)
    except TelegramAPIError as exc:
        logger.error("Не удалось отправить заявку %s администратору %s: %s", app.application_number, config.admin_id, exc)

    await message.answer(
        "⏳ <b>ФОТООТЧЁТ ПОЛУЧЕН!</b>\n\n"
        f"Номер заявки: <code>{app.application_number}</code>\n\n"
        "Твоя заявка отправлена администратору.\n\n"
        "Пожалуйста, дождись проверки. После проверки ты получишь уведомление.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(ApplicationStates.waiting_for_photo)
async def handle_non_photo_in_report_state(message: Message) -> None:
    """Напоминает пользователю отправить именно фотографию (скриншот)."""
    await message.answer(
        "📸 Пожалуйста, отправь именно <b>скриншот (фотографию)</b> опубликованного комментария.\n"
        "Если хочешь отменить — нажми кнопку отмены выше."
    )
