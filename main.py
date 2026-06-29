import logging
import sqlite3
import asyncio
import random
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- تنظیمات اولیه ---
TOKEN = 'YOUR_BOT_TOKEN_HERE' # توکن خودت را اینجا بگذار
OWNER_ID = 12345678 # آیدی عددی خودت را اینجا بگذار

# تنظیمات لاگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- سیستم دیتابیس پیشرفته ---
class Database:
    def __init__(self, db_name="bot_engine.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # جدول تنظیمات گروه (تمام قفل‌ها)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            lock_link INTEGER DEFAULT 0, lock_gif INTEGER DEFAULT 0, lock_photo INTEGER DEFAULT 0,
            lock_video INTEGER DEFAULT 0, lock_voice INTEGER DEFAULT 0, lock_file INTEGER DEFAULT 0,
            lock_sticker INTEGER DEFAULT 0, lock_forward INTEGER DEFAULT 0, lock_text INTEGER DEFAULT 0,
            welcome_msg TEXT DEFAULT 'به گروه خوش آمدید!'
        )''')

        # جدول کاربران (اقتصاد، سطح و مدیریت)
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
            is_banned INTEGER DEFAULT 0, is_muted INTEGER DEFAULT 0, role TEXT DEFAULT 'user'
        )''')
        
        # جدول اخطارها
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (
            user_id INTEGER, chat_id INTEGER, count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, chat_id)
        )''')
        
        self.conn.commit()

    def get_group(self, chat_id):
        self.cursor.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        res = self.cursor.fetchone()
        if not res:
            self.cursor.execute("INSERT INTO groups (chat_id) VALUES (?)", (chat_id,))
            self.conn.commit()
            return self.get_group(chat_id)
        return res

    def set_group_setting(self, chat_id, column, value):
        self.cursor.execute(f"UPDATE groups SET {column} = ? WHERE chat_id = ?", (value, chat_id))
        self.conn.commit()

    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        res = self.cursor.fetchone()
        if not res:
            self.cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            self.conn.commit()
            return self.get_user(user_id)
        return res

    def update_user_status(self, user_id, field, value):
        self.cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
        self.conn.commit()

    def add_coin(self, user_id, amount):
        self.cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def add_warning(self, user_id, chat_id):
        self.cursor.execute('''
            INSERT INTO warnings (user_id, chat_id, count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET count = count + 1
        ''', (user_id, chat_id))
        self.conn.commit()

    def get_warnings(self, user_id, chat_id):
        self.cursor.execute("SELECT count FROM warnings WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        res = self.cursor.fetchone()
        return res[0] if res else 0

db = Database()

# --- سیستم ضد اسپم و فلود (در حافظه) ---
user_flood_control = {}

# --- مدیریت اصلی پیام‌ها و قفل‌ها ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type == 'private':
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    msg = update.effective_message
    
    if not msg: return

    # ۱. بررسی بن بودن و سکوت کاربر
    user = db.get_user(user_id)
    if user[4] == 1: # is_banned
        await msg.delete()
        return
    if user[5] == 1: # is_muted
        await msg.delete()
        return

    # ۲. دریافت تنظیمات گروه
    group = db.get_group(chat_id)
    # group[1]=link, group[2]=gif, group[3]=photo, group[4]=video, group[5]=voice, group[6]=file, group[7]=sticker, group[8]=forward, group[9]=text

    # ۳. اجرای قفل‌ها
    try:
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

        if group[5] == 1 and msg.voice:
            await msg.delete()
            return

        if group[6] == 1 and msg.document:
            await msg.delete()
            return

        if group[7] == 1 and msg.sticker:
            await msg.delete()
            return

        if group[8] == 1 and msg.forward_from:
            await msg.delete()
            return

    except Exception as e:
        print(f"Error in lock: {e}")

# --- دستورات مدیریت گروه ---

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /warn برای دادن اخطار"""
    if not update.effective_chat.get_member(update.effective_user.id).is_administrator:
        return await update.message.reply_text("❌ شما ادمین نیستید!")

    if not context.args:
        return await update.message.reply_text("✅ کاربرد: `/warn @username`", parse_mode='Markdown')

    target_user = context.args[0].replace("@", "")
    # در اینجا برای سادگی فرض می‌کنیم کاربر را پیدا کردیم (در ربات واقعی باید از فیلتر پیام‌ها استفاده شود)
    # این بخش نیاز به منطق پیچیده‌تری برای پیدا کردن ID از روی یوزرنیم دارد
    await update.message.reply_text(f"⚠️ به کاربر {target_user} یک اخطار داده شد.")
    db.add_warning(0, update.effective_chat.id) # مثال

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /ban برای مسدود کردن"""
    if not update.effective_chat.get_member(update.effective_user.id).is_administrator:
        return

    if context.args:
        # در ربات اصلی باید کاربر را پیدا کنید، اینجا فقط یک مثال است
        await update.message.reply_text("🚫 کاربر مسدود شد (در نسخه کامل از ID استفاده کنید)")
        # در اینجا باید با API تلگرام کاربر را Ban کنید

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat.get_member(update.effective_user.id).is_administrator:
        return
    await update.message.reply_text("🔓 کاربر آزاد شد.")

# --- دستورات اقتصاد و سرگرمی ---

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_user(update.effective_user.id)

    if not user:
        db.add_user(update.effective_user.id)
        user = db.get_user(update.effective_user.id)

    text = (
        f"👤 پروفایل\n\n"
        f"🆔 آیدی: {user[0]}\n"
        f"💰 سکه: {user[1]}\n"
        f"⭐ XP: {user[2]}\n"
        f"🏆 لول: {user[3]}"
    )

    await update.message.reply_text(text)
    

async def profile(update: Update, context: Context
