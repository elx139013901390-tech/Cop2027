import os, logging, asyncio, aiosqlite, random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- تنظیمات اولیه ---
TOKEN = os.getenv("TOKEN")
CREATOR_NAME = "امیرعلی فروزان اصل"

# --- تنظیمات دیتابیس ---
async def init_db():
    async with aiosqlite.connect("bot_data.db") as db:
        # جدول کاربران (سکه، امتیاز، دعوت)
        await db.execute('''CREATE TABLE IF NOT EXISTS users 
            (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 100, 
             exp INTEGER DEFAULT 0, last_daily TEXT, invited_by INTEGER)''')
        # جدول گروه‌ها (تنظیمات قفل‌ها)
        await db.execute('''CREATE TABLE IF NOT EXISTS groups 
            (chat_id INTEGER PRIMARY KEY, admin_ids TEXT, 
             lock_links INTEGER DEFAULT 0, lock_media INTEGER DEFAULT 0, 
             welcome_msg TEXT, goodbye_msg TEXT)''')
        # جدول کد هدیه
        await db.execute('''CREATE TABLE IF NOT EXISTS gift_codes 
            (code TEXT PRIMARY KEY, amount INTEGER, uses INTEGER)''')
        # جدول مالک اصلی
        await db.execute('''CREATE TABLE IF NOT EXISTS owner (user_id INTEGER PRIMARY KEY)''')
        await db.commit()

# --- تشخیص مالک اصلی ---
async def get_owner(db):
    async with db.execute("SELECT user_id FROM owner") as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None

# --- سیستم مدیریت مالک (اولین استارت) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with aiosqlite.connect("bot_data.db") as db:
        owner_id = await get_owner(db)
        
        if owner_id is None:
            await db.execute("INSERT INTO owner (user_id) VALUES (?)", (user_id,))
            await db.commit()
            msg = f"🎉 خوش آمدید! شما به عنوان مالک اصلی سیستم ثبت شدید.\nسازنده: {CREATOR_NAME}"
        else:
            # ثبت کاربر در سیستم سکه
            await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            msg = "👋 به ربات خوش آمدید! از دستورات استفاده کنید."

        await update.message.reply_text(msg)

# --- پنل مدیریت اصلی (فقط برای مالک) ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with aiosqlite.connect("bot_data.db") as db:
        owner_id = await get_owner(db)
        if user_id != owner_id:
            return await update.message.reply_text("❌ شما دسترسی به پنل مدیریت کل ندارید.")

        keyboard = [
            [InlineKeyboardButton("💰 مدیریت سکه و کاربران", callback_data="adm_economy"),
             InlineKeyboardButton("🛡 مدیریت گروه‌ها", callback_data="adm_groups")],
            [InlineKeyboardButton("🎁 ساخت کد هدیه", callback_data="adm_gift"),
             InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast")],
            [InlineKeyboardButton("📊 آمار کلی سیستم", callback_data="adm_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"👑 پنل مدیریت کل\nسازنده: {CREATOR_NAME}\n\nیک گزینه را انتخاب کنید:", reply_markup=reply_markup)

# --- بخش بازی و سکه (برای همه) ---
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now().strftime("%Y-%m-%d")
    
    async with aiosqlite.connect("bot_data.db") as db:
        async with db.execute("SELECT coins, last_daily FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            
        if row:
            coins, last_daily = row
            if last_daily == now:
                return await update.message.reply_text("⚠️ شما امروز جایزه خود را دریافت کرده‌اید!")
            
            new_coins = coins + 50 # جایزه روزانه 50 سکه
            await db.execute("UPDATE users SET coins = ?, last_daily = ? WHERE user_id = ?", (new_coins, now, user_id))
            await db.commit()
            await update.message.reply_text(f"🎁 جایزه روزانه دریافت شد!\n💰 سکه جدید: {new_coins}")
        else:
            await db.execute("INSERT INTO users (user_id, coins, last_daily) VALUES (?, ?, ?)", (user_id, 50, now))
            await db.commit()
            await update.message.reply_text("🎉 برای اولین بار جایزه دریافت کردید: 50 سکه")

# --- بخش مدیریت گروه (آنتی اسپم و غیره) ---
async def group_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # اینجا منطق حذف لینک، فیلتر کلمات و غیره قرار می‌گیرد
    pass

# --- اجرای ربات ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    # اجرای دیتابیس قبل از استارت
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("daily", daily))
    
    # هندلر برای دکمه‌های اینلاین
    app.add_handler(CallbackQueryHandler(lambda u, c: None)) # placeholder

    print("Bot is running...")
    app.run_polling()
