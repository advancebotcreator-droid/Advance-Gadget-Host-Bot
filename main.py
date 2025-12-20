#!/usr/bin/env python3
"""
Advance Gadget Host Bot - Advanced Main Module
A sophisticated bot with analytics dashboard, security enhancements, 
performance optimization, modern UI/UX, and comprehensive admin panel.

Author: advancebotcreator-droid
Version: 2.0.0
Created: 2025-12-20
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
import threading
import queue
from abc import ABC, abstractmethod

try:
    import discord
    from discord.ext import commands, tasks
    from discord import app_commands
except ImportError:
    print("Error: discord.py is required. Install with: pip install discord.py")
    sys.exit(1)

try:
    import aiohttp
    import psutil
    import colorama
    from colorama import Fore, Back, Style
    colorama.init(autoreset=True)
except ImportError:
    print("Error: Required packages missing. Install with: pip install aiohttp psutil colorama")
    sys.exit(1)


# ==================== CONFIGURATION ====================
class Config:
    """Central configuration management"""
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    LOG_LEVEL = logging.DEBUG if DEBUG else logging.INFO
    
    # Directories
    DATA_DIR = Path("data")
    LOGS_DIR = Path("logs")
    CACHE_DIR = Path("cache")
    
    # Timeouts and limits
    COMMAND_TIMEOUT = 30
    CACHE_TTL = 3600  # 1 hour
    RATE_LIMIT_WINDOW = 60  # seconds
    MAX_COMMAND_HISTORY = 1000
    
    # Security
    ENCRYPTION_ENABLED = True
    TOKEN_ROTATION_INTERVAL = 86400  # 24 hours
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION = 900  # 15 minutes
    
    @classmethod
    def setup_directories(cls):
        """Create necessary directories"""
        for directory in [cls.DATA_DIR, cls.LOGS_DIR, cls.CACHE_DIR]:
            directory.mkdir(exist_ok=True)


# ==================== LOGGING CONFIGURATION ====================
def setup_logging():
    """Configure advanced logging with rotating handlers"""
    Config.setup_directories()
    
    logger = logging.getLogger('AdvanceBot')
    logger.setLevel(Config.LOG_LEVEL)
    
    # File handler with rotation
    log_file = Config.LOGS_DIR / f"bot_{datetime.utcnow().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(Config.LOG_LEVEL)
    
    # Console handler with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(Config.LOG_LEVEL)
    
    # Formatter
    formatter = logging.Formatter(
        f'{Fore.CYAN}[%(asctime)s]{Style.RESET_ALL} '
        f'{Fore.GREEN}[%(name)s]{Style.RESET_ALL} '
        f'{Fore.YELLOW}[%(levelname)s]{Style.RESET_ALL} '
        f'%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()


# ==================== ENUMS & DATA CLASSES ====================
class UserRole(Enum):
    """User role definitions"""
    OWNER = "owner"
    ADMIN = "admin"
    MODERATOR = "moderator"
    MEMBER = "member"
    GUEST = "guest"


class SecurityLevel(Enum):
    """Security clearance levels"""
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1
    PUBLIC = 0


@dataclass
class User:
    """User data model with advanced fields"""
    user_id: int
    username: str
    role: UserRole = UserRole.MEMBER
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_active: datetime = field(default_factory=datetime.utcnow)
    command_count: int = 0
    experience_points: int = 0
    is_verified: bool = False
    login_attempts: int = 0
    is_locked: bool = False
    locked_until: Optional[datetime] = None
    custom_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['role'] = self.role.value
        data['created_at'] = self.created_at.isoformat()
        data['last_active'] = self.last_active.isoformat()
        if self.locked_until:
            data['locked_until'] = self.locked_until.isoformat()
        return data


@dataclass
class AnalyticsEvent:
    """Analytics event data model"""
    event_id: str
    timestamp: datetime
    event_type: str
    user_id: int
    guild_id: int
    command_name: str
    execution_time: float
    success: bool
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Performance monitoring metrics"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    memory_percent: float
    active_users: int
    commands_processed: int
    average_latency: float
    cache_hit_rate: float


# ==================== SECURITY MANAGER ====================
class SecurityManager:
    """Advanced security management system"""
    
    def __init__(self):
        self.user_tokens: Dict[int, str] = {}
        self.failed_logins: Dict[int, List[datetime]] = {}
        self.session_data: Dict[str, Dict] = {}
        self.logger = logger.getChild('SecurityManager')
    
    def generate_token(self, user_id: int) -> str:
        """Generate secure session token"""
        token = secrets.token_urlsafe(32)
        self.user_tokens[user_id] = token
        self.logger.info(f"Token generated for user {user_id}")
        return token
    
    def verify_token(self, user_id: int, token: str) -> bool:
        """Verify session token"""
        return self.user_tokens.get(user_id) == token
    
    def hash_password(self, password: str) -> str:
        """Hash password with salt"""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return f"{salt}${hash_obj.hex()}"
    
    def verify_password(self, password: str, hash_value: str) -> bool:
        """Verify password against hash"""
        try:
            salt, hash_hex = hash_value.split('$')
            hash_obj = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
            return hash_obj.hex() == hash_hex
        except ValueError:
            return False
    
    def record_failed_login(self, user_id: int) -> bool:
        """Record failed login attempt"""
        now = datetime.utcnow()
        if user_id not in self.failed_logins:
            self.failed_logins[user_id] = []
        
        # Clear old attempts outside window
        self.failed_logins[user_id] = [
            attempt for attempt in self.failed_logins[user_id]
            if (now - attempt).total_seconds() < Config.RATE_LIMIT_WINDOW
        ]
        
        self.failed_logins[user_id].append(now)
        
        if len(self.failed_logins[user_id]) >= Config.MAX_LOGIN_ATTEMPTS:
            self.logger.warning(f"User {user_id} exceeded login attempts")
            return False
        
        return True
    
    def reset_failed_logins(self, user_id: int):
        """Reset failed login counter"""
        self.failed_logins.pop(user_id, None)


# ==================== CACHE SYSTEM ====================
class CacheManager:
    """Advanced caching system with TTL and statistics"""
    
    def __init__(self, ttl: int = Config.CACHE_TTL):
        self.cache: Dict[str, tuple] = {}
        self.ttl = ttl
        self.hits = 0
        self.misses = 0
        self.logger = logger.getChild('CacheManager')
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store value in cache"""
        self.cache[key] = (value, time.time(), ttl or self.ttl)
        self.logger.debug(f"Cache SET: {key}")
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache"""
        if key not in self.cache:
            self.misses += 1
            return None
        
        value, timestamp, ttl = self.cache[key]
        if time.time() - timestamp > ttl:
            del self.cache[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return value
    
    def delete(self, key: str):
        """Delete value from cache"""
        self.cache.pop(key, None)
    
    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
    
    def get_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0


# ==================== ANALYTICS ENGINE ====================
class AnalyticsEngine:
    """Sophisticated analytics and monitoring system"""
    
    def __init__(self):
        self.events: List[AnalyticsEvent] = []
        self.metrics: List[PerformanceMetrics] = []
        self.command_stats: Dict[str, Dict] = {}
        self.logger = logger.getChild('AnalyticsEngine')
    
    def record_event(self, event: AnalyticsEvent):
        """Record analytics event"""
        self.events.append(event)
        
        # Update command stats
        cmd = event.command_name
        if cmd not in self.command_stats:
            self.command_stats[cmd] = {
                'total_calls': 0,
                'success_count': 0,
                'error_count': 0,
                'avg_execution_time': 0,
                'last_executed': None
            }
        
        stats = self.command_stats[cmd]
        stats['total_calls'] += 1
        stats['success_count'] += 1 if event.success else 0
        stats['error_count'] += 1 if not event.success else 0
        stats['last_executed'] = event.timestamp
        
        # Update average execution time
        avg = stats['avg_execution_time']
        stats['avg_execution_time'] = (avg + event.execution_time) / 2
        
        # Cleanup old events (keep last 10000)
        if len(self.events) > Config.MAX_COMMAND_HISTORY:
            self.events = self.events[-Config.MAX_COMMAND_HISTORY:]
    
    def record_metrics(self, metrics: PerformanceMetrics):
        """Record performance metrics"""
        self.metrics.append(metrics)
        if len(self.metrics) > 1000:
            self.metrics = self.metrics[-1000:]
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Generate dashboard data"""
        return {
            'total_events': len(self.events),
            'total_commands': sum(s['total_calls'] for s in self.command_stats.values()),
            'success_rate': self._calculate_success_rate(),
            'top_commands': self._get_top_commands(5),
            'recent_events': [asdict(e) for e in self.events[-10:]],
            'performance': self._get_performance_summary(),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _calculate_success_rate(self) -> float:
        """Calculate overall success rate"""
        if not self.events:
            return 0
        success = sum(1 for e in self.events if e.success)
        return (success / len(self.events)) * 100
    
    def _get_top_commands(self, limit: int = 5) -> List[Dict]:
        """Get top commands by execution count"""
        sorted_cmds = sorted(
            self.command_stats.items(),
            key=lambda x: x[1]['total_calls'],
            reverse=True
        )
        return [
            {
                'command': cmd,
                'calls': stats['total_calls'],
                'success_rate': (stats['success_count'] / stats['total_calls'] * 100) 
                               if stats['total_calls'] > 0 else 0,
                'avg_time': stats['avg_execution_time']
            }
            for cmd, stats in sorted_cmds[:limit]
        ]
    
    def _get_performance_summary(self) -> Dict:
        """Generate performance summary"""
        if not self.metrics:
            return {}
        
        latest = self.metrics[-1]
        return {
            'cpu_usage': latest.cpu_usage,
            'memory_usage': latest.memory_usage,
            'memory_percent': latest.memory_percent,
            'active_users': latest.active_users,
            'avg_latency': latest.average_latency
        }


# ==================== RATE LIMITER ====================
class RateLimiter:
    """Advanced rate limiting system"""
    
    def __init__(self, max_calls: int = 10, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls: Dict[int, List[datetime]] = {}
        self.logger = logger.getChild('RateLimiter')
    
    def is_allowed(self, user_id: int) -> bool:
        """Check if user is within rate limit"""
        now = datetime.utcnow()
        
        if user_id not in self.calls:
            self.calls[user_id] = []
        
        # Clean old calls
        self.calls[user_id] = [
            call for call in self.calls[user_id]
            if (now - call).total_seconds() < self.time_window
        ]
        
        if len(self.calls[user_id]) < self.max_calls:
            self.calls[user_id].append(now)
            return True
        
        self.logger.warning(f"Rate limit exceeded for user {user_id}")
        return False
    
    def get_remaining(self, user_id: int) -> int:
        """Get remaining calls for user"""
        return max(0, self.max_calls - len(self.calls.get(user_id, [])))


# ==================== ADVANCED BOT CLASS ====================
class AdvanceGadgetHostBot(commands.Cog):
    """Main bot cog with advanced features"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger.getChild('AdvanceGadgetHostBot')
        self.security_manager = SecurityManager()
        self.cache_manager = CacheManager()
        self.analytics_engine = AnalyticsEngine()
        self.rate_limiter = RateLimiter(max_calls=20, time_window=60)
        self.users: Dict[int, User] = {}
        self.performance_monitor.start()
    
    async def cog_load(self):
        """Called when cog is loaded"""
        self.logger.info("AdvanceGadgetHostBot loaded successfully")
    
    @tasks.loop(seconds=30)
    async def performance_monitor(self):
        """Monitor system performance"""
        try:
            process = psutil.Process()
            metrics = PerformanceMetrics(
                timestamp=datetime.utcnow(),
                cpu_usage=process.cpu_percent(interval=1),
                memory_usage=process.memory_info().rss / 1024 / 1024,  # MB
                memory_percent=process.memory_percent(),
                active_users=len(self.users),
                commands_processed=sum(u.command_count for u in self.users.values()),
                average_latency=self.bot.latency * 1000,  # Convert to ms
                cache_hit_rate=self.cache_manager.get_hit_rate()
            )
            self.analytics_engine.record_metrics(metrics)
            
            # Log if resources are high
            if metrics.cpu_usage > 80:
                self.logger.warning(f"High CPU usage: {metrics.cpu_usage:.2f}%")
            if metrics.memory_percent > 75:
                self.logger.warning(f"High memory usage: {metrics.memory_percent:.2f}%")
        
        except Exception as e:
            self.logger.error(f"Error in performance_monitor: {e}")
    
    async def get_or_create_user(self, user_id: int, username: str) -> User:
        """Get or create user"""
        if user_id not in self.users:
            self.users[user_id] = User(user_id=user_id, username=username)
            self.logger.info(f"User created: {username} ({user_id})")
        
        user = self.users[user_id]
        user.last_active = datetime.utcnow()
        return user
    
    async def execute_command(self, ctx: commands.Context, command_name: str, 
                            command_func: Callable) -> tuple[bool, Any]:
        """Execute command with analytics and error handling"""
        user = await self.get_or_create_user(ctx.author.id, ctx.author.name)
        
        # Check rate limit
        if not self.rate_limiter.is_allowed(ctx.author.id):
            await ctx.send(f"{Fore.RED}⚠️ Rate limit exceeded. Try again later.{Style.RESET_ALL}")
            return False, "Rate limit exceeded"
        
        start_time = time.time()
        success = False
        error_msg = None
        result = None
        
        try:
            result = await asyncio.wait_for(command_func(ctx), timeout=Config.COMMAND_TIMEOUT)
            success = True
            user.command_count += 1
            user.experience_points += 10
        
        except asyncio.TimeoutError:
            error_msg = "Command execution timeout"
            await ctx.send(f"{Fore.RED}❌ Command timed out{Style.RESET_ALL}")
        
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error executing {command_name}: {e}")
            await ctx.send(f"{Fore.RED}❌ Error: {error_msg}{Style.RESET_ALL}")
        
        finally:
            execution_time = time.time() - start_time
            
            # Record event
            event = AnalyticsEvent(
                event_id=secrets.token_hex(8),
                timestamp=datetime.utcnow(),
                event_type="command_execution",
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else 0,
                command_name=command_name,
                execution_time=execution_time,
                success=success,
                error_message=error_msg
            )
            self.analytics_engine.record_event(event)
        
        return success, result
    
    # ==================== ADMIN COMMANDS ====================
    
    @app_commands.command(name="admin_dashboard", description="View admin dashboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def admin_dashboard(self, interaction: discord.Interaction):
        """Display comprehensive admin dashboard"""
        dashboard_data = self.analytics_engine.get_dashboard_data()
        
        embed = discord.Embed(
            title="📊 Advanced Admin Dashboard",
            description="Real-time analytics and monitoring",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📈 Command Statistics",
            value=f"Total Commands: {dashboard_data['total_commands']}\n"
                  f"Success Rate: {dashboard_data['success_rate']:.2f}%\n"
                  f"Total Events: {dashboard_data['total_events']}",
            inline=False
        )
        
        embed.add_field(
            name="🖥️ Performance",
            value=f"CPU: {dashboard_data['performance'].get('cpu_usage', 0):.2f}%\n"
                  f"Memory: {dashboard_data['performance'].get('memory_percent', 0):.2f}%\n"
                  f"Latency: {dashboard_data['performance'].get('avg_latency', 0):.0f}ms",
            inline=False
        )
        
        embed.add_field(
            name="👥 System",
            value=f"Active Users: {dashboard_data['performance'].get('active_users', 0)}\n"
                  f"Cache Hit Rate: {self.cache_manager.get_hit_rate():.2f}%",
            inline=False
        )
        
        top_cmds = dashboard_data['top_commands']
        if top_cmds:
            top_text = "\n".join([
                f"**{cmd['command']}**: {cmd['calls']} calls ({cmd['success_rate']:.0f}% success)"
                for cmd in top_cmds[:3]
            ])
            embed.add_field(name="🏆 Top Commands", value=top_text, inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="user_stats", description="View user statistics")
    async def user_stats(self, interaction: discord.Interaction, 
                        user: Optional[discord.User] = None):
        """Display user statistics"""
        target_user = user or interaction.user
        bot_user = await self.get_or_create_user(target_user.id, target_user.name)
        
        embed = discord.Embed(
            title=f"👤 {bot_user.username}'s Statistics",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(name="🎯 Role", value=bot_user.role.value, inline=True)
        embed.add_field(name="⚡ Experience", value=bot_user.experience_points, inline=True)
        embed.add_field(name="📝 Commands Used", value=bot_user.command_count, inline=True)
        embed.add_field(name="✅ Verified", value="Yes" if bot_user.is_verified else "No", inline=True)
        embed.add_field(
            name="📅 Member Since",
            value=bot_user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            inline=True
        )
        embed.add_field(
            name="⏰ Last Active",
            value=bot_user.last_active.strftime("%Y-%m-%d %H:%M:%S"),
            inline=True
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="security_status", description="View security status")
    @app_commands.checks.has_permissions(administrator=True)
    async def security_status(self, interaction: discord.Interaction):
        """Display security status"""
        embed = discord.Embed(
            title="🔒 Security Status",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="🛡️ Security Configuration",
            value=f"Encryption: {'Enabled' if Config.ENCRYPTION_ENABLED else 'Disabled'}\n"
                  f"Token Rotation: {Config.TOKEN_ROTATION_INTERVAL}s\n"
                  f"Max Login Attempts: {Config.MAX_LOGIN_ATTEMPTS}\n"
                  f"Lockout Duration: {Config.LOCKOUT_DURATION}s",
            inline=False
        )
        
        locked_users = sum(1 for u in self.users.values() if u.is_locked)
        embed.add_field(
            name="📊 Status",
            value=f"Total Users Monitored: {len(self.users)}\n"
                  f"Locked Accounts: {locked_users}\n"
                  f"Rate Limit Active: True",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="cache_info", description="View cache information")
    @app_commands.checks.has_permissions(administrator=True)
    async def cache_info(self, interaction: discord.Interaction):
        """Display cache information"""
        embed = discord.Embed(
            title="💾 Cache Information",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Cache Statistics",
            value=f"Size: {len(self.cache_manager.cache)} items\n"
                  f"Hits: {self.cache_manager.hits}\n"
                  f"Misses: {self.cache_manager.misses}\n"
                  f"Hit Rate: {self.cache_manager.get_hit_rate():.2f}%\n"
                  f"TTL: {Config.CACHE_TTL}s",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    # ==================== UTILITY COMMANDS ====================
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot ping"""
        latency = self.bot.latency * 1000
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latency: **{latency:.2f}ms**",
            color=discord.Color.green() if latency < 100 else discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="help", description="Show help information")
    async def help_command(self, interaction: discord.Interaction):
        """Show help"""
        embed = discord.Embed(
            title="📚 Advanced Bot Help",
            description="Complete command reference",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 Admin Commands",
            value="`/admin_dashboard` - View analytics dashboard\n"
                  "`/security_status` - Check security status\n"
                  "`/cache_info` - View cache statistics",
            inline=False
        )
        
        embed.add_field(
            name="👤 User Commands",
            value="`/user_stats` - View your statistics\n"
                  "`/ping` - Check latency\n"
                  "`/help` - Show this message",
            inline=False
        )
        
        embed.set_footer(text="Use /command_name for more info")
        
        await interaction.response.send_message(embed=embed)


# ==================== MAIN BOT SETUP ====================
class AdvanceBotClient(commands.Bot):
    """Main bot client with advanced initialization"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger.getChild('AdvanceBotClient')
        self.start_time = datetime.utcnow()
        self.bot_cog = None
    
    async def setup_hook(self):
        """Setup bot hooks and load cogs"""
        self.logger.info("Setting up bot hooks...")
        
        # Add main cog
        self.bot_cog = AdvanceGadgetHostBot(self)
        await self.add_cog(self.bot_cog)
        
        self.logger.info("Bot setup complete")
    
    async def on_ready(self):
        """Called when bot is ready"""
        self.logger.info(f"✅ Bot logged in as {self.user}")
        self.logger.info(f"✅ Bot latency: {self.latency * 1000:.2f}ms")
        
        # Sync commands
        try:
            synced = await self.tree.sync()
            self.logger.info(f"✅ Synced {len(synced)} command(s)")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}")
        
        # Set status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Advanced Bot v2.0 | /help for info"
            )
        )
    
    async def on_error(self, event_method, *args, **kwargs):
        """Handle errors gracefully"""
        self.logger.error(f"Error in {event_method}", exc_info=True)
    
    def get_uptime(self) -> timedelta:
        """Get bot uptime"""
        return datetime.utcnow() - self.start_time


# ==================== MAIN ENTRY POINT ====================
async def main():
    """Main entry point"""
    # Get token from environment
    TOKEN = os.getenv("DISCORD_TOKEN")
    
    if not TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        sys.exit(1)
    
    # Create bot instance
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    intents.dm_messages = True
    intents.guild_messages = True
    
    bot = AdvanceBotClient(
        command_prefix="!",
        intents=intents,
        help_command=None
    )
    
    # Start bot
    logger.info(f"{Fore.YELLOW}Starting Advanced Gadget Host Bot v2.0...{Style.RESET_ALL}")
    logger.info(f"{Fore.CYAN}Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}{Style.RESET_ALL}")
    
    try:
        async with aiohttp.ClientSession() as session:
            await bot.start(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
        await bot.close()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)
