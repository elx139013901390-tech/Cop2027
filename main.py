import logging
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- تنظیمات حیاتی ---
TOKEN = "YOUR_BOT_TOKEN_HERE"  # توکن خود را اینجا بگذارید
CREATOR_NAME = "امیرعلی فروزان اصل"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- مدیریت دیتابیس (هسته اطلاعات) ---
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot_pro.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # جدول مالک اصلی
        self.cursor.execute("CREATE TABLE IF NOT EXISTS owner (user_id INTEGER PRIMARY KEY, is_owner INTEGER)")
        # جدول کاربران (اقتصادی)
        self.cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 100, exp INTEGER DEFAULT 0)")
        # جدول گروه‌ها و قفل‌ها
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY, 
            group_name TEXT,
            lock_link INTEGER DEFAULT 0,
            lock_media INTEGER DEFAULT 0,
            lock_sticker INTEGER DEFAULT 0,
            lock_gif INTEGER DEFAULT 0,
            lock_file INTEGER DEFAULT 0,
            welcome_msg TEXT DEFAULT 'سلام به عضو جدید!'
        )""")
        self.conn.commit()

    def set_owner(self, user_id):
        self.cursor.execute("INSERT OR IGNORE INTO owner (user_id, is_owner) VALUES (?, 1)", (user_id,))
        self.conn.commit()

    def get_owner(self):
        self.cursor.execute("SELECT user_id FROM owner WHERE is_owner = 1")
        res = self.cursor.fetchone()
        return res[0] if res else None

    def add_group(self, chat_id, name):
        self.cursor.execute("INSERT OR IGNORE INTO groups (chat_id, group_name) VALUES (?, ?)", (chat_id, name))
        self.conn.commit()

    def get_group_settings(self, chat_id):
        self.cursor.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        return self.cursor.fetchone()

db = Database()

# --- توابع امنیتی ---
async def is_real_owner(update: Update):
    owner_id = db.get_owner()
    return update.effective_user.id == owner_id

# --- دستورات اصلی ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # تشخیص مالکیت مطلق
    if db.get_owner() is None:
        db.set_owner(user_id)
        msg = f"👑 **شما مالک اصلی ربات شدید!**\n\n🛠 ساخته شده توسط: {CREATOR_NAME}\n\nاز این لحظه تمام پنل‌های مدیریت در اختیار شماست."
    else:
        # ثبت کاربر عادی
        db.cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        db.conn.commit()
        msg = f"سلام {update.effective_user.first_name} عزیز! به ربات مدیریت و بازی خوش آمدی. 🚀"

    await update.message.reply_text(msg, parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پنل مدیریت اصلی که فقط برای مالک باز می‌شود"""
    if not await is_real_owner(update):
        await update.message.reply_text("❌ دسترسی غیرمجاز! این پنل فقط برای مالک اصلی است.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 آمار کل ربات", callback_data='admin_stats'), InlineKeyboardButton("👥 کاربران", callback_data='admin_users')],
        [InlineKeyboardButton("🛡 تنظیمات گروه‌ها", callback_data='admin_groups'), InlineKeyboardButton("💰 مدیریت سکه", callback_data='admin_coins')],
        [InlineKeyboardButton("📢 پیام همگانی", callback_data='admin_broadcast'), InlineKeyboardButton("🎁 کد هدیه", callback_data='admin_gift')],
        [InlineKeyboardButton("🛠 راهنما", callback_data='help_admin')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"👑 **پنل مدیریت فوق حرفه‌ای**\n👤 مالک: {CREATOR_NAME}\n\nلطفاً یک گزینه را انتخاب کنید:", reply_markup=reply_markup, parse_mode='Markdown')

async def group_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور برای گرفتن آمار گروه"""
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("❌ این دستور فقط در گروه‌ها کار می‌کند.")
        return
    
    db.add_group(chat.id, chat.title)
    settings = db.get_group_settings(chat.id)
    
    text = (f"📊 **آمار گروه:**\n\n"
            f"📝 نام: {chat.title}\n"
            f"🆔 شناسه: `{chat.id}`\n"
            f"🛡 وضعیت قفل‌ها: {'فعال' if settings[1] else 'غیرفعال'}")
    await update.message.reply_text(text, parse_mode='Markdown')

# --- مدیریت محتوا (قفل‌ها) ---

async def security_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # اگر در گروه نبودیم یا کاربر ادمین بود، کاری نکن
    if update.effective_chat.type == "private": return
    
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status in ['administrator', 'creator']: return

    # بررسی تنظیمات گروه از دیتابیس
    settings = db.get_group_settings(chat_id)
    if not settings: return

    # فرض: settings[1]=lock_link, settings[2]=lock_media...
    
    # ۱. قفل لینک
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type in ["url", "text_link"]:
                if settings[1] == 1:
                    await update.message.delete()
                    await context.bot.send_message(chat_id, f"🚫 {update.effective_user.first_name}، ارسال لینک ممنوع است!")
                    return

    # ۲. قفل مدیا (عکس، ویدیو، فایل و ...)
    if settings[2] == 1: # قفل کلی مدیا
        if update.message.photo or update.message.video or update.message.document or update.message.sticker:
            await update.message.delete()
            await context.bot.send_message(chat_id, f"🚫 {update.effective_user.first_name}، ارسال فایل/عکس ممنوع است!")
            return

# --- مدیریت دکمه‌ها (Callback) ---

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'admin_stats':
        # اینجا کد گرفتن آمار از دیتابیس قرار می‌گیرد
        await query.edit_message_text("📈 آمار در حال بارگذاری... (بخش در حال توسعه)")
    
    elif query.data == 'back_to_admin':
        # بازگشت به منوی اصلی
        pass # مشابه کد پنل اصلی

# --- اجرای ربات ---

def main():
    app = Application.builder().token(TOKEN).build()

    # هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("آمار_گروه", group_info))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    
    # فیلتر امنیتی (بسیار مهم)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, security_filter))

    print("🚀 سیستم حرفه‌ای فعال شد...")
    app.run_polling()

if __name__ == '__main__':
    main()
