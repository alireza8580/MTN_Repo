#!/usr/bin/env python3
"""
Migration script to consolidate JSON databases into SQLite.

This script migrates the following JSON files into the unified attendance.db:
1. idle_time_database.json -> idle_tracking table
2. offline_time_database.json -> offline_tracking table
3. voice_time_database.json -> voice_tracking table
4. leave_database.json -> leave_records table
5. idle_time_users.json -> discord_users table (for ID mapping)

The main attendance table (from CSV) remains unchanged.
"""

import json
import os
import sqlite3
from datetime import datetime

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISCORD_DIR = os.path.join(SCRIPT_DIR, 'discord')
ATTENDANCE_DB = os.path.join(SCRIPT_DIR, '..', 'attendance_reports', 'attendance.db')

# JSON file paths
IDLE_TIME_DB = os.path.join(DISCORD_DIR, 'idle_time_database.json')
OFFLINE_TIME_DB = os.path.join(DISCORD_DIR, 'offline_time_database.json')
VOICE_TIME_DB = os.path.join(DISCORD_DIR, 'voice_time_database.json')
IDLE_USERS_DB = os.path.join(DISCORD_DIR, 'idle_time_users.json')
LEAVE_DB = os.path.join(SCRIPT_DIR, 'leave_database.json')
REMOTE_WORK_DB = os.path.join(SCRIPT_DIR, 'remote_work_database.json')

# Team member mapping (Discord display name -> Standard name)
TEAM_MEMBERS = {
    'alireza': 'Alireza Aghajanzadeh',
    'alireza8580': 'Alireza Aghajanzadeh',
    'maryam': 'Maryam Marefati',
    'maryam6409': 'Maryam Marefati',
    'hosein feyzollahi': 'Hossein Feizollahi',
    'hosein_feyzollahi': 'Hossein Feizollahi',
    'k1 sadeghi': 'Keivan Sadeghi',
    'k1.sadeghi_15101': 'Keivan Sadeghi',
    'esi': 'Ehsan Yousefi',
    'ehsan.yo': 'Ehsan Yousefi',
    'mohsen': 'Mohsen Roudsaz',
    'mohsen.roud': 'Mohsen Roudsaz',
    'nader': 'Nader Shabibi',
    'nader3307': 'Nader Shabibi',
    'mahsa': 'Zeinabsadat Hejazi',
    'mahsahejszi': 'Zeinabsadat Hejazi',
    'hossein shahreza': 'Hosseinali Shirali',
    'hosseinshahreza': 'Hosseinali Shirali',
    'masoud': 'Masoud Rafiei',
    'masoudraafiee': 'Masoud Rafiei',
    'masoud sereshki': 'Masoud Sereshki',
    'masoudsereshki': 'Masoud Sereshki',
    'nissay87': 'Yassin Alivand',
    'erfan': 'Erfan Heidari',
    'erfan_heidari': 'Erfan Heidari',
    'mari': 'Maryam Yousefi',
    'maryam.you': 'Maryam Yousefi',
}


def normalize_name(display_name):
    """Convert Discord display name to standard name"""
    if not display_name:
        return None
    key = display_name.lower().strip()
    return TEAM_MEMBERS.get(key, display_name)


def init_migration_tables(conn):
    """Create new tables for migrated data"""
    cursor = conn.cursor()
    
    # Discord users table (ID to name mapping)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS discord_users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            standard_name TEXT
        )
    ''')
    
    # Idle tracking (per user per date)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS idle_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            discord_user_id TEXT,
            standard_name TEXT,
            minutes REAL NOT NULL,
            UNIQUE(date, discord_user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_idle_date ON idle_tracking(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_idle_name ON idle_tracking(standard_name)')
    
    # Offline tracking (per user per date)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS offline_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            discord_user_id TEXT,
            standard_name TEXT,
            minutes REAL NOT NULL,
            UNIQUE(date, discord_user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_offline_date ON offline_tracking(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_offline_name ON offline_tracking(standard_name)')
    
    # Voice tracking (per user per date)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voice_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            discord_user_id TEXT,
            standard_name TEXT,
            minutes REAL NOT NULL,
            UNIQUE(date, discord_user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_voice_date ON voice_tracking(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_voice_name ON voice_tracking(standard_name)')
    
    # Leave records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leave_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            leave_type TEXT NOT NULL,  -- 'full_day' or 'hourly'
            hours REAL,  -- For hourly leave
            source_msg TEXT,
            msg_date TEXT,
            channel TEXT,
            UNIQUE(name, date)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_leave_date ON leave_records(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_leave_name ON leave_records(name)')
    
    # Remote work records
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS remote_work (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,
            location TEXT,  -- e.g., 'home', 'cafe', etc.
            source_msg TEXT,
            UNIQUE(name, date)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_remote_date ON remote_work(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_remote_name ON remote_work(name)')
    
    conn.commit()
    print("✓ Migration tables created")


def load_user_mapping():
    """Load Discord user ID to name mapping"""
    if not os.path.exists(IDLE_USERS_DB):
        print(f"⚠ User mapping file not found: {IDLE_USERS_DB}")
        return {}
    
    with open(IDLE_USERS_DB, 'r') as f:
        data = json.load(f)
    
    # Build mapping: user_id -> {username, display_name, standard_name}
    mapping = {}
    for user_id, info in data.items():
        username = info.get('name', '')
        display_name = info.get('display_name', '')
        standard_name = normalize_name(display_name) or normalize_name(username)
        mapping[user_id] = {
            'username': username,
            'display_name': display_name,
            'standard_name': standard_name
        }
    
    return mapping


def migrate_discord_users(conn, user_mapping):
    """Migrate Discord users to SQLite"""
    cursor = conn.cursor()
    
    for user_id, info in user_mapping.items():
        cursor.execute('''
            INSERT OR REPLACE INTO discord_users 
            (user_id, username, display_name, standard_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, info['username'], info['display_name'], info['standard_name']))
    
    conn.commit()
    print(f"✓ Migrated {len(user_mapping)} Discord users")


