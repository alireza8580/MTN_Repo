#!/usr/bin/env python3
"""
Discord Idle Time Tracker Bot
Tracks user idle/online/offline status and calculates daily idle time during work hours.

Features:
- Monitors presence changes (online → idle → offline)
- Tracks ONLY during work hours (08:00-18:00)
- Calculates total idle time per user per day
- Shows idle percentage of work hours
- Stores data in JSON for integration with attendance_tracker.py
- Reports daily summaries

Setup:
1. Create a Discord bot at https://discord.com/developers/applications
2. Enable "Presence Intent" and "Server Members Intent" in Bot settings
3. Invite bot with: OAuth2 URL Generator → bot → Read Message History, View Channels
4. Set DISCORD_BOT_TOKEN in .env file
"""

import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import asyncio

# Load token from .env file
def load_env():
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value

load_env()

# === CONFIG ===
BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')

# Guild (server) ID to monitor - will be auto-detected on first run
GUILD_ID = int(os.environ.get('DISCORD_GUILD_ID', '0'))

# Data storage
DATA_DIR = Path('/root/infrastructure/scripts/discord')
IDLE_DATA_FILE = DATA_DIR / 'idle_time_database.json'
DAILY_REPORT_FILE = DATA_DIR / 'daily_idle_report.json'

# Working hours (track only during these hours)
WORK_START_HOUR = 8   # 08:00
WORK_END_HOUR = 20    # 20:00 (extended for flexible work hours)

# Team members to track (Discord usernames or display names)
# EXCLUDED: Maryam (Maryam Marefati - Team Lead), Alireza (Owner), Hossein Feizollahi (Senior)
# Match by lowercase display_name or username
TEAM_MEMBERS = [
    # Discord username / display_name combos from exports
    'k1 sadeghi', 'k1.sadeghi_15101', 'keivan',
    'nissay87', 'yassin',
    'ehsan', 'esi', 'ehsan.yo',
    'mohsen', 'mohsen.roud',
    'nader', 'nader3307',
    'mahsa', 'mahsahejszi', 'zeinab',
    'hossein shahreza', 'hosseinshahreza', 'hosseinali',
    'masoud rafiei', 'masoudraafiee', 'masoud',  # Discord: masoudraafiee, Display: Masoud
    'masoud sereshki', 'masoudsereshki',
    'erfan', 'erfan_heidari',
    'mari', 'maryam.you',  # Maryam Yousefi (NOT Maryam Marefati)
    # Track but exclude from report:
    'maryam', 'maryam6409',  # Maryam Marefati (Team Lead) - tracked, not reported
    'alireza', 'alireza8580',  # Alireza (Owner) - tracked, not reported
    # NOT tracked at all:
    # 'hosein_feyzollahi', 'hosein feyzollahi'  # Hossein Feizollahi (Senior)
]

# Iran timezone offset
IRAN_OFFSET = timedelta(hours= 3, minutes= 30)

# === INTENTS ===
intents = discord.Intents.default()
intents.presences = True  # Required to track presence
intents.members = True    # Required to see member list
intents.message_content = True
intents.voice_states = True  # Required to track voice channel activity

bot = commands.Bot(command_prefix='!', intents=intents)

# === DATA STRUCTURES ===
# Track current status and timestamps
user_status = {}  # {user_id: {'status': 'online/idle/offline', 'since': datetime}}

# Daily idle time accumulator (now tracks both idle and offline)
daily_idle_time = defaultdict(lambda: defaultdict(float))  # {date_str: {user_id: minutes}}
daily_offline_time = defaultdict(lambda: defaultdict(float))  # {date_str: {user_id: minutes}}

# Voice channel tracking
daily_voice_time = defaultdict(lambda: defaultdict(float))  # {date_str: {user_id: minutes}}
user_voice_status = {}  # {user_id: {'in_voice': True/False, 'since': datetime, 'channel': str}}
VOICE_TIME_FILE = DATA_DIR / 'voice_time_database.json'
VOICE_STATUS_FILE = DATA_DIR / 'voice_status.json'  # Persist open voice sessions

# Idle/offline status persistence (survives restart)
USER_STATUS_FILE = DATA_DIR / 'user_status.json'  # Persist current idle/offline sessions

