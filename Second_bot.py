"""
Бот-счётчик регистрации.
По /start юзер вносится в хранилище и получает номер по порядку (001-456).
Лимит участников: MAX_PLAYERS.
"""

import os
import sqlite3
import logging
import threading
import json
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_PATH = "players.db"
MAX_PLAYERS = 456
BOT_TOKEN = "8766624154:AAFucLrqyoQ6_Og7lLWsccZRzS_W1CeUE00"  # ⚠️ СМЕНИТЕ ТОКЕН!


def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
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
        text = f"Ты зарегистрирован.\nТвой номер: {format_number(number)}"
    else:
        text = "Ты зарегистрирован в качестве персонала."

    if not created:
        text = "Ты уже зарегистрирован.\n" + (
            f"Твой номер: {format_number(number)}" if role == "player" else "Роль: персонал"
        )

    await update.message.reply_text(text)


class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Страница со списком игроков
        if self.path == '/players' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            
            with closing(sqlite3.connect(DB_PATH)) as conn:
                rows = conn.execute(
                    "SELECT number, role, username, full_name, registered_at FROM players ORDER BY id"
                ).fetchall()
                
                html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Игроки</title>
                    <style>
                        body { font-family: Arial; margin: 20px; background: #f0f0f0; }
                        table { border-collapse: collapse; width: 100%; background: white; }
                        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
                        th { background: #4CAF50; color: white; }
                        tr:nth-child(even) { background: #f9f9f9; }
                        .count { margin-top: 20px; font-weight: bold; font-size: 18px; }
                        .header { background: #333; color: white; padding: 10px; border-radius: 5px; }
                    </style>
                </head>
                <body>
                    <div class="header">
                        <h2>📋 Зарегистрированные игроки</h2>
                    </div>
                    <table>
                        <tr>
                            <th>#</th>
                            <th>Номер</th>
                            <th>Роль</th>
                            <th>Username</th>
                            <th>Имя</th>
                            <th>Дата регистрации</th>
                        </tr>
                """
                
                for i, r in enumerate(rows, 1):
                    number, role, username, full_name, registered_at = r
                    num_str = f"{number:03d}" if number else "---"
                    html += f"""
                        <tr>
                            <td>{i}</td>
                            <td><b>{num_str}</b></td>
                            <td>{role}</td>
                            <td>@{username or '-'}</td>
                            <td>{full_name}</td>
                            <td>{registered_at}</td>
                        </tr>
                    """
                
                html += f"""
                    </table>
                    <p class="count">👥 Всего игроков: {len(rows)} из {MAX_PLAYERS}</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
        
        # JSON API
        elif self.path == '/api/players':
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            
            with closing(sqlite3.connect(DB_PATH)) as conn:
                rows = conn.execute(
                    "SELECT number, role, username, full_name, registered_at FROM players ORDER BY id"
                ).fetchall()
                
                data = []
                for r in rows:
                    data.append({
                        "number": r[0],
                        "role": r[1],
                        "username": r[2],
                        "full_name": r[3],
                        "registered_at": r[4]
                    })
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        
        # Обычный пинг
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass


def _run_fake_webserver():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    server.serve_forever()


def main():
    if not BOT_TOKEN:
        raise SystemExit("Задай переменную окружения BOT_TOKEN")

    init_db()
    threading.Thread(target=_run_fake_webserver, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    log.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
