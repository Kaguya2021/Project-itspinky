"""Вспомогательные функции форматирования сообщений и статусов."""

from __future__ import annotations

import html
from typing import Iterable

from database import ApplicationRecord, GiftTierRecord, UserRecord
from services.subscription_checker import SubscriptionCheckReport

STATUS_LABELS: dict[str, str] = {
    "pending": "⏳ На проверке",
    "approved": "✅ Одобрена",
    "rejected": "❌ Отклонена",
}


def escape_html(value: str | None) -> str:
    """Безопасно экранирует строку для HTML-разметки Telegram."""
    return html.escape(value or "")


def format_username(username: str | None) -> str:
    """Форматирует username с префиксом @ или пометкой отсутствия."""
    if not username:
        return "нет username"
    clean = username.lstrip("@")
    return f"@{escape_html(clean)}"


def format_progress_block(unique_participants: int, tiers: Iterable[GiftTierRecord]) -> str:
    """Форматирует блок текущего прогресса акции по уровням подарков."""
    lines = ["🎁 <b>ТЕКУЩИЙ ПРОГРЕСС</b>", ""]
    for tier in tiers:
        current = min(unique_participants, tier.target_participants)
        unlocked = " ✨" if unique_participants >= tier.target_participants else ""
        lines.append(
            f"{escape_html(tier.emoji)} {escape_html(tier.name)}: "
            f"<b>{unique_participants}/{tier.target_participants}</b>{unlocked}"
        )
        _ = current
    return "\n".join(lines)


def format_subscription_list(report: SubscriptionCheckReport) -> str:
    """Форматирует список обязательных заданий со статусами ✅ / ❌."""
    lines: list[str] = []
    for item in report.items:
        title = escape_html(item.subscription.title)
        if item.subscription.task_type == "channel":
            if item.is_completed:
                lines.append(f"✅ {title} — подписан.")
            elif item.verification_mode == "api_error":
                lines.append(f"❌ {title} — ошибка проверки (обратитесь к администратору).")
            else:
                lines.append(f"❌ {title} — не подписан.")
        else:
            if item.is_completed:
                suffix = "подтверждён (БД)" if item.verification_mode == "shared_db" else "подтверждён пользователем"
                lines.append(f"✅ {title} — {suffix}.")
            else:
                lines.append(f"❌ {title} — не запущен / не подтверждён.")
    return "\n".join(lines)


def format_application_admin_caption(app: ApplicationRecord) -> str:
    """Формирует карточку заявки для администратора."""
    status_text = STATUS_LABELS.get(app.status, app.status)
    gift_line = (
        f"\n🎁 <b>Подарок выдан:</b> {escape_html(app.issued_gift_name)} ({escape_html(app.gift_issued_at)})"
        if app.gift_issued
        else "\n🎁 <b>Выдача подарка:</b> ещё не выдан"
    )
    return (
        f"📥 <b>ЗАЯВКА {escape_html(app.application_number)}</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{app.user_id}</code>\n"
        f"👤 <b>Username:</b> {format_username(app.username)}\n"
        f"💬 <b>Комментарий:</b>\n<blockquote>{escape_html(app.comment_text)}</blockquote>\n"
        f"🕒 <b>Дата отправки:</b> {escape_html(app.created_at)} UTC\n"
        f"📌 <b>Статус:</b> {status_text}"
        f"{gift_line}"
    )


def format_user_profile(user: UserRecord, apps: list[ApplicationRecord]) -> str:
    """Формирует профиль пользователя для админ-панели."""
    approved = sum(1 for a in apps if a.status == "approved")
    pending = sum(1 for a in apps if a.status == "pending")
    rejected = sum(1 for a in apps if a.status == "rejected")
    gifts = [a.issued_gift_name for a in apps if a.gift_issued and a.issued_gift_name]
    ban_badge = "🚫 Заблокирован" if user.is_banned else "🟢 Активен"
    participant_badge = "✅ Учтён в акции" if user.is_counted_participant else "➖ Ещё не учтён"
    gifts_text = ", ".join(escape_html(g) for g in gifts) if gifts else "не выдавались"

    return (
        f"👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"🆔 <b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"🔗 <b>Username:</b> {format_username(user.username)}\n"
        f"📛 <b>Имя:</b> {escape_html(user.full_name)}\n"
        f"📅 <b>Регистрация:</b> {escape_html(user.registered_at)} UTC\n"
        f"⏱ <b>Последняя активность:</b> {escape_html(user.last_activity)} UTC\n"
        f"🛡 <b>Статус аккаунта:</b> {ban_badge}\n"
        f"🏆 <b>Участие в акции:</b> {participant_badge}\n"
        f"📸 <b>Заявок всего:</b> {user.applications_count} "
        f"(✅ {approved} | ⏳ {pending} | ❌ {rejected})\n"
        f"🎁 <b>Выданные подарки:</b> {gifts_text}"
    )
