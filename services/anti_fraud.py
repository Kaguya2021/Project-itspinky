"""Сервис защиты от накрутки и спама (Anti-Fraud) для TSPINKY GIFT."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from database import Database


@dataclass(slots=True)
class FraudCheckResult:
    """Результат антифрод-проверки перед приёмом заявки."""

    allowed: bool
    reason: str | None = None


class AntiFraudService:
    """Проверки уникальности, частоты отправки, дублей фотоотчётов и статуса пользователя."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def check_can_submit_application(
        self,
        user_id: int,
        photo_file_unique_id: str,
    ) -> FraudCheckResult:
        """Комплексная проверка перед созданием новой заявки с фотоотчётом."""
        promo_active = await self.db.get_setting("promo_active", "1")
        if promo_active != "1":
            return FraudCheckResult(
                allowed=False,
                reason="⏸ Приём новых заявок временно приостановлен администратором.",
            )

        user = await self.db.get_user(user_id)
        if user and user.is_banned:
            return FraudCheckResult(
                allowed=False,
                reason="🚫 Ваш аккаунт ограничен и не может отправлять заявки.",
            )

        if await self.db.has_approved_application(user_id):
            return FraudCheckResult(
                allowed=False,
                reason=(
                    "✅ Ваша заявка уже одобрена, и вы учтены в списке уникальных участников!\n"
                    "Повторная отправка фотоотчёта не требуется и не увеличивает счётчик."
                ),
            )

        if await self.db.has_pending_application(user_id):
            return FraudCheckResult(
                allowed=False,
                reason=(
                    "⏳ У вас уже есть заявка на проверке у администратора.\n"
                    "Пожалуйста, дождитесь решения по текущей заявке."
                ),
            )

        # Проверка повторного использования того же фотоотчёта
        duplicate = await self.db.find_duplicate_photo(photo_file_unique_id)
        if duplicate is not None:
            return FraudCheckResult(
                allowed=False,
                reason=(
                    "⚠️ Этот скриншот уже был отправлен ранее "
                    f"(заявка {duplicate.application_number}).\n"
                    "Пожалуйста, сделайте новый уникальный скриншот вашего комментария."
                ),
            )

        # Ограничение частоты отправки заявок (cooldown)
        cooldown_raw = await self.db.get_setting("cooldown_seconds", "60")
        try:
            cooldown_seconds = max(0, int(cooldown_raw))
        except ValueError:
            cooldown_seconds = 60

        if cooldown_seconds > 0:
            last_app = await self.db.get_last_user_application(user_id)
            if last_app is not None:
                last_dt = datetime.strptime(last_app.created_at, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                if elapsed < cooldown_seconds:
                    remaining = int(cooldown_seconds - elapsed) + 1
                    return FraudCheckResult(
                        allowed=False,
                        reason=(
                            f"⏱ Слишком частая отправка заявок.\n"
                            f"Подождите ещё {remaining} сек. перед следующей попыткой."
                        ),
                    )

        return FraudCheckResult(allowed=True)
