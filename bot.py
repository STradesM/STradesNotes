import os
import logging
import sqlite3
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8560466214:AAHmwji7tZxiMXzDOWpTb2PFYGYlVHJsjc8")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "6796290674"))  # Chefor's Telegram user ID

DB_PATH = os.path.join(os.path.dirname(__file__), "store.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            code TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def save_file(chat_id: int, message_id: int) -> str:
    code = uuid.uuid4().hex[:8]
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO files (code, chat_id, message_id) VALUES (?, ?, ?)",
        (code, chat_id, message_id),
    )
    conn.commit()
    conn.close()
    return code


def get_file(code: str):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT chat_id, message_id FROM files WHERE code = ?", (code,)
    ).fetchone()
    conn.close()
    return row


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Hi! Send me a link with a file code to receive that file, "
            "e.g. t.me/YourBot?start=abc123"
        )
        return

    code = args[0]
    row = get_file(code)
    if not row:
        await update.message.reply_text("Sorry, that link is invalid or expired.")
        return

    chat_id, message_id = row
    try:
        await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=chat_id,
            message_id=message_id,
        )
    except Exception as e:
        log.error(f"Failed to deliver file for code {code}: {e}")
        await update.message.reply_text(
            "Something went wrong sending that file. Please try again later."
        )


async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You're not authorized to upload files here.")
        return

    message = update.message
    chat_id = message.chat_id
    message_id = message.message_id

    code = save_file(chat_id, message_id)
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={code}"

    await message.reply_text(f"File saved! Share this link:\n{link}")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running.")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    server.serve_forever()


def main():
    threading.Thread(target=run_health_server, daemon=True).start()

    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            (filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO)
            & filters.ChatType.PRIVATE,
            handle_upload,
        )
    )

    log.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
