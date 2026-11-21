"""Бизнес-логика обработки фотоотчётов, одобрения/отклонения и выдачи подарков."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot

from database import ApplicationRecord, Database
from services.anti_fraud import AntiFraudService
from services.subscription_checker import SubscriptionChecker, SubscriptionCheckReport

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SubmissionResult:
    success: bool
    application: ApplicationRecord | None = None
    error_message: str | None = None


@dataclass(slots=True)
class ApprovalResult:
    success: bool
    application: ApplicationRecord | None = None
    added_unique_participant: bool = False
    error_message: str | None = None
    recheck_report: SubscriptionCheckReport | None = None


class ApplicationService:
    """Координирует антифрод, проверку подписок и жизненный цикл заявок."""

    def __init__(
        self,
        db: Database,
        subscription_checker: SubscriptionChecker,
        anti_fraud: AntiFraudService,
    ) -> None:
        self.db = db
        self.subscription_checker = subscription_checker
        self.anti_fraud = anti_fraud

    async def submit_photo_report(
        self,
        bot: Bot,
        user_id: int,
        username: str | None,
        comment_id: int | None,
        comment_text: str,
        photo_file_id: str,
        photo_file_unique_id: str,
    ) -> SubmissionResult:
        """Проверяет подписки, антифрод и регистрирует фотоотчёт."""
        # 1. Реальная проверка обязательных подписок перед приёмом отчёта
        report = await self.subscription_checker.check_all(bot, user_id)
        if not report.all_completed:
            return SubmissionResult(
                success=False,
                error_message=(
                    "❌ Вы не выполнили все обязательные задания или отписались от канала.\n"
                    "Нажмите «🎁 Получить подарок» и пройдите проверку заново."
                ),
            )

        # 2. Антифрод-проверка
        fraud = await self.anti_fraud.check_can_submit_application(user_id, photo_file_unique_id)
        if not fraud.allowed:
            return SubmissionResult(success=False, error_message=fraud.reason)

        # 3. Создание заявки в SQLite
        app = await self.db.create_application(
            user_id=user_id,
            username=username,
            comment_id=comment_id,
            comment_text=comment_text,
            photo_file_id=photo_file_id,
            photo_file_unique_id=photo_file_unique_id,
        )
        return SubmissionResult(success=True, application=app)

    async def approve_application(
        self,
        bot: Bot,
        app_id: int,
        admin_id: int,
    ) -> ApprovalResult:
        """Повторно проверяет обязательные каналы пользователя и одобряет заявку."""
        app = await self.db.get_application(app_id)
        if not app:
            return ApprovalResult(success=False, error_message="Заявка не найдена.")
        if app.status != "pending":
            return ApprovalResult(
                success=False,
                application=app,
                error_message=f"Заявка уже обработана (статус: {app.status}).",
            )

        # Повторная реальная проверка подписок на каналы перед окончательным одобрением
        recheck = await self.subscription_checker.check_all(bot, app.user_id, channels_only=True)
        if not recheck.all_channels_subscribed:
            missing_names = ", ".join(item.subscription.title for item in recheck.missing_channels)
            await self.db.log_admin_action(
                admin_id=admin_id,
                action="approve_blocked_unsubscribed",
                target_user_id=app.user_id,
                target_application_id=app.id,
                details=f"Одобрение заблокировано: нет подписки на {missing_names}",
            )
            return ApprovalResult(
                success=False,
                application=app,
                error_message=(
                    "⚠️ Повторная проверка подписок не пройдена!\n"
                    f"Пользователь не подписан на: {missing_names}.\n"
                    "Одобрение заблокировано защитой от накрутки."
                ),
                recheck_report=recheck,
            )

        updated, added_unique = await self.db.approve_application(app_id, admin_id)
        await self.db.log_admin_action(
            admin_id=admin_id,
            action="application_approved",
            target_user_id=app.user_id,
            target_application_id=app.id,
            details=f"Одобрена заявка {app.application_number} (новый уникальный участник: {added_unique})",
        )
        return ApprovalResult(
            success=True,
            application=updated,
            added_unique_participant=added_unique,
            recheck_report=recheck,
        )

    async def reject_application(
        self,
        app_id: int,
        admin_id: int,
        note: str | None = None,
    ) -> ApprovalResult:
        """Отклоняет заявку и записывает действие администратора в лог."""
        app = await self.db.get_application(app_id)
        if not app:
            return ApprovalResult(success=False, error_message="Заявка не найдена.")
        if app.status != "pending":
            return ApprovalResult(
                success=False,
                application=app,
                error_message=f"Заявка уже обработана (статус: {app.status}).",
            )

        updated = await self.db.reject_application(app_id, admin_id, note=note)
        await self.db.log_admin_action(
            admin_id=admin_id,
            action="application_rejected",
            target_user_id=app.user_id,
            target_application_id=app.id,
            details=f"Отклонена заявка {app.application_number}" + (f" ({note})" if note else ""),
        )
        return ApprovalResult(success=True, application=updated)
