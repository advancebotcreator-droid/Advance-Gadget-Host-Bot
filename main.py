import asyncio
import os
import sys
import logging
import subprocess
import psutil
import sqlite3
import hashlib
import json
import zipfile
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp
from pathlib import Path

# --- নিচের এই অংশে আপনার আসল তথ্যগুলো বসান ---
TOKEN = "8472500254:AAFSn8YuApuuu2JOdnZvQhAgGhza62uYJgw" 
OWNER_ID = 6074463370 # আপনার টেলিগ্রাম আইডি (সংখ্যায়)
ADMIN_ID = 6074463370 # আপনার টেলিগ্রাম আইডি (সংখ্যায়)
YOUR_USERNAME = "@shuvohassan00"
UPDATE_CHANNEL = "https://t.me/GADGET_BOX_OFFICIAL"
# -------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# আইডিগুলো স্ট্রিং হিসেবে আসলেও ইনটিজারে কনভার্ট করে নেবে
OWNER_ID = int(OWNER_ID)
ADMIN_ID = int(ADMIN_ID)

# বাকি কোড আপনার আগের মতোই থাকবে...
BASE_DIR = Path(__file__).parent.absolute()
UPLOAD_BOTS_DIR = BASE_DIR / 'upload_bots'
IROTECH_DIR = BASE_DIR / 'inf'
DATABASE_PATH = IROTECH_DIR / 'bot_data.db'

# (আপনার বাকি ২০০০+ লাইনের কোড এর নিচে থাকবে)

FREE_USER_LIMIT = 20
SUBSCRIBED_USER_LIMIT = 50
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

UPLOAD_BOTS_DIR.mkdir(exist_ok=True)
IROTECH_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

bot_scripts = {}
user_subscriptions = {}
user_files = {}
user_favorites = {}
banned_users = set()
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
bot_stats = {'total_uploads': 0, 'total_downloads': 0, 'total_runs': 0}

def migrate_db():
    logger.info("Running database migrations...")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute("PRAGMA table_info(user_files)")
        columns = [row[1] for row in c.fetchall()]
        if 'upload_date' not in columns:
            logger.info("Adding upload_date column to user_files table...")
            c.execute('ALTER TABLE user_files ADD COLUMN upload_date TEXT')
            logger.info("upload_date column added successfully.")
        
        c.execute("PRAGMA table_info(active_users)")
        columns = [row[1] for row in c.fetchall()]
        if 'join_date' not in columns:
            logger.info("Adding join_date column to active_users table...")
            c.execute('ALTER TABLE active_users ADD COLUMN join_date TEXT')
            logger.info("join_date column added successfully.")
        if 'last_active' not in columns:
            logger.info("Adding last_active column to active_users table...")
            c.execute('ALTER TABLE active_users ADD COLUMN last_active TEXT')
            logger.info("last_active column added successfully.")
        
        conn.commit()
        conn.close()
        logger.info("Database migrations completed successfully.")
    except Exception as e:
        logger.error(f"Database migration error: {e}", exc_info=True)

