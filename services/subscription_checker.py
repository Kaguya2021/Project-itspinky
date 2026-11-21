"""Реальная проверка обязательных подписок через Telegram Bot API и интеграцию ботов."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from database import Database, SubscriptionRecord

logger = logging.getLogger(__name__)

VALID_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


@dataclass(slots=True)
class TaskCheckItem:
    """Результат проверки одного обязательного задания."""

    subscription: SubscriptionRecord
    is_completed: bool
    verification_mode: str  # "telegram_api" | "shared_db" | "honest_confirmation" | "api_error"
    error_detail: str | None = None


@dataclass(slots=True)
class SubscriptionCheckReport:
    """Сводный результат проверки всех обязательных заданий пользователя."""

    items: list[TaskCheckItem]

    @property
    def all_completed(self) -> bool:
        return all(item.is_completed for item in self.items)

    @property
    def all_channels_subscribed(self) -> bool:
        return all(
            item.is_completed
            for item in self.items
            if item.subscription.task_type == "channel"
        )

    @property
    def missing_items(self) -> list[TaskCheckItem]:
        return [item for item in self.items if not item.is_completed]

    @property
    def missing_channels(self) -> list[TaskCheckItem]:
        return [
            item
            for item in self.items
            if item.subscription.task_type == "channel" and not item.is_completed
        ]


class SubscriptionChecker:
    """Сервис проверки реальных подписок на каналы и статуса запуска партнёрского бота."""

    def __init__(self, db: Database, partner_bot_db_path: Path | None = None) -> None:
        self.db = db
        self.partner_bot_db_path = partner_bot_db_path

    async def check_single_channel(self, bot: Bot, user_id: int, sub: SubscriptionRecord) -> TaskCheckItem:
        """Проверяет подписку пользователя на один канал через getChatMember.

        Ошибки Telegram API никогда не засчитываются как успешная подписка.
        """
        try:
            member = await bot.get_chat_member(chat_id=sub.chat_id, user_id=user_id)
            status = member.status
            if status in VALID_MEMBER_STATUSES:
                is_sub = True
            elif status == ChatMemberStatus.RESTRICTED:
                is_sub = bool(getattr(member, "is_member", False))
            else:
                is_sub = False

            await self.db.save_task_status(
                user_id=user_id,
                subscription_id=sub.id,
                is_completed=is_sub,
                verification_mode="telegram_api",
            )
            return TaskCheckItem(
                subscription=sub,
                is_completed=is_sub,
                verification_mode="telegram_api",
            )
        except TelegramForbiddenError as exc:
            logger.error(
                "Бот не имеет доступа к каналу %s (%s): %s. Убедитесь, что бот — администратор.",
                sub.title,
                sub.chat_id,
                exc,
            )
            await self.db.save_task_status(user_id, sub.id, False, "api_error")
            return TaskCheckItem(
                subscription=sub,
                is_completed=False,
                verification_mode="api_error",
                error_detail="Бот не является администратором канала или удалён из него.",
            )
        except TelegramBadRequest as exc:
            logger.error("Ошибка TelegramBadRequest при проверке %s (%s): %s", sub.title, sub.chat_id, exc)
            await self.db.save_task_status(user_id, sub.id, False, "api_error")
            return TaskCheckItem(
                subscription=sub,
                is_completed=False,
                verification_mode="api_error",
                error_detail="Не удалось проверить канал (проверьте права бота и chat_id).",
            )
        except TelegramAPIError as exc:
            logger.error("Ошибка Telegram API при проверке %s: %s", sub.chat_id, exc)
            await self.db.save_task_status(user_id, sub.id, False, "api_error")
            return TaskCheckItem(
                subscription=sub,
                is_completed=False,
                verification_mode="api_error",
                error_detail="Временная ошибка Telegram API.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Неожиданная ошибка при проверке подписки на %s: %s", sub.chat_id, exc)
            await self.db.save_task_status(user_id, sub.id, False, "api_error")
            return TaskCheckItem(
                subscription=sub,
                is_completed=False,
                verification_mode="api_error",
                error_detail="Внутренняя ошибка проверки.",
            )

    async def _check_external_partner_db(self, user_id: int) -> bool:
        """Проверяет запуск бота во внешней общей SQLite-базе, если она настроена."""
        if not self.partner_bot_db_path or not self.partner_bot_db_path.exists():
            return False
        try:
            async with aiosqlite.connect(self.partner_bot_db_path) as ext_conn:
                for query in (
                    "SELECT 1 FROM users WHERE telegram_id = ? LIMIT 1",
                    "SELECT 1 FROM users WHERE user_id = ? LIMIT 1",
                    "SELECT 1 FROM partner_bot_launches WHERE user_id = ? LIMIT 1",
                ):
                    try:
                        cur = await ext_conn.execute(query, (user_id,))
                        if await cur.fetchone():
                            return True
                    except aiosqlite.Error:
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось прочитать внешнюю БД партнёрского бота %s: %s", self.partner_bot_db_path, exc)
        return False

    async def check_partner_bot(self, user_id: int, sub: SubscriptionRecord) -> TaskCheckItem:
        """Проверяет задание запуска стороннего бота.

        1. Если доступна общая таблица partner_bot_launches или PARTNER_BOT_DB_PATH — реальная проверка по БД.
        2. Иначе — честное подтверждение пользователя (Telegram Bot API не позволяет проверять запуск чужого бота).
        """
        if await self.db.has_partner_bot_launch(user_id, sub.chat_id) or await self._check_external_partner_db(user_id):
            await self.db.set_bot_task_confirmed(user_id, True, "shared_db")
            await self.db.save_task_status(user_id, sub.id, True, "shared_db")
            return TaskCheckItem(
                subscription=sub,
                is_completed=True,
                verification_mode="shared_db",
            )

        user = await self.db.get_user(user_id)
        confirmed = bool(user and user.bot_task_confirmed)
        mode = (user.bot_task_mode if user and user.bot_task_mode else "honest_confirmation")
        await self.db.save_task_status(user_id, sub.id, confirmed, mode)
        return TaskCheckItem(
            subscription=sub,
            is_completed=confirmed,
            verification_mode=mode,
        )

    async def check_all(self, bot: Bot, user_id: int, channels_only: bool = False) -> SubscriptionCheckReport:
        """Проверяет все активные обязательные задания пользователя по отдельности."""
        subscriptions = await self.db.list_subscriptions(active_only=True)
        items: list[TaskCheckItem] = []

        for sub in subscriptions:
            if sub.task_type == "channel":
                items.append(await self.check_single_channel(bot, user_id, sub))
            elif not channels_only:
                items.append(await self.check_partner_bot(user_id, sub))

        return SubscriptionCheckReport(items=items)
