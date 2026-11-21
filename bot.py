import asyncio
import logging
import os
import sys

from aiohttp import web
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


async def start_healthcheck_server(port: int) -> web.AppRunner:
    async def handle_health(_request: web.Request) -> web.Response:
        return web.Response(text="TSPINKY GIFT Bot is running", status=200)

    app = web.Application()
    app.router.add_get("/", handle_health)
    app.router.add_get("/health", handle_health)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    return runner


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

    dp["config"] = config
    dp["db"] = db
    dp["subscription_checker"] = subscription_checker
    dp["anti_fraud"] = anti_fraud
    dp["application_service"] = application_service

    setup_routers(dp, admin_id=config.admin_id)

    web_runner: web.AppRunner | None = None
    port_raw = os.getenv("PORT", "").strip()
    if port_raw.isdigit():
        port = int(port_raw)
        web_runner = await start_healthcheck_server(port)
        logger.info("HTTP healthcheck-сервер запущен на 0.0.0.0:%s", port)

    try:
        me = await bot.get_me()
        logger.info("Бот TSPINKY GIFT запущен: @%s (ID: %s), админ: %s", me.username, me.id, config.admin_id)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        if web_runner is not None:
            await web_runner.cleanup()
        await db.close()
        await bot.session.close()
        logger.info("Бот TSPINKY GIFT корректно остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
