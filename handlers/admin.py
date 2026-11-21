"""Административная панель и модерация заявок TSPINKY GIFT.

Доступ строго ограничен Telegram ID главного администратора (по умолчанию 6511859639).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import BotConfig
from database import Database
from keyboards import (
    admin_applications_list_keyboard,
    admin_back_keyboard,
    admin_cancel_fsm_keyboard,
    admin_channels_keyboard,
    admin_gifts_keyboard,
    admin_main_keyboard,
    admin_settings_keyboard,
    admin_user_profile_keyboard,
    admin_users_list_keyboard,
    application_moderation_keyboard,
    gift_issue_select_keyboard,
)
from services import ApplicationService
from utils import (
    escape_html,
    format_application_admin_caption,
    format_progress_block,
    format_user_profile,
)

logger = logging.getLogger(__name__)

USERS_PER_PAGE = 8
APPS_PER_PAGE = 8


class AdminOnlyFilter(BaseFilter):
    """Строгий фильтр доступа только для главного администратора."""

    def __init__(self, admin_id: int) -> None:
        self.admin_id = admin_id

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            return False
        return user.id == self.admin_id


class AdminStates(StatesGroup):
    """FSM-состояния административной панели."""

    add_channel = State()
    add_gift = State()
    edit_gift_target = State()
    edit_cooldown = State()
    edit_support = State()
    broadcast_message = State()
    search_user = State()


def create_admin_router(admin_id: int) -> Router:
    """Создаёт роутер админ-панели с жёсткой привязкой фильтра AdminOnlyFilter."""
    router = Router(name="admin")
    admin_filter = AdminOnlyFilter(admin_id)
    router.message.filter(admin_filter)
    router.callback_query.filter(admin_filter)

    async def _edit_or_send(callback: CallbackQuery, text: str, reply_markup=None) -> None:
        if callback.message is None:
            return
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=reply_markup)

    # ------------------------------------------------------------------
    # Вход и главное меню админ-панели
    # ------------------------------------------------------------------

    @router.message(Command("admin"))
    async def cmd_admin(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "👑 <b>АДМИН-ПАНЕЛЬ TSPINKY GIFT</b>\n\n"
            "Выберите раздел управления:",
            reply_markup=admin_main_keyboard(),
        )

    @router.callback_query(F.data == "admin:noop")
    async def cb_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.callback_query(F.data == "admin:home")
    async def cb_admin_home(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await _edit_or_send(
            callback,
            "👑 <b>АДМИН-ПАНЕЛЬ TSPINKY GIFT</b>\n\nВыберите раздел управления:",
            reply_markup=admin_main_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:cancel_fsm")
    async def cb_cancel_fsm(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await _edit_or_send(
            callback,
            "Действие отменено. Вы в главном меню админ-панели.",
            reply_markup=admin_main_keyboard(),
        )
        await callback.answer("Отменено")

    # ------------------------------------------------------------------
    # 📊 Статистика
    # ------------------------------------------------------------------

    @router.callback_query(F.data == "admin:stats")
    async def cb_admin_stats(callback: CallbackQuery, db: Database) -> None:
        stats = await db.get_statistics()
        progress_block = format_progress_block(stats["unique_participants"], stats["gift_tiers"])
        text = (
            "📊 <b>СТАТИСТИКА TSPINKY GIFT</b>\n\n"
            f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
            f"🟢 Активных за 7 дней: <b>{stats['active_users']}</b>\n\n"
            f"📸 Всего заявок: <b>{stats['total_applications']}</b>\n"
            f"✅ Одобрено: <b>{stats['approved_applications']}</b>\n"
            f"❌ Отклонено: <b>{stats['rejected_applications']}</b>\n"
            f"⏳ Ожидают проверки: <b>{stats['pending_applications']}</b>\n\n"
            f"🏆 Уникальных участников акции: <b>{stats['unique_participants']}</b>\n"
            f"🎁 Фактически выдано подарков: <b>{stats['gifts_issued']}</b>\n\n"
            f"{progress_block}"
        )
        await _edit_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()

    # ------------------------------------------------------------------
    # 👥 Пользователи и профиль
    # ------------------------------------------------------------------

    @router.callback_query(F.data.startswith("admin:users:"))
    async def cb_admin_users(callback: CallbackQuery, db: Database) -> None:
        try:
            page = max(1, int((callback.data or "admin:users:1").split(":")[2]))
        except (IndexError, ValueError):
            page = 1
        offset = (page - 1) * USERS_PER_PAGE
        users = await db.list_users(offset=offset, limit=USERS_PER_PAGE + 1)
        has_next = len(users) > USERS_PER_PAGE
        page_users = users[:USERS_PER_PAGE]
        text = (
            f"👥 <b>ПОЛЬЗОВАТЕЛИ</b> (стр. {page})\n\n"
            "Нажмите на пользователя, чтобы открыть профиль и историю заявок:"
            if page_users
            else "👥 Пользователей пока нет."
        )
        await _edit_or_send(
            callback,
            text,
            reply_markup=admin_users_list_keyboard(page_users, page, has_next),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:user:"))
    async def cb_admin_user_profile(callback: CallbackQuery, db: Database) -> None:
        try:
            target_id = int((callback.data or "").split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Некорректный ID.", show_alert=True)
            return
        user = await db.get_user(target_id)
        if user is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return
        apps = await db.get_user_applications(target_id, limit=20)
        unissued_approved = next((a.id for a in apps if a.status == "approved" and not a.gift_issued), None)
        text = format_user_profile(user, apps)
        await _edit_or_send(
            callback,
            text,
            reply_markup=admin_user_profile_keyboard(user, latest_approved_app_id=unissued_approved),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:ban:"))
    async def cb_admin_ban(callback: CallbackQuery, db: Database) -> None:
        target_id = int((callback.data or "0:0:0").split(":")[2])
        await db.set_user_ban(target_id, True)
        await db.log_admin_action(admin_id, "user_banned", target_user_id=target_id, details="Блокировка пользователя")
        user = await db.get_user(target_id)
        if user:
            apps = await db.get_user_applications(target_id, limit=20)
            await _edit_or_send(
                callback,
                format_user_profile(user, apps),
                reply_markup=admin_user_profile_keyboard(user),
            )
        await callback.answer("Пользователь заблокирован.")

    @router.callback_query(F.data.startswith("admin:unban:"))
    async def cb_admin_unban(callback: CallbackQuery, db: Database) -> None:
        target_id = int((callback.data or "0:0:0").split(":")[2])
        await db.set_user_ban(target_id, False)
        await db.log_admin_action(admin_id, "user_unbanned", target_user_id=target_id, details="Разблокировка пользователя")
        user = await db.get_user(target_id)
        if user:
            apps = await db.get_user_applications(target_id, limit=20)
            unissued_approved = next((a.id for a in apps if a.status == "approved" and not a.gift_issued), None)
            await _edit_or_send(
                callback,
                format_user_profile(user, apps),
                reply_markup=admin_user_profile_keyboard(user, latest_approved_app_id=unissued_approved),
            )
        await callback.answer("Пользователь разблокирован.")

    # ------------------------------------------------------------------
    # 📸 Фотоотчёты: просмотр, одобрение, отклонение, выдача подарка
    # ------------------------------------------------------------------

    @router.callback_query(F.data.startswith("admin:apps:"))
    async def cb_admin_apps_list(callback: CallbackQuery, db: Database) -> None:
        parts = (callback.data or "admin:apps:pending:1").split(":")
        status = parts[2] if len(parts) > 2 else "pending"
        page = max(1, int(parts[3])) if len(parts) > 3 and parts[3].isdigit() else 1

        offset = (page - 1) * APPS_PER_PAGE
        apps = await db.list_applications(status=status, offset=offset, limit=APPS_PER_PAGE + 1)
        has_next = len(apps) > APPS_PER_PAGE
        page_apps = apps[:APPS_PER_PAGE]

        status_titles = {
            "pending": "⏳ Ожидающие проверки",
            "approved": "✅ Одобренные",
            "rejected": "❌ Отклонённые",
        }
        title = status_titles.get(status, status)
        text = (
            f"📸 <b>ФОТООТЧЁТЫ — {title}</b> (стр. {page})\n\n"
            + ("Выберите заявку для просмотра:" if page_apps else "В этом разделе пока нет заявок.")
        )
        await _edit_or_send(
            callback,
            text,
            reply_markup=admin_applications_list_keyboard(page_apps, status, page, has_next),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:app_view:"))
    async def cb_admin_app_view(callback: CallbackQuery, db: Database) -> None:
        app_id = int((callback.data or "0:0:0").split(":")[2])
        app = await db.get_application(app_id)
        if app is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return

        caption = format_application_admin_caption(app)
        kb = application_moderation_keyboard(app)
        if callback.message is not None:
            await callback.message.answer_photo(
                photo=app.photo_file_id,
                caption=caption,
                reply_markup=kb,
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:app_approve:"))
    async def cb_admin_app_approve(
        callback: CallbackQuery,
        bot: Bot,
        application_service: ApplicationService,
    ) -> None:
        app_id = int((callback.data or "0:0:0").split(":")[2])
        result = await application_service.approve_application(bot, app_id, admin_id)

        if not result.success or result.application is None:
            await callback.answer(result.error_message or "Не удалось одобрить заявку.", show_alert=True)
            return

        app = result.application
        # Обновляем подпись у фотоотчёта в чате администратора
        if callback.message is not None:
            caption = format_application_admin_caption(app)
            kb = application_moderation_keyboard(app)
            try:
                if callback.message.photo:
                    await callback.message.edit_caption(caption=caption, reply_markup=kb)
                else:
                    await callback.message.edit_text(text=caption, reply_markup=kb)
            except TelegramBadRequest:
                pass

        # Уведомляем пользователя об одобрении заявки (не о выдаче подарка!)
        try:
            await bot.send_message(
                chat_id=app.user_id,
                text=(
                    "🎉 <b>ТВОЯ ЗАЯВКА ОДОБРЕНА!</b>\n\n"
                    f"Заявка: <code>{escape_html(app.application_number)}</code>\n"
                    "Фотоотчёт успешно проверен.\n\n"
                    "Спасибо за участие в TSPINKY GIFT!"
                ),
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось уведомить пользователя %s об одобрении: %s", app.user_id, exc)

        extra = " (+1 уникальный участник)" if result.added_unique_participant else " (участник уже был учтён)"
        await callback.answer(f"✅ Заявка одобрена{extra}!", show_alert=True)

    @router.callback_query(F.data.startswith("admin:app_reject:"))
    async def cb_admin_app_reject(
        callback: CallbackQuery,
        bot: Bot,
        application_service: ApplicationService,
    ) -> None:
        app_id = int((callback.data or "0:0:0").split(":")[2])
        result = await application_service.reject_application(app_id, admin_id)

        if not result.success or result.application is None:
            await callback.answer(result.error_message or "Не удалось отклонить заявку.", show_alert=True)
            return

        app = result.application
        if callback.message is not None:
            caption = format_application_admin_caption(app)
            kb = application_moderation_keyboard(app)
            try:
                if callback.message.photo:
                    await callback.message.edit_caption(caption=caption, reply_markup=kb)
                else:
                    await callback.message.edit_text(text=caption, reply_markup=kb)
            except TelegramBadRequest:
                pass

        try:
            await bot.send_message(
                chat_id=app.user_id,
                text=(
                    "❌ <b>ЗАЯВКА НЕ ПРОШЛА ПРОВЕРКУ.</b>\n\n"
                    f"Заявка: <code>{escape_html(app.application_number)}</code>\n"
                    "Пожалуйста, проверь правильность выполнения задания и отправь новый фотоотчёт."
                ),
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось уведомить пользователя %s об отклонении: %s", app.user_id, exc)

        await callback.answer("❌ Заявка отклонена.", show_alert=True)

    # ------------------------------------------------------------------
    # 🎁 Ручная выдача подарка (отдельный шаг после одобрения)
    # ------------------------------------------------------------------

    @router.callback_query(F.data.startswith("admin:gift_menu:"))
    async def cb_admin_gift_menu(callback: CallbackQuery, db: Database) -> None:
        app_id = int((callback.data or "0:0:0").split(":")[2])
        app = await db.get_application(app_id)
        if app is None:
            await callback.answer("Заявка не найдена.", show_alert=True)
            return
        if app.status != "approved":
            await callback.answer("Подарок можно выдать только по одобренной заявке.", show_alert=True)
            return
        if app.gift_issued:
            await callback.answer(f"Подарок уже выдан: {app.issued_gift_name}", show_alert=True)
            return

        tiers = await db.list_gift_tiers(active_only=True)
        text = (
            f"🎁 <b>ВЫДАЧА ПОДАРКА ПО ЗАЯВКЕ {escape_html(app.application_number)}</b>\n\n"
            f"Пользователь: <code>{app.user_id}</code>\n"
            "Нажимайте кнопку ниже <b>только после фактической отправки Telegram Gift</b> пользователю.\n"
            "После подтверждения пользователь получит уведомление о выдаче:"
        )
        await _edit_or_send(callback, text, reply_markup=gift_issue_select_keyboard(app.id, tiers))
        await callback.answer()

    @router.callback_query(F.data.startswith("admin:gift_issue:"))
    async def cb_admin_gift_issue(callback: CallbackQuery, bot: Bot, db: Database) -> None:
        parts = (callback.data or "").split(":")
        app_id = int(parts[2])
        tier_id = int(parts[3])

        tier = await db.get_gift_tier(tier_id)
        if tier is None:
            await callback.answer("Уровень подарка не найден.", show_alert=True)
            return

        gift_label = f"{tier.emoji} {tier.name}"
        updated = await db.mark_gift_issued(app_id, admin_id, gift_label)
        if updated is None or not updated.gift_issued:
            await callback.answer("Не удалось отметить подарок как выданный.", show_alert=True)
            return

        try:
            await bot.send_message(
                chat_id=updated.user_id,
                text=(
                    "🎁 <b>ПОДАРОК ВЫДАН!</b>\n\n"
                    f"Администратор подтвердил выдачу твоего подарка: <b>{escape_html(gift_label)}</b>\n"
                    f"Заявка: <code>{escape_html(updated.application_number)}</code>\n\n"
                    "Спасибо за участие в TSPINKY GIFT! ✨"
                ),
            )
        except TelegramAPIError as exc:
            logger.warning("Не удалось уведомить пользователя %s о выдаче подарка: %s", updated.user_id, exc)

        await _edit_or_send(
            callback,
            f"✅ Подарок <b>{escape_html(gift_label)}</b> отмечен как выданный для заявки "
            f"<code>{escape_html(updated.application_number)}</code>.\nПользователь уведомлён.",
            reply_markup=admin_back_keyboard("admin:apps:approved:1", "⬅️ К одобренным заявкам"),
        )
        await callback.answer("🎁 Подарок отмечен как выданный!", show_alert=True)

    # ------------------------------------------------------------------
    # 📢 Управление каналами (добавление/удаление без правки кода)
    # ------------------------------------------------------------------

    @router.callback_query(F.data == "admin:channels")
    async def cb_admin_channels(callback: CallbackQuery, db: Database) -> None:
        subs = await db.list_subscriptions(active_only=False)
        text = (
            "📢 <b>УПРАВЛЕНИЕ КАНАЛАМИ И ЗАДАНИЯМИ</b>\n\n"
            "Нажмите на название, чтобы включить/выключить проверку, или 🗑 для удаления.\n"
            "<i>Напоминание: бот должен быть администратором каждого добавленного канала.</i>"
        )
        await _edit_or_send(callback, text, reply_markup=admin_channels_keyboard(subs))
        await callback.answer()

    @router.callback_query(F.data == "admin:channel_add")
    async def cb_admin_channel_add(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.add_channel)
        await _edit_or_send(
            callback,
            "➕ <b>ДОБАВЛЕНИЕ КАНАЛА</b>\n\n"
            "Отправьте данные канала в одну строку через вертикальную черту <code>|</code>:\n"
            "<code>Название | @username_или_ID | https://t.me/link</code>\n\n"
            "Пример:\n"
            "<code>Мой Канал | @my_channel | https://t.me/my_channel</code>\n\n"
            "Для задания с ботом добавьте в конец <code>| bot</code>.",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.add_channel)
    async def handle_admin_add_channel(message: Message, db: Database, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 3:
            await message.answer(
                "❌ Неверный формат. Используйте:\n"
                "<code>Название | @username_или_ID | https://t.me/link</code>",
                reply_markup=admin_cancel_fsm_keyboard(),
            )
            return

        title, chat_id, url = parts[0], parts[1], parts[2]
        task_type = "bot" if len(parts) >= 4 and parts[3].lower() == "bot" else "channel"
        try:
            sub = await db.add_subscription(title=title, chat_id=chat_id, url=url, task_type=task_type)
            await db.log_admin_action(admin_id, "channel_added", details=f"Добавлен {task_type}: {sub.title} ({sub.chat_id})")
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"❌ Ошибка добавления (возможно, chat_id уже существует): {escape_html(str(exc))}")
            return

        await state.clear()
        subs = await db.list_subscriptions(active_only=False)
        await message.answer(
            f"✅ Канал/задание <b>{escape_html(sub.title)}</b> успешно добавлено!",
            reply_markup=admin_channels_keyboard(subs),
        )

    @router.callback_query(F.data.startswith("admin:channel_toggle:"))
    async def cb_admin_channel_toggle(callback: CallbackQuery, db: Database) -> None:
        sub_id = int((callback.data or "0:0:0").split(":")[2])
        updated = await db.toggle_subscription(sub_id)
        if updated:
            await db.log_admin_action(
                admin_id,
                "channel_toggled",
                details=f"{updated.title}: active={updated.is_active}",
            )
        subs = await db.list_subscriptions(active_only=False)
        await _edit_or_send(
            callback,
            "📢 <b>УПРАВЛЕНИЕ КАНАЛАМИ И ЗАДАНИЯМИ</b>\n\nСтатус обновлён.",
            reply_markup=admin_channels_keyboard(subs),
        )
        await callback.answer("Статус переключён")

    @router.callback_query(F.data.startswith("admin:channel_del:"))
    async def cb_admin_channel_delete(callback: CallbackQuery, db: Database) -> None:
        sub_id = int((callback.data or "0:0:0").split(":")[2])
        sub = await db.get_subscription(sub_id)
        if sub:
            await db.delete_subscription(sub_id)
            await db.log_admin_action(admin_id, "channel_deleted", details=f"Удалён {sub.title} ({sub.chat_id})")
        subs = await db.list_subscriptions(active_only=False)
        await _edit_or_send(
            callback,
            "📢 <b>УПРАВЛЕНИЕ КАНАЛАМИ И ЗАДАНИЯМИ</b>\n\nКанал удалён.",
            reply_markup=admin_channels_keyboard(subs),
        )
        await callback.answer("Удалено")

    # ------------------------------------------------------------------
    # 🎁 Управление подарками
    # ------------------------------------------------------------------

    @router.callback_query(F.data == "admin:gifts")
    async def cb_admin_gifts(callback: CallbackQuery, db: Database) -> None:
        tiers = await db.list_gift_tiers(active_only=False)
        unique_count = await db.get_unique_participants_count()
        text = (
            "🎁 <b>УПРАВЛЕНИЕ ПОДАРКАМИ</b>\n\n"
            f"Текущих уникальных участников: <b>{unique_count}</b>\n"
            "Нажмите на подарок, чтобы изменить цель участников, или 🗑 для удаления:"
        )
        await _edit_or_send(callback, text, reply_markup=admin_gifts_keyboard(tiers))
        await callback.answer()

    @router.callback_query(F.data == "admin:gift_add")
    async def cb_admin_gift_add(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.add_gift)
        await _edit_or_send(
            callback,
            "➕ <b>ДОБАВЛЕНИЕ УРОВНЯ ПОДАРКА</b>\n\n"
            "Отправьте в формате: <code>Эмодзи | Название | Количество_участников</code>\n"
            "Пример: <code>💎 | Бриллиант | 150</code>",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.add_gift)
    async def handle_admin_add_gift(message: Message, db: Database, state: FSMContext) -> None:
        parts = [p.strip() for p in (message.text or "").split("|")]
        if len(parts) != 3 or not parts[2].isdigit() or int(parts[2]) <= 0:
            await message.answer(
                "❌ Неверный формат. Пример: <code>💎 | Бриллиант | 150</code>",
                reply_markup=admin_cancel_fsm_keyboard(),
            )
            return
        try:
            tier = await db.add_gift_tier(parts[0], parts[1], int(parts[2]))
            await db.log_admin_action(
                admin_id,
                "gift_tier_added",
                details=f"Добавлен подарок {tier.emoji} {tier.name} ({tier.target_participants})",
            )
        except Exception as exc:  # noqa: BLE001
            await message.answer(f"❌ Ошибка: {escape_html(str(exc))}")
            return
        await state.clear()
        tiers = await db.list_gift_tiers(active_only=False)
        await message.answer("✅ Уровень подарка добавлен!", reply_markup=admin_gifts_keyboard(tiers))

    @router.callback_query(F.data.startswith("admin:gift_edit:"))
    async def cb_admin_gift_edit(callback: CallbackQuery, state: FSMContext) -> None:
        tier_id = int((callback.data or "0:0:0").split(":")[2])
        await state.set_state(AdminStates.edit_gift_target)
        await state.update_data(edit_tier_id=tier_id)
        await _edit_or_send(
            callback,
            "✏️ Введите новое количество уникальных участников (целое число больше 0):",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.edit_gift_target)
    async def handle_admin_edit_gift_target(message: Message, db: Database, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not raw.isdigit() or int(raw) <= 0:
            await message.answer("❌ Введите целое число больше 0.", reply_markup=admin_cancel_fsm_keyboard())
            return
        data = await state.get_data()
        tier_id = int(data["edit_tier_id"])
        updated = await db.update_gift_target(tier_id, int(raw))
        if updated:
            await db.log_admin_action(
                admin_id,
                "gift_tier_updated",
                details=f"{updated.emoji} {updated.name} -> {updated.target_participants}",
            )
        await state.clear()
        tiers = await db.list_gift_tiers(active_only=False)
        await message.answer("✅ Цель подарка обновлена!", reply_markup=admin_gifts_keyboard(tiers))

    @router.callback_query(F.data.startswith("admin:gift_del:"))
    async def cb_admin_gift_delete(callback: CallbackQuery, db: Database) -> None:
        tier_id = int((callback.data or "0:0:0").split(":")[2])
        tier = await db.get_gift_tier(tier_id)
        if tier:
            await db.delete_gift_tier(tier_id)
            await db.log_admin_action(admin_id, "gift_tier_deleted", details=f"Удалён {tier.emoji} {tier.name}")
        tiers = await db.list_gift_tiers(active_only=False)
        await _edit_or_send(
            callback,
            "🎁 <b>УПРАВЛЕНИЕ ПОДАРКАМИ</b>\n\nУровень удалён.",
            reply_markup=admin_gifts_keyboard(tiers),
        )
        await callback.answer("Удалено")

    # ------------------------------------------------------------------
    # ⚙️ Настройки и 🧾 Логи действий администратора
    # ------------------------------------------------------------------

    @router.callback_query(F.data == "admin:settings")
    async def cb_admin_settings(callback: CallbackQuery, db: Database, config: BotConfig) -> None:
        promo_active = (await db.get_setting("promo_active", "1")) == "1"
        cooldown = await db.get_setting("cooldown_seconds", str(config.submission_cooldown_seconds))
        support = await db.get_setting("support_contact", config.support_contact)
        partner_status = (
            f"подключена ({config.partner_bot_db_path.name})"
            if config.partner_bot_db_path and config.partner_bot_db_path.exists()
            else "не подключена (используется честное подтверждение)"
        )
        text = (
            "⚙️ <b>НАСТРОЙКИ БОТА</b>\n\n"
            f"📌 Статус акции: <b>{'🟢 Активна' if promo_active else '⏸ Приостановлена'}</b>\n"
            f"⏱ Интервал между заявками: <b>{escape_html(cooldown)} сек.</b>\n"
            f"💬 Контакт поддержки: <b>{escape_html(support)}</b>\n"
            f"🔗 Общая БД партнёрского бота: <b>{escape_html(partner_status)}</b>"
        )
        await _edit_or_send(callback, text, reply_markup=admin_settings_keyboard(promo_active))
        await callback.answer()

    @router.callback_query(F.data == "admin:toggle_promo")
    async def cb_toggle_promo(callback: CallbackQuery, db: Database, config: BotConfig) -> None:
        current = (await db.get_setting("promo_active", "1")) == "1"
        new_val = "0" if current else "1"
        await db.set_setting("promo_active", new_val)
        await db.log_admin_action(admin_id, "promo_toggled", details=f"promo_active={new_val}")
        await cb_admin_settings(callback, db, config)

    @router.callback_query(F.data == "admin:edit_cooldown")
    async def cb_edit_cooldown(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.edit_cooldown)
        await _edit_or_send(
            callback,
            "⏱ Введите минимальный интервал между заявками в секундах (например, <code>60</code>):",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.edit_cooldown)
    async def handle_edit_cooldown(message: Message, db: Database, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not raw.isdigit():
            await message.answer("❌ Введите целое неотрицательное число секунд.", reply_markup=admin_cancel_fsm_keyboard())
            return
        await db.set_setting("cooldown_seconds", raw)
        await db.log_admin_action(admin_id, "cooldown_updated", details=f"cooldown_seconds={raw}")
        await state.clear()
        await message.answer(f"✅ Интервал заявок обновлён: <b>{raw} сек.</b>", reply_markup=admin_main_keyboard())

    @router.callback_query(F.data == "admin:edit_support")
    async def cb_edit_support(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.edit_support)
        await _edit_or_send(
            callback,
            "💬 Введите новый контакт поддержки (например, <code>@kaguya2_0</code>):",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.edit_support)
    async def handle_edit_support(message: Message, db: Database, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not raw:
            await message.answer("❌ Контакт не может быть пустым.", reply_markup=admin_cancel_fsm_keyboard())
            return
        await db.set_setting("support_contact", raw)
        await db.log_admin_action(admin_id, "support_updated", details=f"support_contact={raw}")
        await state.clear()
        await message.answer(
            f"✅ Контакт поддержки обновлён: <b>{escape_html(raw)}</b>",
            reply_markup=admin_main_keyboard(),
        )

    @router.callback_query(F.data == "admin:logs")
    async def cb_admin_logs(callback: CallbackQuery, db: Database) -> None:
        logs = await db.list_admin_logs(limit=15)
        if not logs:
            text = "🧾 <b>ЛОГИ ДЕЙСТВИЙ АДМИНИСТРАТОРА</b>\n\nЗаписей пока нет."
        else:
            lines = ["🧾 <b>ПОСЛЕДНИЕ ДЕЙСТВИЯ АДМИНИСТРАТОРА</b>", ""]
            for log in logs:
                lines.append(
                    f"• <code>{escape_html(log.created_at)}</code> | <b>{escape_html(log.action)}</b>\n"
                    f"  {escape_html(log.details)}"
                )
            text = "\n".join(lines)
        await _edit_or_send(callback, text, reply_markup=admin_back_keyboard())
        await callback.answer()

    # ------------------------------------------------------------------
    # 📨 Рассылка
    # ------------------------------------------------------------------

    @router.callback_query(F.data == "admin:broadcast")
    async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.broadcast_message)
        await _edit_or_send(
            callback,
            "📨 <b>РАССЫЛКА ПОЛЬЗОВАТЕЛЯМ</b>\n\n"
            "Отправьте текст или фото с подписью, которое нужно разослать всем активным пользователям бота:",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.broadcast_message)
    async def handle_admin_broadcast(message: Message, bot: Bot, db: Database, state: FSMContext) -> None:
        await state.clear()
        user_ids = await db.get_all_user_ids(exclude_banned=True)
        status_msg = await message.answer(f"📨 Начинаю рассылку для {len(user_ids)} пользователей...")

        sent = 0
        failed = 0
        for uid in user_ids:
            try:
                if message.photo:
                    await bot.send_photo(
                        chat_id=uid,
                        photo=message.photo[-1].file_id,
                        caption=message.caption or "",
                    )
                else:
                    await bot.send_message(chat_id=uid, text=message.text or "")
                sent += 1
            except (TelegramForbiddenError, TelegramBadRequest, TelegramAPIError):
                failed += 1
            await asyncio.sleep(0.05)

        await db.log_admin_action(
            admin_id,
            "broadcast_sent",
            details=f"Доставлено: {sent}, ошибок: {failed}",
        )
        await status_msg.edit_text(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📬 Доставлено: <b>{sent}</b>\n"
            f"⚠️ Не доставлено (бот заблокирован/ошибка): <b>{failed}</b>",
            reply_markup=admin_main_keyboard(),
        )

    # ------------------------------------------------------------------
    # 🔍 Поиск пользователя
    # ------------------------------------------------------------------

    @router.callback_query(F.data == "admin:search")
    async def cb_admin_search(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AdminStates.search_user)
        await _edit_or_send(
            callback,
            "🔍 <b>ПОИСК ПОЛЬЗОВАТЕЛЯ</b>\n\n"
            "Введите Telegram ID (например, <code>6511859639</code>) или username (например, <code>@kaguya2_0</code>):",
            reply_markup=admin_cancel_fsm_keyboard(),
        )
        await callback.answer()

    @router.message(AdminStates.search_user)
    async def handle_admin_search(message: Message, db: Database, state: FSMContext) -> None:
        query = (message.text or "").strip()
        users = await db.find_users(query, limit=10)
        await state.clear()

        if not users:
            await message.answer(
                f"❌ По запросу <code>{escape_html(query)}</code> пользователи не найдены.",
                reply_markup=admin_main_keyboard(),
            )
            return

        if len(users) == 1:
            user = users[0]
            apps = await db.get_user_applications(user.telegram_id, limit=20)
            unissued_approved = next((a.id for a in apps if a.status == "approved" and not a.gift_issued), None)
            await message.answer(
                format_user_profile(user, apps),
                reply_markup=admin_user_profile_keyboard(user, latest_approved_app_id=unissued_approved),
            )
            return

        await message.answer(
            f"🔍 Найдено пользователей: <b>{len(users)}</b>. Выберите нужного:",
            reply_markup=admin_users_list_keyboard(users, page=1, has_next=False),
        )

    return router