def init_db():
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT, upload_date TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_active TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, banned_date TEXT, reason TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS favorites
                     (user_id INTEGER, file_name TEXT, PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS bot_stats
                     (stat_name TEXT PRIMARY KEY, stat_value INTEGER)''')
        
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        
        for stat in ['total_uploads', 'total_downloads', 'total_runs']:
            c.execute('INSERT OR IGNORE INTO bot_stats (stat_name, stat_value) VALUES (?, 0)', (stat,))
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)

def load_data():
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"Invalid expiry date for user {user_id}")
        
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
        
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        
        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(user_id for (user_id,) in c.fetchall())
        
        c.execute('SELECT user_id, file_name FROM favorites')
        for user_id, file_name in c.fetchall():
            if user_id not in user_favorites:
                user_favorites[user_id] = []
            user_favorites[user_id].append(file_name)
        
        c.execute('SELECT stat_name, stat_value FROM bot_stats')
        for stat_name, stat_value in c.fetchall():
            bot_stats[stat_name] = stat_value
        
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(banned_users)} banned, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"Error loading data: {e}", exc_info=True)

init_db()
migrate_db()
load_data()

def get_user_file_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_main_keyboard(user_id):
    if user_id in admin_ids:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Updates", url=UPDATE_CHANNEL)],
            [InlineKeyboardButton(text="📤 Upload File", callback_data="upload_file"),
             InlineKeyboardButton(text="📁 My Files", callback_data="check_files")],
            [InlineKeyboardButton(text="🤖 My Bots", callback_data="bot_control"),
             InlineKeyboardButton(text="⭐ Favorites", callback_data="my_favorites")],
            [InlineKeyboardButton(text="🔍 Search Files", callback_data="search_files"),
             InlineKeyboardButton(text="⚡ Bot Speed", callback_data="bot_speed")],
            [InlineKeyboardButton(text="📊 My Stats", callback_data="statistics"),
             InlineKeyboardButton(text="ℹ️ Help & Info", callback_data="help_info")],
            [InlineKeyboardButton(text="🎯 Features", callback_data="all_features"),
             InlineKeyboardButton(text="👨‍💼 Admin Panel", callback_data="admin_panel")],
            [InlineKeyboardButton(text="💬 Contact", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Updates Channel", url=UPDATE_CHANNEL)],
            [InlineKeyboardButton(text="📤 Upload File", callback_data="upload_file"),
             InlineKeyboardButton(text="📁 My Files", callback_data="check_files")],
            [InlineKeyboardButton(text="🤖 My Bots", callback_data="bot_control"),
             InlineKeyboardButton(text="⭐ Favorites", callback_data="my_favorites")],
            [InlineKeyboardButton(text="🔍 Search Files", callback_data="search_files"),
             InlineKeyboardButton(text="⚡ Bot Speed", callback_data="bot_speed")],
            [InlineKeyboardButton(text="📊 My Stats", callback_data="statistics"),
             InlineKeyboardButton(text="💎 Get Premium", callback_data="get_premium")],
            [InlineKeyboardButton(text="ℹ️ Help", callback_data="help_info"),
             InlineKeyboardButton(text="🎯 Features", callback_data="all_features")],
            [InlineKeyboardButton(text="💬 Contact Owner", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")]
        ])
    return keyboard

def get_admin_panel_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 User Stats", callback_data="admin_total_users"),
         InlineKeyboardButton(text="📁 Files Stats", callback_data="admin_total_files")],
        [InlineKeyboardButton(text="🚀 Running Scripts", callback_data="admin_running_scripts"),
         InlineKeyboardButton(text="💎 Premium Users", callback_data="admin_premium_users")],
        [InlineKeyboardButton(text="➕ Add Admin", callback_data="admin_add_admin"),
         InlineKeyboardButton(text="➖ Remove Admin", callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="➕ Add Premium", callback_data="admin_add_premium"),
         InlineKeyboardButton(text="➖ Remove Premium", callback_data="admin_remove_premium")],
        [InlineKeyboardButton(text="🚫 Ban User", callback_data="admin_ban_user"),
         InlineKeyboardButton(text="✅ Unban User", callback_data="admin_unban_user")],
        [InlineKeyboardButton(text="📊 Bot Analytics", callback_data="admin_analytics"),
         InlineKeyboardButton(text="⚙️ System Info", callback_data="admin_system_status")],
        [InlineKeyboardButton(text="🔒 Lock/Unlock", callback_data="lock_bot"),
         InlineKeyboardButton(text="📢 Broadcast", callback_data="broadcast")],
        [InlineKeyboardButton(text="🗑️ Clean Files", callback_data="admin_clean_files"),
         InlineKeyboardButton(text="💾 Backup DB", callback_data="admin_backup_db")],
        [InlineKeyboardButton(text="📝 View Logs", callback_data="admin_view_logs"),
         InlineKeyboardButton(text="🔄 Restart Bot", callback_data="admin_restart_bot")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    return keyboard

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in banned_users:
        await message.answer("🚫 <b>You are banned from using this bot!</b>\n\nContact admin for more info.", parse_mode="HTML")
        return
    
    active_users.add(user_id)
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute('INSERT OR REPLACE INTO active_users (user_id, join_date, last_active) VALUES (?, ?, ?)', 
                  (user_id, now, now))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving active user: {e}")
    
    welcome_text = f"""
╔═══════════════════════╗
    🌟 <b>WELCOME TO ADVANCED BOT HOSTING</b> 🌟
╚═══════════════════════╝

👋 <b>Hi,</b> {message.from_user.full_name}!

🆔 <b>Your ID:</b> <code>{user_id}</code>
📦 <b>Upload Limit:</b> {get_user_file_limit(user_id)} files
💎 <b>Account:</b> {'Premium ✨' if user_id in user_subscriptions else 'Free 🆓'}

━━━━━━━━━━━━━━━━━━━━
<b>🎯 FREE USER FEATURES:</b>

📤 <b>Upload Files</b> - Upload Python, JS, ZIP files
📁 <b>Manage Files</b> - View, delete, organize
🤖 <b>Bot Control Panel</b> - Start, stop, restart bots
📊 <b>Bot Status</b> - Monitor bot performance
📝 <b>View/Edit Logs</b> - Debug your bots
📦 <b>Export Bots</b> - Download bot with all files
⭐ <b>Add Favorites</b> - Quick access to files
🔍 <b>Search Files</b> - Find files easily
▶️ <b>Run Scripts</b> - Execute Python/JS code
🛑 <b>Stop Scripts</b> - Control running code
📊 <b>View Stats</b> - Your usage statistics
⚡ <b>Speed Test</b> - Check bot response
📥 <b>Download Files</b> - Get your files
💾 <b>File Info</b> - Size, type, date details
ℹ️ <b>Help & Support</b> - Get assistance
🎯 <b>Feature List</b> - Explore all features

━━━━━━━━━━━━━━━━━━━━
<b>✨ Start exploring now! ✨</b>
"""
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    welcome_text = f"""
╔═══════════════════════╗
    🏠 <b>MAIN MENU</b> 🏠
╚═══════════════════════╝

👤 <b>User:</b> {callback.from_user.full_name}
🆔 <b>ID:</b> <code>{user_id}</code>
📦 <b>Files:</b> {len(user_files.get(user_id, []))}/{get_user_file_limit(user_id)}

Use buttons below to navigate 👇
"""
    await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "upload_file")
async def callback_upload_file(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if bot_locked and user_id not in admin_ids:
        await callback.answer("🔒 Bot is locked for maintenance!", show_alert=True)
        return
    
    current_files = len(user_files.get(user_id, []))
    limit = get_user_file_limit(user_id)
    
    upload_text = f"""
╔═══════════════════════╗
    📤 <b>UPLOAD FILES</b> 📤
╚═══════════════════════╝

📊 <b>Current Usage:</b> {current_files}/{limit} files

📝 <b>Supported Formats:</b>
🐍 Python (.py)
🟨 JavaScript (.js)
📦 ZIP Archives (.zip)

━━━━━━━━━━━━━━━━━━━━
<b>💡 How to Upload:</b>

1️⃣ Send your file to the bot
2️⃣ Wait for upload confirmation
3️⃣ File will be saved automatically

⚡ <b>Upload limit:</b> {limit} files
🔥 <b>Quick & Easy!</b>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(upload_text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "check_files")
async def callback_check_files(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    files = user_files.get(user_id, [])
    
    if not files:
        text = """
╔═══════════════════════╗
    📁 <b>MY FILES</b> 📁
╚═══════════════════════╝

📭 <b>No files found!</b>

Upload your first file to get started! 🚀
"""
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Upload File", callback_data="upload_file")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
    else:
        text = f"""
╔═══════════════════════╗
    📁 <b>MY FILES ({len(files)})</b> 📁
╚═══════════════════════╝

"""
        buttons = []
        for i, (file_name, file_type) in enumerate(files, 1):
            icon = "🐍" if file_type == "py" else "🟨" if file_type == "js" else "📦"
            text += f"{i}. {icon} <code>{file_name}</code>\n"
            
            is_favorite = file_name in user_favorites.get(user_id, [])
            star = "⭐" if is_favorite else "☆"
            
            buttons.append([
                InlineKeyboardButton(text=f"▶️ Run {file_name[:15]}", callback_data=f"run_script:{file_name}"),
                InlineKeyboardButton(text=f"🤖 Control {file_name[:10]}", callback_data=f"bot_control:{file_name}"),
                InlineKeyboardButton(text=f"{star}", callback_data=f"toggle_fav:{file_name}")
            ])
            buttons.append([
                InlineKeyboardButton(text=f"📝 Edit {file_name[:15]}", callback_data=f"edit_file:{file_name}"),
                InlineKeyboardButton(text=f"ℹ️ Info {file_name[:15]}", callback_data=f"file_info:{file_name}"),
                InlineKeyboardButton(text=f"🗑️ Delete", callback_data=f"delete_file:{file_name}")
            ])
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "my_favorites")
async def callback_my_favorites(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    favorites = user_favorites.get(user_id, [])
    
    if not favorites:
        text = """
╔═══════════════════════╗
    ⭐ <b>FAVORITES</b> ⭐
╚═══════════════════════╝

💭 No favorite files yet!

Add files to favorites for quick access! 🚀
"""
        buttons = [[InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]]
    else:
        text = f"""
╔═══════════════════════╗
    ⭐ <b>FAVORITES ({len(favorites)})</b> ⭐
╚═══════════════════════╝

"""
        buttons = []
        for i, file_name in enumerate(favorites, 1):
            text += f"{i}. ⭐ <code>{file_name}</code>\n"
            buttons.append([
                InlineKeyboardButton(text=f"▶️ {file_name[:20]}", callback_data=f"run_script:{file_name}"),
                InlineKeyboardButton(text=f"❌", callback_data=f"toggle_fav:{file_name}")
            ])
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "search_files")
async def callback_search_files(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    files = user_files.get(user_id, [])
    
    text = f"""
╔═══════════════════════╗
    🔍 <b>SEARCH FILES</b> 🔍
╚═══════════════════════╝

📊 <b>Total Files:</b> {len(files)}

<b>File Types:</b>
🐍 Python: {sum(1 for f in files if f[1] == 'py')}
🟨 JavaScript: {sum(1 for f in files if f[1] == 'js')}
📦 ZIP: {sum(1 for f in files if f[1] == 'zip')}

━━━━━━━━━━━━━━━━━━━━
To search, use:
<code>/search filename</code>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 View All Files", callback_data="check_files")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "bot_speed")
async def callback_bot_speed(callback: types.CallbackQuery):
    start_time = datetime.now()
    await callback.answer("⚡ Testing...")
    end_time = datetime.now()
    speed = (end_time - start_time).total_seconds() * 1000
    
    if speed < 100:
        status = "🟢 Excellent"
        emoji = "🚀"
    elif speed < 300:
        status = "🟡 Good"
        emoji = "⚡"
    else:
        status = "🔴 Slow"
        emoji = "🐌"
    
    text = f"""
╔═══════════════════════╗
    ⚡ <b>SPEED TEST</b> ⚡
╚═══════════════════════╝

{emoji} <b>Response Time:</b> {speed:.2f}ms
📊 <b>Status:</b> {status}

🖥️ <b>Server Info:</b>
• CPU: {psutil.cpu_percent()}%
• Memory: {psutil.virtual_memory().percent}%
• Uptime: Online ✅

✨ Bot is running smoothly!
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Test Again", callback_data="bot_speed"),
         InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "statistics")
async def callback_statistics(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    user_file_count = len(user_files.get(user_id, []))
    user_fav_count = len(user_favorites.get(user_id, []))
    limit = get_user_file_limit(user_id)
    is_premium = user_id in user_subscriptions
    
    text = f"""
╔═══════════════════════╗
    📊 <b>YOUR STATISTICS</b> 📊
╚═══════════════════════╝

👤 <b>User:</b> {callback.from_user.full_name}
🆔 <b>ID:</b> <code>{user_id}</code>

━━━━━━━━━━━━━━━━━━━━
📦 <b>FILE STATISTICS:</b>

📁 Total Files: {user_file_count}/{limit}
⭐ Favorites: {user_fav_count}
💎 Account: {'Premium ✨' if is_premium else 'Free 🆓'}
🚀 Running: {sum(1 for k in bot_scripts if k.startswith(f"{user_id}_"))}

━━━━━━━━━━━━━━━━━━━━
📈 <b>USAGE:</b>

📤 Uploads: {bot_stats.get('total_uploads', 0)}
📥 Downloads: {bot_stats.get('total_downloads', 0)}
▶️ Script Runs: {bot_stats.get('total_runs', 0)}

{'✅ Bot Status: Active' if not bot_locked else '🔒 Bot: Maintenance'}
"""
    
    if user_id in admin_ids:
        text += f"\n━━━━━━━━━━━━━━━━━━━━\n👑 <b>ADMIN STATS:</b>\n"
        text += f"👥 Total Users: {len(active_users)}\n"
        text += f"📁 Total Files: {sum(len(files) for files in user_files.values())}\n"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "help_info")
async def callback_help_info(callback: types.CallbackQuery):
    text = """
╔═══════════════════════╗
    ℹ️ <b>HELP & INFO</b> ℹ️
╚═══════════════════════╝

<b>🎯 HOW TO USE:</b>

1️⃣ <b>Upload Files:</b>
   • Click 'Upload File'
   • Send your .py, .js, or .zip file
   • File will be saved automatically

2️⃣ <b>Run Scripts:</b>
   • Go to 'My Files'
   • Click 'Run' on any file
   • Monitor script execution

3️⃣ <b>Manage Files:</b>
   • View all files in 'My Files'
   • Add to favorites with ⭐
   • Delete unwanted files

4️⃣ <b>Search:</b>
   • Use /search [filename]
   • Quick file lookup

5️⃣ <b>Bot Control:</b>
   • Use 'My Bots' to control your hosted scripts
   • Start, stop, restart your bots
   • View logs and status

━━━━━━━━━━━━━━━━━━━━
<b>💡 COMMANDS:</b>

/start - Start the bot
/help - Show this help
/search - Search files
/stats - Your statistics
/premium - Premium info

<b>Need help? Contact owner! 💬</b>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Features", callback_data="all_features")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "all_features")
async def callback_all_features(callback: types.CallbackQuery):
    text = """
╔═══════════════════════╗
    🎯 <b>ALL FEATURES</b> 🎯
╚═══════════════════════╝

<b>✨ FREE USER FEATURES (15+):</b>

1. 📤 Upload Files (Python, JS, ZIP)
2. 📁 View & Manage Files
3. 🤖 Bot Control Panel
4. ▶️ Start/Restart/Stop Bots
5. 📊 View Bot Status
6. 📝 View/Edit Logs
7. 📦 Export Bots
8. ✏️ Edit Bot Files
9. ⭐ Add to Favorites
10. 🔍 Search Files by Name
11. ⚡ Bot Speed Test
12. 📊 View Your Statistics
13. 📥 Download Your Files
14. 💾 View File Information
15. ℹ️ Help & Support
16. 🎯 Feature Discovery

━━━━━━━━━━━━━━━━━━━━
<b>💎 PREMIUM FEATURES:</b>

• 50 file upload limit (vs 20)
• Priority support
• Advanced analytics
• Faster processing
• Premium badge
• Advanced bot monitoring
• Custom bot configurations
• Extended log history
• Bot performance analytics

━━━━━━━━━━━━━━━━━━━━
<b>🔥 Upgrade to Premium!</b>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Get Premium", callback_data="get_premium")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "get_premium")
async def callback_get_premium(callback: types.CallbackQuery):
    text = """
╔═══════════════════════╗
    💎 <b>PREMIUM PLAN</b> 💎
╚═══════════════════════╝

<b>✨ PREMIUM BENEFITS:</b>

📦 50 File Upload Limit
⚡ Priority Processing
🚀 Faster Response Time
📊 Advanced Analytics
💬 Priority Support
⭐ Premium Badge
🎯 Exclusive Features

━━━━━━━━━━━━━━━━━━━━
<b>💰 PRICING:</b>

1 Month: $5
3 Months: $12 (Save 20%)
1 Year: $40 (Save 33%)

━━━━━━━━━━━━━━━━━━━━
<b>Contact owner to upgrade! 💬</b>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Owner", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id not in admin_ids:
        await callback.answer("❌ Admin access required!", show_alert=True)
        return
    
    text = """
╔═══════════════════════╗
    👑 <b>ADMIN PANEL</b> 👑
╚═══════════════════════╝

<b>🎛️ CONTROL CENTER:</b>

Manage users, files, system settings
and monitor bot performance.

<b>📊 20+ Admin Features Available!</b>

Select an option below to continue...
"""
    
    await callback.message.edit_text(text, reply_markup=get_admin_panel_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_fav:"))
async def callback_toggle_favorite(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    if user_id not in user_favorites:
        user_favorites[user_id] = []
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        if file_name in user_favorites[user_id]:
            user_favorites[user_id].remove(file_name)
            c.execute('DELETE FROM favorites WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            await callback.answer("❌ Removed from favorites!", show_alert=True)
        else:
            user_favorites[user_id].append(file_name)
            c.execute('INSERT OR IGNORE INTO favorites (user_id, file_name) VALUES (?, ?)', (user_id, file_name))
            await callback.answer("⭐ Added to favorites!", show_alert=True)
        
        conn.commit()
        conn.close()
        
        await callback_check_files(callback)
        
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("file_info:"))
async def callback_file_info(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    file_path = user_folder / file_name
    
    if not file_path.exists():
        await callback.answer("❌ File not found!", show_alert=True)
        return
    
    file_size = file_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    file_ext = file_path.suffix
    modified_time = datetime.fromtimestamp(file_path.stat().st_mtime)
    
    is_favorite = file_name in user_favorites.get(user_id, [])
    
    text = f"""
╔═══════════════════════╗
    ℹ️ <b>FILE INFO</b> ℹ️
╚═══════════════════════╝

📄 <b>Name:</b> <code>{file_name}</code>

📦 <b>Type:</b> {file_ext.upper()} File
💾 <b>Size:</b> {file_size_mb:.2f} MB ({file_size} bytes)
📅 <b>Modified:</b> {modified_time.strftime('%Y-%m-%d %H:%M')}
⭐ <b>Favorite:</b> {'Yes ✨' if is_favorite else 'No'}

🔐 <b>MD5:</b> <code>{hashlib.md5(file_path.read_bytes()).hexdigest()[:16]}...</code>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Run", callback_data=f"run_script:{file_name}"),
         InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_file:{file_name}")],
        [InlineKeyboardButton(text="📁 My Files", callback_data="check_files"),
         InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in banned_users:
        await message.answer("🚫 You are banned from using this bot!")
        return
    
    if bot_locked and user_id not in admin_ids:
        await message.answer("🔒 Bot is currently locked!")
        return
    
    document = message.document
    file_name = document.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in ['.py', '.js', '.zip']:
        await message.answer("❌ Only .py, .js, and .zip files are supported!")
        return
    
    current_files = len(user_files.get(user_id, []))
    limit = get_user_file_limit(user_id)
    
    if current_files >= limit:
        await message.answer(f"❌ Upload limit reached! ({current_files}/{limit})\n\n💎 Upgrade to premium for more space!")
        return
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    user_folder.mkdir(exist_ok=True)
    
    file_path = user_folder / file_name
    
    try:
        file_size_kb = document.file_size / 1024
        
        status_msg = await message.answer(
            f"📤 <b>Preparing upload...</b>\n\n"
            f"📄 File: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"▓░░░░░░░░░ 0%",
            parse_mode="HTML"
        )
        
        await asyncio.sleep(0.3)
        await status_msg.edit_text(
            f"📥 <b>Downloading...</b>\n\n"
            f"📄 File: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"▓▓▓░░░░░░░ 30%",
            parse_mode="HTML"
        )
        
        await bot.download(document, destination=file_path)
        
        await status_msg.edit_text(
            f"💾 <b>Saving to database...</b>\n\n"
            f"📄 File: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"▓▓▓▓▓▓▓░░░ 70%",
            parse_mode="HTML"
        )
        
        if user_id not in user_files:
            user_files[user_id] = []
        
        user_files[user_id].append((file_name, file_ext[1:]))
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, upload_date) VALUES (?, ?, ?, ?)',
                  (user_id, file_name, file_ext[1:], now))
        c.execute('UPDATE bot_stats SET stat_value = stat_value + 1 WHERE stat_name = ?', ('total_uploads',))
        conn.commit()
        conn.close()
        
        bot_stats['total_uploads'] = bot_stats.get('total_uploads', 0) + 1
        
        await status_msg.edit_text(
            f"✅ <b>Finalizing...</b>\n\n"
            f"📄 File: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"▓▓▓▓▓▓▓▓▓▓ 100%",
            parse_mode="HTML"
        )
        
        await asyncio.sleep(0.5)
        
        if file_ext == '.zip':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Extract ZIP", callback_data=f"extract_zip:{file_name}"),
                 InlineKeyboardButton(text="⭐ Add Favorite", callback_data=f"toggle_fav:{file_name}")],
                [InlineKeyboardButton(text="ℹ️ File Info", callback_data=f"file_info:{file_name}"),
                 InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_file:{file_name}")],
                [InlineKeyboardButton(text="📁 My Files", callback_data="check_files"),
                 InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
            ])
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="▶️ Run Now", callback_data=f"run_script:{file_name}"),
                 InlineKeyboardButton(text="🔄 Restart", callback_data=f"restart_script:{file_name}"),
                 InlineKeyboardButton(text="🛑 Stop", callback_data=f"stop_script:{file_name}")],
                [InlineKeyboardButton(text="🤖 Control Panel", callback_data=f"bot_control:{file_name}"),
                 InlineKeyboardButton(text="⭐ Add Favorite", callback_data=f"toggle_fav:{file_name}")],
                [InlineKeyboardButton(text="ℹ️ File Info", callback_data=f"file_info:{file_name}"),
                 InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_file:{file_name}")],
                [InlineKeyboardButton(text="📁 My Files", callback_data="check_files"),
                 InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
            ])
        
        await status_msg.edit_text(
            f"""
╔═══════════════════════╗
    ✅ <b>UPLOAD SUCCESS!</b> ✅
╚═══════════════════════╝

📄 <b>File:</b> <code>{file_name}</code>
📦 <b>Type:</b> {file_ext[1:].upper()}
💾 <b>Size:</b> {document.file_size / 1024:.2f} KB
📊 <b>Usage:</b> {current_files + 1}/{limit}

🎉 File uploaded successfully!
""",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        await message.answer(f"❌ Upload failed: {str(e)}")

@dp.callback_query(F.data.startswith("run_script:"))
async def callback_run_script(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    file_path = user_folder / file_name
    
    if not file_path.exists():
        await callback.answer("❌ File not found!", show_alert=True)
        return
    
    script_key = f"{user_id}_{file_name}"
    
    if script_key in bot_scripts:
        await callback.answer("⚠️ Script is already running!", show_alert=True)
        return
    
    file_ext = file_path.suffix.lower()
    
    try:
        log_file_path = user_folder / f"{file_path.stem}.log"
        log_file = open(log_file_path, 'w')
        
        if file_ext == '.py':
            process = subprocess.Popen(
                [sys.executable, str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        elif file_ext == '.js':
            process = subprocess.Popen(
                ['node', str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        else:
            log_file.close()
            await callback.answer("❌ Cannot run this file type!", show_alert=True)
            return
        
        bot_scripts[script_key] = {
            'process': process,
            'file_name': file_name,
            'script_owner_id': user_id,
            'start_time': datetime.now(),
            'user_folder': str(user_folder),
            'type': file_ext[1:],
            'log_file': log_file
        }
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('UPDATE bot_stats SET stat_value = stat_value + 1 WHERE stat_name = ?', ('total_runs',))
        conn.commit()
        conn.close()
        bot_stats['total_runs'] = bot_stats.get('total_runs', 0) + 1
        
        await callback.answer(f"✅ Script started! (PID: {process.pid})", show_alert=True)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Stop Script", callback_data=f"stop_script:{script_key}")],
            [InlineKeyboardButton(text="📁 My Files", callback_data="check_files"),
             InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error running script: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("restart_script:"))
async def callback_restart_script(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    file_path = user_folder / file_name
    
    if not file_path.exists():
        await callback.answer("❌ File not found!", show_alert=True)
        return
    
    script_key = f"{user_id}_{file_name}"
    
    # Stop the script if it's running
    if script_key in bot_scripts:
        try:
            script_info = bot_scripts[script_key]
            process = script_info['process']
            log_file = script_info.get('log_file')
            
            if log_file and not log_file.closed:
                log_file.close()
            
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            
            for child in children:
                child.terminate()
            
            parent.terminate()
            
            # Wait for process to terminate
            try:
                parent.wait(timeout=5)
            except psutil.TimeoutExpired:
                parent.kill()
                
            del bot_scripts[script_key]
        except Exception as e:
            logger.error(f"Error stopping script for restart: {e}")
    
    # Start the script again
    file_ext = file_path.suffix.lower()
    
    try:
        log_file_path = user_folder / f"{file_path.stem}.log"
        log_file = open(log_file_path, 'a')
        
        if file_ext == '.py':
            process = subprocess.Popen(
                [sys.executable, str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        elif file_ext == '.js':
            process = subprocess.Popen(
                ['node', str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        else:
            log_file.close()
            await callback.answer("❌ Cannot run this file type!", show_alert=True)
            return
        
        bot_scripts[script_key] = {
            'process': process,
            'file_name': file_name,
            'script_owner_id': user_id,
            'start_time': datetime.now(),
            'user_folder': str(user_folder),
            'type': file_ext[1:],
            'log_file': log_file
        }
        
        await callback.answer(f"✅ Script restarted! (PID: {process.pid})", show_alert=True)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Stop Script", callback_data=f"stop_script:{script_key}")],
            [InlineKeyboardButton(text="📁 My Files", callback_data="check_files"),
             InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Error restarting script: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("stop_script:"))
async def callback_stop_script(callback: types.CallbackQuery):
    script_key = callback.data.split(":", 1)[1]
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Script not found or already stopped!", show_alert=True)
        return
    
    try:
        script_info = bot_scripts[script_key]
        process = script_info['process']
        log_file = script_info.get('log_file')
        
        if log_file and not log_file.closed:
            log_file.close()
        
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        
        for child in children:
            child.terminate()
        
        parent.terminate()
        
        del bot_scripts[script_key]
        
        await callback.answer("✅ Script stopped successfully!", show_alert=True)
        
        if callback.from_user.id in admin_ids:
            await callback.message.edit_text("🛑 Script stopped!", parse_mode="HTML")
        else:
            await callback_back_to_main(callback)
        
    except Exception as e:
        logger.error(f"Error stopping script: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("extract_zip:"))
async def callback_extract_zip(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    zip_path = user_folder / file_name
    
    if not zip_path.exists():
        await callback.answer("❌ ZIP file not found!", show_alert=True)
        return
    
    if not zipfile.is_zipfile(zip_path):
        await callback.answer("❌ Invalid ZIP file!", show_alert=True)
        return
    
    try:
        status_text = f"""
╔═══════════════════════╗
    📦 <b>EXTRACTING ZIP</b> 📦
╚═══════════════════════╝

📄 File: <code>{file_name}</code>
⏳ Status: <b>Extracting...</b>

Please wait...
"""
        await callback.message.edit_text(status_text, parse_mode="HTML")
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(user_folder)
            all_files = zip_ref.namelist()
        
        registered_files = []
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        
        for extracted_file in all_files:
            if extracted_file.endswith('/'):
                continue
            
            file_path = Path(extracted_file)
            file_ext = file_path.suffix.lower()
            
            if file_ext in ['.py', '.js']:
                just_name = file_path.name
                
                if user_id not in user_files:
                    user_files[user_id] = []
                
                user_files[user_id].append((just_name, file_ext[1:]))
                
                c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, upload_date) VALUES (?, ?, ?, ?)',
                          (user_id, just_name, file_ext[1:], now))
                
                registered_files.append(just_name)
        
        if user_id in user_files:
            user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
        
        c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
        c.execute('DELETE FROM favorites WHERE user_id = ? AND file_name = ?', (user_id, file_name))
        conn.commit()
        conn.close()
        
        if zip_path.exists():
            zip_path.unlink()
        
        registered_text = "\n".join([f"  • <code>{f}</code>" for f in registered_files[:10]])
        if len(registered_files) > 10:
            registered_text += f"\n  ... and {len(registered_files) - 10} more files"
        elif len(registered_files) == 0:
            registered_text = "  <i>No .py or .js files found</i>"
        
        current_count = len(user_files.get(user_id, []))
        limit = get_user_file_limit(user_id)
        
        success_text = f"""
╔═══════════════════════╗
    ✅ <b>EXTRACTION SUCCESS!</b> ✅
╚═══════════════════════╝

📄 <b>ZIP File:</b> <code>{file_name}</code>
📊 <b>Total Extracted:</b> {len(all_files)} files
✅ <b>Registered:</b> {len(registered_files)} files (.py, .js)
🗑️ <b>ZIP Deleted:</b> Automatically

<b>📋 Registered Files:</b>
{registered_text}

📦 <b>Your Files:</b> {current_count}/{limit}

✨ Extraction completed successfully!
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 My Files", callback_data="check_files"),
             InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(success_text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer("✅ ZIP extracted & registered!")
        
    except zipfile.BadZipFile:
        await callback.answer("❌ Corrupted ZIP file!", show_alert=True)
    except Exception as e:
        logger.error(f"Error extracting ZIP: {e}")
        await callback.answer(f"❌ Extraction failed: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("delete_file:"))
async def callback_delete_file(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    file_path = user_folder / file_name
    
    try:
        if file_path.exists():
            file_path.unlink()
        
        if user_id in user_files:
            user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
        
        if file_name in user_favorites.get(user_id, []):
            user_favorites[user_id].remove(file_name)
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
        c.execute('DELETE FROM favorites WHERE user_id = ? AND file_name = ?', (user_id, file_name))
        conn.commit()
        conn.close()
        
        await callback.answer("✅ File deleted successfully!", show_alert=True)
        await callback_check_files(callback)
        
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "admin_total_users")
async def callback_admin_total_users(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    user_list = "\n".join([f"• <code>{uid}</code>" for uid in list(active_users)[:15]])
    text = f"""
╔═══════════════════════╗
    👥 <b>USER STATISTICS</b> 👥
╚═══════════════════════╝

📊 <b>Total Users:</b> {len(active_users)}
🚫 <b>Banned:</b> {len(banned_users)}
✅ <b>Active:</b> {len(active_users) - len(banned_users)}

<b>📝 Recent Users (15):</b>
{user_list}

{'...' if len(active_users) > 15 else ''}
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_total_files")
async def callback_admin_total_files(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    total_files = sum(len(files) for files in user_files.values())
    py_files = sum(1 for files in user_files.values() for f in files if f[1] == 'py')
    js_files = sum(1 for files in user_files.values() for f in files if f[1] == 'js')
    zip_files = sum(1 for files in user_files.values() for f in files if f[1] == 'zip')
    
    text = f"""
╔═══════════════════════╗
    📁 <b>FILE STATISTICS</b> 📁
╚═══════════════════════╝

📊 <b>Total Files:</b> {total_files}

<b>📦 By Type:</b>
🐍 Python: {py_files}
🟨 JavaScript: {js_files}
📦 ZIP: {zip_files}

<b>📈 Top Users:</b>
"""
    
    top_users = sorted(user_files.items(), key=lambda x: len(x[1]), reverse=True)[:5]
    for user_id, files in top_users:
        text += f"• User <code>{user_id}</code>: {len(files)} files\n"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_running_scripts")
async def callback_admin_running_scripts(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    if not bot_scripts:
        text = """
╔═══════════════════════╗
    🚀 <b>RUNNING SCRIPTS</b> 🚀
╚═══════════════════════╝

💤 No scripts running currently
"""
        buttons = []
    else:
        text = f"""
╔═══════════════════════╗
    🚀 <b>RUNNING ({len(bot_scripts)})</b> 🚀
╚═══════════════════════╝

"""
        buttons = []
        for script_key, info in bot_scripts.items():
            runtime = (datetime.now() - info['start_time']).total_seconds()
            text += f"🔸 <code>{info['file_name']}</code>\n"
            text += f"   PID: {info['process'].pid} | User: {info['script_owner_id']}\n"
            text += f"   Runtime: {int(runtime)}s\n\n"
            buttons.append([InlineKeyboardButton(
                text=f"🛑 Stop {info['file_name'][:15]}", 
                callback_data=f"stop_script:{script_key}"
            )])
    
    buttons.append([InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")])
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_premium_users")
async def callback_admin_premium_users(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    premium_users = [(u, data) for u, data in user_subscriptions.items() if data['expiry'] > datetime.now()]
    
    if not premium_users:
        text = """
╔═══════════════════════╗
    💎 <b>PREMIUM USERS</b> 💎
╚═══════════════════════╝

No active premium subscriptions.
"""
    else:
        text = f"""
╔═══════════════════════╗
    💎 <b>PREMIUM ({len(premium_users)})</b> 💎
╚═══════════════════════╝

"""
        for user_id, data in premium_users:
            expiry_date = data['expiry'].strftime('%Y-%m-%d')
            text += f"💎 User <code>{user_id}</code>\n   Expires: {expiry_date}\n\n"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Premium", callback_data="admin_add_premium")],
        [InlineKeyboardButton(text="➖ Remove Premium", callback_data="admin_remove_premium")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_add_premium")
async def callback_admin_add_premium(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = """
╔═══════════════════════╗
    ➕ <b>ADD PREMIUM</b> ➕
╚═══════════════════════╝

Give premium access to users!

<b>Command:</b>
<code>/addpremium USER_ID DAYS</code>

<b>Examples:</b>
<code>/addpremium 123456789 30</code> (30 days)
<code>/addpremium 987654321 7</code> (7 days)

Premium benefits:
• 50 file limit (vs 20)
• Priority support
• Premium badge
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_remove_premium")
async def callback_admin_remove_premium(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = f"""
╔═══════════════════════╗
    ➖ <b>REMOVE PREMIUM</b> ➖
╚═══════════════════════╝

<b>Current Premium Users ({len([u for u in user_subscriptions if user_subscriptions[u]['expiry'] > datetime.now()])}):</b>

"""
    
    for user_id, data in user_subscriptions.items():
        if data['expiry'] > datetime.now():
            expiry_date = data['expiry'].strftime('%Y-%m-%d')
            text += f"💎 User <code>{user_id}</code>\n   Expires: {expiry_date}\n\n"
    
    text += "\n<b>To remove:</b>\n<code>/removepremium USER_ID</code>"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_analytics")
async def callback_admin_analytics(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = f"""
╔═══════════════════════╗
    📊 <b>BOT ANALYTICS</b> 📊
╚═══════════════════════╝

<b>📈 GLOBAL STATS:</b>

📤 Total Uploads: {bot_stats.get('total_uploads', 0)}
📥 Total Downloads: {bot_stats.get('total_downloads', 0)}
▶️ Script Runs: {bot_stats.get('total_runs', 0)}
👥 Total Users: {len(active_users)}
📁 Total Files: {sum(len(files) for files in user_files.values())}
🚀 Running Now: {len(bot_scripts)}
⭐ Total Favorites: {sum(len(favs) for favs in user_favorites.values())}

<b>💎 PREMIUM:</b>
Active: {len([u for u in user_subscriptions if user_subscriptions[u]['expiry'] > datetime.now()])}
Expired: {len([u for u in user_subscriptions if user_subscriptions[u]['expiry'] <= datetime.now()])}

<b>🛡️ SECURITY:</b>
Banned Users: {len(banned_users)}
Admins: {len(admin_ids)}
Bot Status: {'🔒 Locked' if bot_locked else '✅ Active'}
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_system_status")
async def callback_admin_system_status(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    try:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        text = f"""
╔═══════════════════════╗
    ⚙️ <b>SYSTEM STATUS</b> ⚙️
╚═══════════════════════╝

<b>💻 CPU:</b>
Usage: {cpu}%
{'🟢 Normal' if cpu < 70 else '🟡 High' if cpu < 90 else '🔴 Critical'}

<b>🧠 MEMORY:</b>
Used: {memory.percent}%
Free: {memory.available / (1024**3):.1f} GB
Total: {memory.total / (1024**3):.1f} GB

<b>💾 DISK:</b>
Used: {disk.percent}%
Free: {disk.free / (1024**3):.1f} GB
Total: {disk.total / (1024**3):.1f} GB

<b>🤖 BOT STATUS:</b>
Status: {'🔒 Locked' if bot_locked else '✅ Running'}
Scripts: {len(bot_scripts)} active
Uptime: ✅ Online
"""
        
        back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_system_status")],
            [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
        ])
        
        await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "admin_add_admin")
async def callback_admin_add_admin(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = """
╔═══════════════════════╗
    ➕ <b>ADD ADMIN</b> ➕
╚═══════════════════════╝

To add a new admin, use:
<code>/addadmin USER_ID</code>

<b>Example:</b>
<code>/addadmin 123456789</code>

The user will get full admin privileges!
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_remove_admin")
async def callback_admin_remove_admin(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = f"""
╔═══════════════════════╗
    ➖ <b>REMOVE ADMIN</b> ➖
╚═══════════════════════╝

<b>Current Admins ({len(admin_ids)}):</b>

"""
    
    for admin_id in admin_ids:
        text += f"👑 <code>{admin_id}</code>\n"
    
    text += "\n<b>To remove:</b>\n<code>/removeadmin USER_ID</code>"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_ban_user")
async def callback_admin_ban_user(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = f"""
╔═══════════════════════╗
    🚫 <b>BAN USER</b> 🚫
╚═══════════════════════╝

<b>Currently Banned:</b> {len(banned_users)} users

To ban a user, use:
<code>/ban USER_ID REASON</code>

<b>Example:</b>
<code>/ban 123456789 Spam</code>

Banned users cannot use the bot!
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_unban_user")
async def callback_admin_unban_user(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = f"""
╔═══════════════════════╗
    ✅ <b>UNBAN USER</b> ✅
╚═══════════════════════╝

<b>Banned Users:</b> {len(banned_users)}

"""
    
    if banned_users:
        text += "<b>List:</b>\n"
        for ban_id in list(banned_users)[:10]:
            text += f"🚫 <code>{ban_id}</code>\n"
    
    text += "\n<b>To unban:</b>\n<code>/unban USER_ID</code>"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "lock_bot")
async def callback_lock_bot(callback: types.CallbackQuery):
    global bot_locked
    
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    bot_locked = not bot_locked
    status = "🔒 LOCKED" if bot_locked else "🔓 UNLOCKED"
    
    await callback.answer(f"Bot is now {status}!", show_alert=True)
    await callback_admin_panel(callback)

@dp.callback_query(F.data == "broadcast")
async def callback_broadcast(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = f"""
╔═══════════════════════╗
    📢 <b>BROADCAST</b> 📢
╚═══════════════════════╝

Send a message to all users!

<b>Total Recipients:</b> {len(active_users)}

<b>Command:</b>
<code>/broadcast Your message here</code>

⚠️ Use this feature responsibly!
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_clean_files")
async def callback_admin_clean_files(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = """
╔═══════════════════════╗
    🗑️ <b>CLEAN FILES</b> 🗑️
╚═══════════════════════╝

Clean old or unused files from the system.

<b>Options:</b>
• Delete files older than 30 days
• Remove files from banned users
• Clean temp/log files

<b>Command:</b>
<code>/clean OPTION</code>

⚠️ This action cannot be undone!
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_backup_db")
async def callback_admin_backup_db(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    try:
        backup_path = IROTECH_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        conn = sqlite3.connect(DATABASE_PATH)
        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()
        
        await callback.answer("✅ Database backed up!", show_alert=True)
        
        await callback.message.answer_document(
            FSInputFile(backup_path),
            caption="💾 <b>Database Backup</b>\n\nCreated: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            parse_mode="HTML"
        )
        
        backup_path.unlink()
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await callback.answer(f"❌ Backup failed: {str(e)}", show_alert=True)

@dp.callback_query(F.data == "admin_view_logs")
async def callback_admin_view_logs(callback: types.CallbackQuery):
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Admin only!", show_alert=True)
        return
    
    text = """
╔═══════════════════════╗
    📝 <b>SYSTEM LOGS</b> 📝
╚═══════════════════════╝

View bot logs and activity.

<b>Available Logs:</b>
• Error logs
• User activity
• Script executions
• Admin actions

Logs are stored in the system directory.
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "admin_restart_bot")
async def callback_admin_restart_bot(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Owner only!", show_alert=True)
        return
    
    text = """
╔═══════════════════════╗
    🔄 <b>RESTART BOT</b> 🔄
╚═══════════════════════╝

⚠️ <b>WARNING:</b>
This will restart the entire bot!

All running scripts will be stopped.
Users may experience brief downtime.

<b>Only use if necessary!</b>

Use <code>/restart</code> to confirm.
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

# Bot Control Panel
@dp.callback_query(F.data == "bot_control")
async def callback_bot_control(callback: types.CallbackQuery):
    """Display bot control panel"""
    user_id = callback.from_user.id
    
    # Get user's bots
    user_bots = []
    for script_key, script_info in bot_scripts.items():
        if script_info.get('script_owner_id') == user_id:
            user_bots.append((script_key, script_info))
    
    if not user_bots:
        text = """
╔═══════════════════════╗
    🤖 <b>BOT CONTROL PANEL</b> 🤖
╚═══════════════════════╝

📭 <b>No bots found!</b>

Upload your first bot to get started! 🚀
"""
        buttons = [
            [InlineKeyboardButton(text="📤 Upload Bot", callback_data="upload_file")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ]
    else:
        text = f"""
╔═══════════════════════╗
    🤖 <b>MY BOTS ({len(user_bots)})</b> 🤖
╚═══════════════════════╝

"""
        buttons = []
        
        for script_key, script_info in user_bots:
            status = "🟢 Running" if script_info['process'].poll() is None else "🔴 Stopped"
            file_name = script_info['file_name']
            
            text += f"🤖 <b>{file_name}</b>\n"
            text += f"   Status: {status}\n"
            text += f"   PID: {script_info['process'].pid}\n\n"
            
            buttons.append([
                InlineKeyboardButton(text="▶️ Start", callback_data=f"start_bot:{script_key}"),
                InlineKeyboardButton(text="🔄 Restart", callback_data=f"restart_bot:{script_key}"),
                InlineKeyboardButton(text="🛑 Stop", callback_data=f"stop_script:{script_key}")
            ])
            
            buttons.append([
                InlineKeyboardButton(text="📊 Status", callback_data=f"bot_status:{script_key}"),
                InlineKeyboardButton(text="📝 Logs", callback_data=f"bot_logs:{script_key}"),
                InlineKeyboardButton(text="📦 Export", callback_data=f"export_bot:{script_key}")
            ])
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("bot_control:"))
async def callback_bot_control_file(callback: types.CallbackQuery):
    """Display control panel for a specific file"""
    user_id = callback.from_user.id
    file_name = callback.data.split(":", 1)[1]
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    file_path = user_folder / file_name
    
    if not file_path.exists():
        await callback.answer("❌ File not found!", show_alert=True)
        return
    
    script_key = f"{user_id}_{file_name}"
    is_running = script_key in bot_scripts and bot_scripts[script_key]['process'].poll() is None
    
    text = f"""
╔═══════════════════════╗
    🤖 <b>BOT CONTROL</b> 🤖
╚═══════════════════════╝

📄 <b>File:</b> <code>{file_name}</code>
🔴 <b>Status:</b> {'Running' if is_running else 'Stopped'}

{'PID: ' + str(bot_scripts[script_key]['process'].pid) if is_running else ''}
"""
    
    buttons = []
    
    if is_running:
        buttons.append([
            InlineKeyboardButton(text="🛑 Stop", callback_data=f"stop_script:{script_key}"),
            InlineKeyboardButton(text="🔄 Restart", callback_data=f"restart_script:{file_name}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="▶️ Start", callback_data=f"run_script:{file_name}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="📊 Status", callback_data=f"bot_status:{script_key}"),
        InlineKeyboardButton(text="📝 Logs", callback_data=f"bot_logs:{script_key}")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="📦 Export", callback_data=f"export_bot:{script_key}"),
        InlineKeyboardButton(text="📝 Edit", callback_data=f"edit_file:{file_name}")
    ])
    
    buttons.append([
        InlineKeyboardButton(text="🔙 Back", callback_data="bot_control")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("start_bot:"))
async def callback_start_bot(callback: types.CallbackQuery):
    """Start a stopped bot"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    script_info = bot_scripts[script_key]
    
    if script_info['script_owner_id'] != user_id and user_id not in admin_ids:
        await callback.answer("❌ Not your bot!", show_alert=True)
        return
    
    # Check if already running
    if script_info['process'].poll() is None:
        await callback.answer("⚠️ Bot is already running!", show_alert=True)
        return
    
    try:
        # Start the bot
        user_folder = Path(script_info['user_folder'])
        file_name = script_info['file_name']
        file_path = user_folder / file_name
        
        log_file_path = user_folder / f"{file_path.stem}.log"
        log_file = open(log_file_path, 'a')
        
        if script_info['type'] == 'py':
            process = subprocess.Popen(
                [sys.executable, str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        elif script_info['type'] == 'js':
            process = subprocess.Popen(
                ['node', str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        else:
            log_file.close()
            await callback.answer("❌ Cannot run this file type!", show_alert=True)
            return
        
        # Update the process reference
        bot_scripts[script_key]['process'] = process
        bot_scripts[script_key]['start_time'] = datetime.now()
        bot_scripts[script_key]['log_file'] = log_file
        
        await callback.answer("✅ Bot started successfully!", show_alert=True)
        await callback_bot_control(callback)
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("restart_bot:"))
async def callback_restart_bot(callback: types.CallbackQuery):
    """Restart a running bot"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    script_info = bot_scripts[script_key]
    
    if script_info['script_owner_id'] != user_id and user_id not in admin_ids:
        await callback.answer("❌ Not your bot!", show_alert=True)
        return
    
    try:
        # Stop the bot first
        process = script_info['process']
        log_file = script_info.get('log_file')
        
        if log_file and not log_file.closed:
            log_file.close()
        
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        
        for child in children:
            child.terminate()
        
        parent.terminate()
        
        # Wait for process to terminate
        try:
            parent.wait(timeout=5)
        except psutil.TimeoutExpired:
            parent.kill()
        
        # Start the bot again
        user_folder = Path(script_info['user_folder'])
        file_name = script_info['file_name']
        file_path = user_folder / file_name
        
        log_file_path = user_folder / f"{file_path.stem}.log"
        log_file = open(log_file_path, 'a')
        
        if script_info['type'] == 'py':
            new_process = subprocess.Popen(
                [sys.executable, str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        elif script_info['type'] == 'js':
            new_process = subprocess.Popen(
                ['node', str(file_path)],
                cwd=str(user_folder),
                stdout=log_file,
                stderr=log_file
            )
        else:
            log_file.close()
            await callback.answer("❌ Cannot run this file type!", show_alert=True)
            return
        
        # Update the process reference
        bot_scripts[script_key]['process'] = new_process
        bot_scripts[script_key]['start_time'] = datetime.now()
        bot_scripts[script_key]['log_file'] = log_file
        
        await callback.answer("✅ Bot restarted successfully!", show_alert=True)
        await callback_bot_control(callback)
        
    except Exception as e:
        logger.error(f"Error restarting bot: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("bot_status:"))
async def callback_bot_status(callback: types.CallbackQuery):
    """Show detailed status of a bot"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    script_info = bot_scripts[script_key]
    
    if script_info['script_owner_id'] != user_id and user_id not in admin_ids:
        await callback.answer("❌ Not your bot!", show_alert=True)
        return
    
    # Get process information
    process = script_info['process']
    is_running = process.poll() is None
    
    # Get memory usage if running
    memory_usage = "N/A"
    cpu_usage = "N/A"
    
    if is_running:
        try:
            p = psutil.Process(process.pid)
            memory_info = p.memory_info()
            memory_usage = f"{memory_info.rss / (1024 * 1024):.2f} MB"
            cpu_usage = f"{p.cpu_percent()}%"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    # Calculate uptime
    start_time = script_info['start_time']
    uptime = datetime.now() - start_time
    uptime_str = f"{uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m"
    
    text = f"""
╔═══════════════════════╗
    📊 <b>BOT STATUS</b> 📊
╚═══════════════════════╝

🤖 <b>Bot Name:</b> {script_info['file_name']}
📁 <b>Type:</b> {script_info['type'].upper()}
🆔 <b>PID:</b> {process.pid}
📅 <b>Started:</b> {start_time.strftime('%Y-%m-%d %H:%M:%S')}
⏱️ <b>Uptime:</b> {uptime_str}
🔴 <b>Status:</b> {'Running' if is_running else 'Stopped'}

💾 <b>Memory Usage:</b> {memory_usage}
🖥️ <b>CPU Usage:</b> {cpu_usage}
"""
    
    buttons = [
        [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"bot_status:{script_key}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="bot_control")]
    ]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("bot_logs:"))
async def callback_bot_logs(callback: types.CallbackQuery):
    """Show logs of a bot"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    script_info = bot_scripts[script_key]
    
    if script_info['script_owner_id'] != user_id and user_id not in admin_ids:
        await callback.answer("❌ Not your bot!", show_alert=True)
        return
    
    try:
        user_folder = Path(script_info['user_folder'])
        file_name = script_info['file_name']
        log_file_path = user_folder / f"{Path(file_name).stem}.log"
        
        if not log_file_path.exists():
            text = f"""
╔═══════════════════════╗
    📝 <b>BOT LOGS</b> 📝
╚═══════════════════════╝

📭 <b>No logs found for {file_name}!</b>

Logs will appear here once the bot runs.
"""
        else:
            # Read last 20 lines of log file
            with open(log_file_path, 'r') as f:
                lines = f.readlines()
                recent_lines = lines[-20:] if len(lines) > 20 else lines
            
            log_content = "".join(recent_lines)
            if not log_content.strip():
                log_content = "Log file is empty."
            
            text = f"""
╔═══════════════════════╗
    📝 <b>BOT LOGS</b> 📝
╚═══════════════════════╝

🤖 <b>Bot:</b> {file_name}
📄 <b>Showing last {len(recent_lines)} lines</b>

<pre>{log_content}</pre>
"""
        
        buttons = [
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"bot_logs:{script_key}")],
            [InlineKeyboardButton(text="🗑️ Clear Logs", callback_data=f"clear_logs:{script_key}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="bot_control")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error reading logs: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("clear_logs:"))
async def callback_clear_logs(callback: types.CallbackQuery):
    """Clear logs of a bot"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    script_info = bot_scripts[script_key]
    
    if script_info['script_owner_id'] != user_id and user_id not in admin_ids:
        await callback.answer("❌ Not your bot!", show_alert=True)
        return
    
    try:
        user_folder = Path(script_info['user_folder'])
        file_name = script_info['file_name']
        log_file_path = user_folder / f"{Path(file_name).stem}.log"
        
        if log_file_path.exists():
            log_file_path.unlink()
        
        await callback.answer("✅ Logs cleared successfully!", show_alert=True)
        await callback_bot_logs(callback)
        
    except Exception as e:
        logger.error(f"Error clearing logs: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("export_bot:"))
async def callback_export_bot(callback: types.CallbackQuery):
    """Export a bot with all its files"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    script_info = bot_scripts[script_key]
    
    if script_info['script_owner_id'] != user_id and user_id not in admin_ids:
        await callback.answer("❌ Not your bot!", show_alert=True)
        return
    
    try:
        user_folder = Path(script_info['user_folder'])
        file_name = script_info['file_name']
        
        # Create a temporary directory for export
        export_dir = user_folder / "temp_export"
        export_dir.mkdir(exist_ok=True)
        
        # Create zip file
        export_zip_path = user_folder / f"{Path(file_name).stem}_export.zip"
        
        with zipfile.ZipFile(export_zip_path, 'w') as zipf:
            # Add the main script file
            zipf.write(user_folder / file_name, file_name)
            
            # Add log file if exists
            log_file_path = user_folder / f"{Path(file_name).stem}.log"
            if log_file_path.exists():
                zipf.write(log_file_path, f"{Path(file_name).stem}.log")
            
            # Add any additional files in the same folder with the same name prefix
            prefix = Path(file_name).stem
            for file_path in user_folder.glob(f"{prefix}*"):
                if file_path.name != file_name and file_path.name != f"{prefix}.log":
                    zipf.write(file_path, file_path.name)
        
        # Send the zip file
        await callback.message.answer_document(
            FSInputFile(export_zip_path),
            caption=f"📦 <b>Bot Export</b>\n\n🤖 Bot: {file_name}\n📅 Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="HTML"
        )
        
        # Clean up
        export_zip_path.unlink()
        export_dir.rmdir()
        
        await callback.answer("✅ Bot exported successfully!", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error exporting bot: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("edit_file:"))
async def callback_edit_file(callback: types.CallbackQuery):
    """Open file editor for a bot file"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    file_path = user_folder / script_key
    
    if not file_path.exists():
        await callback.answer("❌ File not found!", show_alert=True)
        return
    
    try:
        # Read file content
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Truncate content if too long for Telegram
        if len(content) > 3500:
            content = content[:3500] + "\n... (content truncated)"
        
        text = f"""
╔═══════════════════════╗
    📝 <b>FILE EDITOR</b> 📝
╚═══════════════════════╝

📄 <b>File:</b> {script_key}
📊 <b>Size:</b> {len(content)} characters

<pre>{content}</pre>
"""
        
        buttons = [
            [InlineKeyboardButton(text="✏️ Edit Line", callback_data=f"edit_line:{script_key}")],
            [InlineKeyboardButton(text="🔍 Find/Replace", callback_data=f"find_replace:{script_key}")],
            [InlineKeyboardButton(text="➕ Insert Line", callback_data=f"insert_line:{script_key}")],
            [InlineKeyboardButton(text="🗑️ Delete Line", callback_data=f"delete_line:{script_key}")],
            [InlineKeyboardButton(text="💾 Save", callback_data=f"save_file:{script_key}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="check_files")]
        ]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error opening file editor: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("edit_line:"))
async def callback_edit_line_prompt(callback: types.CallbackQuery):
    """Prompt user to edit a specific line"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("Please use /edit_line command to edit a line", show_alert=True)

@dp.callback_query(F.data.startswith("find_replace:"))
async def callback_find_replace_prompt(callback: types.CallbackQuery):
    """Prompt user to find and replace text"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("Please use /find_replace command to find and replace text", show_alert=True)

@dp.callback_query(F.data.startswith("insert_line:"))
async def callback_insert_line_prompt(callback: types.CallbackQuery):
    """Prompt user to insert a line"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("Please use /insert_line command to insert a line", show_alert=True)

@dp.callback_query(F.data.startswith("delete_line:"))
async def callback_delete_line_prompt(callback: types.CallbackQuery):
    """Prompt user to delete a line"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("Please use /delete_line command to delete a line", show_alert=True)

@dp.callback_query(F.data.startswith("save_file:"))
async def callback_save_file(callback: types.CallbackQuery):
    """Save file after editing"""
    script_key = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    
    await callback.answer("File saved successfully!", show_alert=True)
    await callback_check_files(callback)

@dp.message(Command("addadmin"))
async def cmd_add_admin(message: types.Message):
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Permission denied!")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.answer("Usage: /addadmin USER_ID")
            return
        
        new_admin_id = int(args[1])
        
        if new_admin_id in admin_ids:
            await message.answer(f"✅ User {new_admin_id} is already an admin!")
            return
        
        admin_ids.add(new_admin_id)
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (new_admin_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ User <code>{new_admin_id}</code> added as admin!", parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Invalid USER_ID!")
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("removeadmin"))
async def cmd_remove_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Only owner can remove admins!")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.answer("Usage: /removeadmin USER_ID")
            return
        
        remove_admin_id = int(args[1])
        
        if remove_admin_id == OWNER_ID:
            await message.answer("❌ Cannot remove owner!")
            return
        
        if remove_admin_id not in admin_ids:
            await message.answer(f"❌ User {remove_admin_id} is not an admin!")
            return
        
        admin_ids.remove(remove_admin_id)
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM admins WHERE user_id = ?', (remove_admin_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ User <code>{remove_admin_id}</code> removed from admins!", parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Invalid USER_ID!")
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("addpremium"))
async def cmd_add_premium(message: types.Message):
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Permission denied!")
        return
    
    try:
        args = message.text.split()
        if len(args) != 3:
            await message.answer("Usage: /addpremium USER_ID DAYS")
            return
        
        user_id = int(args[1])
        days = int(args[2])
        
        if days <= 0:
            await message.answer("❌ Days must be greater than 0!")
            return
        
        expiry = datetime.now() + timedelta(days=days)
        user_subscriptions[user_id] = {'expiry': expiry}
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                  (user_id, expiry.isoformat()))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ <b>Premium Added!</b>\n\n"
            f"User: <code>{user_id}</code>\n"
            f"Duration: {days} days\n"
            f"Expires: {expiry.strftime('%Y-%m-%d %H:%M')}",
            parse_mode="HTML"
        )
        
    except ValueError:
        await message.answer("❌ Invalid input!")
    except Exception as e:
        logger.error(f"Error adding premium: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("removepremium"))
async def cmd_remove_premium(message: types.Message):
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Permission denied!")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.answer("Usage: /removepremium USER_ID")
            return
        
        user_id = int(args[1])
        
        if user_id not in user_subscriptions:
            await message.answer(f"❌ User {user_id} does not have premium!")
            return
        
        del user_subscriptions[user_id]
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ <b>Premium Removed!</b>\n\n"
            f"User: <code>{user_id}</code>\n"
            f"Status: Now a free user",
            parse_mode="HTML"
        )
        
    except ValueError:
        await message.answer("❌ Invalid USER_ID!")
    except Exception as e:
        logger.error(f"Error removing premium: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("ban"))
async def cmd_ban_user(message: types.Message):
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Permission denied!")
        return
    
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            await message.answer("Usage: /ban USER_ID [REASON]")
            return
        
        ban_user_id = int(args[1])
        reason = args[2] if len(args) > 2 else "No reason provided"
        
        if ban_user_id in admin_ids:
            await message.answer("❌ Cannot ban an admin!")
            return
        
        banned_users.add(ban_user_id)
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO banned_users (user_id, banned_date, reason) VALUES (?, ?, ?)',
                  (ban_user_id, datetime.now().isoformat(), reason))
        conn.commit()
        conn.close()
        
        await message.answer(f"🚫 User <code>{ban_user_id}</code> has been banned!\n\nReason: {reason}", parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Invalid USER_ID!")
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("unban"))
async def cmd_unban_user(message: types.Message):
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Permission denied!")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            await message.answer("Usage: /unban USER_ID")
            return
        
        unban_user_id = int(args[1])
        
        if unban_user_id not in banned_users:
            await message.answer(f"❌ User {unban_user_id} is not banned!")
            return
        
        banned_users.remove(unban_user_id)
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM banned_users WHERE user_id = ?', (unban_user_id,))
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ User <code>{unban_user_id}</code> has been unbanned!", parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Invalid USER_ID!")
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if message.from_user.id not in admin_ids:
        await message.answer("❌ Permission denied!")
        return
    
    try:
        broadcast_text = message.text.replace("/broadcast", "", 1).strip()
        
        if not broadcast_text:
            await message.answer("Usage: /broadcast Your message here")
            return
        
        sent_count = 0
        failed_count = 0
        
        status_msg = await message.answer(f"📢 Broadcasting to {len(active_users)} users...")
        
        for user_id in active_users:
            if user_id in banned_users:
                continue
            
            try:
                await bot.send_message(user_id, f"📢 <b>Announcement:</b>\n\n{broadcast_text}", parse_mode="HTML")
                sent_count += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Failed to send to {user_id}: {e}")
                failed_count += 1
        
        await status_msg.edit_text(
            f"✅ <b>Broadcast Complete!</b>\n\n"
            f"✅ Sent: {sent_count}\n"
            f"❌ Failed: {failed_count}",
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error broadcasting: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("search"))
async def cmd_search_files(message: types.Message):
    user_id = message.from_user.id
    
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.answer("Usage: /search filename")
            return
        
        search_term = args[1].lower()
        user_file_list = user_files.get(user_id, [])
        
        matches = [f for f in user_file_list if search_term in f[0].lower()]
        
        if not matches:
            await message.answer(f"🔍 No files found matching '<code>{search_term}</code>'", parse_mode="HTML")
            return
        
        text = f"🔍 <b>Search Results ({len(matches)}):</b>\n\n"
        
        for file_name, file_type in matches:
            icon = "🐍" if file_type == "py" else "🟨" if file_type == "js" else "📦"
            text += f"{icon} <code>{file_name}</code>\n"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = """
╔═══════════════════════╗
    ℹ️ <b>HELP & INFO</b> ℹ️
╚═══════════════════════╝

<b>🎯 HOW TO USE:</b>

1️⃣ <b>Upload Files:</b>
   • Click 'Upload File'
   • Send your .py, .js, or .zip file
   • File will be saved automatically

2️⃣ <b>Run Scripts:</b>
   • Go to 'My Files'
   • Click 'Run' on any file
   • Monitor script execution

3️⃣ <b>Manage Files:</b>
   • View all files in 'My Files'
   • Add to favorites with ⭐
   • Delete unwanted files

4️⃣ <b>Search:</b>
   • Use /search [filename]
   • Quick file lookup

5️⃣ <b>Bot Control:</b>
   • Use 'My Bots' to control your hosted scripts
   • Start, stop, restart your bots
   • View logs and status

━━━━━━━━━━━━━━━━━━━━
<b>💡 COMMANDS:</b>

/start - Start the bot
/help - Show this help
/search - Search files
/stats - Your statistics
/premium - Premium info

<b>Need help? Contact owner! 💬</b>
"""
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Features", callback_data="all_features")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await message.answer(text, reply_markup=back_keyboard, parse_mode="HTML")

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    user_file_count = len(user_files.get(user_id, []))
    user_fav_count = len(user_favorites.get(user_id, []))
    is_premium = user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now()
    
    text = f"""
╔═══════════════════════╗
    📊 <b>YOUR STATISTICS</b> 📊
╚═══════════════════════╝

<b>👤 USER INFO:</b>

🆔 User ID: <code>{user_id}</code>
👤 Name: {message.from_user.full_name}
📦 Files Uploaded: {user_file_count}/{get_user_file_limit(user_id)}
⭐ Favorites: {user_fav_count}
💎 Account: {'Premium ✨' if is_premium else 'Free 🆓'}
🚀 Running: {sum(1 for k in bot_scripts if k.startswith(f"{user_id}_"))}

━━━━━━━━━━━━━━━━━━━━
📈 <b>USAGE:</b>

📤 Uploads: {bot_stats.get('total_uploads', 0)}
📥 Downloads: {bot_stats.get('total_downloads', 0)}
▶️ Script Runs: {bot_stats.get('total_runs', 0)}

{'✅ Bot Status: Active' if not bot_locked else '🔒 Bot: Maintenance'}
"""
    
    if user_id in admin_ids:
        text += f"\n━━━━━━━━━━━━━━━━━━━━\n👑 <b>ADMIN STATS:</b>\n"
        text += f"👥 Total Users: {len(active_users)}\n"
        text += f"📁 Total Files: {sum(len(files) for files in user_files.values())}\n"
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await message.answer(text, reply_markup=back_keyboard, parse_mode="HTML")

@dp.message(Command("edit_line"))
async def cmd_edit_line(message: types.Message):
    """Edit a specific line in a file"""
    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.answer("Usage: /edit_line script_key line_number new_content")
            return
        
        script_key = parts[1]
        line_num = int(parts[2])
        new_content = " ".join(parts[3:])
        
        user_id = message.from_user.id
        
        user_folder = UPLOAD_BOTS_DIR / str(user_id)
        file_path = user_folder / script_key
        
        if not file_path.exists():
            await message.answer("❌ File not found!")
            return
        
        # Read file content
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        # Check if line number is valid
        if line_num < 1 or line_num > len(lines):
            await message.answer(f"❌ Invalid line number! File has {len(lines)} lines.")
            return
        
        # Update the line
        lines[line_num - 1] = new_content + "\n"
        
        # Write back to file
        with open(file_path, 'w') as f:
            f.writelines(lines)
        
        await message.answer(f"✅ Line {line_num} updated successfully!")
        
    except ValueError:
        await message.answer("❌ Invalid line number!")
    except Exception as e:
        logger.error(f"Error editing line: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("insert_line"))
async def cmd_insert_line(message: types.Message):
    """Insert a new line in a file"""
    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.answer("Usage: /insert_line script_key line_number new_content")
            return
        
        script_key = parts[1]
        line_num = int(parts[2])
        new_content = " ".join(parts[3:])
        
        user_id = message.from_user.id
        
        user_folder = UPLOAD_BOTS_DIR / str(user_id)
        file_path = user_folder / script_key
        
        if not file_path.exists():
            await message.answer("❌ File not found!")
            return
        
        # Read file content
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        # Check if line number is valid
        if line_num < 1 or line_num > len(lines) + 1:
            await message.answer(f"❌ Invalid line number! File has {len(lines)} lines.")
            return
        
        # Insert the new line
        lines.insert(line_num - 1, new_content + "\n")
        
        # Write back to file
        with open(file_path, 'w') as f:
            f.writelines(lines)
        
        await message.answer(f"✅ Line inserted at position {line_num} successfully!")
        
    except ValueError:
        await message.answer("❌ Invalid line number!")
    except Exception as e:
        logger.error(f"Error inserting line: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("delete_line"))
async def cmd_delete_line(message: types.Message):
    """Delete a specific line in a file"""
    try:
        parts = message.text.split()
        if len(parts) < 3:
            await message.answer("Usage: /delete_line script_key line_number")
            return
        
        script_key = parts[1]
        line_num = int(parts[2])
        
        user_id = message.from_user.id
        
        user_folder = UPLOAD_BOTS_DIR / str(user_id)
        file_path = user_folder / script_key
        
        if not file_path.exists():
            await message.answer("❌ File not found!")
            return
        
        # Read file content
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        # Check if line number is valid
        if line_num < 1 or line_num > len(lines):
            await message.answer(f"❌ Invalid line number! File has {len(lines)} lines.")
            return
        
        # Delete the line
        deleted_line = lines.pop(line_num - 1)
        
        # Write back to file
        with open(file_path, 'w') as f:
            f.writelines(lines)
        
        await message.answer(f"✅ Line {line_num} deleted successfully!\n\nDeleted content: {deleted_line.strip()}")
        
    except ValueError:
        await message.answer("❌ Invalid line number!")
    except Exception as e:
        logger.error(f"Error deleting line: {e}")
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("find_replace"))
async def cmd_find_replace(message: types.Message):
    """Find and replace text in a file"""
    try:
        parts = message.text.split()
        if len(parts) < 4:
            await message.answer("Usage: /find_replace script_key find_text replace_text")
            return
        
        script_key = parts[1]
        find_text = parts[2]
        replace_text = parts[3]
        
        user_id = message.from_user.id
        
        user_folder = UPLOAD_BOTS_DIR / str(user_id)
        file_path = user_folder / script_key
        
        if not file_path.exists():
            await message.answer("❌ File not found!")
            return
        
        # Read file content
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Count occurrences
        count = content.count(find_text)
        
        if count == 0:
            await message.answer(f"❌ Text '{find_text}' not found in file!")
            return
        
        # Replace all occurrences
        new_content = content.replace(find_text, replace_text)
        
        # Write back to file
        with open(file_path, 'w') as f:
            f.write(new_content)
        
        await message.answer(f"✅ Replaced {count} occurrences of '{find_text}' with '{replace_text}'!")
        
    except Exception as e:
        logger.error(f"Error finding/replacing text: {e}")
        await message.answer(f"❌ Error: {str(e)}")

async def web_server():
    app = web.Application()
    
    async def handle(request):
        return web.Response(text="🚀 Advanced File Host Bot - Powered by Aiogram & Aiohttp!")
    
    app.router.add_get('/', handle)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 5000)
    await site.start()
    logger.info("🌐 Web server started on port 5000")

async def main():
    logger.info("🚀 Starting Advanced File Host Bot...")
    
    asyncio.create_task(web_server())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
