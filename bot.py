"""Точка входа Telegram-бота TSPINKY GIFT."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from database import Database
from handlers import setup_routers
from services import AntiFraudService, ApplicationService, SubscriptionChecker


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    config = load_config()
    configure_logging(config.log_level)
    logger = logging.getLogger("tspinky_gift")

    db = Database(
        db_path=config.db_path,
        support_contact=config.support_contact,
        cooldown_seconds=config.submission_cooldown_seconds,
    )
    await db.connect()

    subscription_checker = SubscriptionChecker(
        db=db,
        partner_bot_db_path=config.partner_bot_db_path,
    )
    anti_fraud = AntiFraudService(db=db)
    application_service = ApplicationService(
        db=db,
        subscription_checker=subscription_checker,
        anti_fraud=anti_fraud,
    )

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Внедрение зависимостей во все хендлеры
    dp["config"] = config
    dp["db"] = db
    dp["subscription_checker"] = subscription_checker
    dp["anti_fraud"] = anti_fraud
    dp["application_service"] = application_service

    setup_routers(dp, admin_id=config.admin_id)

    try:
        me = await bot.get_me()
        logger.info("Бот TSPINKY GIFT запущен: @%s (ID: %s), админ: %s", me.username, me.id, config.admin_id)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()
        logger.info("Бот TSPINKY GIFT корректно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
