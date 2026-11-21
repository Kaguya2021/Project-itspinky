"""Обработчики команды /start и разделов главного меню."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import Database
from keyboards import back_to_menu_keyboard, main_menu_keyboard
from utils import escape_html

router = Router(name="start")

WELCOME_TEXT = (
    "🎁 <b>ДОБРО ПОЖАЛОВАТЬ В TSPINKY GIFT!</b>\n\n"
    "Хочешь получить Telegram-подарок?\n\n"
    "Выполни несколько простых заданий и участвуй в нашей акции!"
)

HOW_TO_TEXT = (
    "❓ <b>КАК ПОЛУЧИТЬ ПОДАРОК</b>\n\n"
    "1️⃣ Нажми <b>«🎁 Получить подарок»</b> и выполни обязательные подписки.\n"
    "2️⃣ Пройди реальную проверку участия.\n"
    "3️⃣ Выбери готовый комментарий и опубликуй его под подходящим видео в TikTok.\n"
    "4️⃣ Отправь скриншот комментария в бот.\n"
    "5️⃣ Дождись проверки администратором — после одобрения ты попадёшь в счётчик участников акции.\n\n"
    "✨ <i>Подарки выдаются администратором вручную после подтверждения выполнения всех условий акции.</i>"
)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, state: FSMContext) -> None:
    """Регистрирует пользователя и открывает главное меню."""
    await state.clear()
    if message.from_user is not None:
        await db.upsert_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    """Возвращает пользователя в главное меню."""
    await state.clear()
    if callback.from_user is not None:
        await db.touch_user(callback.from_user.id)
    if callback.message is not None:
        try:
            await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:how_to")
async def cb_how_to(callback: CallbackQuery, db: Database) -> None:
    """Показывает инструкцию участия в акции."""
    if callback.from_user is not None:
        await db.touch_user(callback.from_user.id)
    if callback.message is not None:
        try:
            await callback.message.edit_text(HOW_TO_TEXT, reply_markup=back_to_menu_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(HOW_TO_TEXT, reply_markup=back_to_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery, db: Database) -> None:
    """Показывает контакты поддержки."""
    if callback.from_user is not None:
        await db.touch_user(callback.from_user.id)
    support = await db.get_setting("support_contact", "@kaguya2_0")
    text = (
        "💬 <b>ПОДДЕРЖКА TSPINKY GIFT</b>\n\n"
        f"По всем вопросам по акции, проверке заявок и выдаче подарков пишите: <b>{escape_html(support)}</b>\n\n"
        "При обращении укажите ваш Telegram ID и номер заявки (если она уже отправлена)."
    )
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