def migrate_tracking_data(conn, json_file, table_name, user_mapping):
    """Migrate idle/offline/voice tracking data"""
    if not os.path.exists(json_file):
        print(f"⚠ File not found: {json_file}")
        return 0
    
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    count = 0
    
    for date_str, users in data.items():
        for user_id, minutes in users.items():
            user_info = user_mapping.get(user_id, {})
            standard_name = user_info.get('standard_name', None)
            
            cursor.execute(f'''
                INSERT OR REPLACE INTO {table_name}
                (date, discord_user_id, standard_name, minutes)
                VALUES (?, ?, ?, ?)
            ''', (date_str, user_id, standard_name, minutes))
            count += 1
    
    conn.commit()
    return count


def migrate_leave_database(conn):
    """Migrate leave_database.json to SQLite"""
    if not os.path.exists(LEAVE_DB):
        print(f"⚠ Leave database not found: {LEAVE_DB}")
        return 0
    
    with open(LEAVE_DB, 'r') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    count = 0
    
    for name, leaves in data.items():
        for date_str, leave_info in leaves.items():
            leave_type = leave_info.get('type', 'full_day')
            hours = leave_info.get('hours')
            source_msg = leave_info.get('source_msg', '')
            msg_date = leave_info.get('msg_date', '')
            channel = leave_info.get('channel', '')
            
            cursor.execute('''
                INSERT OR REPLACE INTO leave_records
                (name, date, leave_type, hours, source_msg, msg_date, channel)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, date_str, leave_type, hours, source_msg, msg_date, channel))
            count += 1
    
    conn.commit()
    return count


def migrate_remote_work(conn):
    """Migrate remote_work_database.json to SQLite"""
    if not os.path.exists(REMOTE_WORK_DB):
        print(f"⚠ Remote work database not found: {REMOTE_WORK_DB}")
        return 0
    
    with open(REMOTE_WORK_DB, 'r') as f:
        data = json.load(f)
    
    cursor = conn.cursor()
    count = 0
    
    for name, records in data.items():
        for date_str, info in records.items():
            location = info.get('location', 'remote')
            source_msg = info.get('source_msg', '')
            
            cursor.execute('''
                INSERT OR REPLACE INTO remote_work
                (name, date, location, source_msg)
                VALUES (?, ?, ?, ?)
            ''', (name, date_str, location, source_msg))
            count += 1
    
    conn.commit()
    return count


def print_summary(conn):
    """Print migration summary"""
    cursor = conn.cursor()
    
    print("\n" + "=" * 50)
    print("Migration Summary")
    print("=" * 50)
    
    tables = [
        ('discord_users', 'Discord Users'),
        ('idle_tracking', 'Idle Records'),
        ('offline_tracking', 'Offline Records'),
        ('voice_tracking', 'Voice Records'),
        ('leave_records', 'Leave Records'),
        ('remote_work', 'Remote Work Records'),
        ('attendance', 'Attendance Records'),
    ]
    
    for table, name in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            print(f"  {name}: {count:,}")
        except sqlite3.OperationalError:
            print(f"  {name}: (table not found)")
    
    # Date range for tracking data
    for table in ['idle_tracking', 'offline_tracking', 'voice_tracking']:
        try:
            cursor.execute(f'SELECT MIN(date), MAX(date) FROM {table}')
            min_date, max_date = cursor.fetchone()
            if min_date:
                print(f"  {table} date range: {min_date} to {max_date}")
        except:
            pass


def main():
    print("=" * 50)
    print("JSON to SQLite Migration")
    print("=" * 50)
    print(f"Database: {ATTENDANCE_DB}")
    print()
    
    # Ensure database exists
    os.makedirs(os.path.dirname(ATTENDANCE_DB), exist_ok=True)
    
    conn = sqlite3.connect(ATTENDANCE_DB)
    
    try:
        # Create tables
        init_migration_tables(conn)
        
        # Load user mapping
        user_mapping = load_user_mapping()
        
        # Migrate Discord users
        migrate_discord_users(conn, user_mapping)
        
        # Migrate tracking data
        idle_count = migrate_tracking_data(conn, IDLE_TIME_DB, 'idle_tracking', user_mapping)
        print(f"✓ Migrated {idle_count} idle tracking records")
        
        offline_count = migrate_tracking_data(conn, OFFLINE_TIME_DB, 'offline_tracking', user_mapping)
        print(f"✓ Migrated {offline_count} offline tracking records")
        
        voice_count = migrate_tracking_data(conn, VOICE_TIME_DB, 'voice_tracking', user_mapping)
        print(f"✓ Migrated {voice_count} voice tracking records")
        
        # Migrate leave database
        leave_count = migrate_leave_database(conn)
        print(f"✓ Migrated {leave_count} leave records")
        
        # Migrate remote work
        remote_count = migrate_remote_work(conn)
        print(f"✓ Migrated {remote_count} remote work records")
        
        # Print summary
        print_summary(conn)
        
    finally:
        conn.close()
    
    print("\n✓ Migration complete!")


if __name__ == '__main__':
    main()
