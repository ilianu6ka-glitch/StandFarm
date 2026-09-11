import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    MessageEntity,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv


# =========================
# НАСТРОЙКИ
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN в .env")

ADMIN_ID = 5422659848

CHANNEL_ID = -1002528491829
CHANNEL_LINK = "https://t.me/+vS1FNsopEiA2Mzgy"

REVIEWS_LINK = "https://t.me/Reviews_StandFarm"

REFERRAL_REWARD = 5
MIN_WITHDRAW = 100


# Custom emoji ID
CUSTOM_DONE = "5206607081334906820"
CUSTOM_TASKS = "5886223731088431288"
CUSTOM_PROFILE = "5796462801547435383"
CUSTOM_GOLD = "5886568200350472339"
CUSTOM_REFERRAL = "5931532925936870156"
CUSTOM_PROMO = "5886632311327299282"
CUSTOM_SUPPORT = "5372981976804366741"
CUSTOM_REVIEWS = "5470060791883374114"


# =========================
# ЛОГИ
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


# =========================
# БАЗА ДАННЫХ
# =========================

DB_PATH = os.path.join(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "."), "standfarm.db")

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


def db_execute(query, params=(), fetchone=False, fetchall=False, commit=False):
    cur = conn.cursor()
    cur.execute(query, params)

    if commit:
        conn.commit()

    if fetchone:
        return cur.fetchone()

    if fetchall:
        return cur.fetchall()

    return cur


def column_exists(table_name, column_name):
    row = db_execute(
        f"PRAGMA table_info({table_name})",
        fetchall=True,
    )
    return any(r["name"] == column_name for r in row)


