#!/usr/bin/env python3
"""
Sync JSON idle/offline/voice data to SQLite database.
This script reads from the Discord bot's JSON files and imports to SQLite.
"""

import json
import sqlite3
from pathlib import Path

DISCORD_DIR = Path('/root/infrastructure/MTN_Repo/discord')
ATTENDANCE_DB = Path('/root/infrastructure/attendance_reports/attendance.db')

# Discord user ID to standard name mapping
STANDARD_NAME_MAP = {
    '681468450870132757': 'Ehsan Yousefi',       # Esi (@ehsan.yo)
    '1029634494862475294': 'Maryam Yousefi',     # Mari (@maryam.you)
    '1428398226704433254': 'Mohsen Roudsaz',     # Mohsen (@mohsen.roud)
    '929347812901138482': 'Nader Shabibi',       # Nader (@nader3307)
    '1380899491745370243': 'Erfan Heidari',      # Erfan (@erfan_heidari)
    '1016789594613743719': 'Hosseinali Shirali', # hossein shahreza (@hosseinshahreza)
    '356431782704316428': 'Masoud Rafiei',       # Masoud (@masoudraafiee)
    '1335373406874501225': 'Zeinabsadat Hejazi', # Mahsa (@mahsahejszi)
    '498491862324215819': 'Yassin Alivand',      # nissay87 (@nissay87)
    '1197192616018718781': 'Masoud Sereshki',    # Masoud Sereshki (@masoudsereshki)
    '1249939570913706081': 'Keivan Sadeghi',     # K1 Sadeghi (@k1.sadeghi_15101)
    # Excluded: 988029106836869181 (Alireza), 736498592168280114 (Maryam Marefati)
}

def sync_json_to_sqlite():
    """Sync all JSON tracking data to SQLite"""
    
    # Load JSON files
    with open(DISCORD_DIR / 'idle_time_database.json') as f:
        idle_data = json.load(f)
    print(f"Loaded idle data: {len(idle_data)} dates")

    with open(DISCORD_DIR / 'offline_time_database.json') as f:
        offline_data = json.load(f)
    print(f"Loaded offline data: {len(offline_data)} dates")

    with open(DISCORD_DIR / 'voice_time_database.json') as f:
        voice_data = json.load(f)
    print(f"Loaded voice data: {len(voice_data)} dates")

    # Connect to SQLite
    conn = sqlite3.connect(str(ATTENDANCE_DB))
    cursor = conn.cursor()
    
    idle_count = 0
    offline_count = 0
    voice_count = 0

    # Insert/update idle data
    for date_str, users in idle_data.items():
        for user_id, minutes in users.items():
            name = STANDARD_NAME_MAP.get(user_id)
            if name and minutes > 0:
                cursor.execute('''
                    INSERT OR REPLACE INTO idle_tracking (date, discord_user_id, standard_name, minutes)
                    VALUES (?, ?, ?, ?)
                ''', (date_str, user_id, name, round(minutes, 2)))
                idle_count += 1
                
    # Insert/update offline data
    for date_str, users in offline_data.items():
        for user_id, minutes in users.items():
            name = STANDARD_NAME_MAP.get(user_id)
            if name and minutes > 0:
                cursor.execute('''
                    INSERT OR REPLACE INTO offline_tracking (date, discord_user_id, standard_name, minutes)
                    VALUES (?, ?, ?, ?)
                ''', (date_str, user_id, name, round(minutes, 2)))
                offline_count += 1

    # Insert/update voice data
    for date_str, users in voice_data.items():
        for user_id, minutes in users.items():
            name = STANDARD_NAME_MAP.get(user_id)
            if name and minutes > 0:
                cursor.execute('''
                    INSERT OR REPLACE INTO voice_tracking (date, discord_user_id, standard_name, minutes)
                    VALUES (?, ?, ?, ?)
                ''', (date_str, user_id, name, round(minutes, 2)))
                voice_count += 1

    conn.commit()
    print(f"Synced: {idle_count} idle, {offline_count} offline, {voice_count} voice records")

    # Verify for recent dates
    cursor.execute('SELECT date, COUNT(*) FROM idle_tracking WHERE date >= "2025-12-24" GROUP BY date ORDER BY date')
    print("\nIdle records by date (after 12-24):")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} records")

    conn.close()
    print("\nDone!")

if __name__ == '__main__':
    sync_json_to_sqlite()
