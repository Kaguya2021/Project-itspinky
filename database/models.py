"""Модели данных и константы начального заполнения для TSPINKY GIFT."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SUBSCRIPTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "RobloxGame1232",
        "chat_id": "@RobloxGame1232",
        "url": "https://t.me/RobloxGame1232",
        "task_type": "channel",
        "button_text": "📢 ПОДПИСАТЬСЯ",
        "sort_order": 1,
    },
    {
        "title": "Kaguya 2.0 Bots",
        "chat_id": "@kaguya_2_0_bots",
        "url": "https://t.me/kaguya_2_0_bots",
        "task_type": "channel",
        "button_text": "📢 ПОДПИСАТЬСЯ",
        "sort_order": 2,
    },
    {
        "title": "@Kaguya_2_0bot",
        "chat_id": "@Kaguya_2_0bot",
        "url": "https://t.me/Kaguya_2_0bot",
        "task_type": "bot",
        "button_text": "🤖 ЗАПУСТИТЬ БОТА",
        "sort_order": 3,
    },
)

DEFAULT_GIFT_TIERS: tuple[dict[str, object], ...] = (
    {"name": "Мишка", "emoji": "🧸", "target_participants": 25, "sort_order": 1},
    {"name": "Роза", "emoji": "🌹", "target_participants": 50, "sort_order": 2},
    {"name": "Торт", "emoji": "🎂", "target_participants": 70, "sort_order": 3},
    {"name": "Кольцо", "emoji": "💍", "target_participants": 100, "sort_order": 4},
)

DEFAULT_COMMENTS: tuple[str, ...] = (
    "Спасибо @tspinkybot за подарок! 🎁",
    "Спасибо @tspinkybot за такую возможность!",
    "Попробуйте @tspinkybot, здесь проходит акция!",
    "Узнал про подарки через @tspinkybot!",
    "Спасибо организаторам @tspinkybot!",
    "Интересная акция от @tspinkybot!",
    "Загляните в @tspinkybot!",
    "Участвую в акции от @tspinkybot!",
    "Спасибо за возможность получить подарок!",
    "@tspinkybot — загляните, если интересно!",
    "Нашёл интересный бот @tspinkybot!",
    "Попробуйте принять участие в акции!",
    "Спасибо за участие! @tspinkybot",
    "Здесь можно узнать об акции: @tspinkybot",
    "Не забудьте проверить @tspinkybot!",
    "Участвуйте в акции вместе с @tspinkybot!",
    "Спасибо за интересный розыгрыш!",
    "@tspinkybot — информация о подарках!",
    "Отличная возможность от @tspinkybot!",
    "Рекомендую посмотреть @tspinkybot!",
)


@dataclass(slots=True)
class UserRecord:
    telegram_id: int
    username: str | None
    full_name: str
    registered_at: str
    last_activity: str
    applications_count: int
    is_counted_participant: bool
    is_banned: bool
    bot_task_confirmed: bool
    bot_task_mode: str | None


@dataclass(slots=True)
class SubscriptionRecord:
    id: int
    title: str
    chat_id: str
    url: str
    task_type: str  # "channel" | "bot"
    button_text: str
    is_active: bool
    sort_order: int
    created_at: str


@dataclass(slots=True)
class TaskRecord:
    id: int
    user_id: int
    subscription_id: int
    is_completed: bool
    verification_mode: str
    checked_at: str


@dataclass(slots=True)
class ApplicationRecord:
    id: int
    application_number: str
    user_id: int
    username: str | None
    comment_id: int | None
    comment_text: str
    photo_file_id: str
    photo_file_unique_id: str
    status: str  # "pending" | "approved" | "rejected"
    admin_note: str | None
    created_at: str
    reviewed_at: str | None
    reviewed_by: int | None
    gift_issued: bool
    issued_gift_name: str | None
    gift_issued_at: str | None
    admin_message_id: int | None


@dataclass(slots=True)
class CommentRecord:
    id: int
    text: str
    is_active: bool
    sort_order: int


@dataclass(slots=True)
class GiftTierRecord:
    id: int
    name: str
    emoji: str
    target_participants: int
    is_active: bool
    sort_order: int


@dataclass(slots=True)
class AdminLogRecord:
    id: int
    admin_id: int
    action: str
    target_user_id: int | None
    target_application_id: int | None
    details: str
    created_at: str
