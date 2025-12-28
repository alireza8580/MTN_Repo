#!/usr/bin/env python3
"""
Remote Work Tracker - Track remote work days for Yassin
Parses Discord messages for دورکار/اهواز patterns
Uses jdatetime for accurate Persian date conversion
"""

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

try:
    import jdatetime
except ImportError:
    print("jdatetime not installed. Run: pip install jdatetime")
    jdatetime = None

# Only track remote work for Yassin
TRACKED_USERS = ['yassin', 'nissay', 'alivand']

# Patterns indicating remote work (NOT leave)
REMOTE_PATTERNS = [
    'دورکار', 'دور کار', 'دورکاری', 'دور کاری',
    'remote', 'انلاین هستم', 'آنلاین هستم'
]

# Location patterns that indicate remote work for Yassin
LOCATION_PATTERNS = ['اهواز', 'ahvaz', 'ahwaz', 'شیراز', 'shiraz']

# Persian months for date parsing
PERSIAN_MONTHS = {
    'فروردین': 1, 'farvardin': 1,
    'اردیبهشت': 2, 'ordibehesht': 2,
    'خرداد': 3, 'khordad': 3,
    'تیر': 4, 'tir': 4,
    'مرداد': 5, 'mordad': 5,
    'شهریور': 6, 'shahrivar': 6,
    'مهر': 7, 'mehr': 7,
    'آبان': 8, 'aban': 8,
    'آذر': 9, 'اذر': 9, 'azar': 9,
    'دی': 10, 'dey': 10, 'day': 10,
    'بهمن': 11, 'bahman': 11,
    'اسفند': 12, 'esfand': 12
}

DISCORD_EXPORT_DIR = '/root/infrastructure/discord_exports'
REMOTE_WORK_DB_FILE = '/root/infrastructure/scripts/remote_work_database.json'


def persian_to_gregorian(year: int, month: int, day: int) -> str:
    """Convert Persian date to Gregorian date string."""
    if not jdatetime:
        return None
    try:
        jd = jdatetime.date(year, month, day)
        gd = jd.togregorian()
        return gd.strftime('%Y-%m-%d')
    except:
        return None


def get_persian_year_from_gregorian(gdate: datetime) -> int:
    """Get Persian year from Gregorian date."""
    if not jdatetime:
        return 1404  # Default
    jd = jdatetime.date.fromgregorian(date=gdate.date())
    return jd.year


def get_latest_discord_export():
    """Get the most recent Discord export file."""
    export_dir = Path(DISCORD_EXPORT_DIR)
    if not export_dir.exists():
        return None
    
    json_files = list(export_dir.glob('*.json'))
    if not json_files:
        return None
    
    # Sort by modification time, newest first
    json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return json_files[0]


def is_yassin(author_name: str) -> bool:
    """Check if author is Yassin."""
    author_lower = author_name.lower()
    return any(pattern in author_lower for pattern in TRACKED_USERS)


def has_remote_pattern(content: str) -> bool:
    """Check if content has remote work patterns."""
    content_lower = content.lower()
    # Must have remote pattern AND location for Yassin
    has_remote = any(p in content_lower for p in REMOTE_PATTERNS)
    has_location = any(p in content_lower for p in LOCATION_PATTERNS)
    return has_remote or has_location


def detect_month_from_content(content: str, message_date: datetime = None) -> int:
    """Detect Persian month number from content or message date."""
    content_lower = content.lower()
    for month_name, month_num in PERSIAN_MONTHS.items():
        if month_name in content_lower or month_name in content:
            return month_num
    
    # If no month in content, use message date's month
    if message_date and jdatetime:
        jd = jdatetime.date.fromgregorian(date=message_date.date())
        return jd.month
    
    return None


