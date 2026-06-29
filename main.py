import logging
import sqlite3
import asyncio
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات اصلی (حتماً تغییر دهید) ---
TOKEN = 'YOUR_BOT_TOKEN_HERE'
OWNER_ID = 12345678  # آیدی عددی تلگرام خودتان

# --- سیستم دیتابیس قدرتمند (SQLite) ---
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot_engine.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # جدول تنظیمات گروه‌ها (تمام قفل‌ها)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS groups 
            (chat_id INTEGER PRIMARY KEY, lock_link INT=0, lock_gif INT=0, lock_photo INT=0, 
             lock_video INT=0, lock_voice INT=0, lock_file INT=0, lock_sticker INT=0, 
             lock_forward INT=0, lock_bot INT=0, welcome_msg TEXT)''')
        
        # جدول اقتصاد و کاربران
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users 
            (user_id INTEGER PRIMARY KEY, coins INT=0, xp INT=0, level INT=1, 
             is_banned INT=0, is_muted INT=0, role TEXT='user')''')
        
        # جدول ادمین‌ها
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
        self.conn.commit()

    def get_group(self, chat_id):
        self.cursor.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        return self.cursor.fetchone()

    def update_group_setting(self, chat_id, column, value):
        self.cursor.execute(f"INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (chat_id,))
        self.cursor.execute(f"UPDATE groups SET {column} = ? WHERE chat_id = ?", (value, chat_id))
        self.conn.commit()

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

    def add_user(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        self.conn.commit()

db = Database()

# --- بخش مدیریت و قفل‌ها (Security Core) ---

async def main_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type == 'private':
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg = update.effective_message

    # چک کردن بن بودن کاربر
    user = db.get_user(user_id)
    if user and user[4] == 1: return

    # دریافت تنظیمات گروه
    group = db.get_group(chat_id)
    if not group:
        db.cursor.execute("INSERT INTO groups (chat_id) VALUES (?)", (chat_id,))
        db.conn.commit()
        return

    # منطق قفل‌ها (Locking System)
    # group[1]=link, group[2]=gif, group[3]=photo, group[4]=video, group[5]=voice, group[6]=file, group[7]=sticker, group[8]=forward
    
    if group[1] == 1 and (msg.entities or msg.caption) and any(e.type in ['url', 'text_link'] for e in (msg.entities or [])):
        await msg.delete()
        return

    if group[2] == 1 and msg.animation:
        await msg.delete()
        return

    if group[3] == 1 and msg.photo:
        await msg.delete()
        return

    if group[4] == 1 and msg.video:
        await msg.delete()
        return

# --- بخش اقتصاد و بازی (Economy & Fun) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.add_user(user_id)
    await update.message.reply_text(
        f"🤖 **سلام {update.effective_user.first_name}!**\n\n"
        f"🚀 به ربات مدیریت پیشرفته خوش آمدی.\n"
        f"🛠 سازنده: **امیرعلی فروزان اصل**\n\n"
        f"💰 سکه: 0 | 🆙 لول: 1\n"
        f"📜 از دستور /help برای مشاهده امکانات استفاده کنید."
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)
    if user:
        text = (f"👤 **پروفایل کاربر**\n\n"
                f"🆔 آیدی: `{user[0]}`\n"
                f"💰 سکه: {user[1]}\n"
                f"✨ XP: {user[2]}\n"
                f"🆙 لول: {user[3]}")
        await update.message.reply_text(text, parse_mode='Markdown')

async def coin_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # بازی شیر یا خط (Fun Section)
    res = random.choice(["شیر 🪙", "خط ❌"])
    user_id = update.effective_user.id
    db.cursor.execute("UPDATE users SET coins = coins + 10 WHERE user_id = ?", (user_id,))
    db.conn.commit()
    await update.message.reply_text(f"نتیجه: {res}\n\n🎉 شما 10 سکه برنده شدید!")

# --- پنل مدیریت (Admin Panel) ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return await update.message.reply_text("❌ فقط مالک ربات می‌تواند این دستور را اجرا کند.")

    keyboard = [
        [InlineKeyboardButton("🔒 قفل لینک", callback_data="lock_link"), InlineKeyboardButton("🔓 باز کردن لینک", callback_data="unlock_link")],
        [InlineKeyboardButton("🎬 قفل فیلم", callback_data="lock_video"), InlineKeyboardButton("🔓 باز کردن فیلم", callback_data="unlock_video")],
        [InlineKeyboardButton("📊 آمار کاربران", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠 **پنل مدیریت اصلی**\nانتخاب کنید چه چیزی را مدیریت کنید:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    await query.answer()

    if query.data == "lock_link":
        db.update_group_setting(chat_id, "lock_link", 1)
        await query.edit_message_text("✅ قفل لینک فعال شد.")
    elif query.data == "unlock_link":
        db.update_group_setting(chat_id, "lock_link", 0)
        await query.edit_message_text("🔓 قفل لینک غیرفعال شد.")
    elif query.data == "lock_video":
        db.update_group_setting(chat_id, "lock_video", 1)
        await query.edit_message_text("✅ قفل فیلم فعال شد.")
    elif query.data == "unlock_video":
        db.update_group_setting(chat_id, "lock_video", 0)
        await query.edit_message_text("🔓 قفل فیلم غیرفعال شد.")

# --- اجرا ---

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    # هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("coin", coin_game))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("help", lambda u, c: u.message.reply_text("دستورات:\n/start - شروع\n/profile - پروفایل\n/coin - بازی سکه\n/admin - پنل مدیریت")))
    
    # هندلر دکمه‌ها
    app.add_handler(CallbackQueryHandler(button_callback))

    # هندلر اصلی فیلتر (Security Engine)
    app.add_handler(MessageHandler(filters.ALL, main_filter))

    print("🚀 ربات با موفقیت توسط امیرعلی فروزان اصل روشن شد...")
    app.run_polling()
