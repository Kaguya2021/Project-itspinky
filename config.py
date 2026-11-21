"""Конфигурация бота TSPINKY GIFT."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class BotConfig:
    """Основные настройки Telegram-бота."""

    bot_token: str
    admin_id: int
    admin_username: str
    db_path: Path
    partner_bot_db_path: Path | None
    submission_cooldown_seconds: int
    support_contact: str
    log_level: str


def load_config() -> BotConfig:
    """Загружает конфигурацию из переменных окружения."""
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ValueError(
            "Не задана переменная окружения BOT_TOKEN. "
            "Создайте файл .env на основе .env.example и укажите токен бота."
        )

    admin_id_raw = os.getenv("ADMIN_ID", "6511859639").strip()
    try:
        admin_id = int(admin_id_raw)
    except ValueError as exc:
        raise ValueError(f"ADMIN_ID должен быть целым числом, получено: {admin_id_raw!r}") from exc

    admin_username = os.getenv("ADMIN_USERNAME", "@kaguya2_0").strip() or "@kaguya2_0"

    db_path_raw = os.getenv("DB_PATH", str(BASE_DIR / "data" / "tspinky_gift.db")).strip()
    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = (BASE_DIR / db_path).resolve()

    partner_raw = os.getenv("PARTNER_BOT_DB_PATH", "").strip()
    partner_bot_db_path: Path | None = None
    if partner_raw:
        candidate = Path(partner_raw)
        partner_bot_db_path = candidate if candidate.is_absolute() else (BASE_DIR / candidate).resolve()

    cooldown_raw = os.getenv("SUBMISSION_COOLDOWN_SECONDS", "60").strip()
    try:
        cooldown = max(0, int(cooldown_raw))
    except ValueError:
        cooldown = 60

    support_contact = os.getenv("SUPPORT_CONTACT", "@kaguya2_0").strip() or "@kaguya2_0"
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"

    return BotConfig(
        bot_token=bot_token,
        admin_id=admin_id,
        admin_username=admin_username,
        db_path=db_path,
        partner_bot_db_path=partner_bot_db_path,
        submission_cooldown_seconds=cooldown,
        support_contact=support_contact,
        log_level=log_level,
    )