def extract_remote_work_dates(content: str, message_date: datetime) -> list:
    """
    Extract remote work dates from message.
    Returns list of Gregorian date strings.
    """
    dates = []
    
    # Get Persian year from message date
    persian_year = get_persian_year_from_gregorian(message_date)
    
    # Detect month from content or message date
    month = detect_month_from_content(content, message_date)
    
    # Pattern 1: "13ام شنبه تا 17 ام چهارشنبه" (Ordibehesht)
    range_match = re.search(r'(\d+)\s*(?:ام|م)?\s*(?:شنبه|یکشنبه|دوشنبه|سه\s*شنبه|چهارشنبه|پنجشنبه|جمعه)?\s*تا\s*(\d+)\s*(?:ام|م)?', content)
    if range_match and month:
        start_day = int(range_match.group(1))
        end_day = int(range_match.group(2))
        
        for day in range(start_day, end_day + 1):
            gdate = persian_to_gregorian(persian_year, month, day)
            if gdate:
                # Skip weekends (Thu=3, Fri=4)
                dt = datetime.strptime(gdate, '%Y-%m-%d')
                if dt.weekday() not in [3, 4]:
                    dates.append(gdate)
    
    # Pattern 2: "19 اذر تا 28-29-30 آذر" (range with multiple end days)
    multi_end_match = re.search(r'(\d+)\s*(?:ام|م)?\s*(?:آذر|اذر|[^\s]+)?\s*تا\s*([\d\-\s]+)\s*(?:آذر|اذر|آبان|مهر)', content)
    if multi_end_match and month:
        start_day = int(multi_end_match.group(1))
        end_part = multi_end_match.group(2)
        # Extract max number from "28-29-30"
        end_numbers = [int(n) for n in re.findall(r'\d+', end_part)]
        if end_numbers:
            end_day = max(end_numbers)
            
            for day in range(start_day, end_day + 1):
                gdate = persian_to_gregorian(persian_year, month, day)
                if gdate:
                    # Skip weekends (Thu=3, Fri=4)
                    dt = datetime.strptime(gdate, '%Y-%m-%d')
                    if dt.weekday() not in [3, 4]:
                        dates.append(gdate)
    
    # Pattern 3: "از 1 شهریور" - from specific date
    from_match = re.search(r'از\s*(\d+)\s*(?:ام|م)?\s*(شهریور|مرداد|آذر|تیر|خرداد|اردیبهشت)', content)
    if from_match:
        day = int(from_match.group(1))
        month_name = from_match.group(2)
        month = PERSIAN_MONTHS.get(month_name)
        if month:
            # Default to one week of remote work
            for d in range(day, day + 7):
                try:
                    gdate = persian_to_gregorian(persian_year, month, d)
                    if gdate:
                        dt = datetime.strptime(gdate, '%Y-%m-%d')
                        if dt.weekday() not in [3, 4]:
                            dates.append(gdate)
                except:
                    break
    
    # Pattern 4: "هفته آینده" or "هفته بعد" - next week (5 working days)
    if ('هفته آینده' in content or 'هفته بعد' in content) and not dates:
        # Get next Saturday (start of Iranian work week)
        current = message_date
        days_until_saturday = (5 - current.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        next_saturday = current + timedelta(days=days_until_saturday)
        
        for i in range(5):  # Sat-Wed (5 working days)
            date = next_saturday + timedelta(days=i)
            dates.append(date.strftime('%Y-%m-%d'))
    
    return dates


def parse_remote_work_messages(export_file: Path) -> dict:
    """Parse Discord export and find remote work messages."""
    with open(export_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    remote_work_entries = {}  # {name: {date: details}}
    
    for ch_name, ch in data.get('channels', {}).items():
        if not isinstance(ch, dict):
            continue
        
        for msg in ch.get('messages', []):
            author = msg.get('author', {}).get('display_name', '')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', '')
            
            if not is_yassin(author):
                continue
            
            if not has_remote_pattern(content):
                continue
            
            # Skip if this looks like leave request (مرخصی) not remote work
            # Remote work = "دورکار" + "اهواز/شیراز" + "آنلاین"
            content_lower = content.lower()
            is_remote = any(p in content for p in REMOTE_PATTERNS)
            has_location = any(p in content_lower for p in LOCATION_PATTERNS)
            
            # If it says مرخصی without دورکار, skip it
            if 'مرخصی' in content and not is_remote:
                continue
            
            # Parse message date
            try:
                msg_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                continue
            
            # Extract dates using improved function
            dates = extract_remote_work_dates(content, msg_date)
            
            # Store entry
            name = 'Yassin Alivand'
            if name not in remote_work_entries:
                remote_work_entries[name] = {}
            
            # Determine location
            location = 'remote'
            if 'اهواز' in content or 'ahvaz' in content.lower():
                location = 'اهواز'
            elif 'شیراز' in content or 'shiraz' in content.lower():
                location = 'شیراز'
            
            for date in dates:
                remote_work_entries[name][date] = {
                    'type': 'remote_work',
                    'location': location,
                    'message': content[:300].replace('\n', ' '),
                    'message_date': timestamp[:10],
                    'channel': ch_name
                }
    
    return remote_work_entries


def build_remote_work_database():
    """Build the remote work database from Discord exports."""
    export_file = get_latest_discord_export()
    if not export_file:
        print("No Discord export found!")
        return {}
    
    print(f"Processing: {export_file}")
    
    entries = parse_remote_work_messages(export_file)
    
    # Save to file
    with open(REMOTE_WORK_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    
    # Print summary
    for name, dates in entries.items():
        print(f"\n{name}: {len(dates)} remote work days")
        for date, details in sorted(dates.items()):
            print(f"  {date}: {details['location']} ({details['message_date']})")
    
    return entries


def load_remote_work_database() -> dict:
    """Load the remote work database."""
    if os.path.exists(REMOTE_WORK_DB_FILE):
        with open(REMOTE_WORK_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def is_remote_work(name: str, date_str: str) -> dict:
    """Check if person was working remotely on given date."""
    db = load_remote_work_database()
    
    # Check exact name match
    if name in db and date_str in db[name]:
        return db[name][date_str]
    
    # Check similar names
    for db_name, dates in db.items():
        if name.lower() in db_name.lower() or db_name.lower() in name.lower():
            if date_str in dates:
                return dates[date_str]
        # First name match
        if name.split()[0].lower() == db_name.split()[0].lower():
            if date_str in dates:
                return dates[date_str]
    
    return None


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Track remote work days')
    parser.add_argument('--build', action='store_true', help='Build/rebuild database')
    parser.add_argument('--check', nargs=2, metavar=('NAME', 'DATE'), help='Check if person was remote on date')
    args = parser.parse_args()
    
    if args.build:
        build_remote_work_database()
    elif args.check:
        result = is_remote_work(args.check[0], args.check[1])
        if result:
            print(f"Remote work: {result}")
        else:
            print("Not remote work")
    else:
        # Default: build and show summary
        build_remote_work_database()
