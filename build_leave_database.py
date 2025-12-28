#!/usr/bin/env python3
"""
Build Leave Database
Scans all Discord messages, parses leave requests, and builds a database
of actual leave dates for each person.

Output: /root/infrastructure/scripts/leave_database.json
Format: {
    "person_name": {
        "YYYY-MM-DD": {"type": "full_day"|"hourly", "hours": N, "source_msg": "..."},
        ...
    }
}
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from leave_parser import parse_leave_request

DISCORD_EXPORTS_DIR = '/root/infrastructure/discord_exports'
LEAVE_DB_FILE = '/root/infrastructure/scripts/leave_database.json'

# Leave request patterns
LEAVE_PATTERNS = [
    'morakhasi', 'morekhasi', 'مرخصی',
    'off basham', 'off bashim', 
    'leave mikham', 'leave mikhastam','morkhasi',
]

# Negation patterns - these patterns mean it's NOT a leave request
# Pattern: "مرخصی + negation" within close proximity
NEGATION_PHRASES = [
    'مرخصی نرفتم',      # didn't go on leave
    'مرخصی نمیرم',      # won't go on leave
    'مرخصی نمی‌رم',     # won't go on leave (with ZWNJ)
    'morakhasi naraftam',
    'morakhasi nemiram',
]

# Personal channels mapping
PERSONAL_CHANNELS = {
    'masoud_chan': 'Masoud Rafiei',
    'maryam_y_chan': 'Maryam Yousefi',
    'ehsan_chan': 'Ehsan Yousefi',
    'hosseinali_chan': 'Hosseinali Shirali',
    'erfan_chan': 'Erfan Heidari',
    'keivan_chan': 'Keivan Sadeghi',
    'nader_chan': 'Nader Shabibi',
    'mahsa_chan': 'Zeinabsadat Hejazi',
    'yassin_chan': 'Yassin Alivand',
    'mohsen_chan': 'Mohsen Roudsaz',
    'masoud_sereshki_chan': 'Masoud Sereshki',
}

# Team members mapping
TEAM_MEMBERS = {
    'mari': 'Maryam Yousefi',
    'k1 sadeghi': 'Keivan Sadeghi',
    'keivan': 'Keivan Sadeghi',
    'nissay87': 'Ehsan Yousefi',
    'ehsan': 'Ehsan Yousefi',
    'esi': 'Ehsan Yousefi',
    'mohsen': 'Mohsen Roudsaz',
    'nader': 'Nader Shabibi',
    'mahsa': 'Zeinabsadat Hejazi',
    'hossein shahreza': 'Hosseinali Shirali',
    'hosseinali': 'Hosseinali Shirali',
    'masoud rafiei': 'Masoud Rafiei',
    'masoud sereshki': 'Masoud Sereshki',
    'yassin': 'Yassin Alivand',
    'erfan': 'Erfan Heidari',
}

# Iran timezone
IRAN_OFFSET = timedelta(hours=3, minutes=30)

def get_latest_discord_file():
    import glob
    files = glob.glob(os.path.join(DISCORD_EXPORTS_DIR, '*.json'))
    if not files:
        return None
    return max(files, key=os.path.getctime)

def normalize_name(display_name):
    name_lower = display_name.lower().strip()
    if name_lower in TEAM_MEMBERS:
        return TEAM_MEMBERS[name_lower]
    for key, value in TEAM_MEMBERS.items():
        if key in name_lower:
            return value
    if name_lower == 'masoud':
        return 'Masoud Rafiei'
    return display_name

def is_leave_request(content):
    content_lower = content.lower()
    
    # Check if it's a negation phrase (e.g., "مرخصی نرفتم")
    for phrase in NEGATION_PHRASES:
        if phrase in content_lower:
            return False
    
    return any(p in content_lower for p in LEAVE_PATTERNS)

def parse_timestamp(ts):
    try:
        utc_dt = datetime.fromisoformat(ts.replace('+00:00', ''))
        iran_dt = utc_dt + IRAN_OFFSET
        return iran_dt
    except:
        return None

def build_leave_database():
    """Scan all messages and build leave database"""
    discord_file = get_latest_discord_file()
    if not discord_file:
        print("No Discord export file found!")
        return
    
    print(f"Reading: {discord_file}")
    
    with open(discord_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    channels = data.get('channels', {})
    leave_db = defaultdict(dict)
    
    # Track messages processed
    total_messages = 0
    leave_messages = 0
    
    # Scan all channels
    for channel_name, channel_data in channels.items():
        if not isinstance(channel_data, dict):
            continue
        
        messages = channel_data.get('messages', [])
        
        # Determine person from channel (for personal channels)
        channel_person = PERSONAL_CHANNELS.get(channel_name)
        
        for msg in messages:
            total_messages += 1
            content = msg.get('content', '')
            
            if not is_leave_request(content):
                continue
            
            leave_messages += 1
            
            # Get author
            author_data = msg.get('author', {})
            display_name = author_data.get('display_name', author_data.get('name', ''))
            author_name = normalize_name(display_name)
            
            # If it's a personal channel, attribute to channel owner
            # (People often request leave FOR themselves in their own channel)
            if channel_person:
                person_name = channel_person
            else:
                person_name = author_name
            
            # Get message date
            timestamp = parse_timestamp(msg.get('timestamp', ''))
            if not timestamp:
                continue
            message_date = timestamp.strftime('%Y-%m-%d')
            
            # Parse leave dates from message
            result = parse_leave_request(content, message_date)
            
            # Add each leave date to database
            for leave_date in result.get('dates', []):
                leave_db[person_name][leave_date] = {
                    'type': result.get('type', 'full_day'),
                    'hours': result.get('hours'),
                    'source_msg': content[:100],
                    'msg_date': message_date,
                    'channel': channel_name,
                }
    
    print(f"Processed {total_messages} messages")
    print(f"Found {leave_messages} leave-related messages")
    
    # Save database
    with open(LEAVE_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(dict(leave_db), f, ensure_ascii=False, indent=2)
    
    print(f"Leave database saved to: {LEAVE_DB_FILE}")
    
    # Summary
    print("\n=== Leave Summary ===")
    for person, dates in sorted(leave_db.items()):
        full_days = sum(1 for d in dates.values() if d['type'] != 'hourly')
        hourly = sum(1 for d in dates.values() if d['type'] == 'hourly')
        print(f"  {person}: {full_days} full days, {hourly} hourly")
    
    total_days = sum(len(d) for d in leave_db.values())
    print(f"\nTotal leave entries: {total_days}")

if __name__ == '__main__':
    build_leave_database()