def init_db():
    db_execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER,
            referral_reward_given INTEGER NOT NULL DEFAULT 0,
            first_task_completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,
        commit=True,
    )

    # Миграции для старой базы.
    if not column_exists("users", "username"):
        db_execute("ALTER TABLE users ADD COLUMN username TEXT", commit=True)

    if not column_exists("users", "first_name"):
        db_execute("ALTER TABLE users ADD COLUMN first_name TEXT", commit=True)

    if not column_exists("users", "referral_reward_given"):
        db_execute(
            "ALTER TABLE users ADD COLUMN referral_reward_given INTEGER NOT NULL DEFAULT 0",
            commit=True,
        )

    if not column_exists("users", "first_task_completed"):
        db_execute(
            "ALTER TABLE users ADD COLUMN first_task_completed INTEGER NOT NULL DEFAULT 0",
            commit=True,
        )

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            reward INTEGER NOT NULL,
            answer TEXT,
            invite_link TEXT,
            channels TEXT,
            created_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        commit=True,
    )

    if not column_exists("tasks", "channels"):
        db_execute("ALTER TABLE tasks ADD COLUMN channels TEXT", commit=True)

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS task_completions (
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY (user_id, task_id)
        )
        """,
        commit=True,
    )

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
        """,
        commit=True,
    )

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS promo_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            reward INTEGER NOT NULL,
            max_activations INTEGER NOT NULL,
            activations INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,
        commit=True,
    )

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS promo_activations (
            promo_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            activated_at TEXT NOT NULL,
            PRIMARY KEY (promo_id, user_id)
        )
        """,
        commit=True,
    )


init_db()


# =========================
# BOT / DISPATCHER
# =========================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()

ADMIN_PANEL_ENABLED = True


# =========================
# КЛАВИАТУРЫ
# =========================

def user_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📋 Задания"),
                KeyboardButton(text="👤 Профиль"),
            ],
            [
                KeyboardButton(text="💰 Получить голду"),
                KeyboardButton(text="🔗 Моя реферальная ссылка"),
            ],
            [
                KeyboardButton(text="🎟 Промокод"),
                KeyboardButton(text="⭐ Отзывы"),
            ],
            [
                KeyboardButton(text="🆘 Поддержка"),
            ],
        ],
        resize_keyboard=True,
    )


def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="➕ Добавить задание"),
                KeyboardButton(text="📋 Список заданий"),
            ],
            [
                KeyboardButton(text="🎟 Создать промокод"),
                KeyboardButton(text="📋 Промокоды"),
            ],
            [
                KeyboardButton(text="📣 Выложить объявление"),
                KeyboardButton(text="💸 Выдача голды"),
            ],
            [
                KeyboardButton(text="👥 Рефералы"),
                KeyboardButton(text="🔴 Выключить админ-панель"),
            ],
            [
                KeyboardButton(text="⬅️ Назад"),
            ],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Выйти")],
        ],
        resize_keyboard=True,
    )


def broadcast_confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Отправить всем",
                    callback_data="broadcast_send",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="broadcast_cancel",
                ),
            ],
        ]
    )


def subscribe_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=CHANNEL_LINK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить подписку",
                    callback_data="check_subscription",
                )
            ],
        ]
    )


def start_after_sub_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Начать пользоваться",
                    callback_data="start_using",
                )
            ]
        ]
    )


# =========================
# СИСТЕМА СОСТОЯНИЙ
# =========================

class TaskAnswerState(StatesGroup):
    waiting_answer = State()


class SupportState(StatesGroup):
    waiting_message = State()


class WithdrawState(StatesGroup):
    waiting_amount = State()


class PromoState(StatesGroup):
    waiting_code = State()


class BroadcastState(StatesGroup):
    waiting_text = State()


class AdminTaskState(StatesGroup):
    waiting_type = State()
    waiting_title = State()
    waiting_description = State()
    waiting_reward = State()
    waiting_answer = State()
    waiting_channels = State()
    waiting_link = State()


class AdminPromoState(StatesGroup):
    waiting_code = State()
    waiting_reward = State()
    waiting_limit = State()


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def now():
    return datetime.now().isoformat(timespec="seconds")


def custom_entity(custom_emoji_id):
    return MessageEntity(
        type="custom_emoji",
        offset=0,
        length=2,
        custom_emoji_id=custom_emoji_id,
    )


async def send_custom(
    message: Message,
    symbol: str,
    custom_id: str,
    text: str,
    reply_markup=None,
):
    # Убираем HTML-теги, чтобы они не отображались как обычный текст
    # при отправке сообщения с custom emoji entity.
    text = text.replace("<b>", "")
    text = text.replace("</b>", "")
    text = text.replace("<code>", "")
    text = text.replace("</code>", "")

    await message.answer(
        symbol + text,
        entities=[custom_entity(custom_id)],
        reply_markup=reply_markup,
    )


def add_user(user_id, username=None, first_name=None, referred_by=None):
    existing = db_execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )

    if existing:
        db_execute(
            """
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
            """,
            (username, first_name, user_id),
            commit=True,
        )
        return

    if referred_by == user_id:
        referred_by = None

    db_execute(
        """
        INSERT INTO users (
            user_id,
            username,
            first_name,
            balance,
            referred_by,
            referral_reward_given,
            first_task_completed,
            created_at
        )
        VALUES (?, ?, ?, 0, ?, 0, 0, ?)
        """,
        (
            user_id,
            username,
            first_name,
            referred_by,
            now(),
        ),
        commit=True,
    )


def get_user(user_id):
    return db_execute(
        "SELECT * FROM users WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )


def get_balance(user_id):
    row = get_user(user_id)
    return int(row["balance"]) if row else 0


def change_balance(user_id, amount):
    db_execute(
        """
        UPDATE users
        SET balance = balance + ?
        WHERE user_id = ?
        """,
        (amount, user_id),
        commit=True,
    )


def task_completed(user_id, task_id):
    row = db_execute(
        """
        SELECT 1
        FROM task_completions
        WHERE user_id = ? AND task_id = ?
        """,
        (user_id, task_id),
        fetchone=True,
    )
    return row is not None


def mark_task_completed(user_id, task_id):
    db_execute(
        """
        INSERT OR IGNORE INTO task_completions (
            user_id,
            task_id,
            completed_at
        )
        VALUES (?, ?, ?)
        """,
        (user_id, task_id, now()),
        commit=True,
    )


async def complete_first_task(user_id):
    user = get_user(user_id)

    if not user:
        return

    if user["first_task_completed"]:
        return

    db_execute(
        """
        UPDATE users
        SET first_task_completed = 1
        WHERE user_id = ?
        """,
        (user_id,),
        commit=True,
    )

    await reward_referrer(user_id)


async def reward_referrer(user_id):
    user = get_user(user_id)

    if not user:
        return

    referrer_id = user["referred_by"]

    if not referrer_id:
        return

    if user["referral_reward_given"]:
        return

    referrer = get_user(referrer_id)

    if not referrer:
        return

    change_balance(referrer_id, REFERRAL_REWARD)

    db_execute(
        """
        UPDATE users
        SET referral_reward_given = 1
        WHERE user_id = ?
        """,
        (user_id,),
        commit=True,
    )

    try:
        await bot.send_message(
            referrer_id,
            (
                f"🎉 По вашей реферальной ссылке присоединился пользователь "
                f"и выполнил первое задание!\n\n"
                f"💰 Вам начислено <b>{REFERRAL_REWARD} голды</b>."
            ),
        )
    except Exception:
        logging.exception("Не удалось уведомить реферера")


def parse_referral(text):
    if not text:
        return None

    if not text.startswith("/start"):
        return None

    parts = text.split(maxsplit=1)

    if len(parts) < 2:
        return None

    payload = parts[1].strip()

    if payload.startswith("ref_"):
        payload = payload[4:]

    try:
        referrer_id = int(payload)
        return referrer_id
    except ValueError:
        return None


def task_type_name(task_type):
    names = {
        "math": "Математика",
        "text": "Текстовый ответ",
        "join_request": "Вступление по заявке",
        "contest": "Конкурс",
    }
    return names.get(task_type, task_type)


# =========================
# ПРОВЕРКА ПОДПИСКИ
# =========================

async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id,
        )

        return member.status in {
            "member",
            "administrator",
            "creator",
        }
    except Exception as e:
        logging.warning("Ошибка проверки подписки: %s", e)
        return False


# =========================
# START
# =========================

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()

    referrer_id = parse_referral(message.text)

    add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        referrer_id,
    )

    if message.from_user.id == ADMIN_ID and ADMIN_PANEL_ENABLED:
        await message.answer(
            "🛠 <b>Админ-панель</b>\n\nВыберите действие:",
            reply_markup=admin_keyboard(),
        )
        return

    subscribed = await is_subscribed(message.from_user.id)

    if not subscribed:
        await message.answer(
            "👋 <b>Добро пожаловать в StandFarm!</b>\n\n"
            "Чтобы пользоваться ботом, сначала подпишитесь на наш канал.",
            reply_markup=subscribe_keyboard(),
        )
        return

    await message.answer(
        "🚀 <b>Добро пожаловать в StandFarm!</b>\n\n"
        "Выберите нужный раздел в меню.",
        reply_markup=user_keyboard(),
    )


@dp.callback_query(F.data == "check_subscription")
async def check_subscription(callback: CallbackQuery):
    subscribed = await is_subscribed(callback.from_user.id)

    if not subscribed:
        await callback.answer(
            "❌ Подписка не найдена. Подпишитесь на канал.",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        "✅ <b>Подписка подтверждена!</b>\n\n"
        "Теперь можно начать пользоваться ботом.",
        reply_markup=start_after_sub_keyboard(),
    )
    await callback.answer()


@dp.callback_query(F.data == "start_using")
async def start_using(callback: CallbackQuery):
    await callback.message.answer(
        "🚀 <b>Готово!</b>\n\n"
        "Теперь можно выполнять задания и получать голду.",
        reply_markup=user_keyboard(),
    )
    await callback.answer()


# =========================
# АДМИН
# =========================

@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    global ADMIN_PANEL_ENABLED

    if message.from_user.id != ADMIN_ID:
        return

    await state.clear()
    ADMIN_PANEL_ENABLED = True

    await message.answer(
        "🛠 <b>Админ-панель включена.</b>",
        reply_markup=admin_keyboard(),
    )


@dp.message(F.text == "🔴 Выключить админ-панель")
async def disable_admin_panel(message: Message, state: FSMContext):
    global ADMIN_PANEL_ENABLED

    if message.from_user.id != ADMIN_ID:
        return

    await state.clear()
    ADMIN_PANEL_ENABLED = False

    await message.answer(
        "🔴 Админ-панель выключена.",
        reply_markup=user_keyboard(),
    )


@dp.message(F.text == "⬅️ Назад")
async def admin_back(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()

        if ADMIN_PANEL_ENABLED:
            await message.answer(
                "🛠 Админ-панель.",
                reply_markup=admin_keyboard(),
            )
        else:
            await message.answer(
                "Главное меню.",
                reply_markup=user_keyboard(),
            )
        return

    await state.clear()
    await message.answer(
        "Главное меню.",
        reply_markup=user_keyboard(),
    )


# =========================
# ПРОФИЛЬ
# =========================

@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):
    user = get_user(message.from_user.id)

    if not user:
        add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )
        user = get_user(message.from_user.id)

    await send_custom(
        message,
        "😎",
        CUSTOM_PROFILE,
        (
            "\n\n"
            f"ID: <code>{message.from_user.id}</code>\n"
            f"Баланс: <b>{user['balance']} голды</b>\n"
            f"Выполнено заданий: "
            f"{db_execute('SELECT COUNT(*) AS c FROM task_completions WHERE user_id = ?', (message.from_user.id,), fetchone=True)['c']}"
        ),
    )


# =========================
# ЗАДАНИЯ
# =========================

@dp.message(F.text == "📋 Задания")
async def show_tasks(message: Message):
    if message.from_user.id != ADMIN_ID:
        if not await is_subscribed(message.from_user.id):
            await message.answer(
                "❌ Сначала подпишитесь на канал.",
                reply_markup=subscribe_keyboard(),
            )
            return

    rows = db_execute(
        """
        SELECT *
        FROM tasks
        WHERE active = 1
        ORDER BY id DESC
        """,
        fetchall=True,
    )

    if not rows:
        await send_custom(
            message,
            "📋",
            CUSTOM_TASKS,
            "\n\nПока нет доступных заданий.",
        )
        return

    buttons = []

    for task in rows:
        if task_completed(message.from_user.id, task["id"]):
            continue

        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{task['title']} — {task['reward']} голды",
                    callback_data=f"task:{task['id']}",
                )
            ]
        )

    if not buttons:
        await send_custom(
            message,
            "📋",
            CUSTOM_TASKS,
            "\n\nВы уже выполнили все доступные задания.",
        )
        return

    await send_custom(
        message,
        "📋",
        CUSTOM_TASKS,
        "\n\nВыберите задание:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@dp.callback_query(F.data.startswith("task:"))
async def open_task(callback: CallbackQuery, state: FSMContext):
    try:
        task_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка задания.", show_alert=True)
        return

    task = db_execute(
        "SELECT * FROM tasks WHERE id = ? AND active = 1",
        (task_id,),
        fetchone=True,
    )

    if not task:
        await callback.answer("Задание не найдено.", show_alert=True)
        return

    if task_completed(callback.from_user.id, task_id):
        await callback.answer("Вы уже выполнили это задание.", show_alert=True)
        return

    if task["task_type"] == "math":
        await state.set_state(TaskAnswerState.waiting_answer)
        await state.update_data(task_id=task_id)

        await callback.message.answer(
            f"🧮 <b>{escape(task['title'])}</b>\n\n"
            f"{escape(task['description'])}\n\n"
            "Напишите ответ числом:",
            reply_markup=cancel_keyboard(),
        )

    elif task["task_type"] == "text":
        await state.set_state(TaskAnswerState.waiting_answer)
        await state.update_data(task_id=task_id)

        await callback.message.answer(
            f"📝 <b>{escape(task['title'])}</b>\n\n"
            f"{escape(task['description'])}\n\n"
            "Напишите ответ:",
            reply_markup=cancel_keyboard(),
        )

    elif task["task_type"] == "join_request":
        invite_link = task["invite_link"]

        await callback.message.answer(
            f"📢 <b>{escape(task['title'])}</b>\n\n"
            f"{escape(task['description'])}\n\n"
            "Нажмите кнопку ниже и отправьте заявку на вступление.\n"
            "Награда начисляется автоматически после отправки заявки.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📢 Отправить заявку",
                            url=invite_link,
                        )
                    ]
                ]
            ),
        )

    elif task["task_type"] == "contest":
        channels = [
            x.strip()
            for x in (task["channels"] or "").splitlines()
            if x.strip()
        ]

        buttons = []

        for channel in channels:
            if channel.startswith("https://t.me/"):
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text="📢 Открыть канал",
                            url=channel,
                        )
                    ]
                )

        buttons.append(
            [
                InlineKeyboardButton(
                    text="✅ Проверить участие",
                    callback_data=f"contest_check:{task_id}",
                )
            ]
        )

        await callback.message.answer(
            f"🏆 <b>{escape(task['title'])}</b>\n\n"
            f"{escape(task['description'])}\n\n"
            "Подпишитесь на все указанные каналы, затем нажмите "
            "«Проверить участие».",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

    await callback.answer()


@dp.message(TaskAnswerState.waiting_answer)
async def process_task_answer(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer(
            "Вы вышли из задания.",
            reply_markup=user_keyboard(),
        )
        return

    data = await state.get_data()
    task_id = data.get("task_id")

    task = db_execute(
        "SELECT * FROM tasks WHERE id = ? AND active = 1",
        (task_id,),
        fetchone=True,
    )

    if not task:
        await state.clear()
        await message.answer(
            "Задание больше недоступно.",
            reply_markup=user_keyboard(),
        )
        return

    expected = (task["answer"] or "").strip()
    actual = message.text.strip()

    if actual.lower() != expected.lower():
        await message.answer(
            "❌ Неверный ответ. Попробуйте ещё раз.",
            reply_markup=cancel_keyboard(),
        )
        return

    if not task_completed(message.from_user.id, task_id):
        mark_task_completed(message.from_user.id, task_id)
        change_balance(message.from_user.id, task["reward"])
        await complete_first_task(message.from_user.id)

    await state.clear()

    await send_custom(
        message,
        "✔️",
        CUSTOM_DONE,
        (
            "\n\nЗадание выполнено!\n"
            f"💰 Вам начислено <b>{task['reward']} голды</b>.\n"
            f"💰 Ваш баланс: <b>{get_balance(message.from_user.id)} голды</b>"
        ),
        reply_markup=user_keyboard(),
    )


@dp.callback_query(F.data.startswith("contest_check:"))
async def contest_check(callback: CallbackQuery):
    try:
        task_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка.", show_alert=True)
        return

    task = db_execute(
        "SELECT * FROM tasks WHERE id = ? AND active = 1",
        (task_id,),
        fetchone=True,
    )

    if not task:
        await callback.answer("Задание не найдено.", show_alert=True)
        return

    if task_completed(callback.from_user.id, task_id):
        await callback.answer("Вы уже получили награду.", show_alert=True)
        return

    channels = [
        x.strip()
        for x in (task["channels"] or "").splitlines()
        if x.strip()
    ]

    if not channels:
        await callback.answer(
            "У задания не указаны каналы.",
            show_alert=True,
        )
        return

    missing = []

    for channel in channels:
        username_or_id = channel

        if channel.startswith("https://t.me/"):
            username_or_id = "@" + channel.split("/")[-1].replace("+", "")

        try:
            member = await bot.get_chat_member(
                chat_id=username_or_id,
                user_id=callback.from_user.id,
            )

            if member.status not in {
                "member",
                "administrator",
                "creator",
            }:
                missing.append(channel)
        except Exception:
            missing.append(channel)

    if missing:
        await callback.answer(
            "❌ Вы подписались не на все каналы.",
            show_alert=True,
        )
        return

    mark_task_completed(callback.from_user.id, task_id)
    change_balance(callback.from_user.id, task["reward"])
    await complete_first_task(callback.from_user.id)

    await callback.message.answer(
        "✔️ <b>Задание выполнено!</b>\n\n"
        f"💰 Вам начислено <b>{task['reward']} голды</b>.\n"
        f"💰 Баланс: <b>{get_balance(callback.from_user.id)} голды</b>",
        reply_markup=user_keyboard(),
    )
    await callback.answer()


# =========================
# JOIN REQUEST
# =========================

@dp.chat_join_request()
async def handle_join_request(request):
    user_id = request.from_user.id

    if request.invite_link:
        invite_link = request.invite_link.invite_link

        task = db_execute(
            """
            SELECT *
            FROM tasks
            WHERE task_type = 'join_request'
              AND active = 1
              AND invite_link = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (invite_link,),
            fetchone=True,
        )

        if task and not task_completed(user_id, task["id"]):
            mark_task_completed(user_id, task["id"])
            change_balance(user_id, task["reward"])
            await complete_first_task(user_id)

            try:
                await bot.send_message(
                    user_id,
                    "✔️ <b>Заявка принята!</b>\n\n"
                    f"💰 Вам начислено <b>{task['reward']} голды</b>.\n"
                    f"💰 Баланс: <b>{get_balance(user_id)} голды</b>",
                    reply_markup=user_keyboard(),
                )
            except Exception:
                logging.exception(
                    "Не удалось отправить уведомление о выполнении join request"
                )