# User info cache
user_info = {}  # {user_id: {'name': str, 'display_name': str}}

# Check-in/Check-out times (loaded from attendance_tracker or detected via messages)
user_work_hours = {}  # {user_id: {'check_in': datetime, 'check_out': datetime}}


def get_iran_time():
    """Get current time in Iran timezone"""
    from datetime import timezone
    return datetime.now(timezone.utc) + IRAN_OFFSET


def get_today_str():
    """Get today's date string in Iran timezone"""
    return get_iran_time().strftime('%Y-%m-%d')


def is_team_member(member):
    """Check if member is in our tracked team"""
    name_lower = member.display_name.lower()
    username_lower = member.name.lower()
    
    for team_name in TEAM_MEMBERS:
        if team_name.lower() in name_lower or team_name.lower() in username_lower:
            return True
    return False


def load_data():
    """Load saved idle, offline, and voice time data"""
    global daily_idle_time, daily_offline_time, daily_voice_time, user_voice_status, user_status
    
    # Load idle time
    if os.path.exists(IDLE_DATA_FILE):
        try:
            with open(IDLE_DATA_FILE, 'r') as f:
                data = json.load(f)
                # Convert to defaultdict
                for date_str, users in data.items():
                    for user_id, minutes in users.items():
                        daily_idle_time[date_str][user_id] = minutes
        except Exception as e:
            print(f"Error loading idle data: {e}")
    
    # Load offline time
    offline_file = DATA_DIR / 'offline_time_database.json'
    if os.path.exists(offline_file):
        try:
            with open(offline_file, 'r') as f:
                data = json.load(f)
                for date_str, users in data.items():
                    for user_id, minutes in users.items():
                        daily_offline_time[date_str][user_id] = minutes
        except Exception as e:
            print(f"Error loading offline data: {e}")
    
    # Load voice time
    if os.path.exists(VOICE_TIME_FILE):
        try:
            with open(VOICE_TIME_FILE, 'r') as f:
                data = json.load(f)
                for date_str, users in data.items():
                    for user_id, minutes in users.items():
                        daily_voice_time[date_str][user_id] = minutes
        except Exception as e:
            print(f"Error loading voice data: {e}")
    
    # Load voice status (open sessions) - survives bot restart
    if os.path.exists(VOICE_STATUS_FILE):
        try:
            with open(VOICE_STATUS_FILE, 'r') as f:
                data = json.load(f)
                for user_id, status in data.items():
                    if status.get('in_voice') and status.get('since'):
                        # Convert ISO string back to datetime
                        since_str = status['since']
                        since = datetime.fromisoformat(since_str)
                        user_voice_status[int(user_id)] = {
                            'in_voice': True,
                            'since': since,
                            'channel': status.get('channel', 'Unknown')
                        }
                        print(f"🎤 Restored voice session: user {user_id} in {status.get('channel')} since {since_str}")
        except Exception as e:
            print(f"Error loading voice status: {e}")
    
    # Load user idle/offline status (open sessions) - survives bot restart
    if os.path.exists(USER_STATUS_FILE):
        try:
            with open(USER_STATUS_FILE, 'r') as f:
                data = json.load(f)
                for user_id, status in data.items():
                    if status.get('status') and status.get('since'):
                        since_str = status['since']
                        since = datetime.fromisoformat(since_str)
                        user_status[int(user_id)] = {
                            'status': status['status'],
                            'since': since
                        }
                        print(f"📊 Restored status: user {user_id} was {status['status']} since {since_str}")
        except Exception as e:
            print(f"Error loading user status: {e}")


