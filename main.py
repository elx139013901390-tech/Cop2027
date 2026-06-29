import logging
import sqlite3
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- تنظیمات اولیه ---
# در Railway بهتر است توکن را در قسمت Variables وارد کنی
TOKEN = "YOUR_BOT_TOKEN_HERE" 
CREATOR_NAME = "امیرعلی فروزان اصل"

# تنظیمات لاگ برای رفع خطا
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- بخش دیتابیس ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    # جدول مالک اصلی
    cursor.execute('''CREATE TABLE IF NOT EXISTS owner (user_id INTEGER PRIMARY KEY, is_owner INTEGER)''')
    # جدول کاربران (برای سکه و امتیاز)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 0, exp INTEGER DEFAULT 0)''')
    # جدول گروه‌ها و تنظیمات
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (chat_id INTEGER PRIMARY KEY, group_name TEXT, lock_gif INTEGER DEFAULT 0, lock_sticker INTEGER DEFAULT 0, lock_photo INTEGER DEFAULT 0, lock_video INTEGER DEFAULT 0, lock_file INTEGER DEFAULT 0, lock_link INTEGER DEFAULT 0, filter_words TEXT DEFAULT '')''')
    conn.commit()
    conn.close()

def get_owner():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM owner WHERE is_owner = 1")
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else None

# --- توابع کمکی ---
async def is_owner(update: Update):
    owner_id = get_owner()
    return update.effective_user.id == owner_id

# --- دستورات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    # تشخیص اولین استارت‌کننده به عنوان مالک
    cursor.execute("SELECT is_owner FROM owner WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO owner (user_id, is_owner) VALUES (?, 1)", (user_id,))
        await update.message.reply_text(f"🎉 تبریک! شما به عنوان مالک اصلی ربات ثبت شدید.\n\n🛠 مدیریت ربات توسط: {CREATOR_NAME}")
    else:
        # ثبت کاربر معمولی
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await update.message.reply_text(f"سلام {update.effective_user.first_name} عزیز! به ربات مدیریت و بازی خوش آمدی.")
    
    conn.commit()
    conn.close()

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_owner(update):
        await update.message.reply_text("❌ متأسفم، فقط مالک اصلی به این پنل دسترسی دارد.")
        return

    keyboard = [
        [InlineKeyboardButton("📊 آمار کل ربات", callback_data='stats_all'), InlineKeyboardButton("👥 مدیریت کاربران", callback_data='manage_users')],
        [InlineKeyboardButton("🛡 تنظیمات گروه‌ها", callback_data='group_settings'), InlineKeyboardButton("💰 مدیریت سکه", callback_data='coin_mgmt')],
        [InlineKeyboardButton("📜 کد هدیه", callback_data='gift_code'), InlineKeyboardButton("📢 پیام همگانی", callback_data='broadcast')],
        [InlineKeyboardButton("🛠 راهنما", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"👑 پنل مدیریت اصلی\nسازنده: {CREATOR_NAME}\n\nلطفاً یک گزینه را انتخاب کنید:", reply_markup=reply_markup)

async def group_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور برای گرفتن آمار گروه خاص"""
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("این دستور فقط در گروه‌ها کار می‌کند.")
        return
    
    # در اینجا می‌توانیم اطلاعات تنظیمات گروه را از دیتابیس بخوانیم
    await update.message.reply_text(f"📊 آمار گروه: {chat.title}\n🆔 شناسه: `{chat.id}`\n✅ وضعیت: فعال")

async def stats_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """آمار کل ربات (فقط برای مالک)"""
    if not await is_owner(update): return
    
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM groups")
    group_count = cursor.fetchone()[0]
    conn.close()
    
    await update.callback_query.message.edit_text(
        f"📈 آمار کلی ربات:\n\n👥 کاربران: {user_count}\n🏘 گروه‌ها: {group_count}\n🛠 سازنده: {CREATOR_NAME}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_admin')]])
    )

# --- هندلر پیام‌ها (قفل‌ها) ---

async def content_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # اگر کاربر ادمین بود، کاری انجام نشود
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status in ['administrator', 'creator']:
        return

    # چک کردن تنظیمات قفل در دیتابیس (در اینجا برای نمونه فقط لینک و عکس را مثال می‌زنیم)
    # در نسخه کامل، باید از جدول groups چک شود
    
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "url":
                await update.message.delete()
                await context.bot.send_message(chat_id, "🚫 ارسال لینک ممنوع است!")
                return

    if update.message.photo:
        # فرض بر اینکه قفل عکس فعال است
        await update.message.delete()
        await context.bot.send_message(chat_id, "🚫 ارسال عکس ممنوع است!")

# --- مدیریت دکمه‌ها ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_admin':
        # بازگشت به منوی اصلی ادمین
        keyboard = [
            [InlineKeyboardButton("📊 آمار کل ربات", callback_data='stats_all'), InlineKeyboardButton("👥 مدیریت کاربران", callback_data='manage_users')],
            [InlineKeyboardButton("🛡 تنظیمات گروه‌ها", callback_data='group_settings'), InlineKeyboardButton("💰 مدیریت سکه", callback_data='coin_mgmt')],
            [InlineKeyboardButton("🛠 راهنما", callback_data='help')]
        ]
        await query.edit_message_text("👑 پنل مدیریت اصلی:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data == 'stats_all':
        await stats_all(update, context)

# --- اجرای اصلی ---
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    # هندلرها
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("آمار_گروه", group_stats))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # هندلر مدیریت محتوا (لینک، عکس و غیره)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, content_handler))

    print("🚀 ربات با موفقیت روشن شد...")
    app.run_polling()

if __name__ == '__main__':
    main()
