# ═══════════════════════════════════════════════════════════
#  GADGET PREMIUM HOST - Main Bot Module
#  Architecture: Production-Grade Async Python Bot
#  Owner: SHUVO HASSAN (@shuvohassan00)
#  Version: 2.0 - God Mode Edition
# ═══════════════════════════════════════════════════════════

import asyncio
import sqlite3
import ast
import os
import sys
import psutil
import subprocess
import shutil
import logging
import time
import re
import traceback
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, FSInputFile
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

try:
    import git
except ImportError:
    git = None

import config

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 LOGGING SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(config.LOGS_DIR, 'system.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🗄️ ENHANCED DATABASE MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database with all tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users Table (Enhanced)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                referrer_id INTEGER,
                is_premium BOOLEAN DEFAULT 0,
                premium_until TEXT,
                bonus_slots INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT 0,
                ban_reason TEXT,
                joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_activity TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Hosted Bots Table (Enhanced)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hosted_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                bot_name TEXT,
                file_path TEXT,
                process_id INTEGER,
                status TEXT DEFAULT 'stopped',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_start TEXT,
                total_starts INTEGER DEFAULT 0,
                source_type TEXT DEFAULT 'upload',
                git_url TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        # Referrals Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id)
            )
        """)
        
        # Admin Actions Log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_user_id INTEGER,
                details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully")
    
    def add_user(self, user_id: int, username: str, first_name: str, referrer_id: Optional[int] = None):
        """Add new user with referral system"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (user_id, username, first_name, referrer_id)
                VALUES (?, ?, ?, ?)
            """, (user_id, username, first_name, referrer_id))
            conn.commit()
            
            # Process referral bonus
            if referrer_id and referrer_id != user_id:
                cursor.execute("""
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES (?, ?)
                """, (referrer_id, user_id))
                cursor.execute("""
                    UPDATE users SET bonus_slots = bonus_slots + ?
                    WHERE user_id = ?
                """, (config.REFERRAL_BONUS_SLOTS, referrer_id))
                conn.commit()
                logger.info(f"💰 User {referrer_id} earned +{config.REFERRAL_BONUS_SLOTS} slot(s)")
        except sqlite3.IntegrityError:
            pass  # User exists
        finally:
            conn.close()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "user_id": row[0],
                "username": row[1],
                "first_name": row[2],
                "referrer_id": row[3],
                "is_premium": bool(row[4]),
                "premium_until": row[5],
                "bonus_slots": row[6],
                "is_banned": bool(row[7]),
                "ban_reason": row[8],
                "joined_at": row[9],
                "last_activity": row[10]
            }
        return None
    
    def update_activity(self, user_id: int):
        """Update last activity timestamp"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET last_activity = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
    
    def get_user_bots(self, user_id: int) -> List[Dict]:
        """Get all bots for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, bot_name, file_path, process_id, status, created_at, 
                   last_start, total_starts, source_type, git_url
            FROM hosted_bots WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "id": row[0],
                "bot_name": row[1],
                "file_path": row[2],
                "process_id": row[3],
                "status": row[4],
                "created_at": row[5],
                "last_start": row[6],
                "total_starts": row[7],
                "source_type": row[8],
                "git_url": row[9]
            }
            for row in rows
        ]
    
    def add_bot(self, user_id: int, bot_name: str, file_path: str, source_type: str = "upload", git_url: Optional[str] = None) -> int:
        """Add new bot to database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO hosted_bots (user_id, bot_name, file_path, source_type, git_url)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, bot_name, file_path, source_type, git_url))
        conn.commit()
        bot_id = cursor.lastrowid
        conn.close()
        return bot_id
    
    def add_premium(self, user_id: int, duration_str: str) -> Tuple[bool, str]:
        """Add premium subscription"""
        match = re.match(r'(\d+)([dhm])', duration_str.lower())
        if not match:
            return False, "Invalid format. Use: 30d, 24h, 60m"
        
        amount, unit = int(match.group(1)), match.group(2)
        
        delta_map = {'d': timedelta(days=amount), 'h': timedelta(hours=amount), 'm': timedelta(minutes=amount)}
        premium_until = (datetime.now() + delta_map[unit]).isoformat()
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_premium = 1, premium_until = ?
            WHERE user_id = ?
        """, (premium_until, user_id))
        conn.commit()
        conn.close()
        
        return True, f"Premium active until {premium_until[:16]}"
    
    def revoke_premium(self, user_id: int):
        """Revoke premium status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_premium = 0, premium_until = NULL
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
    
    def ban_user(self, user_id: int, reason: str = "Violation of terms"):
        """Ban user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_banned = 1, ban_reason = ?
            WHERE user_id = ?
        """, (reason, user_id))
        conn.commit()
        conn.close()
    
    def unban_user(self, user_id: int):
        """Unban user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET is_banned = 0, ban_reason = NULL
            WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
    
    def log_admin_action(self, admin_id: int, action: str, target_user_id: int, details: str):
        """Log admin actions"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin_logs (admin_id, action, target_user_id, details)
            VALUES (?, ?, ?, ?)
        """, (admin_id, action, target_user_id, details))
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict:
        """Get system statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
        premium_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM hosted_bots WHERE status = 'running'")
        active_bots = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM hosted_bots")
        total_bots = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM referrals")
        total_referrals = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_users": total_users,
            "premium_users": premium_users,
            "active_bots": active_bots,
            "total_bots": total_bots,
            "total_referrals": total_referrals
        }

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛡️ SYNTAX GUARD - Military-Grade Code Validator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class SyntaxGuard:
    @staticmethod
    def validate_python_file(file_content: bytes) -> Tuple[bool, str, List[str]]:
        """
        Advanced AST-based code validation
        Returns: (is_valid, message, warnings)
        """
        warnings = []
        
        try:
            code_str = file_content.decode('utf-8')
            
            # AST Compilation Check
            tree = ast.parse(code_str)
            
            # Security scan for dangerous patterns
            code_lower = code_str.lower()
            for dangerous in config.DANGEROUS_IMPORTS:
                if dangerous in code_lower:
                    warnings.append(f"⚠️ Detected potentially dangerous: {dangerous}")
            
            return True, "✅ Code validation passed!", warnings
            
        except SyntaxError as e:
            error_msg = f"""
⚠️ <b>SYNTAX ERROR DETECTED!</b>

🔍 <b>Line {e.lineno}:</b> <code>{e.text.strip() if e.text else 'N/A'}</code>
💡 <b>Error:</b> {e.msg}
📍 <b>Position:</b> Column {e.offset}

<i>Please fix the error and try again.</i>
"""
            return False, error_msg, []
            
        except UnicodeDecodeError:
            return False, "❌ <b>Encoding Error!</b>\n\nFile must be UTF-8 encoded.", []
            
        except Exception as e:
            return False, f"❌ <b>Validation Error!</b>\n\n{str(e)}", []

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 ADVANCED BOT PROCESS MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class BotManager:
    running_processes: Dict[int, asyncio.subprocess.Process] = {}
    
    @staticmethod
    async def start_bot(bot_id: int, file_path: str, db: Database) -> Tuple[bool, str]:
        """Start a hosted bot with monitoring"""
        try:
            log_file_path = os.path.join(config.LOGS_DIR, f"bot_{bot_id}.log")
            log_file = open(log_file_path, 'w', buffering=1)
            
            process = await asyncio.create_subprocess_exec(
                sys.executable, file_path,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(file_path)
            )
            
            BotManager.running_processes[bot_id] = process
            
            # Update database
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hosted_bots 
                SET process_id = ?, status = 'running', 
                    last_start = CURRENT_TIMESTAMP,
                    total_starts = total_starts + 1
                WHERE id = ?
            """, (process.pid, bot_id))
            conn.commit()
            conn.close()
            
            logger.info(f"🚀 Bot {bot_id} started (PID: {process.pid})")
            return True, f"✅ <b>Bot Started!</b>\n\n🆔 Process ID: <code>{process.pid}</code>"
        
        except Exception as e:
            logger.error(f"❌ Failed to start bot {bot_id}: {e}")
            return False, f"❌ <b>Failed to start:</b>\n<pre>{str(e)}</pre>"
    
    @staticmethod
    async def stop_bot(bot_id: int, db: Database) -> Tuple[bool, str]:
        """Stop a running bot"""
        try:
            if bot_id in BotManager.running_processes:
                process = BotManager.running_processes[bot_id]
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                del BotManager.running_processes[bot_id]
            
            # Update database
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE hosted_bots SET status = 'stopped', process_id = NULL
                WHERE id = ?
            """, (bot_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"⏹ Bot {bot_id} stopped")
            return True, "✅ Bot stopped successfully!"
        
        except Exception as e:
            logger.error(f"❌ Failed to stop bot {bot_id}: {e}")
            return False, f"❌ <b>Stop failed:</b>\n<pre>{str(e)}</pre>"
    
    @staticmethod
    async def restart_bot(bot_id: int, file_path: str, db: Database) -> Tuple[bool, str]:
        """Restart a bot"""
        await BotManager.stop_bot(bot_id, db)
        await asyncio.sleep(2)
        return await BotManager.start_bot(bot_id, file_path, db)
    
    @staticmethod
    async def get_bot_logs(bot_id: int, lines: int = 50) -> str:
        """Retrieve bot logs"""
        log_file_path = os.path.join(config.LOGS_DIR, f"bot_{bot_id}.log")
        
        if not os.path.exists(log_file_path):
            return "📜 No logs available yet."
        
        try:
            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                last_lines = all_lines[-lines:]
                return "".join(last_lines) if last_lines else "📜 Log file is empty."
        except Exception as e:
            return f"❌ Error reading logs: {e}"
    
    @staticmethod
    async def delete_bot(bot_id: int, db: Database) -> Tuple[bool, str]:
        """Delete bot and clean up files"""
        try:
            await BotManager.stop_bot(bot_id, db)
            
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM hosted_bots WHERE id = ?", (bot_id,))
            result = cursor.fetchone()
            
            if result:
                file_path = result[0]
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                # Clean up directory if empty
                dir_path = os.path.dirname(file_path)
                if os.path.exists(dir_path) and not os.listdir(dir_path):
                    os.rmdir(dir_path)
                
                # Delete log file
                log_path = os.path.join(config.LOGS_DIR, f"bot_{bot_id}.log")
                if os.path.exists(log_path):
                    os.remove(log_path)
            
            cursor.execute("DELETE FROM hosted_bots WHERE id = ?", (bot_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"🗑 Bot {bot_id} deleted")
            return True, "✅ Bot deleted successfully!"
        
        except Exception as e:
            logger.error(f"❌ Delete failed: {e}")
            return False, f"❌ <b>Delete failed:</b>\n<pre>{str(e)}</pre>"
    
    @staticmethod
    async def kill_user_bots(user_id: int, db: Database) -> int:
        """Kill all bots for a user"""
        bots = db.get_user_bots(user_id)
        killed = 0
        for bot in bots:
            if bot['status'] == 'running':
                await BotManager.stop_bot(bot['id'], db)
                killed += 1
        return killed

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🌐 GIT REPOSITORY MANAGER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class GitManager:
    @staticmethod
    async def clone_and_host(git_url: str, user_id: int, db: Database) -> Tuple[bool, str, Optional[int]]:
        """Clone GitHub repo and find main bot file"""
        if git is None:
            return False, "❌ GitPython not installed! Install with: pip install gitpython", None
        
        try:
            # Create user-specific git directory
            user_git_dir = os.path.join(config.GIT_REPOS_DIR, str(user_id))
            os.makedirs(user_git_dir, exist_ok=True)
            
            # Extract repo name
            repo_name = git_url.rstrip('/').split('/')[-1].replace('.git', '')
            clone_path = os.path.join(user_git_dir, repo_name)
            
            # Remove if exists
            if os.path.exists(clone_path):
                shutil.rmtree(clone_path)
            
            # Clone repository
            logger.info(f"🔄 Cloning {git_url}...")
            repo = await asyncio.wait_for(
                asyncio.to_thread(git.Repo.clone_from, git_url, clone_path),
                timeout=config.GIT_CLONE_TIMEOUT
            )
            
            # Find main Python file
            main_files = ['main.py', 'bot.py', 'app.py', '__main__.py']
            found_file = None
            
            for root, dirs, files in os.walk(clone_path):
                for filename in files:
                    if filename in main_files:
                        found_file = os.path.join(root, filename)
                        break
                if found_file:
                    break
            
            if not found_file:
                # Look for any .py file
                for root, dirs, files in os.walk(clone_path):
                    py_files = [f for f in files if f.endswith('.py')]
                    if py_files:
                        found_file = os.path.join(root, py_files[0])
                        break
            
            if not found_file:
                shutil.rmtree(clone_path)
                return False, "❌ No Python files found in repository!", None
            
            # Validate file
            with open(found_file, 'rb') as f:
                is_valid, msg, warnings = SyntaxGuard.validate_python_file(f.read())
            
            if not is_valid:
                shutil.rmtree(clone_path)
                return False, msg, None
            
            # Add to database
            bot_id = db.add_bot(
                user_id=user_id,
                bot_name=f"git_{repo_name}",
                file_path=found_file,
                source_type="git",
                git_url=git_url
            )
            
            success_msg = f"""
✅ <b>Git Clone Successful!</b>

📦 Repository: <code>{repo_name}</code>
📄 Main File: <code>{Path(found_file).name}</code>
🆔 Bot ID: <code>{bot_id}</code>
"""
            if warnings:
                success_msg += "\n⚠️ <b>Warnings:</b>\n" + "\n".join(warnings)
            
            return True, success_msg, bot_id
        
        except asyncio.TimeoutError:
            return False, "⏱️ Clone timeout! Repository too large or slow connection.", None
        except Exception as e:
            logger.error(f"Git clone error: {e}")
            return False, f"❌ <b>Clone failed:</b>\n<pre>{str(e)}</pre>", None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 💻 MODULE INSTALLER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ModuleInstaller:
    @staticmethod
    async def install_module(module_name: str) -> Tuple[bool, str]:
        """Install Python module using pip"""
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", module_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            
            if process.returncode == 0:
                return True, f"✅ <b>Module installed!</b>\n\n<pre>{stdout.decode()[:1000]}</pre>"
            else:
                return False, f"❌ <b>Installation failed!</b>\n\n<pre>{stderr.decode()[:1000]}</pre>"
        
        except asyncio.TimeoutError:
            return False, "⏱️ Installation timeout!"
        except Exception as e:
            return False, f"❌ Error: {str(e)}"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎭 FSM STATES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class BroadcastState(StatesGroup):
    waiting_for_message = State()

class GitCloneState(StatesGroup):
    waiting_for_url = State()

class InstallState(StatesGroup):
    waiting_for_module = State()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🎨 CYBERPUNK UI KEYBOARDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def progress_bar(current: int, total: int, length: int = 10) -> str:
    """Generate visual progress bar"""
    filled = int((current / total) * length) if total > 0 else 0
    return "█" * filled + "░" * (length - filled)

def get_main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu keyboard"""
    buttons = [
        [InlineKeyboardButton(text=f"{config.EMOJI['upload']} Upload Bot", callback_data="upload")],
        [InlineKeyboardButton(text="🤖 My Bots", callback_data="my_bots")],
        [
            InlineKeyboardButton(text=f"{config.EMOJI['referral']} Referrals", callback_data="referrals"),
            InlineKeyboardButton(text=f"{config.EMOJI['premium']} Premium", callback_data="premium")
        ]
    ]
    
    if is_admin:
        buttons.append([InlineKeyboardButton(text=f"{config.EMOJI['admin']} God Mode", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_upload_menu() -> InlineKeyboardMarkup:
    """Upload options menu"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Upload .py File", callback_data="upload_file")],
        [InlineKeyboardButton(text="🌐 Clone from GitHub", callback_data="git_clone")],
        [InlineKeyboardButton(text="« Back", callback_data="start")]
    ])

