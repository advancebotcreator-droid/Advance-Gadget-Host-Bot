# ═══════════════════════════════════════════════════════════
#  GADGET PREMIUM HOST - Configuration Module
#  Owner: SHUVO HASSAN (@shuvohassan00)
#  Architecture: Production-Grade Async System
# ═══════════════════════════════════════════════════════════

import os
from typing import List, Dict

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔐 BOT CREDENTIALS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_TOKEN = "8472500254:AAGA4Y9GjVv_lhNaxZq5idt-sdOiLQmBG5A"  # Get from @BotFather

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 👑 OWNER CONFIGURATION (EXTREME SECURITY)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OWNER_ID = 7857957075  # SHUVO HASSAN
OWNER_USERNAME = "shuvohassan00"
ADMINS: List[int] = [OWNER_ID]  # Only owner has God Mode access

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📢 FORCE SUBSCRIBE CHANNELS (GATEKEEPER SYSTEM)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORCE_CHANNELS: List[Dict] = [
    {
        "name": "📢 Gadget Premium Zone",
        "username": "gadgetpremiumzone",
        "chat_id": -1003593905694,  # Replace with actual channel ID
        "invite_link": "https://t.me/gadgetpremiumzone",
        "type": "public"
    },
    {
        "name": "💎 VIP Premium Group",
        "username": None,  # Private channel
        "chat_id": -1002735546783,  # Replace with actual channel ID
        "invite_link": "https://t.me/+KKp8d5K5UyozNzI1",
        "type": "private"
    }
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💎 PREMIUM & ECONOMY SYSTEM
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FREE_BOT_SLOTS = 1  # Free users get 1 slot
PREMIUM_BOT_SLOTS = 999  # Premium = Unlimited
REFERRAL_BONUS_SLOTS = 1  # +1 slot per referral

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📁 FILE SYSTEM PATHS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "hosting_bot.db")
BOTS_DIR = os.path.join(BASE_DIR, "hosted_bots")
LOGS_DIR = os.path.join(BASE_DIR, "bot_logs")
GIT_REPOS_DIR = os.path.join(BASE_DIR, "git_repos")

# Create directories
for directory in [BOTS_DIR, LOGS_DIR, GIT_REPOS_DIR]:
    os.makedirs(directory, exist_ok=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎨 CYBERPUNK UI DESIGN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BOT_NAME = "⚡ GADGET PREMIUM HOST"

BANNER_CYBERPUNK = """
╔══════════════════════════════════╗
║  ⚡ GADGET PREMIUM HOST ⚡       ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ║
║  🚀 Next-Gen Bot Hosting         ║
║  💎 Unlimited Power              ║
║  🛡️ Military-Grade Security      ║
║  👑 Owner: @shuvohassan00        ║
╚══════════════════════════════════╝
"""

# Emojis for UI consistency
EMOJI = {
    "start": "▶️",
    "stop": "⏹",
    "restart": "🔄",
    "logs": "📜",
    "delete": "🗑",
    "upload": "📤",
    "premium": "💎",
    "referral": "👥",
    "server": "🖥️",
    "admin": "👑",
    "ban": "🚫",
    "maintenance": "🛠️",
    "shell": "💻",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "loading": "⏳",
    "lock": "🔒",
    "fire": "🔥"
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⚙️ SYSTEM CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MAINTENANCE_MODE = False  # Toggle with /maintenance command
PREMIUM_CHECK_INTERVAL = 3600  # Check premium expiry every hour
MAX_LOG_LINES = 100  # Max log lines to display
SHELL_TIMEOUT = 30  # Timeout for /exec commands (seconds)
GIT_CLONE_TIMEOUT = 300  # Git clone timeout (5 minutes)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔒 SECURITY SETTINGS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALLOWED_FILE_EXTENSIONS = [".py"]  # Only Python files
MAX_FILE_SIZE_MB = 10  # Maximum upload size
DANGEROUS_IMPORTS = ["os.system", "subprocess.call", "eval", "exec"]  # Warning check
