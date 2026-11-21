"""Регистрация всех роутеров бота TSPINKY GIFT."""

from __future__ import annotations

from aiogram import Dispatcher

from handlers.admin import create_admin_router
from handlers.applications import router as applications_router
from handlers.comments import router as comments_router
from handlers.start import router as start_router
from handlers.statistics import router as statistics_router
from handlers.subscriptions import router as subscriptions_router
from handlers.tasks import router as tasks_router


def setup_routers(dp: Dispatcher, admin_id: int) -> None:
    """Подключает все роутеры в корректном порядке приоритета."""
    dp.include_router(create_admin_router(admin_id))
    dp.include_router(start_router)
    dp.include_router(subscriptions_router)
    dp.include_router(tasks_router)
    dp.include_router(comments_router)
    dp.include_router(applications_router)
    dp.include_router(statistics_router)
