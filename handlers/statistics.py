"""Обработчик раздела «Моя статистика» для пользователя."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from database import Database
from keyboards import back_to_menu_keyboard
from utils import STATUS_LABELS, escape_html, format_progress_block

router = Router(name="statistics")


@router.callback_query(F.data == "menu:stats")
async def cb_user_statistics(callback: CallbackQuery, db: Database) -> None:
    """Показывает личную статистику пользователя и общий прогресс акции."""
    user_tg = callback.from_user
    if user_tg is None:
        return

    user = await db.upsert_user(user_tg.id, user_tg.username, user_tg.full_name)
    apps = await db.get_user_applications(user.telegram_id, limit=5)
    unique_count = await db.get_unique_participants_count()
    tiers = await db.list_gift_tiers(active_only=True)

    participant_status = (
        "✅ Ты учтён в числе уникальных участников акции"
        if user.is_counted_participant
        else "⏳ Твоя заявка ещё не одобрена"
    )

    if apps:
        last_app = apps[0]
        last_status = STATUS_LABELS.get(last_app.status, last_app.status)
        gift_info = (
            f"🎁 Выдан подарок: <b>{escape_html(last_app.issued_gift_name)}</b>"
            if last_app.gift_issued
            else "🎁 Подарок: ожидает решения и выдачи администратором"
        )
        app_block = (
            f"📸 <b>Последняя заявка:</b> <code>{escape_html(last_app.application_number)}</code>\n"
            f"📌 <b>Статус:</b> {last_status}\n"
            f"{gift_info}"
        )
    else:
        app_block = "📸 <b>Заявки:</b> ты ещё не отправлял фотоотчёт."

    progress_block = format_progress_block(unique_count, tiers)

    text = (
        "📊 <b>МОЯ СТАТИСТИКА</b>\n\n"
        f"🆔 <b>Твой ID:</b> <code>{user.telegram_id}</code>\n"
        f"🏆 <b>Статус участия:</b> {participant_status}\n"
        f"🗂 <b>Всего отправлено заявок:</b> {user.applications_count}\n\n"
        f"{app_block}\n\n"
        f"{progress_block}"
    )

    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=back_to_menu_keyboard())
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=back_to_menu_keyboard())
    await callback.answer()
