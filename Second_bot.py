import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from supabase import create_client, Client
import traceback

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MAX_PLAYERS = 456

SUPABASE_URL = "https://etsfnhefcmonmjmwuhsk.supabase.co"
SUPABASE_KEY = "sb_publishable_SFX8_Ml6TjzWnY3j7a7xMw_tkBk1zQv"
BOT_TOKEN = "8766624154:AAG_V4GnGKfvgD8Bol4UF2uDl1-ns_Yicx4"  # ЗАМЕНИТЕ НА АКТУАЛЬНЫЙ ТОКЕН

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Задайте SUPABASE_URL и SUPABASE_KEY")
if not BOT_TOKEN:
    raise SystemExit("Задайте BOT_TOKEN")

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    log.info("Подключение к Supabase успешно")
except Exception as e:
    log.error(f"Ошибка подключения к Supabase: {e}")
    raise

def format_number(n: int) -> str:
    return f"{n:03d}"

def get_player_by_user_id(user_id: int):
    try:
        res = supabase.table("players").select("number, role").eq("user_id", user_id).execute()
        if res.data:
            return res.data[0]["number"], res.data[0]["role"]
    except Exception as e:
        log.error(f"Ошибка get_player: {e}")
    return None

def count_players():
    try:
        res = supabase.table("players").select("id", count="exact").eq("role", "player").execute()
        return res.count
    except Exception as e:
        log.error(f"Ошибка count_players: {e}")
        return 0

def register_player(user_id: int, username: str, full_name: str):
    existing = get_player_by_user_id(user_id)
    if existing:
        return existing[0], existing[1], False

    current_count = count_players()
    if current_count < MAX_PLAYERS:
        next_number = current_count + 1
        role = "player"
    else:
        next_number = None
        role = "staff"

    data = {
        "number": next_number,
        "role": role,
        "user_id": user_id,
        "username": username,
        "full_name": full_name
    }
    try:
        supabase.table("players").insert(data).execute()
        return next_number, role, True
    except Exception as e:
        log.error(f"Ошибка регистрации: {e}")
        return None, None, False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        number, role, created = register_player(
            user_id=user.id,
            username=user.username or "",
            full_name=user.full_name or "",
        )

        if number is None and role is None:
            await update.message.reply_text("❌ Ошибка регистрации. Попробуйте позже.")
            return

        if role == "player":
            text = f"✅ Ты зарегистрирован.\nТвой номер: {format_number(number)}"
        else:
            text = "✅ Ты зарегистрирован в качестве персонала."

        if not created:
            text = "Ты уже зарегистрирован.\n" + (
                f"Твой номер: {format_number(number)}" if role == "player" else "Роль: персонал"
            )

        await update.message.reply_text(text)
    except Exception as e:
        log.error(f"Ошибка в start: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")

class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path == '/players' or self.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()

                res = supabase.table("players").select("number, role, username, full_name, registered_at").order("id").execute()
                rows = res.data

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
                    <div class="header"><h2>📋 Зарегистрированные игроки</h2></div>
                    <table>
                        <tr><th>#</th><th>Номер</th><th>Роль</th><th>Username</th><th>Имя</th><th>Дата регистрации</th></tr>
                """
                for i, r in enumerate(rows, 1):
                    num_str = f"{r['number']:03d}" if r['number'] else "---"
                    html += f"""
                        <tr>
                            <td>{i}</td>
                            <td><b>{num_str}</b></td>
                            <td>{r['role']}</td>
                            <td>@{r['username'] or '-'}</td>
                            <td>{r['full_name']}</td>
                            <td>{r['registered_at']}</td>
                        </tr>
                    """
                html += f"""
                    </table>
                    <p class="count">👥 Всего игроков: {len(rows)} из {MAX_PLAYERS}</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
        except Exception as e:
            log.error(f"Ошибка в веб-сервере: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Ошибка: {e}".encode())

    def log_message(self, format, *args):
        pass

def _run_fake_webserver():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    server.serve_forever()

def main():
    threading.Thread(target=_run_fake_webserver, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    log.info("🚀 Бот запущен с Supabase")
    app.run_polling()

if __name__ == "__main__":
    main()