# =========================
# ПОЛУЧИТЬ ГОЛДУ / ВЫВОД
# =========================

@dp.message(F.text == "💰 Получить голду")
async def get_gold(message: Message):
    balance = get_balance(message.from_user.id)

    await send_custom(
        message,
        "🪙",
        CUSTOM_GOLD,
        (
            "\n\n"
            f"💰 Ваш баланс: <b>{balance} голды</b>\n\n"
            "Минимум для вывода: <b>100 голды</b>\n\n"
            "Введите количество голды, которое хотите вывести."
        ),
        reply_markup=cancel_keyboard(),
    )

    await WithdrawState.waiting_amount.set()


@dp.message(WithdrawState.waiting_amount)
async def process_withdraw(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer(
            "Вы вышли из раздела вывода.",
            reply_markup=user_keyboard(),
        )
        return

    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Введите количество голды целым числом.",
            reply_markup=cancel_keyboard(),
        )
        return

    balance = get_balance(message.from_user.id)

    if amount < MIN_WITHDRAW:
        await message.answer(
            f"❌ Минимальная сумма вывода — <b>{MIN_WITHDRAW} голды</b>.",
            reply_markup=cancel_keyboard(),
        )
        return

    if amount > balance:
        await message.answer(
            f"❌ Недостаточно голды.\n\n"
            f"Ваш баланс: <b>{balance} голды</b>.",
            reply_markup=cancel_keyboard(),
        )
        return

    pending = db_execute(
        """
        SELECT id
        FROM withdrawals
        WHERE user_id = ? AND status = 'pending'
        LIMIT 1
        """,
        (message.from_user.id,),
        fetchone=True,
    )

    if pending:
        await state.clear()
        await message.answer(
            "⏳ У вас уже есть активная заявка на вывод.\n"
            "Дождитесь обработки предыдущей заявки.",
            reply_markup=user_keyboard(),
        )
        return

    change_balance(message.from_user.id, -amount)

    cur = db_execute(
        """
        INSERT INTO withdrawals (
            user_id,
            amount,
            status,
            created_at
        )
        VALUES (?, ?, 'pending', ?)
        """,
        (message.from_user.id, amount, now()),
        commit=True,
    )

    withdrawal_id = cur.lastrowid

    user = get_user(message.from_user.id)

    username = (
        f"@{user['username']}"
        if user and user["username"]
        else "без username"
    )

    # Сообщение админу о каждой новой заявке.
    try:
        await bot.send_message(
            ADMIN_ID,
            "💸 <b>Новая заявка на вывод!</b>\n\n"
            f"Заявка №<code>{withdrawal_id}</code>\n"
            f"Пользователь: {escape(username)}\n"
            f"ID: <code>{message.from_user.id}</code>\n"
            f"Сумма: <b>{amount} голды</b>\n"
            f"Баланс после заявки: <b>{get_balance(message.from_user.id)} голды</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Голда выдана",
                            callback_data=f"withdraw_paid:{withdrawal_id}",
                        )
                    ]
                ]
            ),
        )
    except Exception:
        logging.exception("Не удалось уведомить администратора о выводе")

    await state.clear()

    await message.answer(
        "✅ <b>Заявка на вывод создана!</b>\n\n"
        f"💰 Сумма: <b>{amount} голды</b>\n\n"
        "Администратор проверит заявку и напишет вам "
        "в личные сообщения, когда голда будет выдана.",
        reply_markup=user_keyboard(),
    )