def save_data():
    """Save idle, offline, and voice time data to files"""
    try:
        # Save idle time
        data = {date_str: dict(users) for date_str, users in daily_idle_time.items()}
        with open(IDLE_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Save offline time
        offline_file = DATA_DIR / 'offline_time_database.json'
        offline_data = {date_str: dict(users) for date_str, users in daily_offline_time.items()}
        with open(offline_file, 'w') as f:
            json.dump(offline_data, f, indent=2)
        
        # Save voice time
        voice_data = {date_str: dict(users) for date_str, users in daily_voice_time.items()}
        with open(VOICE_TIME_FILE, 'w') as f:
            json.dump(voice_data, f, indent=2)
        
        # Save voice status (open sessions) - survives bot restart
        voice_status_data = {}
        for user_id, status in user_voice_status.items():
            if status.get('in_voice') and status.get('since'):
                voice_status_data[str(user_id)] = {
                    'in_voice': True,
                    'since': status['since'].isoformat(),
                    'channel': status.get('channel', 'Unknown')
                }
        with open(VOICE_STATUS_FILE, 'w') as f:
            json.dump(voice_status_data, f, indent=2)
        
        # Save user idle/offline status (open sessions) - survives bot restart
        user_status_data = {}
        for user_id, status in user_status.items():
            if status.get('status') and status.get('since'):
                user_status_data[str(user_id)] = {
                    'status': status['status'],
                    'since': status['since'].isoformat()
                }
        with open(USER_STATUS_FILE, 'w') as f:
            json.dump(user_status_data, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")


def save_user_info():
    """Save user info cache"""
    try:
        user_info_file = DATA_DIR / 'idle_time_users.json'
        with open(user_info_file, 'w') as f:
            json.dump(user_info, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving user info: {e}")


@bot.event
async def on_ready():
    """Bot is connected and ready"""
    global GUILD_ID
    
    print(f'✅ Bot connected as {bot.user}')
    print(f'📊 Tracking idle time for team members (work hours: {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00)')
    
    load_data()
    
    # Auto-detect guild if not set
    if not GUILD_ID and bot.guilds:
        guild = bot.guilds[0]  # Use first guild
        GUILD_ID = guild.id
        print(f'📍 Auto-detected guild: {guild.name} (ID: {guild.id})')
        print(f'   Add to .env: DISCORD_GUILD_ID={guild.id}')
    
    # Initialize status for all members
    guild = bot.get_guild(GUILD_ID) if GUILD_ID else None
    if guild:
        print(f'📍 Monitoring guild: {guild.name}')
        for member in guild.members:
            if is_team_member(member):
                user_status[member.id] = {
                    'status': str(member.status),
                    'since': get_iran_time()
                }
                user_info[str(member.id)] = {
                    'name': member.name,
                    'display_name': member.display_name
                }
                print(f'  👤 Tracking: {member.display_name} ({member.status})')
        save_user_info()
    else:
        print('⚠️ No guild found. Make sure DISCORD_GUILD_ID is set or bot is in a server.')
    
    # Start periodic save task
    if not save_task.is_running():
        save_task.start()
    
    # Start daily reset task
    if not daily_reset_task.is_running():
        daily_reset_task.start()


def is_work_hours(dt=None):
    """Check if given datetime (or now) is within work hours (08:00-18:00)"""
    if dt is None:
        dt = get_iran_time()
    return WORK_START_HOUR <= dt.hour < WORK_END_HOUR


def get_user_work_hours(user_id, dt):
    """Get user's work hours for the day (check_in to check_out, or default 08-18)"""
    today = dt.strftime('%Y-%m-%d')
    
    if str(user_id) in user_work_hours and user_work_hours[str(user_id)].get('date') == today:
        data = user_work_hours[str(user_id)]
        check_in = data.get('check_in')
        check_out = data.get('check_out')
        return check_in, check_out
    
    # Default: 08:00 - 18:00
    return None, None


def calculate_work_hours_overlap(start_time, end_time, user_id=None):
    """
    Calculate how many minutes of a time range overlap with work hours.
    If user_id provided and has check_in/check_out, use those instead of fixed 08-18.
    """
    if start_time >= end_time:
        return 0.0
    
    # Get user-specific work hours if available
    if user_id:
        check_in, check_out = get_user_work_hours(user_id, start_time)
        if check_in:
            work_start = check_in
            work_end = check_out if check_out else start_time.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
        else:
            # Default work hours
            work_start = start_time.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
            work_end = start_time.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
    else:
        work_start = start_time.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
        work_end = start_time.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
    
    # Clamp to work hours
    effective_start = max(start_time, work_start)
    effective_end = min(end_time, work_end)
    
    if effective_start >= effective_end:
        return 0.0
    
    return (effective_end - effective_start).total_seconds() / 60


@bot.event
async def on_presence_update(before, after):
    """Called when a member's presence changes"""
    if not is_team_member(after):
        return
    
    user_id = after.id
    now = get_iran_time()
    today = get_today_str()
    
    # Get previous status
    prev_data = user_status.get(user_id, {'status': 'offline', 'since': now})
    prev_status = prev_data['status']
    prev_since = prev_data['since']
    
    new_status = str(after.status)
    
    # Only process if status actually changed
    if prev_status == new_status:
        return
    
    # Calculate time spent in previous status - ONLY during work hours (or check_in to check_out)
    duration_minutes = calculate_work_hours_overlap(prev_since, now, user_id)
    
    # Track idle time
    if prev_status == 'idle' and duration_minutes > 0:
        daily_idle_time[today][str(user_id)] += duration_minutes
        print(f'🟡 {after.display_name}: +{duration_minutes:.1f} min idle (total: {daily_idle_time[today][str(user_id)]:.1f} min)')
    
    # Track offline time
    if prev_status == 'offline' and duration_minutes > 0:
        daily_offline_time[today][str(user_id)] += duration_minutes
        print(f'⚫ {after.display_name}: +{duration_minutes:.1f} min offline (total: {daily_offline_time[today][str(user_id)]:.1f} min)')
    
    # Update current status
    user_status[user_id] = {
        'status': new_status,
        'since': now
    }
    
    # Update user info
    user_info[str(user_id)] = {
        'name': after.name,
        'display_name': after.display_name
    }
    
    # Log status change (with work hours indicator)
    status_emoji = {'online': '🟢', 'idle': '🟡', 'dnd': '🔴', 'offline': '⚫'}
    work_indicator = "📍" if is_work_hours(now) else "🌙"
    print(f'{status_emoji.get(new_status, "❓")} {work_indicator} {after.display_name}: {prev_status} → {new_status}')


# Patterns for check-in and check-out messages
CHECKIN_PATTERNS = [
    'سلام', 'salam', 'hi', 'hello', 'صبح بخیر', 'morning',
    'سلام روزتون', 'سلام صبح', 'سلام همگی'
]
CHECKOUT_PATTERNS = [
    'خسته نباشید', 'khaste nabashid', 'bye', 'فعلا', 'felan', 
    'شب بخیر', 'good night', 'خداحافظ', 'میرم', 'برم', 'روز خوب'
]


def is_checkin_message(content):
    """Check if message is a check-in (سلام)"""
    content_lower = content.lower().strip()
    for pattern in CHECKIN_PATTERNS:
        if pattern in content_lower and len(content_lower) < 50:  # Short messages only
            return True
    return False


def is_checkout_message(content):
    """Check if message is a check-out (خداحافظی)"""
    content_lower = content.lower().strip()
    for pattern in CHECKOUT_PATTERNS:
        if pattern in content_lower:
            return True
    return False


@bot.event
async def on_message(message):
    """Track check-in and check-out messages"""
    # Ignore bot messages
    if message.author.bot:
        return
    
    # Only process team members
    if not is_team_member(message.author):
        await bot.process_commands(message)
        return
    
    user_id = message.author.id
    now = get_iran_time()
    today = get_today_str()
    content = message.content
    
    # Check for check-in (سلام)
    if is_checkin_message(content):
        if str(user_id) not in user_work_hours or user_work_hours[str(user_id)].get('date') != today:
            user_work_hours[str(user_id)] = {
                'date': today,
                'check_in': now,
                'check_out': None
            }
            print(f'📥 {message.author.display_name} checked in at {now.strftime("%H:%M")}')
    
    # Check for check-out (خداحافظی)
    if is_checkout_message(content):
        if str(user_id) in user_work_hours and user_work_hours[str(user_id)].get('date') == today:
            user_work_hours[str(user_id)]['check_out'] = now
            print(f'📤 {message.author.display_name} checked out at {now.strftime("%H:%M")}')
    
    # Process commands
    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    """Track voice channel activity (join/leave)"""
    if not is_team_member(member):
        return
    
    user_id = member.id
    now = get_iran_time()
    today = get_today_str()
    
    # User joined a voice channel
    if before.channel is None and after.channel is not None:
        user_voice_status[user_id] = {
            'in_voice': True,
            'since': now,
            'channel': after.channel.name
        }
        print(f'🎤 {member.display_name} joined voice: {after.channel.name}')
    
    # User left a voice channel
    elif before.channel is not None and after.channel is None:
        if user_id in user_voice_status and user_voice_status[user_id].get('in_voice'):
            since = user_voice_status[user_id]['since']
            # Calculate voice time (only during work hours)
            duration_minutes = calculate_work_hours_overlap(since, now, user_id)
            if duration_minutes > 0:
                daily_voice_time[today][str(user_id)] += duration_minutes
                print(f'🎤 {member.display_name} left voice after {duration_minutes:.1f} min (total: {daily_voice_time[today][str(user_id)]:.1f} min)')
            
            user_voice_status[user_id] = {
                'in_voice': False,
                'since': None,
                'channel': None
            }
    
    # User switched voice channels
    elif before.channel != after.channel:
        # Still in voice, just log the switch
        if user_id in user_voice_status:
            user_voice_status[user_id]['channel'] = after.channel.name
        print(f'🎤 {member.display_name} switched voice: {before.channel.name} → {after.channel.name}')


@tasks.loop(minutes=5)
async def save_task():
    """Periodically save data"""
    save_data()
    save_user_info()


@tasks.loop(hours=1)
async def daily_reset_task():
    """Check if day changed and finalize previous day's data"""
    now = get_iran_time()
    today = get_today_str()
    
    # At midnight (or close to it), finalize any open idle sessions
    if now.hour == 0 and now.minute < 5:
        yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Finalize any open idle sessions from yesterday
        for user_id, status_data in user_status.items():
            if status_data['status'] == 'idle':
                # Calculate remaining idle time from yesterday (only work hours: 08-18)
                since = status_data['since']
                if since.strftime('%Y-%m-%d') == yesterday:
                    # End of work day (18:00)
                    work_end = since.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
                    duration_minutes = calculate_work_hours_overlap(since, work_end)
                    if duration_minutes > 0:
                        daily_idle_time[yesterday][str(user_id)] += duration_minutes
                    
                    # Reset 'since' to today at work start
                    today_work_start = now.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
                    user_status[user_id]['since'] = today_work_start
        
        save_data()
        generate_daily_report(yesterday)
    
    # At 18:00 (end of work day), finalize all idle sessions for today
    if now.hour == WORK_END_HOUR and now.minute < 5:
        print(f"📴 Work hours ended. Finalizing today's idle sessions...")
        for user_id, status_data in user_status.items():
            if status_data['status'] == 'idle':
                since = status_data['since']
                work_end = now.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
                duration_minutes = calculate_work_hours_overlap(since, work_end)
                if duration_minutes > 0:
                    daily_idle_time[today][str(user_id)] += duration_minutes
                    user_name = user_info.get(str(user_id), {}).get('display_name', str(user_id))
                    print(f'  ⏱️ {user_name}: +{duration_minutes:.1f} min idle (end of day)')
        save_data()


def generate_daily_report(date_str):
    """Generate daily idle time report"""
    # Total work hours = WORK_END_HOUR - WORK_START_HOUR = 18 - 8 = 10 hours = 600 minutes
    total_work_minutes = (WORK_END_HOUR - WORK_START_HOUR) * 60
    
    report = {
        'date': date_str,
        'generated_at': get_iran_time().isoformat(),
        'work_hours': f'{WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00',
        'total_work_minutes': total_work_minutes,
        'users': {}
    }
    
    if date_str in daily_idle_time:
        for user_id, minutes in daily_idle_time[date_str].items():
            info = user_info.get(user_id, {'display_name': f'User_{user_id}'})
            idle_percent = (minutes / total_work_minutes) * 100
            active_minutes = total_work_minutes - minutes
            active_percent = (active_minutes / total_work_minutes) * 100
            
            report['users'][info.get('display_name', user_id)] = {
                'idle_minutes': round(minutes, 1),
                'idle_hours': round(minutes / 60, 2),
                'idle_percent': round(idle_percent, 1),
                'active_minutes': round(active_minutes, 1),
                'active_percent': round(active_percent, 1)
            }
    
    # Save report
    try:
        # Load existing reports
        all_reports = {}
        if os.path.exists(DAILY_REPORT_FILE):
            with open(DAILY_REPORT_FILE, 'r') as f:
                all_reports = json.load(f)
        
        all_reports[date_str] = report
        
        with open(DAILY_REPORT_FILE, 'w') as f:
            json.dump(all_reports, f, indent=2, ensure_ascii=False)
        
        print(f'📋 Daily report generated for {date_str}')
    except Exception as e:
        print(f'Error generating report: {e}')


# === BOT COMMANDS ===
@bot.command(name='idle')
async def show_idle(ctx, date_str: str = None):
    """Show idle time summary for today or specified date
    Usage: !idle or !idle 2025-12-23
    """
    if date_str is None:
        date_str = get_today_str()
    
    if date_str not in daily_idle_time or not daily_idle_time[date_str]:
        await ctx.send(f'📊 No idle data for {date_str}')
        return
    
    # Total work minutes = 10 hours = 600 minutes
    total_work_minutes = (WORK_END_HOUR - WORK_START_HOUR) * 60
    
    # Build message
    lines = [f'📊 **Idle Time Report - {date_str}**']
    lines.append(f'⏰ Work Hours: {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00 ({total_work_minutes//60}h)\n')
    
    total_idle = 0
    sorted_users = sorted(
        daily_idle_time[date_str].items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    for user_id, minutes in sorted_users:
        info = user_info.get(user_id, {'display_name': f'User_{user_id}'})
        name = info.get('display_name', user_id)
        hours = minutes / 60
        idle_percent = (minutes / total_work_minutes) * 100
        total_idle += minutes
        
        # Color code based on idle percentage
        if idle_percent > 50:
            emoji = '🔴'  # High idle
        elif idle_percent > 25:
            emoji = '🟡'  # Medium idle
        else:
            emoji = '🟢'  # Low idle
        
        if minutes > 60:
            lines.append(f'{emoji} {name}: {hours:.1f}h ({idle_percent:.0f}% idle)')
        else:
            lines.append(f'{emoji} {name}: {minutes:.0f}m ({idle_percent:.0f}% idle)')
    
    avg_idle = total_idle / len(sorted_users) if sorted_users else 0
    avg_percent = (avg_idle / total_work_minutes) * 100
    lines.append(f'\n**Team Average: {avg_idle:.0f} min ({avg_percent:.0f}% idle)**')
    
    await ctx.send('\n'.join(lines))


@bot.command(name='status')
async def show_status(ctx):
    """Show current status of all tracked team members"""
    if not user_status:
        await ctx.send('📊 No status data available')
        return
    
    lines = ['📊 **Current Team Status**\n']
    status_emoji = {'online': '🟢', 'idle': '🟡', 'dnd': '🔴', 'offline': '⚫'}
    
    for user_id, data in user_status.items():
        info = user_info.get(str(user_id), {'display_name': f'User_{user_id}'})
        name = info.get('display_name', str(user_id))
        status = data['status']
        since = data['since'].strftime('%H:%M')
        emoji = status_emoji.get(status, '❓')
        
        # Show check-in time if available
        work_data = user_work_hours.get(str(user_id), {})
        check_in = work_data.get('check_in')
        check_str = f" [in: {check_in.strftime('%H:%M')}]" if check_in else ""
        
        lines.append(f'{emoji} {name}: {status} (since {since}){check_str}')
    
    await ctx.send('\n'.join(lines))


@bot.command(name='offline')
async def show_offline(ctx, date_str: str = None):
    """Show offline time summary for today or specified date
    Usage: !offline or !offline 2025-12-23
    """
    if date_str is None:
        date_str = get_today_str()
    
    if date_str not in daily_offline_time or not daily_offline_time[date_str]:
        await ctx.send(f'📊 No offline data for {date_str}')
        return
    
    # Total work minutes = 10 hours = 600 minutes
    total_work_minutes = (WORK_END_HOUR - WORK_START_HOUR) * 60
    
    # Build message
    lines = [f'⚫ **Offline Time Report - {date_str}**']
    lines.append(f'⏰ Work Hours: {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00\n')
    
    total_offline = 0
    sorted_users = sorted(
        daily_offline_time[date_str].items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    for user_id, minutes in sorted_users:
        info = user_info.get(user_id, {'display_name': f'User_{user_id}'})
        name = info.get('display_name', user_id)
        hours = minutes / 60
        offline_percent = (minutes / total_work_minutes) * 100
        total_offline += minutes
        
        if minutes > 60:
            lines.append(f'⚫ {name}: {hours:.1f}h ({offline_percent:.0f}% offline)')
        else:
            lines.append(f'⚫ {name}: {minutes:.0f}m ({offline_percent:.0f}% offline)')
    
    avg_offline = total_offline / len(sorted_users) if sorted_users else 0
    lines.append(f'\n**Team Total Offline: {total_offline:.0f} min ({total_offline/60:.1f}h)**')
    
    await ctx.send('\n'.join(lines))


@bot.command(name='voice')
async def show_voice(ctx, date_str: str = None):
    """Show voice channel time summary for today or specified date
    Usage: !voice or !voice 2025-12-23
    """
    if date_str is None:
        date_str = get_today_str()
    
    if date_str not in daily_voice_time or not daily_voice_time[date_str]:
        await ctx.send(f'🎤 No voice data for {date_str}')
        return
    
    # Total work minutes = 10 hours = 600 minutes
    total_work_minutes = (WORK_END_HOUR - WORK_START_HOUR) * 60
    
    # Build message
    lines = [f'🎤 **Voice Channel Time Report - {date_str}**']
    lines.append(f'⏰ Work Hours: {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00\n')
    
    total_voice = 0
    sorted_users = sorted(
        daily_voice_time[date_str].items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    for user_id, minutes in sorted_users:
        info = user_info.get(user_id, {'display_name': f'User_{user_id}'})
        name = info.get('display_name', user_id)
        hours = minutes / 60
        voice_percent = (minutes / total_work_minutes) * 100
        total_voice += minutes
        
        if minutes > 60:
            lines.append(f'🎤 {name}: {hours:.1f}h ({voice_percent:.0f}% on voice)')
        else:
            lines.append(f'🎤 {name}: {minutes:.0f}m ({voice_percent:.0f}% on voice)')
    
    # Show who is currently in voice
    in_voice_now = [uid for uid, data in user_voice_status.items() if data.get('in_voice')]
    if in_voice_now:
        lines.append(f'\n**Currently in voice:** {len(in_voice_now)} users')
        for uid in in_voice_now:
            info = user_info.get(str(uid), {'display_name': f'User_{uid}'})
            name = info.get('display_name', str(uid))
            channel = user_voice_status[uid].get('channel', 'Unknown')
            lines.append(f'  🟢 {name} in #{channel}')
    
    lines.append(f'\n**Team Total Voice: {total_voice:.0f} min ({total_voice/60:.1f}h)**')
    
    await ctx.send('\n'.join(lines))


@bot.command(name='save')
async def force_save(ctx):
    """Force save current data"""
    save_data()
    save_user_info()
    await ctx.send('💾 Data saved!')


@bot.command(name='report')
async def force_report(ctx, date_str: str = None):
    """Generate report for specified date
    Usage: !report or !report 2025-12-23
    """
    if date_str is None:
        date_str = get_today_str()
    
    generate_daily_report(date_str)
    await ctx.send(f'📋 Report generated for {date_str}')


# === MAIN ===
if __name__ == '__main__':
    if not BOT_TOKEN:
        print('❌ No token found. Make sure .env file exists with DISCORD_BOT_TOKEN')
        print('   Create .env file in same directory:')
        print('   DISCORD_BOT_TOKEN=your_token_here')
        print('   DISCORD_GUILD_ID=your_guild_id (optional, will auto-detect)')
        exit(1)
    
    print('🚀 Starting Discord Idle Tracker Bot...')
    print(f'⏰ Tracking work hours: {WORK_START_HOUR:02d}:00-{WORK_END_HOUR:02d}:00')
    print(f'📁 Data file: {IDLE_DATA_FILE}')
    print(f'📁 Report file: {DAILY_REPORT_FILE}')
    
    bot.run(BOT_TOKEN)
