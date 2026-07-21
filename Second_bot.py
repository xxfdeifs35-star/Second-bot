"""
Бот-счётчик регистрации.
По /start юзер вносится в хранилище и получает номер по порядку (001-456).
Лимит участников: MAX_PLAYERS.

Установка (Pydroid 3):
    pip install python-telegram-bot

Запуск:
    задать BOT_TOKEN ниже или через переменную окружения
    запустить файл
"""

import os
import sqlite3
import logging
from contextlib import closing

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH = "players.db"
MAX_PLAYERS = 456
BOT_TOKEN = "8766624154:AAFucLrqyoQ6_Og7lLWsccZRzS_W1CeUE00"


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        # WAL защищает от повреждения файла при внезапном закрытии Pydroid/телефона
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number INTEGER,
                role TEXT NOT NULL,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def format_number(n: int) -> str:
    return f"{n:03d}"


def get_player_by_user_id(user_id: int):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute(
            "SELECT number, role FROM players WHERE user_id = ?", (user_id,)
        )
        row = cur.fetchone()
        return row if row else None


def count_players() -> int:
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.execute("SELECT COUNT(*) FROM players WHERE role = 'player'")
        return cur.fetchone()[0]


def register_player(user_id: int, username: str, full_name: str):
    """
    Возвращает (number, role, created: bool).
    Если юзер уже зарегистрирован — вернёт его существующие данные.
    Первые MAX_PLAYERS получают role='player' и номер по порядку.
    Все следующие получают role='staff' без номера игрока.
    """
    existing = get_player_by_user_id(user_id)
    if existing is not None:
        number, role = existing
        return number, role, False

    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("SELECT COUNT(*) FROM players WHERE role = 'player'")
        current_count = cur.fetchone()[0]

        if current_count < MAX_PLAYERS:
            next_number = current_count + 1
            role = "player"
        else:
            next_number = None
            role = "staff"

        conn.execute(
            "INSERT INTO players (number, role, user_id, username, full_name) "
            "VALUES (?, ?, ?, ?, ?)",
            (next_number, role, user_id, username, full_name),
        )
        conn.commit()
        return next_number, role, True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    number, role, created = register_player(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name or "",
    )

    if role == "player":
        text = f"ты зарегистрировался.\nТвой номер: {format_number(number)}"
    else:
        text = "Ты получил свой номер."

    if not created:
        text = "Ты уже зарегистрирован.\n" + (
            f"Твой номер: {format_number(number)}" if role == "player" else ""
        )

    await update.message.reply_text(text)


def main():
    if not BOT_TOKEN:
        raise SystemExit("Задай переменную окружения BOT_TOKEN")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    log.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
    