@dp.callback_query(F.data.startswith("withdraw_paid:"))
async def withdraw_paid(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    try:
        withdrawal_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка заявки.", show_alert=True)
        return

    withdrawal = db_execute(
        """
        SELECT *
        FROM withdrawals
        WHERE id = ?
        """,
        (withdrawal_id,),
        fetchone=True,
    )

    if not withdrawal:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    if withdrawal["status"] != "pending":
        await callback.answer(
            "Эта заявка уже обработана.",
            show_alert=True,
        )
        return

    db_execute(
        """
        UPDATE withdrawals
        SET status = 'paid'
        WHERE id = ?
        """,
        (withdrawal_id,),
        commit=True,
    )

    user_id = withdrawal["user_id"]
    amount = withdrawal["amount"]

    try:
        await bot.send_message(
            user_id,
            "💰 <b>Голда выдана!</b>\n\n"
            f"Ваша заявка на вывод <b>{amount} голды</b> обработана.\n"
            "Спасибо за использование StandFarm!",
            reply_markup=user_keyboard(),
        )
    except Exception:
        logging.exception("Не удалось уведомить пользователя о выплате")

    await callback.message.edit_text(
        callback.message.text + "\n\n✅ <b>Заявка отмечена как выданная.</b>"
    )
    await callback.answer("Готово.")


# =========================
# РЕФЕРАЛЬНАЯ ССЫЛКА
# =========================

@dp.message(F.text == "🔗 Моя реферальная ссылка")
async def referral(message: Message):
    link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{message.from_user.id}"

    await send_custom(
        message,
        "⬇️",
        CUSTOM_REFERRAL,
        (
            "\n\n"
            "Ваша реферальная ссылка:\n\n"
            f"<code>{escape(link)}</code>\n\n"
            f"💰 За каждого приглашённого пользователя вы получите "
            f"<b>{REFERRAL_REWARD} голды</b> после того, как он выполнит "
            "своё первое задание."
        ),
    )


# =========================
# ПРОМОКОДЫ
# =========================

@dp.message(F.text == "🎟 Промокод")
async def promo_start(message: Message, state: FSMContext):
    await state.set_state(PromoState.waiting_code)

    await send_custom(
        message,
        "🎁",
        CUSTOM_PROMO,
        "\n\nВведите промокод:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(PromoState.waiting_code)
async def promo_activate(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer(
            "Вы вышли из ввода промокода.",
            reply_markup=user_keyboard(),
        )
        return

    code = message.text.strip().upper()

    promo = db_execute(
        "SELECT * FROM promo_codes WHERE code = ?",
        (code,),
        fetchone=True,
    )

    if not promo:
        await message.answer(
            "❌ Промокод не найден.",
            reply_markup=cancel_keyboard(),
        )
        return

    existing = db_execute(
        """
        SELECT 1
        FROM promo_activations
        WHERE promo_id = ? AND user_id = ?
        """,
        (promo["id"], message.from_user.id),
        fetchone=True,
    )

    if existing:
        await state.clear()
        await message.answer(
            "❌ Вы уже активировали этот промокод.",
            reply_markup=user_keyboard(),
        )
        return

    conn.execute("BEGIN IMMEDIATE")

    try:
        current = conn.execute(
            """
            SELECT *
            FROM promo_codes
            WHERE id = ?
            """,
            (promo["id"],),
        ).fetchone()

        if not current:
            conn.rollback()
            await state.clear()
            await message.answer(
                "❌ Промокод не найден.",
                reply_markup=user_keyboard(),
            )
            return

        if current["activations"] >= current["max_activations"]:
            conn.rollback()
            await state.clear()
            await message.answer(
                "❌ Лимит активаций этого промокода уже исчерпан.",
                reply_markup=user_keyboard(),
            )
            return

        already = conn.execute(
            """
            SELECT 1
            FROM promo_activations
            WHERE promo_id = ? AND user_id = ?
            """,
            (current["id"], message.from_user.id),
        ).fetchone()

        if already:
            conn.rollback()
            await state.clear()
            await message.answer(
                "❌ Вы уже активировали этот промокод.",
                reply_markup=user_keyboard(),
            )
            return

        conn.execute(
            """
            INSERT INTO promo_activations (
                promo_id,
                user_id,
                activated_at
            )
            VALUES (?, ?, ?)
            """,
            (current["id"], message.from_user.id, now()),
        )

        conn.execute(
            """
            UPDATE promo_codes
            SET activations = activations + 1
            WHERE id = ?
            """,
            (current["id"],),
        )

        conn.execute(
            """
            UPDATE users
            SET balance = balance + ?
            WHERE user_id = ?
            """,
            (current["reward"], message.from_user.id),
        )

        conn.commit()

        reward = current["reward"]

    except Exception:
        conn.rollback()
        logging.exception("Ошибка активации промокода")

        await state.clear()
        await message.answer(
            "❌ Произошла ошибка. Попробуйте ещё раз.",
            reply_markup=user_keyboard(),
        )
        return

    await state.clear()

    await message.answer(
        "🎉 <b>Промокод активирован!</b>\n\n"
        f"💰 Вам начислено <b>{reward} голды</b>.\n"
        f"💰 Баланс: <b>{get_balance(message.from_user.id)} голды</b>",
        reply_markup=user_keyboard(),
    )


# =========================
# ОТЗЫВЫ
# =========================

@dp.message(F.text == "⭐ Отзывы")
async def reviews(message: Message):
    await send_custom(
        message,
        "✍️",
        CUSTOM_REVIEWS,
        (
            "\n\n"
            "⭐ <b>Отзывы StandFarm</b>\n\n"
            "Здесь пользователи делятся своим опытом, "
            "скриншотами и отзывами о получении голды."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐ Открыть отзывы",
                        url=REVIEWS_LINK,
                    )
                ]
            ]
        ),
    )


