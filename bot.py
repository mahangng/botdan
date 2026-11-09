hereimport asyncio
import sqlite3
import re
from datetime import datetime
from fast_rub import Client, filters
from fast_rub.types import Update, UpdateButton

# ==========================================
# ⚙️ تنظیمات (اینجا را پر کنید)
# ==========================================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_ID = "YOUR_RUBIKA_USER_ID"   # آیدی عددی خودتان در روبیکا
DB_FILE = "linkdoni.db"

# ==========================================
# 🗄️ مدیریت دیتابیس (SQLite داخلی)
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def add_link(user_id: str, url: str, title: str = None):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO links (user_id, url, title) VALUES (?, ?, ?)",
            (user_id, url, title)
        )
        conn.commit()
        return cur.lastrowid

def get_pending_links():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM links WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]

def update_link_status(link_id: int, status: str):
    with get_db() as conn:
        conn.execute("UPDATE links SET status = ? WHERE id = ?", (status, link_id))
        conn.commit()

def delete_link(link_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
        conn.commit()

def save_user(user_id: str, first_name: str = None, username: str = None):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
            (user_id, first_name, username)
        )
        conn.commit()

def get_stats():
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM links WHERE status='pending'").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM links WHERE status='approved'").fetchone()[0]
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {"total": total, "pending": pending, "approved": approved, "users": users}

# ==========================================
# 🤖 ربات
# ==========================================
bot = Client(BOT_TOKEN)

# ---------- اعتبارسنجی لینک ----------
URL_REGEX = re.compile(
    r'^(https?://)?'
    r'([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}'
    r'(:\d+)?(/[^\s]*)?$'
)

def is_valid_url(text: str) -> bool:
    return bool(URL_REGEX.match(text.strip()))

# ---------- ثبت‌نام کاربر ----------
async def ensure_user(msg: Update):
    save_user(
        user_id=str(msg.sender_id),
        first_name=getattr(msg, 'sender_name', None),
        username=getattr(msg, 'sender_username', None)
    )

# ---------- دریافت لینک از کاربر ----------
@bot.on_message(filters.text & ~filters.text.startswith('/'))
async def handle_link(msg: Update):
    # اگر ادمین است، پیام‌هایش را نادیده بگیر (تا دستورات ادمین تداخل نکنند)
    if str(msg.sender_id) == ADMIN_ID:
        return

    await ensure_user(msg)
    text = msg.text.strip()

    if not is_valid_url(text):
        await msg.reply("❌ لطفاً یک **لینک معتبر** ارسال کنید.\nمثال: `https://example.com`")
        return

    link_id = add_link(str(msg.sender_id), text)

    await msg.reply(
        "✅ لینک شما دریافت شد و در صف بررسی قرار گرفت.\n"
        "پس از تأیید ادمین، در کانال منتشر می‌شود.\n"
        f"🆔 شناسه پیگیری: `{link_id}`"
    )

    # اطلاع‌رسانی به ادمین
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔔 **لینک جدید**\n"
            f"👤 کاربر: `{msg.sender_id}`\n"
            f"🔗 لینک: {text}\n"
            f"🆔 شناسه: `{link_id}`"
        )
    except Exception:
        pass  # اگر ادمین ربات را استارت نکرده باشد

# ---------- دستور /start ----------
@bot.on_message(filters.text("/start"))
async def start_cmd(msg: Update):
    await ensure_user(msg)
    await msg.reply(
        "👋 سلام!\n"
        "من ربات **لینکدونی** هستم.\n"
        "کافی است لینک خود را ارسال کنید تا پس از تأیید ادمین ثبت شود."
    )

# ---------- دستورات مدیریتی ----------
@bot.on_message(filters.text("/stats") & filters.user(ADMIN_ID))
async def admin_stats(msg: Update):
    s = get_stats()
    await msg.reply(
        f"📊 **آمار ربات**\n"
        f"👥 کاربران: `{s['users']}`\n"
        f"🔗 کل لینک‌ها: `{s['total']}`\n"
        f"⏳ در انتظار: `{s['pending']}`\n"
        f"✅ تأییدشده: `{s['approved']}`"
    )

@bot.on_message(filters.text("/pending") & filters.user(ADMIN_ID))
async def admin_pending(msg: Update):
    pending = get_pending_links()
    if not pending:
        await msg.reply("✅ هیچ لینک در انتظاری وجود ندارد.")
        return

    await msg.reply(f"⏳ **{len(pending)} لینک در انتظار:**")
    for link in pending[:5]:  # فقط ۵ مورد اول برای جلوگیری از اسپم
        text = (
            f"🆔 `{link['id']}`\n"
            f"👤 کاربر: `{link['user_id']}`\n"
            f"🔗 {link['url']}\n"
            f"📅 {link['created_at']}"
        )
        await bot.send_message(ADMIN_ID, text)

# ---------- تأیید/رد با دستور ----------
@bot.on_message(filters.text.startswith("/approve_") & filters.user(ADMIN_ID))
async def approve_link(msg: Update):
    try:
        link_id = int(msg.text.replace("/approve_", "").strip())
        update_link_status(link_id, "approved")
        await msg.reply(f"✅ لینک `{link_id}` تأیید شد.")
    except (ValueError, Exception) as e:
        await msg.reply(f"❌ خطا: `{e}`")

@bot.on_message(filters.text.startswith("/reject_") & filters.user(ADMIN_ID))
async def reject_link(msg: Update):
    try:
        link_id = int(msg.text.replace("/reject_", "").strip())
        update_link_status(link_id, "rejected")
        await msg.reply(f"❌ لینک `{link_id}` رد شد.")
    except (ValueError, Exception) as e:
        await msg.reply(f"❌ خطا: `{e}`")

# ---------- مدیریت دکمه‌های شیشه‌ای (تأیید/رد سریع) ----------
@bot.on_button()
async def handle_button(btn: UpdateButton):
    # فقط ادمین می‌تواند از دکمه‌ها استفاده کند
    if str(btn.sender_id) != ADMIN_ID:
        await btn.answer("⛔ شما دسترسی ندارید.", show_alert=True)
        return

    button_id = btn.new_message.aux_data.button_id
    # فرمت button_id: "approve_123" یا "reject_123"
    if "_" not in button_id:
        return

    action, raw_id = button_id.split("_", 1)
    try:
        link_id = int(raw_id)
    except ValueError:
        return

    if action == "approve":
        update_link_status(link_id, "approved")
        await btn.answer(f"✅ لینک {link_id} تأیید شد.")
    elif action == "reject":
        update_link_status(link_id, "rejected")
        await btn.answer(f"❌ لینک {link_id} رد شد.")
    else:
        await btn.answer("⚠️ دستور نامعتبر.")

# ==========================================
# 🚀 اجرا
# ==========================================
async def main():
    init_db()
    print("✅ ربات لینکدونی آماده است...")
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
