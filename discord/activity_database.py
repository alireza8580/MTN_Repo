#!/usr/bin/env python3
"""
Activity Database Module
Stores detailed activity data in SQLite for future analysis
"""

import sqlite3
import os
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple

# Database location
DATABASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_FILE = os.path.join(DATABASE_DIR, 'activity.db')


def get_connection():
    """Get database connection with row_factory for dict-like access"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database schema"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Activity sessions table - stores idle/offline/voice periods
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT,
            date TEXT NOT NULL,  -- YYYY-MM-DD format
            activity_type TEXT NOT NULL,  -- 'idle', 'offline', 'voice'
            start_time TEXT NOT NULL,  -- HH:MM:SS format
            end_time TEXT,  -- NULL if session still open
            duration_minutes REAL,  -- Calculated on session close
            channel_id TEXT,  -- For voice sessions
            channel_name TEXT,  -- For voice sessions
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create indexes for common queries
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sessions_user_date 
        ON activity_sessions(user_id, date)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_sessions_date_type 
        ON activity_sessions(date, activity_type)
    ''')
    
    # Daily summary table - aggregated totals per user per day
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT,
            date TEXT NOT NULL,
            idle_minutes REAL DEFAULT 0,
            offline_minutes REAL DEFAULT 0,
            voice_minutes REAL DEFAULT 0,
            session_count INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        )
    ''')
    
    # User mapping table - Discord ID to name
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            display_name TEXT,
            username TEXT,
            first_seen TEXT,
            last_seen TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at: {DATABASE_FILE}")


# === Session Management ===

def start_session(user_id: str, user_name: str, activity_type: str, 
                  channel_id: str = None, channel_name: str = None) -> int:
    """Start a new activity session, returns session ID"""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    
    cursor.execute('''
        INSERT INTO activity_sessions 
        (user_id, user_name, date, activity_type, start_time, channel_id, channel_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, user_name, date_str, activity_type, time_str, channel_id, channel_name))
    
    session_id = cursor.lastrowid
    
    # Update user last seen
    cursor.execute('''
        INSERT INTO users (user_id, display_name, first_seen, last_seen)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            display_name = excluded.display_name,
            last_seen = excluded.last_seen
    ''', (user_id, user_name, now.isoformat(), now.isoformat()))
    
    conn.commit()
    conn.close()
    return session_id


def end_session(session_id: int) -> float:
    """End a session and calculate duration, returns duration in minutes"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get session start time
    cursor.execute('SELECT start_time, date FROM activity_sessions WHERE id = ?', (session_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return 0
    
    start_time = datetime.strptime(f"{row['date']} {row['start_time']}", '%Y-%m-%d %H:%M:%S')
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds() / 60
    
    cursor.execute('''
        UPDATE activity_sessions 
        SET end_time = ?, duration_minutes = ?
        WHERE id = ?
    ''', (end_time.strftime('%H:%M:%S'), duration, session_id))
    
    conn.commit()
    conn.close()
    return duration


def end_sessions_by_user_type(user_id: str, activity_type: str) -> List[float]:
    """End all open sessions of a type for a user, returns list of durations"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get all open sessions
    cursor.execute('''
        SELECT id FROM activity_sessions 
        WHERE user_id = ? AND activity_type = ? AND end_time IS NULL
    ''', (user_id, activity_type))
    
    sessions = cursor.fetchall()
    conn.close()
    
    durations = []
    for session in sessions:
        duration = end_session(session['id'])
        durations.append(duration)
    
    return durations


# === Query Functions ===

def get_user_sessions(user_id: str, date_str: str, activity_type: str = None) -> List[Dict]:
    """Get all sessions for a user on a date, optionally filtered by type"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if activity_type:
        cursor.execute('''
            SELECT * FROM activity_sessions 
            WHERE user_id = ? AND date = ? AND activity_type = ?
            ORDER BY start_time
        ''', (user_id, date_str, activity_type))
    else:
        cursor.execute('''
            SELECT * FROM activity_sessions 
            WHERE user_id = ? AND date = ?
            ORDER BY start_time
        ''', (user_id, date_str))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_user_totals(user_id: str, date_str: str) -> Dict[str, float]:
    """Get total minutes per activity type for a user on a date"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT activity_type, SUM(duration_minutes) as total
        FROM activity_sessions 
        WHERE user_id = ? AND date = ? AND duration_minutes IS NOT NULL
        GROUP BY activity_type
    ''', (user_id, date_str))
    
    rows = cursor.fetchall()
    conn.close()
    
    return {row['activity_type']: row['total'] or 0 for row in rows}


def get_all_users_totals(date_str: str) -> Dict[str, Dict[str, float]]:
    """Get totals for all users on a date"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, user_name, activity_type, SUM(duration_minutes) as total
        FROM activity_sessions 
        WHERE date = ? AND duration_minutes IS NOT NULL
        GROUP BY user_id, activity_type
    ''', (date_str,))
    
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        user_id = row['user_id']
        if user_id not in result:
            result[user_id] = {'user_name': row['user_name'], 'idle': 0, 'offline': 0, 'voice': 0}
        result[user_id][row['activity_type']] = row['total'] or 0
    
    return result


def check_overlap(user_id: str, date_str: str, check_start: str, check_end: str, 
                  activity_types: List[str] = None) -> List[Dict]:
    """
    Check if a time range overlaps with any activity sessions.
    Useful for checking if idle/offline was during BRB.
    
    Args:
        user_id: Discord user ID
        date_str: Date in YYYY-MM-DD format
        check_start: Start time in HH:MM or HH:MM:SS format
        check_end: End time in HH:MM or HH:MM:SS format
        activity_types: List of types to check (default: ['idle', 'offline'])
    
    Returns:
        List of overlapping sessions with overlap_minutes calculated
    """
    if activity_types is None:
        activity_types = ['idle', 'offline']
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Normalize time format
    if len(check_start) == 5:
        check_start += ':00'
    if len(check_end) == 5:
        check_end += ':00'
    
    placeholders = ','.join('?' * len(activity_types))
    cursor.execute(f'''
        SELECT *, 
            CASE 
                WHEN end_time IS NULL THEN start_time
                ELSE end_time
            END as effective_end
        FROM activity_sessions 
        WHERE user_id = ? AND date = ? 
        AND activity_type IN ({placeholders})
        AND start_time < ?
        AND (end_time IS NULL OR end_time > ?)
        ORDER BY start_time
    ''', (user_id, date_str, *activity_types, check_end, check_start))
    
    rows = cursor.fetchall()
    conn.close()
    
    overlaps = []
    for row in rows:
        session = dict(row)
        
        # Calculate overlap
        sess_start = datetime.strptime(f"{date_str} {session['start_time']}", '%Y-%m-%d %H:%M:%S')
        sess_end_str = session['end_time'] or datetime.now().strftime('%H:%M:%S')
        sess_end = datetime.strptime(f"{date_str} {sess_end_str}", '%Y-%m-%d %H:%M:%S')
        
        range_start = datetime.strptime(f"{date_str} {check_start}", '%Y-%m-%d %H:%M:%S')
        range_end = datetime.strptime(f"{date_str} {check_end}", '%Y-%m-%d %H:%M:%S')
        
        overlap_start = max(sess_start, range_start)
        overlap_end = min(sess_end, range_end)
        
        if overlap_end > overlap_start:
            overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
            session['overlap_minutes'] = overlap_minutes
            overlaps.append(session)
    
    return overlaps


# === Summary Functions ===

def update_daily_summary(user_id: str, user_name: str, date_str: str):
    """Update or create daily summary for a user"""
    totals = get_user_totals(user_id, date_str)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Count sessions
    cursor.execute('''
        SELECT COUNT(*) as cnt FROM activity_sessions 
        WHERE user_id = ? AND date = ?
    ''', (user_id, date_str))
    session_count = cursor.fetchone()['cnt']
    
    cursor.execute('''
        INSERT INTO daily_summary 
        (user_id, user_name, date, idle_minutes, offline_minutes, voice_minutes, session_count, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET
            idle_minutes = excluded.idle_minutes,
            offline_minutes = excluded.offline_minutes,
            voice_minutes = excluded.voice_minutes,
            session_count = excluded.session_count,
            updated_at = excluded.updated_at
    ''', (
        user_id, user_name, date_str,
        totals.get('idle', 0),
        totals.get('offline', 0),
        totals.get('voice', 0),
        session_count,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()


# === Migration from JSON ===

def migrate_from_json(idle_file: str, offline_file: str, voice_file: str):
    """Migrate existing JSON data to SQLite (for historical data)"""
    import json
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Migrate idle time
    if os.path.exists(idle_file):
        with open(idle_file) as f:
            data = json.load(f)
        for date_str, users in data.items():
            for user_id, minutes in users.items():
                cursor.execute('''
                    INSERT OR IGNORE INTO daily_summary 
                    (user_id, date, idle_minutes)
                    VALUES (?, ?, ?)
                ''', (user_id, date_str, minutes))
                cursor.execute('''
                    UPDATE daily_summary SET idle_minutes = ? 
                    WHERE user_id = ? AND date = ?
                ''', (minutes, user_id, date_str))
    
    # Migrate offline time
    if os.path.exists(offline_file):
        with open(offline_file) as f:
            data = json.load(f)
        for date_str, users in data.items():
            for user_id, minutes in users.items():
                cursor.execute('''
                    INSERT OR IGNORE INTO daily_summary 
                    (user_id, date, offline_minutes)
                    VALUES (?, ?, ?)
                ''', (user_id, date_str, minutes))
                cursor.execute('''
                    UPDATE daily_summary SET offline_minutes = ? 
                    WHERE user_id = ? AND date = ?
                ''', (minutes, user_id, date_str))
    
    # Migrate voice time
    if os.path.exists(voice_file):
        with open(voice_file) as f:
            data = json.load(f)
        for date_str, users in data.items():
            for user_id, minutes in users.items():
                cursor.execute('''
                    INSERT OR IGNORE INTO daily_summary 
                    (user_id, date, voice_minutes)
                    VALUES (?, ?, ?)
                ''', (user_id, date_str, minutes))
                cursor.execute('''
                    UPDATE daily_summary SET voice_minutes = ? 
                    WHERE user_id = ? AND date = ?
                ''', (minutes, user_id, date_str))
    
    conn.commit()
    conn.close()
    print("Migration complete!")


# Initialize on import
if __name__ == '__main__':
    init_database()
    print("Database created/verified!")
