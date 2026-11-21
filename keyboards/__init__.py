"""Пакет клавиатур TSPINKY GIFT."""

from keyboards.admin import (
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
from keyboards.user import (
    back_to_menu_keyboard,
    cancel_photo_keyboard,
    comments_page_keyboard,
    main_menu_keyboard,
    promo_task_keyboard,
    stage_passed_keyboard,
    subscriptions_keyboard,
)

__all__ = [
    "main_menu_keyboard",
    "back_to_menu_keyboard",
    "subscriptions_keyboard",
    "stage_passed_keyboard",
    "promo_task_keyboard",
    "comments_page_keyboard",
    "cancel_photo_keyboard",
    "admin_main_keyboard",
    "admin_back_keyboard",
    "admin_cancel_fsm_keyboard",
    "application_moderation_keyboard",
    "gift_issue_select_keyboard",
    "admin_applications_list_keyboard",
    "admin_users_list_keyboard",
    "admin_user_profile_keyboard",
    "admin_channels_keyboard",
    "admin_gifts_keyboard",
    "admin_settings_keyboard",
]
