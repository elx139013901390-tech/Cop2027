import os
import re
import logging
import aiosqlite
from datetime import timedelta, datetime

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# تنظیمات اولیه
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = os.getenv("TOKEN")
DB_FILE = "bot.db"
CREATOR = "امیرعلی فروزان اصل"

if not TOKEN:
    raise ValueError("TOKEN environment variable is not set!")

# =========================
# دیتابیس
# =========================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                lock_gif INTEGER DEFAULT 0,
                lock_sticker INTEGER DEFAULT 0,
                lock_photo INTEGER DEFAULT 0,
                lock_video INTEGER DEFAULT 0,
                lock_document INTEGER DEFAULT 0,
                lock_links INTEGER DEFAULT 0,
                welcome INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS filtered_words (
                chat_id INTEGER,
                word TEXT,
                UNIQUE(chat_id, word)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                chat_id INTEGER,
                user_id INTEGER,
                count INTEGER DEFAULT 0,
                UNIQUE(chat_id, user_id)
            )
        """)
        await db.commit()

async def get_settings(chat_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT lock_gif, lock_sticker, lock_photo, lock_video, lock_document, lock_links, welcome FROM settings WHERE chat_id=?",
            (chat_id,)
        )
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO settings (chat_id) VALUES (?)", (chat_id,))
            await db.commit()
            return {
                "lock_gif": 0,
                "lock_sticker": 0,
                "lock_photo": 0,
                "lock_video": 0,
                "lock_document": 0,
                "lock_links": 0,
                "welcome": 1
            }
        return {
            "lock_gif": row[0],
            "lock_sticker": row[1],
            "lock_photo": row[2],
            "lock_video": row[3],
            "lock_document": row[4],
            "lock_links": row[5],
            "welcome": row[6],
        }

async def set_setting(chat_id: int, key: str, value: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO settings (chat_id) VALUES (?)", (chat_id,))
        await db.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, chat_id))
        await db.commit()

async def add_filtered_word(chat_id: int, word: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO filtered_words (chat_id, word) VALUES (?, ?)",
            (chat_id, word.lower().strip())
        )
        await db.commit()

async def remove_filtered_word(chat_id: int, word: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "DELETE FROM filtered_words WHERE chat_id=? AND word=?",
            (chat_id, word.lower().strip())
        )
        await db.commit()

async def get_filtered_words(chat_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT word FROM filtered_words WHERE chat_id=?", (chat_id,))
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def get_warn(chat_id: int, user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            "SELECT count FROM warns WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

async def set_warn(chat_id: int, user_id: int, count: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO warns (chat_id, user_id, count)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET count=excluded.count
        """, (chat_id, user_id, count))
        await db.commit()

# =========================
# ابزارها
# =========================
def is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_chat)

async def can_manage(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")

def contains_link(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r"https?://",
        r"t\.me/",
        r"www\.",
        r"\btelegram\.me\b",
        r"\bjoinchat\b",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)

# =========================
# دستورات
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"سلام!\n"
        f"من ربات مدیریت گروه هستم.\n"
        f"سازنده: {CREATOR}\n\n"
        f"دستورات اصلی:\n"
        f"/lockgif /unlockgif\n"
        f"/locksticker /unlocksticker\n"
        f"/lockphoto /unlockphoto\n"
        f"/lockvideo /unlockvideo\n"
        f"/lockfile /unlockfile\n"
        f"/locklink /unlocklink\n"
        f"/addword <کلمه>\n"
        f"/delword <کلمه>\n"
        f"/warn <reply>\n"
        f"/mute <reply>\n"
        f"/kick <reply>\n"
        f"/ban <reply>\n"
        f"/settings"
    )

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = await get_settings(chat_id)
    words = await get_filtered_words(chat_id)
    text = (
        f"⚙️ تنظیمات گروه\n\n"
        f"قفل گیف: {'✅' if s['lock_gif'] else '❌'}\n"
        f"قفل استیکر: {'✅' if s['lock_sticker'] else '❌'}\n"
        f"قفل عکس: {'✅' if s['lock_photo'] else '❌'}\n"
        f"قفل ویدیو: {'✅' if s['lock_video'] else '❌'}\n"
        f"قفل فایل: {'✅' if s['lock_document'] else '❌'}\n"
        f"قفل لینک: {'✅' if s['lock_links'] else '❌'}\n"
        f"خوش‌آمدگویی: {'✅' if s['welcome'] else '❌'}\n"
        f"\nکلمات فیلتر شده:\n" + (", ".join(words) if words else "ندارد")
    )
    await update.message.reply_text(text)

async def lock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, value: int, title: str):
    chat_id = update.effective_chat.id
    await set_setting(chat_id, key, value)
    await update.message.reply_text(f"{title} {'فعال' if value else 'غیرفعال'} شد.")

