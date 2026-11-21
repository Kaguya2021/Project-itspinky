"""Асинхронный слой работы с SQLite (aiosqlite) для TSPINKY GIFT."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from database.models import (
    DEFAULT_COMMENTS,
    DEFAULT_GIFT_TIERS,
    DEFAULT_SUBSCRIPTIONS,
    AdminLogRecord,
    ApplicationRecord,
    CommentRecord,
    GiftTierRecord,
    SubscriptionRecord,
    UserRecord,
)

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """Возвращает текущее время в UTC в формате ISO-8601."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """Менеджер базы данных SQLite с автоинициализацией схемы и сохранением состояния."""

    def __init__(self, db_path: Path, support_contact: str = "@kaguya2_0", cooldown_seconds: int = 60) -> None:
        self.db_path = db_path
        self.support_contact = support_contact
        self.default_cooldown_seconds = cooldown_seconds
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Открывает соединение с SQLite, включает WAL и создаёт таблицы."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON;")
        await self._conn.execute("PRAGMA journal_mode = WAL;")
        await self._create_schema()
        await self._seed_defaults()
        await self._conn.commit()
        logger.info("База данных SQLite инициализирована: %s", self.db_path)

    async def close(self) -> None:
        """Корректно закрывает соединение с базой данных."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Соединение с базой данных не открыто. Вызовите await db.connect().")
        return self._conn

    async def _create_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT NOT NULL DEFAULT '',
                registered_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                applications_count INTEGER NOT NULL DEFAULT 0,
                is_counted_participant INTEGER NOT NULL DEFAULT 0,
                is_banned INTEGER NOT NULL DEFAULT 0,
                bot_task_confirmed INTEGER NOT NULL DEFAULT 0,
                bot_task_mode TEXT
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                chat_id TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'channel' CHECK(task_type IN ('channel', 'bot')),
                button_text TEXT NOT NULL DEFAULT '📢 ПОДПИСАТЬСЯ',
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                subscription_id INTEGER NOT NULL,
                is_completed INTEGER NOT NULL DEFAULT 0,
                verification_mode TEXT NOT NULL DEFAULT 'telegram_api',
                checked_at TEXT NOT NULL,
                UNIQUE(user_id, subscription_id),
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_number TEXT NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                username TEXT,
                comment_id INTEGER,
                comment_text TEXT NOT NULL,
                photo_file_id TEXT NOT NULL,
                photo_file_unique_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                admin_note TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER,
                gift_issued INTEGER NOT NULL DEFAULT 0,
                issued_gift_name TEXT,
                gift_issued_at TEXT,
                admin_message_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                FOREIGN KEY (comment_id) REFERENCES comments(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS gift_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                emoji TEXT NOT NULL,
                target_participants INTEGER NOT NULL CHECK(target_participants > 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_user_id INTEGER,
                target_application_id INTEGER,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS partner_bot_launches (
                user_id INTEGER PRIMARY KEY,
                bot_username TEXT NOT NULL,
                launched_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
            CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
            CREATE INDEX IF NOT EXISTS idx_applications_photo_uid ON applications(photo_file_unique_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
            CREATE INDEX IF NOT EXISTS idx_admin_logs_created ON admin_logs(created_at);
            """
        )

    async def _seed_defaults(self) -> None:
        now = utc_now_iso()

        # Каналы и задания (заполняем только если таблица пустая)
        cursor = await self.conn.execute("SELECT COUNT(*) AS cnt FROM subscriptions")
        row = await cursor.fetchone()
        if row and row["cnt"] == 0:
            for item in DEFAULT_SUBSCRIPTIONS:
                await self.conn.execute(
                    """
                    INSERT OR IGNORE INTO subscriptions
                    (title, chat_id, url, task_type, button_text, is_active, sort_order, created_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        item["title"],
                        item["chat_id"],
                        item["url"],
                        item["task_type"],
                        item["button_text"],
                        item["sort_order"],
                        now,
                    ),
                )

        # 20 готовых комментариев
        cursor = await self.conn.execute("SELECT COUNT(*) AS cnt FROM comments")
        row = await cursor.fetchone()
        if row and row["cnt"] == 0:
            for idx, text in enumerate(DEFAULT_COMMENTS, start=1):
                await self.conn.execute(
                    "INSERT OR IGNORE INTO comments (text, is_active, sort_order) VALUES (?, 1, ?)",
                    (text, idx),
                )

        # Уровни подарков
        cursor = await self.conn.execute("SELECT COUNT(*) AS cnt FROM gift_progress")
        row = await cursor.fetchone()
        if row and row["cnt"] == 0:
            for tier in DEFAULT_GIFT_TIERS:
                await self.conn.execute(
                    """
                    INSERT OR IGNORE INTO gift_progress
                    (name, emoji, target_participants, is_active, sort_order)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (tier["name"], tier["emoji"], tier["target_participants"], tier["sort_order"]),
                )

        # Настройки по умолчанию
        default_settings = {
            "promo_active": "1",
            "cooldown_seconds": str(self.default_cooldown_seconds),
            "support_contact": self.support_contact,
            "promo_title": "TSPINKY GIFT",
        }
        for key, value in default_settings.items():
            await self.conn.execute(
                "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )

    # ------------------------------------------------------------------
    # Пользователи
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_user(row: aiosqlite.Row) -> UserRecord:
        return UserRecord(
            telegram_id=row["telegram_id"],
            username=row["username"],
            full_name=row["full_name"],
            registered_at=row["registered_at"],
            last_activity=row["last_activity"],
            applications_count=row["applications_count"],
            is_counted_participant=bool(row["is_counted_participant"]),
            is_banned=bool(row["is_banned"]),
            bot_task_confirmed=bool(row["bot_task_confirmed"]),
            bot_task_mode=row["bot_task_mode"],
        )

    async def upsert_user(self, telegram_id: int, username: str | None, full_name: str) -> UserRecord:
        now = utc_now_iso()
        clean_username = username.lstrip("@") if username else None
        await self.conn.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, registered_at, last_activity)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_activity = excluded.last_activity
            """,
            (telegram_id, clean_username, full_name or "", now, now),
        )
        await self.conn.commit()
        user = await self.get_user(telegram_id)
        assert user is not None
        return user

    async def touch_user(self, telegram_id: int) -> None:
        await self.conn.execute(
            "UPDATE users SET last_activity = ? WHERE telegram_id = ?",
            (utc_now_iso(), telegram_id),
        )
        await self.conn.commit()

    async def get_user(self, telegram_id: int) -> UserRecord | None:
        cursor = await self.conn.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return self._row_to_user(row) if row else None

    async def find_users(self, query: str, limit: int = 10) -> list[UserRecord]:
        q = query.strip().lstrip("@")
        if not q:
            return []
        if q.isdigit():
            cursor = await self.conn.execute(
                "SELECT * FROM users WHERE telegram_id = ? LIMIT ?",
                (int(q), limit),
            )
        else:
            cursor = await self.conn.execute(
                """
                SELECT * FROM users
                WHERE LOWER(COALESCE(username, '')) LIKE LOWER(?)
                   OR LOWER(full_name) LIKE LOWER(?)
                ORDER BY last_activity DESC
                LIMIT ?
                """,
                (f"%{q}%", f"%{q}%", limit),
            )
        rows = await cursor.fetchall()
        return [self._row_to_user(r) for r in rows]

    async def list_users(self, offset: int = 0, limit: int = 10) -> list[UserRecord]:
        cursor = await self.conn.execute(
            "SELECT * FROM users ORDER BY registered_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()
        return [self._row_to_user(r) for r in rows]

    async def get_all_user_ids(self, exclude_banned: bool = True) -> list[int]:
        if exclude_banned:
            cursor = await self.conn.execute("SELECT telegram_id FROM users WHERE is_banned = 0")
        else:
            cursor = await self.conn.execute("SELECT telegram_id FROM users")
        rows = await cursor.fetchall()
        return [int(r["telegram_id"]) for r in rows]

    async def set_user_ban(self, telegram_id: int, banned: bool) -> None:
        await self.conn.execute(
            "UPDATE users SET is_banned = ? WHERE telegram_id = ?",
            (1 if banned else 0, telegram_id),
        )
        await self.conn.commit()

    async def set_bot_task_confirmed(self, telegram_id: int, confirmed: bool, mode: str) -> None:
        await self.conn.execute(
            """
            UPDATE users
            SET bot_task_confirmed = ?, bot_task_mode = ?, last_activity = ?
            WHERE telegram_id = ?
            """,
            (1 if confirmed else 0, mode, utc_now_iso(), telegram_id),
        )
        await self.conn.commit()

    # ------------------------------------------------------------------
    # Подписки / каналы и таблица tasks
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_subscription(row: aiosqlite.Row) -> SubscriptionRecord:
        return SubscriptionRecord(
            id=row["id"],
            title=row["title"],
            chat_id=row["chat_id"],
            url=row["url"],
            task_type=row["task_type"],
            button_text=row["button_text"],
            is_active=bool(row["is_active"]),
            sort_order=row["sort_order"],
            created_at=row["created_at"],
        )

    async def list_subscriptions(self, active_only: bool = True) -> list[SubscriptionRecord]:
        if active_only:
            cursor = await self.conn.execute(
                "SELECT * FROM subscriptions WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM subscriptions ORDER BY sort_order ASC, id ASC"
            )
        rows = await cursor.fetchall()
        return [self._row_to_subscription(r) for r in rows]

    async def get_subscription(self, sub_id: int) -> SubscriptionRecord | None:
        cursor = await self.conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        row = await cursor.fetchone()
        return self._row_to_subscription(row) if row else None

    async def add_subscription(
        self,
        title: str,
        chat_id: str,
        url: str,
        task_type: str = "channel",
        button_text: str | None = None,
    ) -> SubscriptionRecord:
        now = utc_now_iso()
        btn = button_text or ("🤖 ЗАПУСТИТЬ БОТА" if task_type == "bot" else "📢 ПОДПИСАТЬСЯ")
        cursor = await self.conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM subscriptions")
        row = await cursor.fetchone()
        next_order = int(row["next_order"]) if row else 1

        cursor = await self.conn.execute(
            """
            INSERT INTO subscriptions (title, chat_id, url, task_type, button_text, is_active, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (title.strip(), chat_id.strip(), url.strip(), task_type, btn, next_order, now),
        )
        await self.conn.commit()
        sub = await self.get_subscription(int(cursor.lastrowid))
        assert sub is not None
        return sub

    async def delete_subscription(self, sub_id: int) -> bool:
        cursor = await self.conn.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def toggle_subscription(self, sub_id: int) -> SubscriptionRecord | None:
        sub = await self.get_subscription(sub_id)
        if not sub:
            return None
        new_state = 0 if sub.is_active else 1
        await self.conn.execute("UPDATE subscriptions SET is_active = ? WHERE id = ?", (new_state, sub_id))
        await self.conn.commit()
        return await self.get_subscription(sub_id)

    async def save_task_status(
        self,
        user_id: int,
        subscription_id: int,
        is_completed: bool,
        verification_mode: str = "telegram_api",
    ) -> None:
        now = utc_now_iso()
        await self.conn.execute(
            """
            INSERT INTO tasks (user_id, subscription_id, is_completed, verification_mode, checked_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, subscription_id) DO UPDATE SET
                is_completed = excluded.is_completed,
                verification_mode = excluded.verification_mode,
                checked_at = excluded.checked_at
            """,
            (user_id, subscription_id, 1 if is_completed else 0, verification_mode, now),
        )
        await self.conn.commit()

    async def get_user_tasks_map(self, user_id: int) -> dict[int, bool]:
        cursor = await self.conn.execute(
            "SELECT subscription_id, is_completed FROM tasks WHERE user_id = ?",
            (user_id,),
        )
        rows = await cursor.fetchall()
        return {int(r["subscription_id"]): bool(r["is_completed"]) for r in rows}

    async def record_partner_bot_launch(self, user_id: int, bot_username: str) -> None:
        """Записывает факт запуска партнёрского бота в общую таблицу."""
        await self.conn.execute(
            """
            INSERT OR REPLACE INTO partner_bot_launches (user_id, bot_username, launched_at)
            VALUES (?, ?, ?)
            """,
            (user_id, bot_username.lstrip("@").lower(), utc_now_iso()),
        )
        await self.conn.commit()

    async def has_partner_bot_launch(self, user_id: int, bot_username: str) -> bool:
        cursor = await self.conn.execute(
            """
            SELECT 1 FROM partner_bot_launches
            WHERE user_id = ? AND LOWER(bot_username) = LOWER(?)
            LIMIT 1
            """,
            (user_id, bot_username.lstrip("@")),
        )
        return (await cursor.fetchone()) is not None

    # ------------------------------------------------------------------
    # Комментарии
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_comment(row: aiosqlite.Row) -> CommentRecord:
        return CommentRecord(
            id=row["id"],
            text=row["text"],
            is_active=bool(row["is_active"]),
            sort_order=row["sort_order"],
        )

    async def list_comments(self, active_only: bool = True) -> list[CommentRecord]:
        if active_only:
            cursor = await self.conn.execute(
                "SELECT * FROM comments WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
            )
        else:
            cursor = await self.conn.execute("SELECT * FROM comments ORDER BY sort_order ASC, id ASC")
        rows = await cursor.fetchall()
        return [self._row_to_comment(r) for r in rows]

    async def get_comment(self, comment_id: int) -> CommentRecord | None:
        cursor = await self.conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        row = await cursor.fetchone()
        return self._row_to_comment(row) if row else None

    # ------------------------------------------------------------------
    # Заявки (фотоотчёты)
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_application(row: aiosqlite.Row) -> ApplicationRecord:
        return ApplicationRecord(
            id=row["id"],
            application_number=row["application_number"],
            user_id=row["user_id"],
            username=row["username"],
            comment_id=row["comment_id"],
            comment_text=row["comment_text"],
            photo_file_id=row["photo_file_id"],
            photo_file_unique_id=row["photo_file_unique_id"],
            status=row["status"],
            admin_note=row["admin_note"],
            created_at=row["created_at"],
            reviewed_at=row["reviewed_at"],
            reviewed_by=row["reviewed_by"],
            gift_issued=bool(row["gift_issued"]),
            issued_gift_name=row["issued_gift_name"],
            gift_issued_at=row["gift_issued_at"],
            admin_message_id=row["admin_message_id"],
        )

    async def create_application(
        self,
        user_id: int,
        username: str | None,
        comment_id: int | None,
        comment_text: str,
        photo_file_id: str,
        photo_file_unique_id: str,
    ) -> ApplicationRecord:
        now = utc_now_iso()
        clean_username = username.lstrip("@") if username else None
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")

        cursor = await self.conn.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM applications")
        row = await cursor.fetchone()
        seq = int(row["next_id"]) if row else 1
        app_number = f"TSG-{date_part}-{seq:04d}"

        cursor = await self.conn.execute(
            """
            INSERT INTO applications (
                application_number, user_id, username, comment_id, comment_text,
                photo_file_id, photo_file_unique_id, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                app_number,
                user_id,
                clean_username,
                comment_id,
                comment_text,
                photo_file_id,
                photo_file_unique_id,
                now,
            ),
        )
        app_id = int(cursor.lastrowid)

        await self.conn.execute(
            """
            UPDATE users
            SET applications_count = applications_count + 1,
                last_activity = ?
            WHERE telegram_id = ?
            """,
            (now, user_id),
        )
        await self.conn.commit()

        app = await self.get_application(app_id)
        assert app is not None
        return app

    async def set_application_admin_message(self, app_id: int, message_id: int) -> None:
        await self.conn.execute(
            "UPDATE applications SET admin_message_id = ? WHERE id = ?",
            (message_id, app_id),
        )
        await self.conn.commit()

    async def get_application(self, app_id: int) -> ApplicationRecord | None:
        cursor = await self.conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,))
        row = await cursor.fetchone()
        return self._row_to_application(row) if row else None

    async def get_user_applications(self, user_id: int, limit: int = 20) -> list[ApplicationRecord]:
        cursor = await self.conn.execute(
            "SELECT * FROM applications WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_application(r) for r in rows]

    async def get_last_user_application(self, user_id: int) -> ApplicationRecord | None:
        cursor = await self.conn.execute(
            "SELECT * FROM applications WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_application(row) if row else None

    async def has_pending_application(self, user_id: int) -> bool:
        cursor = await self.conn.execute(
            "SELECT 1 FROM applications WHERE user_id = ? AND status = 'pending' LIMIT 1",
            (user_id,),
        )
        return (await cursor.fetchone()) is not None

    async def has_approved_application(self, user_id: int) -> bool:
        cursor = await self.conn.execute(
            "SELECT 1 FROM applications WHERE user_id = ? AND status = 'approved' LIMIT 1",
            (user_id,),
        )
        return (await cursor.fetchone()) is not None

    async def find_duplicate_photo(self, photo_file_unique_id: str) -> ApplicationRecord | None:
        cursor = await self.conn.execute(
            "SELECT * FROM applications WHERE photo_file_unique_id = ? LIMIT 1",
            (photo_file_unique_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_application(row) if row else None

    async def list_applications(
        self,
        status: str | None = None,
        offset: int = 0,
        limit: int = 10,
    ) -> list[ApplicationRecord]:
        if status:
            cursor = await self.conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM applications ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        return [self._row_to_application(r) for r in rows]

    async def approve_application(self, app_id: int, admin_id: int) -> tuple[ApplicationRecord | None, bool]:
        """Одобряет заявку. Возвращает (заявка, был_ли_добавлен_новый_уникальный_участник)."""
        app = await self.get_application(app_id)
        if not app or app.status != "pending":
            return app, False

        now = utc_now_iso()
        await self.conn.execute(
            """
            UPDATE applications
            SET status = 'approved', reviewed_at = ?, reviewed_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, admin_id, app_id),
        )

        # Засчитываем уникального участника строго один раз на Telegram ID
        cursor = await self.conn.execute(
            """
            UPDATE users
            SET is_counted_participant = 1, last_activity = ?
            WHERE telegram_id = ? AND is_counted_participant = 0
            """,
            (now, app.user_id),
        )
        added_unique = cursor.rowcount > 0
        await self.conn.commit()
        return await self.get_application(app_id), added_unique

    async def reject_application(self, app_id: int, admin_id: int, note: str | None = None) -> ApplicationRecord | None:
        app = await self.get_application(app_id)
        if not app or app.status != "pending":
            return app

        now = utc_now_iso()
        await self.conn.execute(
            """
            UPDATE applications
            SET status = 'rejected', admin_note = ?, reviewed_at = ?, reviewed_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (note, now, admin_id, app_id),
        )
        await self.conn.commit()
        return await self.get_application(app_id)

    async def mark_gift_issued(
        self,
        app_id: int,
        admin_id: int,
        gift_name: str,
    ) -> ApplicationRecord | None:
        app = await self.get_application(app_id)
        if not app or app.status != "approved" or app.gift_issued:
            return app

        now = utc_now_iso()
        await self.conn.execute(
            """
            UPDATE applications
            SET gift_issued = 1, issued_gift_name = ?, gift_issued_at = ?
            WHERE id = ? AND status = 'approved' AND gift_issued = 0
            """,
            (gift_name, now, app_id),
        )
        await self.conn.commit()
        await self.log_admin_action(
            admin_id=admin_id,
            action="gift_issued",
            target_user_id=app.user_id,
            target_application_id=app.id,
            details=f"Выдан подарок: {gift_name}",
        )
        return await self.get_application(app_id)

    # ------------------------------------------------------------------
    # Прогресс подарков
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_gift_tier(row: aiosqlite.Row) -> GiftTierRecord:
        return GiftTierRecord(
            id=row["id"],
            name=row["name"],
            emoji=row["emoji"],
            target_participants=row["target_participants"],
            is_active=bool(row["is_active"]),
            sort_order=row["sort_order"],
        )

    async def list_gift_tiers(self, active_only: bool = True) -> list[GiftTierRecord]:
        if active_only:
            cursor = await self.conn.execute(
                "SELECT * FROM gift_progress WHERE is_active = 1 ORDER BY target_participants ASC, id ASC"
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM gift_progress ORDER BY target_participants ASC, id ASC"
            )
        rows = await cursor.fetchall()
        return [self._row_to_gift_tier(r) for r in rows]

    async def get_gift_tier(self, tier_id: int) -> GiftTierRecord | None:
        cursor = await self.conn.execute("SELECT * FROM gift_progress WHERE id = ?", (tier_id,))
        row = await cursor.fetchone()
        return self._row_to_gift_tier(row) if row else None

    async def add_gift_tier(self, emoji: str, name: str, target_participants: int) -> GiftTierRecord:
        cursor = await self.conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM gift_progress")
        row = await cursor.fetchone()
        next_order = int(row["next_order"]) if row else 1
        cursor = await self.conn.execute(
            """
            INSERT INTO gift_progress (name, emoji, target_participants, is_active, sort_order)
            VALUES (?, ?, ?, 1, ?)
            """,
            (name.strip(), emoji.strip(), target_participants, next_order),
        )
        await self.conn.commit()
        tier = await self.get_gift_tier(int(cursor.lastrowid))
        assert tier is not None
        return tier

    async def update_gift_target(self, tier_id: int, target_participants: int) -> GiftTierRecord | None:
        await self.conn.execute(
            "UPDATE gift_progress SET target_participants = ? WHERE id = ?",
            (target_participants, tier_id),
        )
        await self.conn.commit()
        return await self.get_gift_tier(tier_id)

    async def delete_gift_tier(self, tier_id: int) -> bool:
        cursor = await self.conn.execute("DELETE FROM gift_progress WHERE id = ?", (tier_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_unique_participants_count(self) -> int:
        """Считает только уникальных пользователей с одобренными заявками."""
        cursor = await self.conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS cnt FROM applications WHERE status = 'approved'"
        )
        row = await cursor.fetchone()
        return int(row["cnt"]) if row else 0

    # ------------------------------------------------------------------
    # Настройки и логирование действий администратора
    # ------------------------------------------------------------------

    async def get_setting(self, key: str, default: str = "") -> str:
        cursor = await self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return str(row["value"]) if row else default

    async def set_setting(self, key: str, value: str) -> None:
        now = utc_now_iso()
        await self.conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
        await self.conn.commit()

    async def log_admin_action(
        self,
        admin_id: int,
        action: str,
        target_user_id: int | None = None,
        target_application_id: int | None = None,
        details: str = "",
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO admin_logs (admin_id, action, target_user_id, target_application_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_id, action, target_user_id, target_application_id, details, utc_now_iso()),
        )
        await self.conn.commit()

    async def list_admin_logs(self, limit: int = 15) -> list[AdminLogRecord]:
        cursor = await self.conn.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = await cursor.fetchall()
        return [
            AdminLogRecord(
                id=r["id"],
                admin_id=r["admin_id"],
                action=r["action"],
                target_user_id=r["target_user_id"],
                target_application_id=r["target_application_id"],
                details=r["details"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Агрегированная статистика
    # ------------------------------------------------------------------

    async def get_statistics(self) -> dict[str, Any]:
        active_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        async def _scalar(sql: str, params: tuple[Any, ...] = ()) -> int:
            cur = await self.conn.execute(sql, params)
            r = await cur.fetchone()
            return int(r[0]) if r and r[0] is not None else 0

        total_users = await _scalar("SELECT COUNT(*) FROM users")
        active_users = await _scalar("SELECT COUNT(*) FROM users WHERE last_activity >= ?", (active_cutoff,))
        total_apps = await _scalar("SELECT COUNT(*) FROM applications")
        approved_apps = await _scalar("SELECT COUNT(*) FROM applications WHERE status = 'approved'")
        rejected_apps = await _scalar("SELECT COUNT(*) FROM applications WHERE status = 'rejected'")
        pending_apps = await _scalar("SELECT COUNT(*) FROM applications WHERE status = 'pending'")
        gifts_issued = await _scalar("SELECT COUNT(*) FROM applications WHERE gift_issued = 1")
        unique_participants = await self.get_unique_participants_count()
        tiers = await self.list_gift_tiers(active_only=True)

        return {
            "total_users": total_users,
            "active_users": active_users,
            "total_applications": total_apps,
            "approved_applications": approved_apps,
            "rejected_applications": rejected_apps,
            "pending_applications": pending_apps,
            "gifts_issued": gifts_issued,
            "unique_participants": unique_participants,
            "gift_tiers": tiers,
        }