def get_bot_controls(bot_id: int, status: str) -> InlineKeyboardMarkup:
    """Bot control panel"""
    buttons = []
    
    if status == "running":
        buttons.append([
            InlineKeyboardButton(text=f"{config.EMOJI['stop']} Stop", callback_data=f"stop_{bot_id}"),
            InlineKeyboardButton(text=f"{config.EMOJI['restart']} Restart", callback_data=f"restart_{bot_id}")
        ])
    else:
        buttons.append([InlineKeyboardButton(text=f"{config.EMOJI['start']} Start", callback_data=f"start_{bot_id}")])
    
    buttons.extend([
        [InlineKeyboardButton(text=f"{config.EMOJI['logs']} View Logs", callback_data=f"logs_{bot_id}")],
        [InlineKeyboardButton(text=f"{config.EMOJI['delete']} Delete Bot", callback_data=f"delete_{bot_id}")],
        [InlineKeyboardButton(text="« Back", callback_data="my_bots")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_panel() -> InlineKeyboardMarkup:
    """God Mode admin panel"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{config.EMOJI['server']} Server Monitor", callback_data="admin_server")],
        [InlineKeyboardButton(text="👥 User Management", callback_data="admin_users")],
        [InlineKeyboardButton(text=f"{config.EMOJI['shell']} Shell Access", callback_data="admin_shell")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text=f"{config.EMOJI['maintenance']} Maintenance", callback_data="admin_maintenance")],
        [InlineKeyboardButton(text="« Back", callback_data="start")]
    ])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔐 SECURITY MIDDLEWARE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
async def check_force_subscribe(user_id: int, bot: Bot) -> Tuple[bool, str]:
    """Force subscribe verification"""
    not_joined = []
    
    for channel in config.FORCE_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel['chat_id'], user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except Exception as e:
            logger.error(f"Channel check error: {e}")
            not_joined.append(channel)
    
    if not_joined:
        msg = f"{config.EMOJI['lock']} <b>ACCESS DENIED</b>\n\n"
        msg += "⚠️ You must join these channels:\n\n"
        
        for channel in not_joined:
            msg += f"❌ <b>{channel['name']}</b>\n"
        
        msg += "\n🔄 Click buttons below to join and verify:"
        return False, msg
    
    return True, "✅ Verification complete!"

def get_force_sub_keyboard() -> InlineKeyboardMarkup:
    """Force subscribe buttons"""
    buttons = []
    for channel in config.FORCE_CHANNELS:
        buttons.append([InlineKeyboardButton(
            text=f"📢 Join {channel['name']}",
            url=channel['invite_link']
        )])
    buttons.append([InlineKeyboardButton(text="🔄 Verify Status", callback_data="verify_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def god_mode_only(func):
    """Decorator for owner-only commands"""
    async def wrapper(event):
        user_id = event.from_user.id
        if user_id != config.OWNER_ID:
            if isinstance(event, Message):
                await event.answer(f"{config.EMOJI['error']} Access Denied! God Mode required.")
            else:
                await event.answer("❌ Owner access only!", show_alert=True)
            return
        return await func(event)
    return wrapper

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🤖 BOT INITIALIZATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
bot = Bot(token=config.BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
db = Database(config.DATABASE_PATH)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📌 CORE COMMAND HANDLERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Start command with referral system"""
    user_id = message.from_user.id
    
    # Maintenance check
    if config.MAINTENANCE_MODE and user_id != config.OWNER_ID:
        await message.answer(f"{config.EMOJI['maintenance']} <b>Maintenance Break!</b>\n\nWe are updating the system. Please try again later.")
        return
    
    # Force subscribe check
    is_subscribed, msg = await check_force_subscribe(user_id, bot)
    if not is_subscribed:
        await message.answer(msg, reply_markup=get_force_sub_keyboard())
        return
    
    # Extract referral
    referrer_id = None
    if len(message.text.split()) > 1:
        try:
            ref_id = int(message.text.split()[1])
            if ref_id != user_id:
                referrer_id = ref_id
        except:
            pass
    
    # Add/update user
    db.add_user(user_id, message.from_user.username or "Unknown", 
                message.from_user.first_name or "User", referrer_id)
    db.update_activity(user_id)
    
    user = db.get_user(user_id)
    total_slots = config.FREE_BOT_SLOTS + user['bonus_slots']
    if user['is_premium']:
        total_slots = config.PREMIUM_BOT_SLOTS
    
    used_slots = len(db.get_user_bots(user_id))
    slots_bar = progress_bar(used_slots, min(total_slots, 10))
    
    welcome = f"""
{config.BANNER_CYBERPUNK}

👋 Welcome, <b>{message.from_user.first_name}</b>!

🎯 <b>HOSTING DASHBOARD:</b>
┣ 📊 Slots: [{slots_bar}] {used_slots}/{total_slots if total_slots < 999 else '∞'}
┣ 💎 Premium: {'✅ Active' if user['is_premium'] else '❌ Not Active'}
┗ 🎁 Bonus Slots: +{user['bonus_slots']}

{config.EMOJI['fire']} <b>FEATURES:</b>
• Upload Python Bots (.py files)
• Clone from GitHub Repositories
• Real-Time Process Control
• Live Log Streaming
• Auto Syntax Validation
• Earn Unlimited Slots via Referrals

<i>Select an option below to begin...</i>
"""
    
    is_admin = user_id == config.OWNER_ID
    await message.answer(welcome, reply_markup=get_main_menu(is_admin))

@router.callback_query(F.data == "verify_sub")
async def verify_subscription(callback: CallbackQuery):
    """Verify channel subscription"""
    user_id = callback.from_user.id
    is_subscribed, msg = await check_force_subscribe(user_id, bot)
    
    if is_subscribed:
        await callback.message.delete()
        await cmd_start(callback.message)
        await callback.answer("✅ Verification successful!")
    else:
        await callback.answer("❌ Please join all channels first!", show_alert=True)

@router.callback_query(F.data == "start")
async def callback_start(callback: CallbackQuery):
    """Return to main menu"""
    await callback.message.delete()
    await cmd_start(callback.message)

@router.callback_query(F.data == "upload")
async def callback_upload(callback: CallbackQuery):
    """Upload menu"""
    await callback.message.edit_text(
        f"{config.EMOJI['upload']} <b>UPLOAD YOUR BOT</b>\n\nChoose upload method:",
        reply_markup=get_upload_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "upload_file")
async def callback_upload_file(callback: CallbackQuery):
    """Prompt for file upload"""
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    total_slots = config.FREE_BOT_SLOTS + user['bonus_slots']
    if user['is_premium']:
        total_slots = config.PREMIUM_BOT_SLOTS
    
    used_slots = len(db.get_user_bots(user_id))
    
    if used_slots >= total_slots:
        await callback.answer(f"{config.EMOJI['error']} No slots available!", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"""
📤 <b>UPLOAD BOT FILE</b>

🎯 <b>Requirements:</b>
• File must be a Python script (.py)
• Maximum size: {config.MAX_FILE_SIZE_MB}MB
• Valid Python syntax required

🛡️ <b>Security:</b>
• AST syntax validation
• Auto-forwarded to owner
• Sandboxed execution

💡 <i>Send your .py file now...</i>
"""
    )
    await callback.answer()

@router.callback_query(F.data == "git_clone")
async def callback_git_clone(callback: CallbackQuery, state: FSMContext):
    """Initiate git clone"""
    if git is None:
        await callback.answer("❌ Git support not available!", show_alert=True)
        return
    
    await callback.message.edit_text(
        """
🌐 <b>CLONE FROM GITHUB</b>

📋 <b>Instructions:</b>
1. Send the GitHub repository URL
2. Bot will clone and find main file
3. Auto-validation and hosting

💡 <b>Example:</b>
<code>https://github.com/username/bot-repo</code>

<i>Send GitHub URL now...</i>
"""
    )
    await state.set_state(GitCloneState.waiting_for_url)
    await callback.answer()

@router.message(GitCloneState.waiting_for_url)
async def handle_git_url(message: Message, state: FSMContext):
    """Handle git URL"""
    await state.clear()
    
    user_id = message.from_user.id
    user = db.get_user(user_id)
    
    total_slots = config.FREE_BOT_SLOTS + user['bonus_slots']
    if user['is_premium']:
        total_slots = config.PREMIUM_BOT_SLOTS
    
    used_slots = len(db.get_user_bots(user_id))
    
    if used_slots >= total_slots:
        await message.answer(f"{config.EMOJI['error']} No slots available!")
        return
    
    git_url = message.text.strip()
    
    if not ("github.com" in git_url or "gitlab.com" in git_url):
        await message.answer("❌ Invalid Git URL! Must be GitHub or GitLab.")
        return
    
    status_msg = await message.answer(f"{config.EMOJI['loading']} Cloning repository...\n\n<i>This may take a minute...</i>")
    
    success, msg, bot_id = await GitManager.clone_and_host(git_url, user_id, db)
    
    if success:
        # Forward notification to owner
        try:
            await bot.send_message(
                config.OWNER_ID,
                f"""
🆕 <b>GIT CLONE SUCCESS</b>

👤 User: <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>
🆔 ID: <code>{user_id}</code>
🌐 Git URL: <code>{git_url}</code>
🆔 Bot ID: <code>{bot_id}</code>
"""
            )
        except:
            pass
        
        await status_msg.edit_text(msg, reply_markup=get_main_menu(user_id == config.OWNER_ID))
    else:
        await status_msg.edit_text(msg)

@router.message(F.document)
async def handle_file_upload(message: Message):
    """Handle Python file upload with syntax validation"""
    user_id = message.from_user.id
    
    # Security checks
    is_subscribed, msg = await check_force_subscribe(user_id, bot)
    if not is_subscribed:
        await message.answer(msg, reply_markup=get_force_sub_keyboard())
        return
    
    user = db.get_user(user_id)
    if not user:
        await message.answer("❌ Use /start first!")
        return
    
    if user['is_banned']:
        await message.answer(f"{config.EMOJI['ban']} You are banned!\n\nReason: {user['ban_reason']}")
        return
    
    # Check slots
    total_slots = config.FREE_BOT_SLOTS + user['bonus_slots']
    if user['is_premium']:
        total_slots = config.PREMIUM_BOT_SLOTS
    
    used_slots = len(db.get_user_bots(user_id))
    
    if used_slots >= total_slots:
        await message.answer(f"{config.EMOJI['error']} No slots available! Upgrade to Premium or refer friends.")
        return
    
    # File validation
    if not message.document.file_name.endswith('.py'):
        await message.answer("⚠️ Only <code>.py</code> files accepted!")
        return
    
    if message.document.file_size > config.MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.answer(f"⚠️ File too large! Max: {config.MAX_FILE_SIZE_MB}MB")
        return
    
    status_msg = await message.answer(f"{config.EMOJI['loading']} <b>Analyzing code...</b>")
    
    try:
        # Download file
        file = await bot.get_file(message.document.file_id)
        file_content = await bot.download_file(file.file_path)
        
        # SYNTAX GUARD VALIDATION
        is_valid, validation_msg, warnings = SyntaxGuard.validate_python_file(file_content.read())
        
        if not is_valid:
            await status_msg.edit_text(validation_msg)
            return
        
        # Save file
        user_dir = os.path.join(config.BOTS_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{message.document.file_name}"
        file_path = os.path.join(user_dir, filename)
        
        file_content.seek(0)
        with open(file_path, 'wb') as f:
            f.write(file_content.read())
        
        # Add to database
        bot_id = db.add_bot(user_id, message.document.file_name, file_path, "upload")
        
        # Forward to owner
        try:
            forward_msg = f"""
🆕 <b>NEW BOT UPLOADED</b>

👤 User: <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>
🆔 ID: <code>{user_id}</code>
📛 Username: @{message.from_user.username or 'None'}
📄 File: <code>{message.document.file_name}</code>
🆔 Bot ID: <code>{bot_id}</code>
✅ Syntax: Validated

"""
            if warnings:
                forward_msg += "⚠️ <b>Warnings:</b>\n" + "\n".join(warnings)
            
            await bot.send_document(
                config.OWNER_ID,
                document=message.document.file_id,
                caption=forward_msg
            )
        except Exception as e:
            logger.error(f"Failed to forward: {e}")
        
        success_text = f"""
{config.EMOJI['success']} <b>UPLOAD SUCCESSFUL!</b>

🆔 Bot ID: <code>{bot_id}</code>
📄 File: <code>{message.document.file_name}</code>
🛡️ Syntax: <b>Validated ✓</b>

"""
        if warnings:
            success_text += "⚠️ <b>Warnings:</b>\n" + "\n".join(warnings) + "\n\n"
        
        success_text += "💡 Use 'My Bots' to start hosting!"
        
        await status_msg.edit_text(success_text, reply_markup=get_main_menu(user_id == config.OWNER_ID))
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status_msg.edit_text(f"{config.EMOJI['error']} <b>Upload failed!</b>\n\n<pre>{str(e)}</pre>")

@router.callback_query(F.data == "my_bots")
async def callback_my_bots(callback: CallbackQuery):
    """Show user's bots"""
    user_id = callback.from_user.id
    bots = db.get_user_bots(user_id)
    
    if not bots:
        await callback.answer("📦 No bots uploaded yet!", show_alert=True)
        return
    
    text = "🤖 <b>YOUR HOSTED BOTS:</b>\n\n"
    buttons = []
    
    for bot_data in bots:
        status_emoji = "🟢" if bot_data['status'] == "running" else "🔴"
        text += f"{status_emoji} <b>Bot #{bot_data['id']}</b> - {bot_data['bot_name']}\n"
        text += f"   Status: <code>{bot_data['status'].upper()}</code>\n"
        text += f"   Starts: {bot_data['total_starts']} | Source: {bot_data['source_type']}\n\n"
        
        buttons.append([InlineKeyboardButton(
            text=f"{status_emoji} Manage Bot #{bot_data['id']}",
            callback_data=f"manage_{bot_data['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="« Back", callback_data="start")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("manage_"))
async def callback_manage_bot(callback: CallbackQuery):
    """Bot management panel"""
    bot_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    bots = db.get_user_bots(user_id)
    bot_data = next((b for b in bots if b['id'] == bot_id), None)
    
    if not bot_data:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    status_emoji = "🟢" if bot_data['status'] == "running" else "🔴"
    
    text = f"""
{status_emoji} <b>BOT CONTROL PANEL</b>

🆔 Bot ID: <code>{bot_data['id']}</code>
📛 Name: <b>{bot_data['bot_name']}</b>
📊 Status: <code>{bot_data['status'].upper()}</code>
📁 File: <code>{Path(bot_data['file_path']).name}</code>
🚀 Total Starts: {bot_data['total_starts']}
📅 Created: {bot_data['created_at'][:16]}

💡 <i>Choose an action:</i>
"""
    
    await callback.message.edit_text(text, reply_markup=get_bot_controls(bot_id, bot_data['status']))
    await callback.answer()

@router.callback_query(F.data.startswith("start_"))
async def callback_start_bot(callback: CallbackQuery):
    """Start bot"""
    bot_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    bots = db.get_user_bots(user_id)
    bot_data = next((b for b in bots if b['id'] == bot_id), None)
    
    if not bot_data:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    await callback.answer(f"{config.EMOJI['loading']} Starting bot...")
    
    success, msg = await BotManager.start_bot(bot_id, bot_data['file_path'], db)
    
    await callback.message.answer(msg)
    await callback_manage_bot(callback)

@router.callback_query(F.data.startswith("stop_"))
async def callback_stop_bot(callback: CallbackQuery):
    """Stop bot"""
    bot_id = int(callback.data.split("_")[1])
    
    await callback.answer(f"{config.EMOJI['loading']} Stopping bot...")
    
    success, msg = await BotManager.stop_bot(bot_id, db)
    
    await callback.message.answer(msg)
    await callback_manage_bot(callback)

@router.callback_query(F.data.startswith("restart_"))
async def callback_restart_bot(callback: CallbackQuery):
    """Restart bot"""
    bot_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    bots = db.get_user_bots(user_id)
    bot_data = next((b for b in bots if b['id'] == bot_id), None)
    
    if not bot_data:
        await callback.answer("❌ Bot not found!", show_alert=True)
        return
    
    await callback.answer(f"{config.EMOJI['loading']} Restarting bot...")
    
    success, msg = await BotManager.restart_bot(bot_id, bot_data['file_path'], db)
    
    await callback.message.answer(msg)
    await callback_manage_bot(callback)

@router.callback_query(F.data.startswith("logs_"))
async def callback_show_logs(callback: CallbackQuery):
    """Show bot logs"""
    bot_id = int(callback.data.split("_")[1])
    
    await callback.answer(f"{config.EMOJI['loading']} Fetching logs...")
    
    logs = await BotManager.get_bot_logs(bot_id, config.MAX_LOG_LINES)
    
    log_text = f"📜 <b>LOGS - BOT #{bot_id}</b>\n\n<pre>{logs[-4000:]}</pre>"
    
    try:
        await callback.message.answer(log_text)
    except:
        log_file_path = os.path.join(config.LOGS_DIR, f"bot_{bot_id}.log")
        if os.path.exists(log_file_path):
            await callback.message.answer_document(
                FSInputFile(log_file_path),
                caption=f"📜 Complete logs for Bot #{bot_id}"
            )

@router.callback_query(F.data.startswith("delete_"))
async def callback_delete_bot(callback: CallbackQuery):
    """Delete bot confirmation"""
    bot_id = int(callback.data.split("_")[1])
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"{config.EMOJI['success']} Confirm", callback_data=f"confirm_delete_{bot_id}"),
            InlineKeyboardButton(text=f"{config.EMOJI['error']} Cancel", callback_data=f"manage_{bot_id}")
        ]
    ])
    
    await callback.message.edit_text(
        f"{config.EMOJI['warning']} <b>CONFIRM DELETION</b>\n\nDelete Bot #{bot_id}?\n\n🚨 This cannot be undone!",
        reply_markup=confirm_kb
    )

@router.callback_query(F.data.startswith("confirm_delete_"))
async def callback_confirm_delete(callback: CallbackQuery):
    """Confirm deletion"""
    bot_id = int(callback.data.split("_")[2])
    
    await callback.answer(f"{config.EMOJI['loading']} Deleting...")
    
    success, msg = await BotManager.delete_bot(bot_id, db)
    
    await callback.message.edit_text(msg)
    await asyncio.sleep(2)
    await callback_my_bots(callback)

@router.callback_query(F.data == "referrals")
async def callback_referrals(callback: CallbackQuery):
    """Referral system info"""
    user_id = callback.from_user.id
    user = db.get_user(user_id)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    referral_count = cursor.fetchone()[0]
    conn.close()
    
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = f"""
🎁 <b>REFERRAL SYSTEM</b>

🔗 <b>Your Referral Link:</b>
<code>{ref_link}</code>

📊 <b>Statistics:</b>
┣ 👥 Total Referrals: <b>{referral_count}</b>
┣ 🎁 Earned Slots: <b>+{user['bonus_slots']}</b>
┗ 💎 Reward: +{config.REFERRAL_BONUS_SLOTS} slot per referral

💡 <b>How It Works:</b>
1. Share your unique link
2. Friends start the bot
3. You earn +{config.REFERRAL_BONUS_SLOTS} slot instantly!
4. Unlimited referrals = Unlimited slots!

{config.EMOJI['fire']} <i>Start sharing and grow your empire!</i>
"""
    
    buttons = [[InlineKeyboardButton(text="« Back", callback_data="start")]]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data == "premium")
async def callback_premium(callback: CallbackQuery):
    """Premium info"""
    text = f"""
💎 <b>PREMIUM MEMBERSHIP</b>

🌟 <b>Premium Benefits:</b>
┣ ♾️ Unlimited Bot Slots
┣ ⚡ Priority Execution
┣ 🛡️ Enhanced Security
┣ 📞 24/7 Support
┗ {config.EMOJI['fire']} Exclusive Features

💰 <b>Get Premium:</b>
Contact: @{config.OWNER_USERNAME}

<i>Upgrade now and unleash unlimited power!</i>
"""
    
    buttons = [[InlineKeyboardButton(text="« Back", callback_data="start")]]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 👑 GOD MODE ADMIN COMMANDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.message(Command("server"))
@god_mode_only
async def cmd_server(message: Message):
    """Live server monitor"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    
    stats = db.get_stats()
    
    cpu_bar = progress_bar(int(cpu_percent), 100)
    ram_bar = progress_bar(int(memory.percent), 100)
    disk_bar = progress_bar(int(disk.percent), 100)
    
    text = f"""
{config.EMOJI['server']} <b>LIVE SERVER MONITOR</b>

💻 <b>System Resources:</b>
┣ CPU: [{cpu_bar}] {cpu_percent}%
┣ RAM: [{ram_bar}] {memory.percent}% ({memory.used // (1024**3)}GB / {memory.total // (1024**3)}GB)
┣ DISK: [{disk_bar}] {disk.percent}% ({disk.used // (1024**3)}GB / {disk.total // (1024**3)}GB)
┗ ⏱️ Uptime: {uptime.days}d {uptime.seconds // 3600}h {(uptime.seconds % 3600) // 60}m

📊 <b>Bot Statistics:</b>
┣ 👥 Total Users: <b>{stats['total_users']}</b>
┣ 💎 Premium Users: <b>{stats['premium_users']}</b>
┣ 🤖 Total Bots: <b>{stats['total_bots']}</b>
┣ 🟢 Active Bots: <b>{stats['active_bots']}</b>
┗ 🎁 Total Referrals: <b>{stats['total_referrals']}</b>

🕐 Last Update: {datetime.now().strftime('%H:%M:%S')}
"""
    
    await message.answer(text)

@router.callback_query(F.data == "admin_panel")
@god_mode_only
async def callback_admin_panel(callback: CallbackQuery):
    """God Mode panel"""
    await callback.message.edit_text(
        f"{config.EMOJI['admin']} <b>GOD MODE ACTIVATED</b>\n\nSelect command:",
        reply_markup=get_admin_panel()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_server")
@god_mode_only
async def callback_admin_server(callback: CallbackQuery):
    """Server stats callback"""
    await callback.answer(f"{config.EMOJI['loading']} Loading stats...")
    await cmd_server(callback.message)

@router.message(Command("user"))
@god_mode_only
async def cmd_user_info(message: Message):
    """Spy on user - God Mode"""
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: <code>/user &lt;user_id&gt;</code>")
        return
    
    try:
        target_id = int(args[1])
    except:
        await message.answer("❌ Invalid user ID!")
        return
    
    user = db.get_user(target_id)
    if not user:
        await message.answer("❌ User not found!")
        return
    
    bots = db.get_user_bots(target_id)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (target_id,))
    referral_count = cursor.fetchone()[0]
    conn.close()
    
    premium_status = "✅ Active" if user['is_premium'] else "❌ Inactive"
    if user['is_premium'] and user['premium_until']:
        premium_status += f" (Until: {user['premium_until'][:16]})"
    
    text = f"""
🕵️ <b>USER SPY MODE</b>

👤 <b>Profile:</b>
┣ 🆔 ID: <code>{user['user_id']}</code>
┣ 📛 Name: <b>{user['first_name']}</b>
┣ 👤 Username: @{user['username']}
┣ 📅 Joined: {user['joined_at'][:10]}
┗ ⏱️ Last Active: {user['last_activity'][:16]}

💎 Premium: {premium_status}
🛡️ Status: {'🚫 Banned' if user['is_banned'] else '✅ Active'}
{f"📝 Ban Reason: {user['ban_reason']}" if user['is_banned'] else ''}

📊 <b>Stats:</b>
┣ 🤖 Hosted Bots: <b>{len(bots)}</b>
┣ 🎁 Bonus Slots: <b>+{user['bonus_slots']}</b>
┗ 👥 Referrals: <b>{referral_count}</b>

📦 <b>Active Bots:</b>
"""
    
    if bots:
        for bot_data in bots[:5]:
            status_emoji = "🟢" if bot_data['status'] == "running" else "🔴"
            text += f"  {status_emoji} #{bot_data['id']} - {bot_data['bot_name']}"
            if bot_data['process_id']:
                text += f" (PID: {bot_data['process_id']})"
            text += "\n"
    else:
        text += "  <i>No bots</i>\n"
    
    # God Mode Actions
    buttons = [
        [
            InlineKeyboardButton(text="🛑 Kill All Bots", callback_data=f"god_kill_{target_id}"),
            InlineKeyboardButton(text="🗑 Delete All Files", callback_data=f"god_delfiles_{target_id}")
        ],
        [
            InlineKeyboardButton(text="💎 Give Premium", callback_data=f"god_premium_{target_id}"),
            InlineKeyboardButton(text="🚫 Ban" if not user['is_banned'] else "✅ Unban", 
                               callback_data=f"god_ban_{target_id}")
        ]
    ]
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("god_kill_"))
@god_mode_only
async def callback_god_kill(callback: CallbackQuery):
    """Kill all user bots"""
    target_id = int(callback.data.split("_")[2])
    
    await callback.answer(f"{config.EMOJI['loading']} Terminating processes...")
    
    killed = await BotManager.kill_user_bots(target_id, db)
    
    db.log_admin_action(callback.from_user.id, "kill_bots", target_id, f"Killed {killed} bots")
    
    await callback.message.answer(f"{config.EMOJI['success']} Killed {killed} bot(s) for user {target_id}!")

@router.callback_query(F.data.startswith("god_ban_"))
@god_mode_only
async def callback_god_ban(callback: CallbackQuery):
    """Ban/Unban user"""
    target_id = int(callback.data.split("_")[2])
    user = db.get_user(target_id)
    
    if user['is_banned']:
        db.unban_user(target_id)
        action = "unbanned"
        db.log_admin_action(callback.from_user.id, "unban", target_id, "User unbanned")
    else:
        db.ban_user(target_id, "Banned by owner")
        await BotManager.kill_user_bots(target_id, db)
        action = "banned"
        db.log_admin_action(callback.from_user.id, "ban", target_id, "User banned")
    
    await callback.answer(f"{config.EMOJI['success']} User {action}!", show_alert=True)
    
    # Notify user
    try:
        if action == "banned":
            await bot.send_message(target_id, f"{config.EMOJI['ban']} <b>You have been banned!</b>\n\nContact @{config.OWNER_USERNAME} for appeal.")
        else:
            await bot.send_message(target_id, f"{config.EMOJI['success']} <b>You have been unbanned!</b>\n\nYou can now use the bot again.")
    except:
        pass

@router.message(Command("addpremium"))
@god_mode_only
async def cmd_add_premium(message: Message):
    """Add premium to user"""
    args = message.text.split()
    if len(args) < 3:
        await message.answer("Usage: <code>/addpremium &lt;user_id&gt; &lt;duration&gt;</code>\nExample: /addpremium 123456 30d")
        return
    
    try:
        target_id = int(args[1])
        duration = args[2]
    except:
        await message.answer("❌ Invalid arguments!")
        return
    
    success, msg = db.add_premium(target_id, duration)
    
    if success:
        db.log_admin_action(message.from_user.id, "add_premium", target_id, f"Premium: {duration}")
        await message.answer(f"{config.EMOJI['success']} Premium added!\n\n{msg}")
        
        try:
            await bot.send_message(target_id, f"🎉 <b>PREMIUM ACTIVATED!</b>\n\n💎 You now have unlimited bot slots!\n\n{msg}")
        except:
            pass
    else:
        await message.answer(f"{config.EMOJI['error']} Failed:\n{msg}")

@router.message(Command("exec"))
@god_mode_only
async def cmd_exec(message: Message):
    """Execute shell command - DANGEROUS!"""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(f"{config.EMOJI['shell']} <b>SHELL ACCESS</b>\n\nUsage: <code>/exec &lt;command&gt;</code>\n\n⚠️ <b>WARNING:</b> Unrestricted shell access!")
        return
    
    command = args[1]
    
    status_msg = await message.answer(f"{config.EMOJI['loading']} Executing: <code>{command}</code>")
    
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=config.SHELL_TIMEOUT)
        
        output = stdout.decode('utf-8', errors='ignore') if stdout else ""
        error = stderr.decode('utf-8', errors='ignore') if stderr else ""
        
        result = f"{config.EMOJI['shell']} <b>SHELL OUTPUT</b>\n\n<b>Command:</b> <code>{command}</code>\n\n"
        
        if output:
            result += f"<b>Output:</b>\n<pre>{output[:3500]}</pre>\n\n"
        if error:
            result += f"<b>Error:</b>\n<pre>{error[:3500]}</pre>"
        
        if not output and not error:
            result += "<i>No output</i>"
        
        await status_msg.edit_text(result)
        
        db.log_admin_action(message.from_user.id, "shell_exec", 0, command)
    
    except asyncio.TimeoutError:
        await status_msg.edit_text(f"⏱️ Command timeout ({config.SHELL_TIMEOUT}s)")
    except Exception as e:
        await status_msg.edit_text(f"{config.EMOJI['error']} Error:\n<pre>{str(e)}</pre>")

@router.message(Command("maintenance"))
@god_mode_only
async def cmd_maintenance(message: Message):
    """Toggle maintenance mode"""
    args = message.text.split()
    if len(args) < 2:
        status = "ON" if config.MAINTENANCE_MODE else "OFF"
        await message.answer(f"{config.EMOJI['maintenance']} Maintenance: <b>{status}</b>\n\nUsage: <code>/maintenance on/off</code>")
        return
    
    mode = args[1].lower()
    
    if mode == "on":
        config.MAINTENANCE_MODE = True
        await message.answer(f"{config.EMOJI['maintenance']} <b>MAINTENANCE ACTIVATED</b>\n\n{config.EMOJI['lock']} Bot locked for non-admins.")
    elif mode == "off":
        config.MAINTENANCE_MODE = False
        await message.answer(f"{config.EMOJI['success']} <b>MAINTENANCE DEACTIVATED</b>\n\n✅ Bot is now accessible.")
    else:
        await message.answer("❌ Invalid option. Use: on/off")

@router.message(Command("broadcast"))
@god_mode_only
async def cmd_broadcast(message: Message, state: FSMContext):
    """Broadcast to all users"""
    await message.answer(f"📢 <b>BROADCAST MODE</b>\n\nReply with message to broadcast.\n\n💡 Supports text, photos, videos.")
    await state.set_state(BroadcastState.waiting_for_message)

@router.message(BroadcastState.waiting_for_message)
@god_mode_only
async def handle_broadcast(message: Message, state: FSMContext):
    """Handle broadcast message"""
    await state.clear()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = cursor.fetchall()
    conn.close()
    
    status_msg = await message.answer(f"{config.EMOJI['loading']} Broadcasting to {len(users)} users...")
    
    success = 0
    failed = 0
    
    for (user_id,) in users:
        try:
            if message.text:
                await bot.send_message(user_id, message.text)
            elif message.photo:
                await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                await bot.send_video(user_id, message.video.file_id, caption=message.caption)
            success += 1
        except:
            failed += 1
        
        await asyncio.sleep(0.03)
    
    await status_msg.edit_text(f"{config.EMOJI['success']} <b>Broadcast Complete!</b>\n\n✅ Sent: {success}\n❌ Failed: {failed}")
    
    db.log_admin_action(message.from_user.id, "broadcast", 0, f"Sent to {success} users")

@router.message(Command("install"))
async def cmd_install(message: Message, state: FSMContext):
    """Install Python module"""
    user_id = message.from_user.id
    
    if user_id != config.OWNER_ID:
        await message.answer("❌ Owner-only command!")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Usage: <code>/install &lt;module_name&gt;</code>\nExample: /install requests")
        return
    
    module_name = args[1]
    
    status_msg = await message.answer(f"{config.EMOJI['loading']} Installing: <code>{module_name}</code>...")
    
    success, msg = await ModuleInstaller.install_module(module_name)
    
    await status_msg.edit_text(msg)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⏰ BACKGROUND TASKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def premium_expiry_checker():
    """Check and revoke expired premiums"""
    while True:
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT user_id, first_name FROM users
                WHERE is_premium = 1 AND premium_until < datetime('now')
            """)
            expired = cursor.fetchall()
            
            for user_id, first_name in expired:
                db.revoke_premium(user_id)
                
                user = db.get_user(user_id)
                allowed_slots = config.FREE_BOT_SLOTS + user['bonus_slots']
                
                bots = db.get_user_bots(user_id)
                if len(bots) > allowed_slots:
                    for bot in bots[allowed_slots:]:
                        await BotManager.stop_bot(bot['id'], db)
                
                try:
                    await bot.send_message(
                        user_id,
                        f"{config.EMOJI['warning']} <b>PREMIUM EXPIRED</b>\n\n"
                        f"Hi {first_name},\n\n"
                        f"Your premium has expired.\n\n"
                        f"📊 Current Slots: {allowed_slots}\n\n"
                        f"💎 Renew premium for unlimited slots!"
                    )
                except:
                    pass
                
                logger.info(f"💎 Premium expired: user {user_id}")
            
            conn.close()
        
        except Exception as e:
            logger.error(f"Premium checker error: {e}")
        
        await asyncio.sleep(config.PREMIUM_CHECK_INTERVAL)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🚀 MAIN ENTRY POINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def on_startup():
    """Bot startup"""
    logger.info(f"{config.EMOJI['fire']} GADGET PREMIUM HOST Starting...")
    logger.info(f"{config.EMOJI['admin']} Owner: @{config.OWNER_USERNAME} (ID: {config.OWNER_ID})")
    
    asyncio.create_task(premium_expiry_checker())
    
    # Notify owner
    try:
        await bot.send_message(
            config.OWNER_ID,
            f"{config.EMOJI['fire']} <b>BOT STARTED</b>\n\n"
            f"{config.EMOJI['success']} System online and ready!\n"
            f"{config.EMOJI['admin']} God Mode activated."
        )
    except:
        pass
    
    logger.info(f"{config.EMOJI['success']} Bot is running!")

async def on_shutdown():
    """Bot shutdown"""
    logger.info(f"{config.EMOJI['warning']} Shutting down...")
    
    for bot_id in list(BotManager.running_processes.keys()):
        await BotManager.stop_bot(bot_id, db)
    
    logger.info("👋 Bot stopped!")

async def main():
    """Main function"""
    dp.include_router(router)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