async def lockgif(update, context): await lock_cmd(update, context, "lock_gif", 1, "قفل گیف")
async def unlockgif(update, context): await lock_cmd(update, context, "lock_gif", 0, "قفل گیف")
async def locksticker(update, context): await lock_cmd(update, context, "lock_sticker", 1, "قفل استیکر")
async def unlocksticker(update, context): await lock_cmd(update, context, "lock_sticker", 0, "قفل استیکر")
async def lockphoto(update, context): await lock_cmd(update, context, "lock_photo", 1, "قفل عکس")
async def unlockphoto(update, context): await lock_cmd(update, context, "lock_photo", 0, "قفل عکس")
async def lockvideo(update, context): await lock_cmd(update, context, "lock_video", 1, "قفل ویدیو")
async def unlockvideo(update, context): await lock_cmd(update, context, "lock_video", 0, "قفل ویدیو")
async def lockfile(update, context): await lock_cmd(update, context, "lock_document", 1, "قفل فایل")
async def unlockfile(update, context): await lock_cmd(update, context, "lock_document", 0, "قفل فایل")
async def locklink(update, context): await lock_cmd(update, context, "lock_links", 1, "قفل لینک")
async def unlocklink(update, context): await lock_cmd(update, context, "lock_links", 0, "قفل لینک")

async def addword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("استفاده: /addword <کلمه>")
    word = " ".join(context.args).strip()
    await add_filtered_word(update.effective_chat.id, word)
    await update.message.reply_text(f"کلمه «{word}» به فیلتر اضافه شد.")

async def delword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("استفاده: /delword <کلمه>")
    word = " ".join(context.args).strip()
    await remove_filtered_word(update.effective_chat.id, word)
    await update.message.reply_text(f"کلمه «{word}» از فیلتر حذف شد.")

async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("برای اخطار باید روی پیام کاربر ریپلای کنید.")
    chat_id = update.effective_chat.id
    user_id = update.message.reply_to_message.from_user.id
    count = await get_warn(chat_id, user_id) + 1
    await set_warn(chat_id, user_id, count)
    await update.message.reply_text(f"کاربر {update.message.reply_to_message.from_user.mention_html()} اخطار گرفت. ({count}/3)", parse_mode="HTML")
    if count >= 3:
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
        except:
            pass

async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("برای سکوت باید روی پیام کاربر ریپلای کنید.")
    user_id = update.message.reply_to_message.from_user.id
    until = datetime.now() + timedelta(days=1)
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(update.effective_chat.id, user_id, permissions=perms, until_date=until)
    await update.message.reply_text("کاربر سکوت شد.")

async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("برای کیک باید روی پیام کاربر ریپلای کنید.")
    user_id = update.message.reply_to_message.from_user.id
    await context.bot.ban_chat_member(update.effective_chat.id, user_id)
    await context.bot.unban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text("کاربر کیک شد.")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("برای بن باید روی پیام کاربر ریپلای کنید.")
    user_id = update.message.reply_to_message.from_user.id
    await context.bot.ban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text("کاربر بن شد.")

# =========================
# خوش‌آمدگویی
# =========================
async def welcome_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.new_chat_members:
        s = await get_settings(update.effective_chat.id)
        if s["welcome"]:
            for user in update.message.new_chat_members:
                await update.message.reply_text(
                    f"خوش آمدی {user.mention_html()} 🌹\n"
                    f"به گروه خوش اومدی.\n"
                    f"سازنده ربات: {CREATOR}",
                    parse_mode="HTML"
                )

# =========================
# کنترل پیام‌ها
# =========================
async def moderation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    chat_id = update.effective_chat.id
    s = await get_settings(chat_id)
    msg = update.message

    if msg.text and contains_link(msg.text) and s["lock_links"]:
        await msg.delete()
        return

    if msg.animation and s["lock_gif"]:
        await msg.delete()
        return

    if msg.sticker and s["lock_sticker"]:
        await msg.delete()
        return

    if msg.photo and s["lock_photo"]:
        await msg.delete()
        return

    if msg.video and s["lock_video"]:
        await msg.delete()
        return

    if msg.document and s["lock_document"]:
        await msg.delete()
        return

    if msg.text:
        words = await get_filtered_words(chat_id)
        lower = msg.text.lower()
        for w in words:
            if w in lower:
                await msg.delete()
                return

# =========================
# اجرا
# =========================
async def post_init(app):
    await init_db()

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))

    app.add_handler(CommandHandler("lockgif", lockgif))
    app.add_handler(CommandHandler("unlockgif", unlockgif))
    app.add_handler(CommandHandler("locksticker", locksticker))
    app.add_handler(CommandHandler("unlocksticker", unlocksticker))
    app.add_handler(CommandHandler("lockphoto", lockphoto))
    app.add_handler(CommandHandler("unlockphoto", unlockphoto))
    app.add_handler(CommandHandler("lockvideo", lockvideo))
    app.add_handler(CommandHandler("unlockvideo", unlockvideo))
    app.add_handler(CommandHandler("lockfile", lockfile))
    app.add_handler(CommandHandler("unlockfile", unlockfile))
    app.add_handler(CommandHandler("locklink", locklink))
    app.add_handler(CommandHandler("unlocklink", unlocklink))

    app.add_handler(CommandHandler("addword", addword))
    app.add_handler(CommandHandler("delword", delword))

    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_handler))
    app.add_handler(MessageHandler(filters.ALL, moderation_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
