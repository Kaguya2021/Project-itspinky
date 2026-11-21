"""Обработчик раздела выбора из 20 готовых комментариев с copy_text."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

from database import Database
from keyboards import cancel_photo_keyboard, comments_page_keyboard
from utils import escape_html

router = Router(name="comments")

COMMENTS_PER_PAGE = 5


class ApplicationStates(StatesGroup):
    """Состояния отправки фотоотчёта пользователем."""

    waiting_for_photo = State()


@router.callback_query(F.data == "comments:noop")
async def cb_comments_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("comments:page:"))
async def cb_comments_page(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    """Отображает страницу из 20 готовых комментариев с кнопками копирования и выбора."""
    await state.clear()
    if callback.from_user is not None:
        await db.touch_user(callback.from_user.id)

    try:
        page = max(1, int((callback.data or "comments:page:1").split(":")[2]))
    except (IndexError, ValueError):
        page = 1

    all_comments = await db.list_comments(active_only=True)
    if not all_comments:
        await callback.answer("Список комментариев пуст.", show_alert=True)
        return

    total_pages = max(1, math.ceil(len(all_comments) / COMMENTS_PER_PAGE))
    page = min(page, total_pages)
    start_idx = (page - 1) * COMMENTS_PER_PAGE
    page_items = all_comments[start_idx : start_idx + COMMENTS_PER_PAGE]

    lines = [
        f"💬 <b>ВЫБЕРИТЕ КОММЕНТАРИЙ</b> (стр. {page}/{total_pages})",
        "",
        "Нажмите <b>«📋 СКОПИРОВАТЬ»</b>, чтобы скопировать текст, затем <b>«✅ Выбрать»</b> для отправки скриншота:",
        "",
    ]
    for item in page_items:
        lines.append(f"<b>{item.sort_order}.</b> <code>{escape_html(item.text)}</code>")

    text = "\n".join(lines)
    kb = comments_page_keyboard(page_items, page, total_pages)

    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("comments:copy_fallback:"))
async def cb_comment_copy_fallback(callback: CallbackQuery, db: Database) -> None:
    """Резервный способ копирования, если клиент/версия не поддерживает copy_text."""
    try:
        comment_id = int((callback.data or "").split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Комментарий не найден.", show_alert=True)
        return

    comment = await db.get_comment(comment_id)
    if comment is None:
        await callback.answer("Комментарий не найден.", show_alert=True)
        return

    if callback.message is not None:
        await callback.message.answer(
            f"📋 Нажмите на текст, чтобы скопировать:\n\n<code>{escape_html(comment.text)}</code>"
        )
    await callback.answer("Текст отправлен для копирования!")


@router.callback_query(F.data.startswith("comments:select:"))
async def cb_select_comment(callback: CallbackQuery, db: Database, state: FSMContext) -> None:
    """Фиксирует выбранный комментарий и переводит пользователя в режим ожидания скриншота."""
    user = callback.from_user
    if user is None or not callback.data:
        return
    await db.touch_user(user.id)

    try:
        comment_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный выбор комментария.", show_alert=True)
        return

    comment = await db.get_comment(comment_id)
    if comment is None:
        await callback.answer("Комментарий не найден.", show_alert=True)
        return

    await state.set_state(ApplicationStates.waiting_for_photo)
    await state.update_data(comment_id=comment.id, comment_text=comment.text)

    text = (
        "📸 <b>ПОСЛЕДНИЙ ШАГ!</b>\n\n"
        "Опубликуй выбранный комментарий и отправь сюда скриншот результата.\n\n"
        f"💬 <b>Твой комментарий:</b>\n<code>{escape_html(comment.text)}</code>"
    )

    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=cancel_photo_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=cancel_photo_keyboard())
    await callback.answer("Отправь скриншот комментария в чат 📸")