# =========================
# ПОДДЕРЖКА
# =========================

@dp.message(F.text == "🆘 Поддержка")
async def support_start(message: Message, state: FSMContext):
    await state.set_state(SupportState.waiting_message)

    await send_custom(
        message,
        "🤖",
        CUSTOM_SUPPORT,
        (
            "\n\n"
            "🆘 Напишите сообщение для поддержки.\n"
            "Оно будет отправлено администратору."
        ),
        reply_markup=cancel_keyboard(),
    )


@dp.message(SupportState.waiting_message)
async def support_message(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer(
            "Вы вышли из поддержки.",
            reply_markup=user_keyboard(),
        )
        return

    user = get_user(message.from_user.id)

    username = (
        f"@{user['username']}"
        if user and user["username"]
        else "без username"
    )

    try:
        await bot.send_message(
            ADMIN_ID,
            "🆘 <b>Новое сообщение в поддержку</b>\n\n"
            f"Пользователь: {escape(username)}\n"
            f"ID: <code>{message.from_user.id}</code>\n\n"
            f"{escape(message.text)}",
        )
    except Exception:
        logging.exception("Не удалось отправить сообщение поддержки")

    await state.clear()

    await message.answer(
        "✅ Сообщение отправлено администратору.",
        reply_markup=user_keyboard(),
    )


# =========================
# АДМИН: ДОБАВЛЕНИЕ ЗАДАНИЯ
# =========================

@dp.message(F.text == "➕ Добавить задание")
async def admin_add_task(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    await state.set_state(AdminTaskState.waiting_type)

    await message.answer(
        "➕ <b>Добавление задания</b>\n\n"
        "Напишите тип задания:\n\n"
        "<code>math</code> — математика\n"
        "<code>text</code> — текстовый ответ\n"
        "<code>join_request</code> — заявка на вступление\n"
        "<code>contest</code> — конкурс с проверкой каналов\n\n"
        "Для выхода нажмите «❌ Выйти».",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminTaskState.waiting_type)
async def admin_task_type(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer(
            "Отменено.",
            reply_markup=admin_keyboard(),
        )
        return

    task_type = message.text.strip().lower()

    if task_type not in {
        "math",
        "text",
        "join_request",
        "contest",
    }:
        await message.answer(
            "❌ Неизвестный тип. Используйте: math, text, join_request, contest.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(task_type=task_type)
    await state.set_state(AdminTaskState.waiting_title)

    await message.answer(
        "Введите название задания:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminTaskState.waiting_title)
async def admin_task_title(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    await state.update_data(title=message.text.strip())
    await state.set_state(AdminTaskState.waiting_description)

    await message.answer(
        "Введите описание/условие задания:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminTaskState.waiting_description)
async def admin_task_description(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    await state.update_data(description=message.text.strip())
    await state.set_state(AdminTaskState.waiting_reward)

    await message.answer(
        "Введите награду в голде:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminTaskState.waiting_reward)
async def admin_task_reward(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    try:
        reward = int(message.text.strip())
        if reward <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введите положительное целое число.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    task_type = data["task_type"]

    await state.update_data(reward=reward)

    if task_type in {"math", "text"}:
        await state.set_state(AdminTaskState.waiting_answer)

        await message.answer(
            "Введите правильный ответ на задание:",
            reply_markup=cancel_keyboard(),
        )

    elif task_type == "contest":
        await state.set_state(AdminTaskState.waiting_channels)

        await message.answer(
            "Введите ссылки на ВСЕ каналы для проверки — по одной ссылке на строку.\n\n"
            "Например:\n"
            "https://t.me/channel1\n"
            "https://t.me/channel2",
            reply_markup=cancel_keyboard(),
        )

    elif task_type == "join_request":
        await state.set_state(AdminTaskState.waiting_link)

        await message.answer(
            "Введите ссылку-приглашение с заявкой на вступление.\n\n"
            "Если такой ссылки ещё нет, сначала создайте её в Telegram "
            "для нужного канала.",
            reply_markup=cancel_keyboard(),
        )


@dp.message(AdminTaskState.waiting_answer)
async def admin_task_answer(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()

    db_execute(
        """
        INSERT INTO tasks (
            task_type,
            title,
            description,
            reward,
            answer,
            invite_link,
            channels,
            created_at,
            active
        )
        VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, 1)
        """,
        (
            data["task_type"],
            data["title"],
            data["description"],
            data["reward"],
            message.text.strip(),
            now(),
        ),
        commit=True,
    )

    await state.clear()

    await message.answer(
        "✅ Задание создано.",
        reply_markup=admin_keyboard(),
    )


@dp.message(AdminTaskState.waiting_channels)
async def admin_task_channels(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    channels = message.text.strip()

    if not channels:
        await message.answer(
            "❌ Укажите хотя бы один канал.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()

    db_execute(
        """
        INSERT INTO tasks (
            task_type,
            title,
            description,
            reward,
            answer,
            invite_link,
            channels,
            created_at,
            active
        )
        VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, 1)
        """,
        (
            data["task_type"],
            data["title"],
            data["description"],
            data["reward"],
            channels,
            now(),
        ),
        commit=True,
    )

    await state.clear()

    await message.answer(
        "✅ Конкурсное задание создано.",
        reply_markup=admin_keyboard(),
    )


@dp.message(AdminTaskState.waiting_link)
async def admin_task_link(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    invite_link = message.text.strip()

    if not invite_link.startswith("https://t.me/"):
        await message.answer(
            "❌ Нужна Telegram-ссылка вида https://t.me/...",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()

    db_execute(
        """
        INSERT INTO tasks (
            task_type,
            title,
            description,
            reward,
            answer,
            invite_link,
            channels,
            created_at,
            active
        )
        VALUES (?, ?, ?, ?, NULL, ?, NULL, ?, 1)
        """,
        (
            data["task_type"],
            data["title"],
            data["description"],
            data["reward"],
            invite_link,
            now(),
        ),
        commit=True,
    )

    await state.clear()

    await message.answer(
        "✅ Задание на вступление по заявке создано.",
        reply_markup=admin_keyboard(),
    )


# =========================
# АДМИН: СПИСОК ЗАДАНИЙ
# =========================

@dp.message(F.text == "📋 Список заданий")
async def admin_tasks(message: Message):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    rows = db_execute(
        "SELECT * FROM tasks ORDER BY id DESC",
        fetchall=True,
    )

    if not rows:
        await message.answer(
            "📋 Заданий пока нет.",
            reply_markup=admin_keyboard(),
        )
        return

    text = "📋 <b>Список заданий:</b>\n\n"

    for task in rows:
        status = "🟢" if task["active"] else "🔴"

        text += (
            f"{status} <b>#{task['id']} {escape(task['title'])}</b>\n"
            f"Тип: {task_type_name(task['task_type'])}\n"
            f"Награда: {task['reward']} голды\n\n"
        )

    await message.answer(
        text,
        reply_markup=admin_keyboard(),
    )


# =========================
# АДМИН: СОЗДАТЬ ПРОМОКОД
# =========================

@dp.message(F.text == "🎟 Создать промокод")
async def admin_create_promo(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    await state.set_state(AdminPromoState.waiting_code)

    await message.answer(
        "🎟 Введите новый промокод:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminPromoState.waiting_code)
async def admin_promo_code(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    code = message.text.strip().upper()

    if not code:
        await message.answer(
            "❌ Код не может быть пустым.",
            reply_markup=cancel_keyboard(),
        )
        return

    existing = db_execute(
        "SELECT id FROM promo_codes WHERE code = ?",
        (code,),
        fetchone=True,
    )

    if existing:
        await message.answer(
            "❌ Такой промокод уже существует.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(code=code)
    await state.set_state(AdminPromoState.waiting_reward)

    await message.answer(
        "Введите награду промокода в голде:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminPromoState.waiting_reward)
async def admin_promo_reward(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    try:
        reward = int(message.text.strip())
        if reward <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введите положительное целое число.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(reward=reward)
    await state.set_state(AdminPromoState.waiting_limit)

    await message.answer(
        "Введите максимальное количество активаций:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(AdminPromoState.waiting_limit)
async def admin_promo_limit(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_keyboard())
        return

    try:
        limit = int(message.text.strip())
        if limit <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введите положительное целое число.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()

    try:
        db_execute(
            """
            INSERT INTO promo_codes (
                code,
                reward,
                max_activations,
                activations,
                created_at
            )
            VALUES (?, ?, ?, 0, ?)
            """,
            (
                data["code"],
                data["reward"],
                limit,
                now(),
            ),
            commit=True,
        )
    except sqlite3.IntegrityError:
        await state.clear()
        await message.answer(
            "❌ Такой промокод уже существует.",
            reply_markup=admin_keyboard(),
        )
        return

    await state.clear()

    await message.answer(
        "✅ <b>Промокод создан!</b>\n\n"
        f"Код: <code>{escape(data['code'])}</code>\n"
        f"Награда: <b>{data['reward']} голды</b>\n"
        f"Лимит активаций: <b>{limit}</b>",
        reply_markup=admin_keyboard(),
    )


# =========================
# АДМИН: СПИСОК ПРОМОКОДОВ
# =========================

@dp.message(F.text == "📋 Промокоды")
async def admin_promos(message: Message):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    rows = db_execute(
        """
        SELECT *
        FROM promo_codes
        ORDER BY id DESC
        """,
        fetchall=True,
    )

    if not rows:
        await message.answer(
            "🎟 Промокодов пока нет.",
            reply_markup=admin_keyboard(),
        )
        return

    text = "🎟 <b>Промокоды:</b>\n\n"

    for promo in rows:
        text += (
            f"<code>{escape(promo['code'])}</code>\n"
            f"💰 Награда: {promo['reward']} голды\n"
            f"📊 Активаций: {promo['activations']} / {promo['max_activations']}\n\n"
        )

    await message.answer(
        text,
        reply_markup=admin_keyboard(),
    )


# =========================
# АДМИН: ВЫДАЧА ГОЛДЫ
# =========================

@dp.message(F.text == "💸 Выдача голды")
async def admin_withdrawals(message: Message):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    rows = db_execute(
        """
        SELECT
            w.*,
            u.username,
            u.first_name
        FROM withdrawals w
        LEFT JOIN users u ON u.user_id = w.user_id
        WHERE w.status = 'pending'
        ORDER BY w.id DESC
        """,
        fetchall=True,
    )

    if not rows:
        await message.answer(
            "💸 Активных заявок на вывод нет.",
            reply_markup=admin_keyboard(),
        )
        return

    for row in rows:
        username = (
            f"@{row['username']}"
            if row["username"]
            else "без username"
        )

        await message.answer(
            "💸 <b>Заявка на вывод</b>\n\n"
            f"№<code>{row['id']}</code>\n"
            f"Пользователь: {escape(username)}\n"
            f"ID: <code>{row['user_id']}</code>\n"
            f"Сумма: <b>{row['amount']} голды</b>\n"
            f"Создана: {row['created_at']}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Голда выдана",
                            callback_data=f"withdraw_paid:{row['id']}",
                        )
                    ]
                ]
            ),
        )


# =========================
# АДМИН: РЕФЕРАЛЫ
# =========================

@dp.message(F.text == "👥 Рефералы")
async def admin_referrals(message: Message):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    total_users = db_execute(
        "SELECT COUNT(*) AS c FROM users",
        fetchone=True,
    )["c"]

    referred_users = db_execute(
        """
        SELECT COUNT(*) AS c
        FROM users
        WHERE referred_by IS NOT NULL
        """,
        fetchone=True,
    )["c"]

    rewarded = db_execute(
        """
        SELECT COUNT(*) AS c
        FROM users
        WHERE referral_reward_given = 1
        """,
        fetchone=True,
    )["c"]

    await message.answer(
        "👥 <b>Реферальная статистика</b>\n\n"
        f"👤 Всего пользователей: <b>{total_users}</b>\n"
        f"🔗 Пришли по ссылке: <b>{referred_users}</b>\n"
        f"🎁 Реферальная награда выдана: <b>{rewarded}</b>\n"
        f"💰 Награда за первого выполненного задания: "
        f"<b>{REFERRAL_REWARD} голды</b>",
        reply_markup=admin_keyboard(),
    )


# =========================
# АДМИН: ОБЪЯВЛЕНИЯ / РАССЫЛКА
# =========================

@dp.message(F.text == "📣 Выложить объявление")
async def admin_broadcast_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID or not ADMIN_PANEL_ENABLED:
        return

    await state.set_state(BroadcastState.waiting_text)

    await message.answer(
        "📣 <b>Создание объявления</b>\n\n"
        "Напишите текст, который хотите отправить всем пользователям.\n\n"
        "Например:\n"
        "📢 Вышло новое задание!\n"
        "💰 За выполнение можно получить 20 голды.\n\n"
        "После ввода я покажу предпросмотр и попрошу подтвердить рассылку.",
        reply_markup=cancel_keyboard(),
    )


@dp.message(BroadcastState.waiting_text)
async def admin_broadcast_text(message: Message, state: FSMContext):
    if message.text == "❌ Выйти":
        await state.clear()
        await message.answer(
            "Создание объявления отменено.",
            reply_markup=admin_keyboard(),
        )
        return

    text = message.text.strip()

    if not text:
        await message.answer(
            "❌ Объявление не может быть пустым.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(broadcast_text=text)

    await message.answer(
        "📣 <b>Предпросмотр объявления:</b>\n\n"
        f"{escape(text)}\n\n"
        "Отправить это сообщение всем пользователям?",
        reply_markup=broadcast_confirm_keyboard(),
    )


@dp.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await state.clear()

    await callback.message.edit_text(
        "❌ Рассылка отменена."
    )

    await callback.message.answer(
        "🛠 Админ-панель.",
        reply_markup=admin_keyboard(),
    )

    await callback.answer()


@dp.callback_query(F.data == "broadcast_send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text")

    if not text:
        await state.clear()
        await callback.answer(
            "Текст объявления не найден.",
            show_alert=True,
        )
        return

    users = db_execute(
        "SELECT user_id FROM users",
        fetchall=True,
    )

    await callback.message.edit_text(
        "📤 <b>Рассылка запущена...</b>\n\n"
        f"Получателей: <b>{len(users)}</b>"
    )

    success = 0
    failed = 0

    for row in users:
        user_id = row["user_id"]

        try:
            await bot.send_message(
                user_id,
                text,
            )
            success += 1

            # Небольшая пауза снижает риск упереться в лимиты Telegram.
            await asyncio.sleep(0.05)

        except Exception as e:
            failed += 1
            logging.warning(
                "Не удалось отправить объявление пользователю %s: %s",
                user_id,
                e,
            )

    await state.clear()

    await callback.message.answer(
        "✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Успешно отправлено: <b>{success}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>",
        reply_markup=admin_keyboard(),
    )

    await callback.answer()


# =========================
# ОБЩИЕ КНОПКИ / СОХРАНЕНИЕ ПОЛЬЗОВАТЕЛЯ
# =========================

@dp.message()
async def fallback(message: Message):
    # Любое обычное сообщение пользователя добавляет/обновляет его в базе.
    if message.from_user:
        add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
        )

    if message.from_user.id == ADMIN_ID and ADMIN_PANEL_ENABLED:
        await message.answer(
            "🛠 Используйте кнопки админ-панели.",
            reply_markup=admin_keyboard(),
        )
        return

    await message.answer(
        "Выберите действие в меню.",
        reply_markup=user_keyboard(),
    )


# =========================
# ЗАПУСК
# =========================

async def main():
    logging.info("StandFarm bot started")

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("StandFarm bot stopped")
