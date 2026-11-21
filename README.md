# 🎁 TSPINKY GIFT — Telegram Gift Bot

Полноценный асинхронный Telegram-бот на **Python 3.12+**, **aiogram 3.x** и **SQLite (aiosqlite)** для проведения рекламной акции, модерации фотоотчётов, защиты от накрутки и ручной выдачи Telegram Gifts.

## Структура проекта

```text
tspinky_gift/
├── bot.py                        # Точка входа, DI-зависимости, запуск polling
├── config.py                     # Загрузка конфигурации из .env
├── requirements.txt              # Зависимости Python
├── .env.example                  # Пример файла окружения
├── README.md                     # Инструкция по установке и деплою
├── database/
│   ├── __init__.py
│   ├── connection.py             # Асинхронный слой SQLite (WAL, схема, CRUD, статистика)
│   └── models.py                 # Модели данных и начальные задания/подарки/20 комментариев
├── handlers/
│   ├── __init__.py               # Регистрация роутеров
│   ├── start.py                  # /start, главное меню, «Как получить», «Поддержка»
│   ├── subscriptions.py          # Обязательные задания и реальная проверка getChatMember
│   ├── tasks.py                  # Рекламное задание и прогресс уровней подарков
│   ├── comments.py               # 20 готовых комментариев с кнопками copy_text
│   ├── applications.py           # Приём фотоотчёта (FSM) и отправка админу
│   ├── statistics.py             # Раздел «Моя статистика»
│   └── admin.py                  # Защищённая админ-панель (/admin) и выдача подарков
├── keyboards/
│   ├── __init__.py
│   ├── user.py                   # Inline-клавиатуры пользователя (включая CopyTextButton)
│   └── admin.py                  # Inline-клавиатуры админ-панели и модерации
├── services/
│   ├── __init__.py
│   ├── subscription_checker.py   # Проверка каналов (getChatMember) и партнёрского бота
│   ├── anti_fraud.py             # Защита от накрутки, дублей фото и спама
│   └── application_service.py    # Жизненный цикл заявок + повторная проверка перед одобрением
└── utils/
    ├── __init__.py
    └── helpers.py                # HTML-форматирование карточек, прогресса и профилей
```

> **Примечание об архитектуре:** модуль работы с БД размещён внутри пакета `database/connection.py` (вместо одновременного наличия `database.py` и каталога `database/`), чтобы исключить конфликт имён Python.

---

## 1. Создание Telegram-бота через @BotFather

1. Откройте в Telegram официального бота **@BotFather**.
2. Отправьте команду `/newbot`.
3. Введите отображаемое имя бота, например: `TSPINKY GIFT`.
4. Введите username бота (должен заканчиваться на `bot`), например: `tspinkybot`.
5. Скопируйте выданный токен (`1234567890:AAF...`) — он понадобится для файла `.env`.
6. (Опционально) Настройте описание и команды через `/setdescription` и `/setcommands`:
   ```text
   start - 🎁 Главное меню
   ```

---

## 2. Добавление бота администратором в каналы

Реальная проверка подписок работает через метод Telegram Bot API `getChatMember`. Без прав администратора Telegram не позволяет боту проверять состав участников канала.

Для обоих обязательных каналов (**RobloxGame1232** — `https://t.me/RobloxGame1232` и **Kaguya 2.0 Bots** — `https://t.me/kaguya_2_0_bots`):

1. Откройте канал в Telegram → нажмите на название канала → **Изменить** (или значок карандаша).
2. Перейдите в раздел **Администраторы** → **Добавить администратора**.
3. Найдите вашего бота по `@username` и добавьте его.
4. Минимально достаточно права просмотра участников (стандартные права администратора канала).
5. Сохраните изменения.

### Проверка третьего задания (`@Kaguya_2_0bot`)

Telegram Bot API **не позволяет** одному боту напрямую узнать, запускал ли пользователь другой бот. В проекте реализованы оба честных режима:

- **Режим общей БД (реальная проверка):** если `@Kaguya_2_0bot` работает на том же сервере и хранит пользователей в SQLite (таблица `users` с колонкой `telegram_id`/`user_id` или таблица `partner_bot_launches`), укажите путь к его БД в переменной `PARTNER_BOT_DB_PATH` в `.env`. Тогда `TSPINKY GIFT` автоматически проверит наличие `telegram_id` в базе.
- **Режим честного подтверждения (по умолчанию):** если `PARTNER_BOT_DB_PATH` не задан, пользователь нажимает кнопку `✅ Я запустил @Kaguya_2_0bot` и видит явное предупреждение, что подтверждение не гарантирует запуск без общей БД.

---

## 3. Локальная установка и запуск

Требуется **Python 3.12+** (также совместим с Python 3.11+).

```bash
cd tspinky_gift
python3 -m venv .venv
source .venv/bin/activate        # На Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Создайте файл `.env` из шаблона и заполните `BOT_TOKEN`:

```bash
cp .env.example .env
nano .env
```

Запустите бота:

```bash
python3 bot.py
```

При первом запуске автоматически создастся файл `data/tspinky_gift.db` со всеми таблицами (`users`, `subscriptions`, `tasks`, `applications`, `comments`, `gift_progress`, `settings`, `admin_logs`, `partner_bot_launches`), тремя обязательными заданиями, четырьмя уровнями подарков и 20 готовыми комментариями.

---

## 4. Запуск на VPS (Ubuntu / Debian) через systemd

1. Подключитесь к серверу и установите Python:
   ```bash
   sudo apt update && sudo apt install -y python3 python3-venv python3-pip
   ```
2. Загрузите папку `tspinky_gift` в `/opt/tspinky_gift`, создайте виртуальное окружение и `.env`:
   ```bash
   cd /opt/tspinky_gift
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```
3. Создайте systemd-сервис `/etc/systemd/system/tspinky-gift.service`:
   ```ini
   [Unit]
   Description=TSPINKY GIFT Telegram Bot
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/tspinky_gift
   ExecStart=/opt/tspinky_gift/.venv/bin/python /opt/tspinky_gift/bot.py
   Restart=always
   RestartSec=5
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```
4. Включите автозапуск и запустите бота:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now tspinky-gift
   sudo systemctl status tspinky-gift
   ```
5. Просмотр логов в реальном времени:
   ```bash
   journalctl -u tspinky-gift -f
   ```

---

## 5. Ключевые механизмы защиты от накрутки и выдачи подарков

- **Строгий доступ к `/admin`:** все команды и callback-кнопки админ-панели защищены фильтром `AdminOnlyFilter(6511859639)`.
- **Повторная проверка подписок перед одобрением:** при нажатии `✅ ОДОБРИТЬ` бот заново вызывает `getChatMember` по всем активным каналам. Если пользователь отписался — одобрение блокируется.
- **Уникальность участников:** счётчик прогресса подарков считает `COUNT(DISTINCT user_id)` среди одобренных заявок; повторная отправка фотоотчёта невозможна после одобрения.
- **Защита от дублей скриншотов и спама:** проверяется `photo_file_unique_id` по всей базе заявок и действует настраиваемый cooldown между попытками.
- **Отдельная выдача подарков:** одобрение заявки (`approved`) не помечает подарок как выданный. Администратор нажимает `🎁 ВЫДАТЬ ПОДАРОК` только после фактической отправки Telegram Gift, и только тогда пользователь получает уведомление о выдаче.
