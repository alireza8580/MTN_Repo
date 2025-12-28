#!/usr/bin/env python3
"""
DBA Team Attendance Tracker
Tracks: check-in/check-out times, brb duration, work hours, leave requests, idle time
"""
import json
import re
import csv
from datetime import datetime, timedelta
from collections import defaultdict
import os
import glob

# === CONFIG ===
# Use environment variables with fallback to original paths for Docker compatibility
BASE_DIR = os.environ.get('APP_BASE_DIR', '/root/infrastructure')
SCRIPTS_DIR = os.environ.get('SCRIPTS_DIR', os.path.join(BASE_DIR, 'scripts'))

DISCORD_EXPORTS_DIR = os.environ.get('DISCORD_EXPORT_DIR', os.path.join(BASE_DIR, 'discord_exports'))
LEAVE_LOG_FILE = os.path.join(SCRIPTS_DIR, 'leave_log.json')
LEAVE_DATABASE_FILE = os.path.join(SCRIPTS_DIR, 'leave_database.json')
ATTENDANCE_DATABASE_FILE = os.path.join(SCRIPTS_DIR, 'attendance_database.json')  # Check-in/out times & leave ranges
EMAIL_DIR = os.environ.get('MTN_EMAIL_DIR', os.path.join(BASE_DIR, 'mtn_emails'))
IDLE_TIME_FILE = os.path.join(SCRIPTS_DIR, 'discord/idle_time_database.json')
IDLE_USERS_FILE = os.path.join(SCRIPTS_DIR, 'discord/idle_time_users.json')
OFFLINE_TIME_FILE = os.path.join(SCRIPTS_DIR, 'discord/offline_time_database.json')
VOICE_TIME_FILE = os.path.join(SCRIPTS_DIR, 'discord/voice_time_database.json')
STANDBY_SHIFT_FILE = os.environ.get('STANDBY_SHIFT_FILE', os.path.join(BASE_DIR, 'MTN_standby_shift.csv'))
HOLIDAY_SHIFT_FILE = os.environ.get('HOLIDAY_SHIFT_FILE', os.path.join(BASE_DIR, 'holiday_shifts.csv'))

# Team members mapping (Discord display name -> Standard name)
# EXCLUDED: Alireza Aghajanzadeh (owner), Maryam Marefati (team lead)
TEAM_MEMBERS = {
    # Discord usernames -> Standard names (extracted from Discord exports)
    # Format: 'display_name_lower': 'Standard Name',
    
    # Maryam Yousefi - Discord: maryam.you, Display: Mari
    'mari': 'Maryam Yousefi',
    'maryam.you': 'Maryam Yousefi',
    
    # Keivan Sadeghi - Discord: k1.sadeghi_15101, Display: K1 Sadeghi
    'k1 sadeghi': 'Keivan Sadeghi',
    'k1.sadeghi_15101': 'Keivan Sadeghi',
    'keivan': 'Keivan Sadeghi',
    
    # Yassin Alivand - Discord: nissay87
    'nissay87': 'Yassin Alivand',
    'yassin': 'Yassin Alivand',
    
    # Ehsan Yousefi - Discord: ehsan.yo, Display: Esi
    'ehsan': 'Ehsan Yousefi',
    'esi': 'Ehsan Yousefi',
    'ehsan.yo': 'Ehsan Yousefi',
    
    # Mohsen Roudsaz - Discord: mohsen.roud, Display: Mohsen
    'mohsen': 'Mohsen Roudsaz',
    'mohsen.roud': 'Mohsen Roudsaz',
    
    # Nader Shabibi - Discord: nader3307, Display: Nader
    'nader': 'Nader Shabibi',
    'nader3307': 'Nader Shabibi',
    
    # Zeinabsadat Hejazi - Discord: mahsahejszi, Display: Mahsa
    'mahsa': 'Zeinabsadat Hejazi',
    'mahsahejszi': 'Zeinabsadat Hejazi',
    
    # Hosseinali Shirali - Discord: hosseinshahreza, Display: hossein shahreza
    'hossein shahreza': 'Hosseinali Shirali',
    'hosseinshahreza': 'Hosseinali Shirali',
    'hosseinali': 'Hosseinali Shirali',
    
    # Masoud Rafiei - Discord: masoudraafiee, Display: Masoud
    'masoud rafiei': 'Masoud Rafiei',
    'masoudraafiee': 'Masoud Rafiei',
    'masoud': 'Masoud Rafiei',  # When just 'masoud' without surname
    
    # Masoud Sereshki - Discord: masoudsereshki, Display: Masoud Sereshki
    'masoud sereshki': 'Masoud Sereshki',
    'masoudsereshki': 'Masoud Sereshki',
    
    # Erfan Heidari - Discord: erfan_heidari, Display: Erfan
    'erfan': 'Erfan Heidari',
    'erfan_heidari': 'Erfan Heidari',
    
    # === EXCLUDED MEMBERS (included for name normalization, filtered by EXCLUDED_MEMBERS set) ===
    # Maryam Marefati - Discord: maryam6409, Display: Maryam
    'maryam': 'Maryam Marefati',
    'maryam6409': 'Maryam Marefati',
    
    # Alireza Aghajanzadeh - Discord: alireza8580, Display: Alireza
    'alireza': 'Alireza Aghajanzadeh',
    'alireza8580': 'Alireza Aghajanzadeh',
    
    # Hossein Feizollahi - Discord: hosein_feyzollahi, Display: Hosein Feyzollahi
    'hosein feyzollahi': 'Hossein Feizollahi',
    'hosein_feyzollahi': 'Hossein Feizollahi',
    
    # === LEFT THE TEAM ===
    # Hadi Toofiani - Discord: hadi.toofani9531 - LEFT 2025-12-23
    # 'hadi.toofani': 'Hadi Toofiani',
    # 'hadi.toofani9531': 'Hadi Toofiani',
}

# People to EXCLUDE from attendance tracking
# - Alireza Aghajanzadeh: Owner/Consultant
# - Maryam Marefati: Team Lead
# - Hossein Feizollahi: Senior + GoldenGate Consultant (different schedule)
EXCLUDED_MEMBERS = {'Alireza Aghajanzadeh', 'Maryam Marefati', 'Hossein Feizollahi'}

# Standby CSV name -> Standard name mapping
STANDBY_NAME_MAPPING = {
    # 'hadi': 'Hadi Toofiani',  # LEFT THE TEAM
    'keyvan': 'Keivan Sadeghi',
    'keivan': 'Keivan Sadeghi',
    'nader': 'Nader Shabibi',
    'masoud': 'Masoud Rafiei',  # In standby CSV, 'Masoud' refers to Rafiei (Sereshki has no standby)
    'maryam': 'Maryam Marefati',
    'mary': 'Maryam Yousefi',  # In standby CSV, 'Mary' refers to mari (Maryam Yousefi)
    'mari': 'Maryam Yousefi',
    'mahsa': 'Zeinabsadat Hejazi',
    'hossein': 'Hosseinali Shirali',
    'erfan': 'Erfan Heidari',
    'mohsen': 'Mohsen Roudsaz',
    'ehsan': 'Ehsan Yousefi',
    'yassin': 'Yassin Alivand',
}

# Personal channels mapping (channel name -> Standard name)
# People request vacation in their personal channels
# Format: 'channel_name': 'Standard Name',  # email prefix
# NOTE: Include both old and new channel names for historical data compatibility
PERSONAL_CHANNELS = {
    # New channel names (after Dec 2025 rename)
    'mahsa_chan': 'Zeinabsadat Hejazi',       # zeinabsadat.he@
    'masoud_rafiei_chan': 'Masoud Rafiei',    # masoud.raf@
    'masoud_sereshki_chan': 'Masoud Sereshki', # masoud.s@
    'mari_chan': 'Maryam Yousefi',            # maryam.you@
    'keivan_chan': 'Keivan Sadeghi',          # keivan.s@
    'ehsan_chan': 'Ehsan Yousefi',            # ehsan.you@
    # 'maryam_chan': 'Maryam Marefati',       # EXCLUDED - Team Lead
    'nader_chan': 'Nader Shabibi',            # nader.sh@
    'erfan_chan': 'Erfan Heidari',            # erfan.he@
    'hosseinali_chan': 'Hosseinali Shirali',  # hosseinali.s@
    'yassin_chan': 'Yassin Alivand',          # yasin.aa@
    'mohsen_chan': 'Mohsen Roudsaz',          # mohsen.r@
    
    # Old channel names (for historical data before Dec 2025)
    'mahsa_chann': 'Zeinabsadat Hejazi',
    'maryam_y_chan': 'Maryam Yousefi',
    'keivan_chann': 'Keivan Sadeghi',
    'erfan_chann': 'Erfan Heidari',
    'hosseinali-chann': 'Hosseinali Shirali',
    'mohsen_chann': 'Mohsen Roudsaz',
}

# Work hours config (flexible hours)
EXPECTED_CHECK_IN = 8  # 8:00 AM (earliest acceptable)
EXPECTED_CHECK_IN_LATEST = 9.5  # 9:30 AM (latest acceptable - flexible)
EXPECTED_CHECK_OUT = 17  # 5:00 PM (17:00 - earliest acceptable)
EXPECTED_CHECK_OUT_LATEST = 20  # 8:00 PM (20:00 - latest acceptable, extended)
MIN_WORK_HOURS = 8
WORK_HOURS_TOTAL_MINUTES = 720  # 8:00 to 20:00 = 12 hours = 720 minutes (for idle % calc)
BRB_DEFAULT_MAX_MINUTES = 30  # BRB over 30min needs hourly leave
BRB_LUNCH_MINUTES = 60  # Lunch break is 1 hour

# Iran weekend: Thursday (3) and Friday (4)
# weekday(): Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
# In Iran: Saturday=0, Sunday=1, Monday=2, Tuesday=3, Wednesday=4, Thursday=5, Friday=6
# So Thursday=3, Friday=4 are weekends
WEEKEND_DAYS = [3, 4]  # Thursday and Friday (Python weekday())


def is_weekend(date_str):
    """Check if date is weekend in Iran (Thursday/Friday)"""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return dt.weekday() in WEEKEND_DAYS


def get_oncall_person(date_str):
    """
    Get who is on-call (standby) for this date from MTN_standby_shift.csv
    Returns: (main_oncall, support_person) tuple
    
    On Wednesday (handover day):
    - main_oncall = new week's on-call (incoming)
    - support_person = previous week's on-call (outgoing)
    """
    if not os.path.exists(STANDBY_SHIFT_FILE):
        return None, None
    
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    is_wednesday = target_date.weekday() == 2  # Wednesday = 2
    
    main_oncall = None
    previous_oncall = None
    
    with open(STANDBY_SHIFT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    for i, row in enumerate(rows):
        day_str = row.get('day', '').strip('"')
        try:
            csv_date = datetime.strptime(day_str, '%A, %B %d, %Y')
            if csv_date.date() == target_date.date():
                # Found the date
                shift_name = row.get('shift', '').strip().lower()
                support = row.get('support (Thursday and Friday)', '').strip().lower()
                
                # Map to standard names
                main_oncall = STANDBY_NAME_MAPPING.get(shift_name, None)
                support_name = STANDBY_NAME_MAPPING.get(support, None) if support != 'no support' else None
                
                # On Wednesday, also get the previous week's on-call person
                if is_wednesday and i > 0:
                    # Look backwards to find the previous week's on-call
                    prev_row = rows[i - 1]
                    prev_shift = prev_row.get('shift', '').strip().lower()
                    previous_oncall = STANDBY_NAME_MAPPING.get(prev_shift, None)
                    
                    # Return both: main is new week, support is outgoing
                    if previous_oncall and previous_oncall != main_oncall:
                        return main_oncall, previous_oncall
                
                return main_oncall, support_name
        except ValueError:
            continue
    
    return None, None


def is_oncall_wednesday(date_str, oncall_person):
    """
    Check if the date is Wednesday and oncall_person is the oncall for that week.
    On Wednesday, oncall person has special schedule:
    - Option 1: Come 8:00-12:00, rest until 17:00
    - Option 2: Come at 13:00 and stay
    Either way, they should not be flagged for late/early issues.
    """
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    return target_date.weekday() == 2 and oncall_person is not None  # Wednesday = 2


def get_oncall_wednesday_valid_times():
    """
    Get valid check-in/check-out times for oncall person on Wednesday.
    Returns dict with validation rules.
    
    Option 1: 8:00-12:00 morning, rest until 17:00 (no afternoon work)
    Option 2: 13:00+ afternoon start
    
    Either is valid - oncall person should not be flagged.
    """
    return {
        'option1_checkin_start': 8.0,   # 08:00
        'option1_checkin_end': 9.5,     # 09:30 (normal latest)
        'option1_checkout_start': 12.0, # 12:00
        'option1_checkout_end': 13.0,   # 13:00
        'option2_checkin_start': 13.0,  # 13:00
        'option2_checkin_end': 14.0,    # 14:00 (flexible)
    }


def get_holiday_support_person(date_str):
    """
    Get the support person for a holiday from holiday_shifts.csv
    During holidays, the support person is responsible from 08:00-17:00.
    
    CSV format: date (Jalali),support person
    Example: 1404/03/14,Alireza
    
    Returns: support_person name or None
    """
    try:
        import jdatetime
    except ImportError:
        return None
    
    if not os.path.exists(HOLIDAY_SHIFT_FILE):
        return None
    
    # Convert Gregorian date to Jalali
    try:
        greg_date = datetime.strptime(date_str, '%Y-%m-%d')
        jalali_date = jdatetime.date.fromgregorian(date=greg_date)
        jalali_str = jalali_date.strftime('%Y/%m/%d')  # e.g., 1404/03/14
    except:
        return None
    
    with open(HOLIDAY_SHIFT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_date = row.get('date', '').strip()
            # Normalize date format (handle 1404/3/14 vs 1404/03/14)
            try:
                parts = csv_date.split('/')
                if len(parts) == 3:
                    csv_normalized = f"{parts[0]}/{int(parts[1]):02d}/{int(parts[2]):02d}"
                    if csv_normalized == jalali_str:
                        support = row.get('support person', '').strip()
                        # Map short name to standard name
                        return map_holiday_name(support)
            except:
                continue
    
    return None


def map_holiday_name(name):
    """Map holiday CSV names to standard team member names"""
    name_lower = name.lower()
    name_mapping = {
        'alireza': 'Alireza Aghajanzadeh Gheshlaghi',
        'maryam': 'Maryam Marefati',
        'mary': 'Maryam Yousefi',
        'mahsa': 'Zeinabsadat Hejazi',
        'hadi': 'Hadi Toofiani',  # Former member
        'keyvan': 'Keivan Sadeghi',
        'nader': 'Nader Shabibi',
        'ehsan': 'Ehsan Yousefi',
        'masoud': 'Masoud Rafiei',
        'erfan': 'Erfan Heidari',
        'hossein': 'Hossein Feizollahi',
    }
    return name_mapping.get(name_lower, name)


def is_holiday(date_str):
    """
    Check if date is a holiday (from holiday_shifts.csv)
    Returns: True if the date is in the holiday list
    """
    return get_holiday_support_person(date_str) is not None


def get_oncall_week_range(date_str):
    """
    Get the on-call week range for a given date.
    On-call starts Wednesday 17:00 and ends next Wednesday 08:00.
    Returns: (start_date, end_date) as strings
    """
    target_date = datetime.strptime(date_str, '%Y-%m-%d')
    target_weekday = target_date.weekday()  # 0=Mon, 2=Wed
    
    # Find the Wednesday that starts this on-call week
    days_since_wed = (target_weekday - 2) % 7  # Wednesday = 2
    if days_since_wed == 0:  # It's Wednesday
        # Before 17:00, use last week's on-call
        # After 17:00, use this week's on-call
        # For simplicity, assume full day = last Wednesday's on-call
        oncall_start = target_date - timedelta(days=7)
    else:
        oncall_start = target_date - timedelta(days=days_since_wed)
    
    oncall_end = oncall_start + timedelta(days=7)
    
    return oncall_start.strftime('%Y-%m-%d'), oncall_end.strftime('%Y-%m-%d')


def get_latest_discord_file():
    """Get the most recent Discord export file"""
    files = glob.glob(os.path.join(DISCORD_EXPORTS_DIR, '*.json'))
    if not files:
        return None
    return max(files, key=os.path.getctime)


# Iran timezone offset: +03:30
IRAN_OFFSET = timedelta(hours=3, minutes=30)


def parse_timestamp(ts):
    """Parse Discord timestamp to datetime in Iran timezone (+3:30)"""
    try:
        # Format: 2025-12-20T05:27:00.000000+00:00
        utc_dt = datetime.fromisoformat(ts.replace('+00:00', ''))
        # Convert to Iran time
        iran_dt = utc_dt + IRAN_OFFSET
        return iran_dt
    except:
        return None

def normalize_name(display_name):
    """Normalize Discord display name to standard name"""
    name_lower = display_name.lower().strip()
    
    # Direct match first (for names like "masoud sereshki")
    if name_lower in TEAM_MEMBERS:
        return TEAM_MEMBERS[name_lower]
    
    # Partial match - check if key is in display name
    for key, value in TEAM_MEMBERS.items():
        if key in name_lower:
            return value
    
    # Special case for just "Masoud" - default to Rafiei
    if name_lower == 'masoud':
        return 'Masoud Rafiei'
    
    return display_name

def parse_brb_duration(content):
    """Parse brb message for custom duration like 'brb 1h', 'brb 2h', 'brb nahar'"""
    content_lower = content.lower().strip()
    
    # Check for hour specification
    match = re.search(r'brb\s*(\d+)\s*h', content_lower)
    if match:
        return int(match.group(1)) * 60  # Return minutes
    
    # Check for lunch patterns - assume 1 hour
    lunch_patterns = ['nahar', 'ناهار', 'lunch', 'ghaza', 'غذا']
    if any(p in content_lower for p in lunch_patterns):
        return BRB_LUNCH_MINUTES  # 60 minutes for lunch
    
    # Default brb
    return BRB_DEFAULT_MAX_MINUTES

def is_greeting(content):
    """Check if message is a morning greeting"""
    patterns = ['salam', 'صبح', 'sobh', 'روز بخیر', 'rooz', 'bekheir', 'bkheir', 'be kheir', 'vorud', 'ورود']
    content_lower = content.lower()
    
    # Check for 'hi' separately - must be word boundary (standalone or with punctuation)
    has_hi = content_lower.startswith('hi ') or content_lower.startswith('hi,') or content_lower == 'hi' or ' hi ' in content_lower
    
    has_greeting_pattern = any(p in content_lower for p in patterns) or has_hi
    has_khaste = 'khaste' in content_lower
    has_salam = 'salam' in content_lower
    
    # If both salam and khaste exist (like "salam khaste nabashid") - it's a greeting
    # If only khaste exists without salam - it's a goodbye (not greeting)
    if has_greeting_pattern:
        if has_khaste and has_salam:
            return True  # "salam ... khaste nabashid" = greeting
        elif has_khaste:
            return False  # Only "khaste nabashid" = goodbye
        else:
            return True  # Normal greeting without khaste
    return False

def is_goodbye(content):
    """Check if message is an end-of-day goodbye"""
    # Common patterns and typos for goodbye
    patterns = [
        'khaste nabashid', 'khasteh nabashid', 
        'khaste nabshid', 'khasteh nabshid',  # Common typos (missing 'a')
        'khastenabashid', 'khastehnabashid',  # No space variants
        'khasteh nabasheed', 'khaste nabasheed',  # Different transliteration
        'خسته نباشید', 'خسته‌نباشید',  # Persian with/without half-space
        'felan', 'shb khosh', 'شب خوش', 
        'khodafez', 'khodahafez', 'khodanegahdar', 
        'bye', 'خروج',
        'shabetun khosh', 'shabetoon khosh',  # Good night variants
        'shab bekheir', 'shabbekheir',  # Good night
    ]
    content_lower = content.lower()
    
    # If message has BOTH greeting (salam) AND goodbye (khaste), treat as greeting not goodbye
    # e.g., "salam mojadad khaste nabashid" is a greeting (check-in), not goodbye
    # But "felan ba ejaze morkhas... khaste nabashid" is goodbye (no salam)
    greeting_patterns = ['salam', 'سلام', 'sobh', 'صبح', 'روز بخیر']
    if any(gp in content_lower for gp in greeting_patterns):
        return False
    
    return any(p in content_lower for p in patterns)

def is_brb(content):
    """Check if message is brb (be right back)"""
    return content.lower().strip().startswith('brb')

def is_brb_lunch(content):
    """Check if BRB is for lunch (gets 1 hour instead of 30min)"""
    content_lower = content.lower()
    lunch_patterns = ['nahar', 'ناهار', 'lunch', 'ghaza', 'غذا']
    return is_brb(content) and any(p in content_lower for p in lunch_patterns)

def is_brb_special(content):
    """
    Check if BRB is for special/emergency reasons (power outage, internet, etc.)
    
    PROTOTYPE - Currently commented out in calculations.
    When activated:
    - Special BRB gets up to 2 hours allowed (similar to lunch)
    - Does NOT deduct from effective work time
    - Max 2 hours per day for all special BRBs combined
    
    Examples:
    - brb bargh (power outage)
    - brb net / brb internet (internet issue)
    - brb ab (water)
    - brb ezterar (emergency)
    """
    content_lower = content.lower()
    special_patterns = [
        'bargh', 'برق',           # Power outage
        'net', 'internet', 'اینترنت', 'نت',  # Internet issues
        'ab', 'آب',               # Water
        'ezterar', 'اضطراری',     # Emergency
        'emergency',
    ]
    return is_brb(content) and any(p in content_lower for p in special_patterns)

# TODO: When activating special BRB:
# 1. Add 'brb_special_time' to attendance defaultdict
# 2. Track special BRB duration separately
# 3. Allow up to 120 minutes (2 hours) of special BRB without deduction
# 4. Add brb_special_excess to CSV export

def is_wednesday(date_str):
    """Check if date is Wednesday (shift handover day)"""
    from datetime import datetime
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return dt.weekday() == 2  # Monday=0, Wednesday=2

def calculate_oncall_metrics(name, date_str, data, is_new_oncall=False, is_prev_oncall=False):
    """
    Calculate on-call person's metrics based on day of week.
    
    Wednesday (shift handover):
    - New on-call: Must have 4 hours presence
      - First check-in and check-out matter
      - Second check-in must be before 17:00
      - Effective time = actual hours + 5 (so if 4h worked -> 9h effective)
    - Previous on-call: Gets automatic 9 hours effective (resting after shift)
    
    Saturday to Tuesday:
    - On-call: Gets automatic 9 hours effective (only check-in matters)
    
    Returns dict with:
    - show_metrics: bool - whether to show metrics for this person
    - check_in_status: 'OK' / 'LATE' / 'MISSING'
    - expected_hours: float - expected work hours for on-call
    - notes: str - any special notes
    - auto_effective: float - automatic effective hours (9 for most cases)
    """
    result = {
        'show_metrics': True,
        'check_in_status': '',
        'expected_hours': 0,
        'notes': '',
        'second_check_in': None,  # For Wednesday new on-call
        'effective_bonus': 0,  # Hours to add to effective time (9-4=5 for Wed on-call)
        'auto_effective': 0,  # Automatic 9 hours for non-Wednesday on-call
    }
    
    # Previous on-call on Wednesday - gets 9 hours automatic (resting after shift)
    if is_wednesday(date_str) and is_prev_oncall:
        result['show_metrics'] = False
        result['notes'] = 'آنکال قبلی - استراحت'
        result['auto_effective'] = 9  # Automatic 9 hours
        return result
    
    # New on-call on Wednesday - show metrics but with adjustments
    if is_wednesday(date_str) and is_new_oncall:
        result['show_metrics'] = True  # Show metrics normally
        result['expected_hours'] = 4
        result['effective_bonus'] = 5  # Add 5 hours (9-4=5) to effective time
        
        # Find second check-in time from greetings (greeting after 12:00)
        greetings = data.get('greetings', [])
        second_greeting = None
        for ts in greetings:
            if ts and ts.hour >= 12:  # After noon = second check-in
                second_greeting = ts.strftime('%H:%M')
                break
        
        if second_greeting:
            result['second_check_in'] = second_greeting
            result['notes'] = f'ورود دوم: {second_greeting}'
        else:
            result['notes'] = 'آنکال جدید'
        return result
    
    # Regular on-call days (Sat-Tue) - on-call gets 9 hours automatic
    if is_new_oncall:
        result['show_metrics'] = False
        result['auto_effective'] = 9  # Automatic 9 hours
        check_in_time = data.get('check_in')
        if check_in_time:
            # Check if online before 17:00
            from datetime import datetime
            try:
                t = datetime.strptime(check_in_time, '%H:%M')
                if t.hour < 17:
                    result['check_in_status'] = 'OK'
                    result['notes'] = f'ورود {check_in_time}'
                else:
                    result['check_in_status'] = 'LATE'
                    result['notes'] = f'ورود {check_in_time} (دیر)'
            except:
                result['notes'] = check_in_time
        else:
            result['check_in_status'] = 'MISSING'
            result['notes'] = 'ورود نداشته'
        return result
    
    return result

def is_back(content):
    """Check if message is 'b' (back)"""
    content_clean = content.lower().strip()
    return content_clean == 'b' or content_clean == 'back' or content_clean == 'برگشتم'

def is_leave_request(content):
    """Check if message is a leave request for vacation/time-off"""
    content_lower = content.lower()
    
    # Exclude code blocks (templates/examples)
    if '```' in content:
        return False
    
    # Exclude patterns - messages about leave but NOT leave requests
    exclude_patterns = [
        'niazi nist',      # "you don't need to" - advice, not request
        'niaz nist',       # same
        'نیازی نیست',      # Persian "no need"
        'نیاز نیست',       # Persian "no need"
        'lazem nist',      # "not necessary"
        'لازم نیست',       # Persian "not necessary"
        # Approval/instruction messages (from manager, not leave request)
        'rad shod',        # "approved" - approval message
        'rad shode',       # "has been approved"
        'تایید شد',         # Persian "approved"
        'haminja bezan',   # "post it here" - instruction
        'inja bezan',      # "post here" - instruction
        'format ro',       # "the format" - explaining format
        'lotfan',          # "please" (usually in instructions)
        'لطفا',             # Persian "please"
    ]
    
    if any(p in content_lower for p in exclude_patterns):
        return False
    
    # Primary patterns - strong indicators of leave request
    primary_patterns = [
        'morakhasi',       # مرخصی in Finglish
        'morekhasi',       # مرخصی in Finglish (alternate spelling)
        'مرخصی',            # مرخصی in Persian
        'off basham',      # time off request
        'off bashim',      # time off request (plural)
        'leave mikham',    # leave request
        'leave mikhastam', # leave request past tense
    ]
    
    if any(p in content_lower for p in primary_patterns):
        return True
    
    # Note: Removed 'nistam' and 'نیستم' as they cause too many false positives
    # (e.g., "motmen nistam" = "I'm not sure" would match)
    
    return False


def is_remote_work_request(content):
    """
    Check if message is a remote work (دورکاری) request.
    
    Patterns:
    - durkari mikhastam (Finglish)
    - doorkari mikhastam (Finglish alternate)
    - دورکاری میخواستم (Persian)
    - durkari mikham (Finglish)
    - دورکاری میخوام (Persian)
    - mikhastam remote basham (reverse order)
    - میخواستم ریموت باشم (Persian reverse order)
    
    Date patterns (optional):
    - az tarikh X ta tarikh Y
    - از تاریخ x تا تاریخ y
    - tarikh X
    - تاریخ x
    
    Returns: True if message is a remote work request
    
    NOTE: Currently not shown in report. Used for future remote work tracking.
    """
    content_lower = content.lower()
    
    # Primary remote work patterns
    remote_patterns = [
        'durkari mikhastam',
        'doorkari mikhastam',
        'دورکاری میخواستم',
        'durkari mikham',
        'doorkari mikham',
        'دورکاری میخوام',
        'durkari daram',
        'doorkari daram',
        'دورکاری دارم',
        # Reverse patterns - "mikhastam remote basham"
        'mikhastam remote',
        'میخواستم ریموت',
        'mikham remote',
        'میخوام ریموت',
    ]
    
    if any(p in content_lower for p in remote_patterns):
        return True
    
    return False


def parse_remote_work_dates(content):
    """
    Parse remote work request and extract date range.
    
    Patterns:
    - "az tarikh 1404/10/05 ta tarikh 1404/10/07"
    - "از تاریخ ۱۴۰۴/۱۰/۰۵ تا تاریخ ۱۴۰۴/۱۰/۰۷"
    - "tarikh 1404/10/05"
    - "emruz" (today)
    - "farda" (tomorrow)
    
    Returns: (start_date, end_date) as strings, or None if no dates found
    """
    import re
    content_lower = content.lower()
    
    # Pattern: "az tarikh X ta tarikh Y" or "از تاریخ x تا تاریخ y"
    range_pattern = r'(?:az\s+)?(?:tarikh|تاریخ)\s*[:\s]?\s*(\d{4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s*(?:ta|تا)\s*(?:tarikh|تاریخ)?\s*[:\s]?\s*(\d{4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})'
    match = re.search(range_pattern, content_lower)
    
    if match:
        return (match.group(1), match.group(2))
    
    # Pattern: Single date "tarikh X"
    single_pattern = r'(?:tarikh|تاریخ)\s*[:\s]?\s*(\d{4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})'
    match = re.search(single_pattern, content_lower)
    
    if match:
        return (match.group(1), match.group(1))  # Same start and end
    
    # Pattern: "emruz" or "farda"
    if 'emruz' in content_lower or 'امروز' in content_lower:
        today = datetime.now().strftime('%Y-%m-%d')
        return (today, today)
    
    if 'farda' in content_lower or 'فردا' in content_lower:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        return (tomorrow, tomorrow)
    
    return None


def parse_hourly_leave(content):
    """
    Parse hourly leave request and extract start/end times.
    
    Patterns:
    - "morekhasi mikham az saat 14:00 ta 17:00"
    - "مرخصی میخوام از ساعت ۱۴:۰۰ تا ۱۷:۰۰"
    - "morakhasi 14 ta 17"
    - "off az 2 ta 5"
    - "hodode saat 12 yek saat morekhasi" (around 12, one hour leave)
    - "saat 10 do saat morekhasi" (at 10, two hours leave)
    
    Returns: (start_hour, start_min, end_hour, end_min) or None if not hourly leave
    """
    content_lower = content.lower()
    
    # Check if it's a leave-related message first
    leave_patterns = [
        'morakhasi', 'morekhasi', 'مرخصی', 
        'off ', 'leave'  # space after 'off' to avoid matching 'offline'
    ]
    
    if not any(p in content_lower for p in leave_patterns):
        return None
    
    import re
    
    # === Duration-based patterns ===
    # Pattern: "hodode saat X yek/do/se saat" or "saat X yek saat"
    # Persian number words to digits
    duration_words = {
        'yek': 1, 'ye': 1, 'یک': 1, 'یه': 1, '1': 1,
        'do': 2, 'دو': 2, '2': 2,
        'se': 3, 'سه': 3, '3': 3,
        'chahar': 4, 'چهار': 4, '4': 4,
        'nim': 0.5, 'نیم': 0.5,  # half hour
    }
    
    # Pattern: "saat X [yek/do/se/...] saat morekhasi"
    # hodode saat 12 yek saat morekhasi
    # saat 10 do saat morakhasi
    duration_pattern = r'(?:hodode\s+)?saat\s+(\d{1,2})(?::(\d{2}))?\s+(\w+)\s+saat'
    duration_match = re.search(duration_pattern, content_lower)
    
    if duration_match:
        start_hour = int(duration_match.group(1))
        start_min = int(duration_match.group(2)) if duration_match.group(2) else 0
        duration_word = duration_match.group(3)
        
        # Adjust for work hours context (1-7 means PM in work context)
        if 1 <= start_hour <= 7:
            start_hour += 12
        
        # Get duration in hours
        duration_hours = duration_words.get(duration_word)
        if duration_hours:
            end_total_minutes = start_hour * 60 + start_min + int(duration_hours * 60)
            end_hour = end_total_minutes // 60
            end_min = end_total_minutes % 60
            
            # Validate hours
            if 0 <= start_hour <= 23 and 0 <= end_hour <= 23:
                return (start_hour, start_min, end_hour, end_min)
    
    # === Time range patterns ===
    # Pattern: "az saat HH:MM ta HH:MM" or "az HH ta HH"
    # Match patterns like "14:00 ta 17:00" or "14 ta 17"
    time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(?:ta|تا)\s*(\d{1,2})(?::(\d{2}))?'
    match = re.search(time_pattern, content_lower)
    
    if match:
        start_hour = int(match.group(1))
        start_min = int(match.group(2)) if match.group(2) else 0
        end_hour = int(match.group(3))
        end_min = int(match.group(4)) if match.group(4) else 0
        
        # Adjust for work hours context (1-7 means 13:00-19:00 PM, not AM)
        # When someone says "saat 2 ta 4", they mean 14:00-16:00 in work context
        if 1 <= start_hour <= 7:
            start_hour += 12
        if 1 <= end_hour <= 7:
            end_hour += 12
        
        # Validate hours (work hours typically 8-18)
        if 0 <= start_hour <= 23 and 0 <= end_hour <= 23:
            return (start_hour, start_min, end_hour, end_min)
    
    return None


def calculate_leave_duration(leave_times):
    """Calculate total leave duration in minutes from (start_h, start_m, end_h, end_m)"""
    if not leave_times:
        return 0
    start_h, start_m, end_h, end_m = leave_times
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m
    return max(0, end_minutes - start_minutes)

def analyze_attendance(date_str=None):
    """Analyze attendance for a specific date"""
    discord_file = get_latest_discord_file()
    if not discord_file:
        print("No Discord export file found!")
        return
    
    with open(discord_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    channels = data.get('channels', {})
    if 'general_new' not in channels:
        print("general_new channel not found!")
        return
    
    messages = channels['general_new'].get('messages', [])
    
    # Filter by date (in Iran timezone, not UTC)
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    
    # Filter messages by Iran date (not UTC date)
    day_messages = []
    for m in messages:
        ts = m.get('timestamp', '')
        iran_dt = parse_timestamp(ts)
        if iran_dt and iran_dt.date() == target_date:
            day_messages.append(m)
    
    # Track attendance per person
    attendance = defaultdict(lambda: {
        'check_in': None,
        'check_out': None,
        'brb_sessions': [],  # [(start_time, expected_back, actual_back)]
        'current_brb': None,
        'leave_requests': [],
        'total_brb_time': 0,
        'brb_lunch_time': 0,  # Lunch BRB time (1 hour allowed)
        'brb_other_time': 0,  # Other BRB time (max 60 min allowed in total)
        'brb_other_excess': 0,  # Excess from single BRB sessions exceeding 30 min
        'greetings': [],  # List of greeting timestamps for detecting second check-in
    })
    
    for msg in day_messages:
        author_data = msg.get('author', {})
        display_name = author_data.get('display_name', author_data.get('name', ''))
        name = normalize_name(display_name)
        content = msg.get('content', '')
        timestamp = parse_timestamp(msg.get('timestamp', ''))
        
        if not timestamp:
            continue
        
        # Check-in (morning greeting)
        if is_greeting(content):
            # Track all greetings for second check-in detection
            attendance[name]['greetings'].append(timestamp)
            # First greeting is the check-in
            if attendance[name]['check_in'] is None:
                attendance[name]['check_in'] = timestamp
        
        # Check-out (goodbye)
        if is_goodbye(content):
            attendance[name]['check_out'] = timestamp
        
        # BRB start
        if is_brb(content):
            expected_duration = parse_brb_duration(content)
            attendance[name]['current_brb'] = {
                'start': timestamp,
                'expected_duration': expected_duration,
                'is_lunch': is_brb_lunch(content),  # Track if this is lunch BRB
            }
        
        # Back from BRB
        if is_back(content) and attendance[name]['current_brb']:
            brb = attendance[name]['current_brb']
            actual_duration = (timestamp - brb['start']).total_seconds() / 60
            is_lunch = brb.get('is_lunch', False)
            attendance[name]['brb_sessions'].append({
                'start': brb['start'],
                'end': timestamp,
                'expected_minutes': brb['expected_duration'],
                'actual_minutes': actual_duration,
                'overtime': actual_duration > brb['expected_duration'],
                'is_lunch': is_lunch,
            })
            attendance[name]['total_brb_time'] += actual_duration
            # Track lunch vs other BRB separately
            if is_lunch:
                attendance[name]['brb_lunch_time'] += actual_duration
            else:
                # For non-lunch BRB, if single session exceeds 30 min:
                # - ENTIRE session is excess (not just amount over 30)
                # - Session loses the 30 min free allowance
                if actual_duration > 30:
                    # This session violated the 30 min limit - ENTIRE session is excess
                    attendance[name]['brb_other_excess'] += actual_duration  # Full session, not just excess
                    # brb_other_time tracks allowed time - this session has 0 allowed
                else:
                    attendance[name]['brb_other_time'] += actual_duration
            attendance[name]['current_brb'] = None
        
        # NOTE: Leave requests are NOT processed from general_new channel
        # Leave/vacation requests should only come from personal channels
        # This avoids duplicate counting and keeps leave tracking consistent
    
    # === Check personal channels for leave requests (ONLY place for leave) ===
    for channel_name, person_name in PERSONAL_CHANNELS.items():
        if channel_name not in channels:
            continue
        ch_data = channels[channel_name]
        if not isinstance(ch_data, dict):
            continue
        ch_messages = ch_data.get('messages', [])
        
        # Filter by date
        day_ch_messages = [m for m in ch_messages if date_str in m.get('timestamp', '')]
        
        for msg in day_ch_messages:
            content = msg.get('content', '')
            timestamp = parse_timestamp(msg.get('timestamp', ''))
            author_display = msg.get('author', {}).get('display_name', '')
            
            if not timestamp:
                continue
            
            # Only accept leave requests FROM the channel owner (the person themselves)
            # Skip messages from managers/others (e.g., Alireza, Maryam approving leave)
            if author_display:
                # Normalize author display name to standard name using TEAM_MEMBERS
                author_key = author_display.lower().strip()
                author_standard = TEAM_MEMBERS.get(author_key)
                
                # If author is not the channel owner, skip this message
                # This filters out manager responses like "rad shod"
                if author_standard and author_standard != person_name:
                    continue
                # If author not in mapping but is an excluded member's name, skip
                if not author_standard and author_key in ['alireza', 'maryam', 'hosein feyzollahi']:
                    continue
            
            # Check for leave request
            if is_leave_request(content):
                hourly_leave = parse_hourly_leave(content)
                leave_duration = calculate_leave_duration(hourly_leave) if hourly_leave else None
                attendance[person_name]['leave_requests'].append({
                    'time': timestamp,
                    'content': content,
                    'channel': channel_name,
                    'hourly': hourly_leave,
                    'duration_minutes': leave_duration,
                })
    
    # === Deduplicate hourly leave requests ===
    # If same person has multiple requests with same time range, keep only one
    for name, data in attendance.items():
        seen_ranges = set()
        unique_leaves = []
        for leave in data['leave_requests']:
            hourly = leave.get('hourly')
            if hourly:
                # Use time range as key for deduplication
                range_key = (hourly[0], hourly[1], hourly[2], hourly[3])
                if range_key not in seen_ranges:
                    seen_ranges.add(range_key)
                    unique_leaves.append(leave)
            else:
                # Full day leave - keep all (could be different reasons)
                unique_leaves.append(leave)
        data['leave_requests'] = unique_leaves
    
    return attendance, date_str

def print_attendance_report(attendance, date_str, oncall_person=None, support_person=None):
    """Print formatted attendance report"""
    print("=" * 70)
    print(f"📊 گزارش حضور و غیاب تیم DBA - {date_str}")
    print("=" * 70)
    
    # People to skip from warnings (on-call, support, and excluded members)
    skip_for_warnings = set(EXCLUDED_MEMBERS)  # Start with excluded members
    if oncall_person:
        skip_for_warnings.add(oncall_person)
    if support_person:
        skip_for_warnings.add(support_person)
    
    # Check if it's Wednesday (special oncall handover day)
    oncall_wednesday = is_oncall_wednesday(date_str, oncall_person)
    
    if oncall_wednesday:
        print(f"\n🔔 آنکال امروز (چهارشنبه - روز تحویل):")
        print(f"   📥 آنکال جدید: {oncall_person}")
        if support_person:
            print(f"   📤 آنکال قبلی (استراحت): {support_person}")
    else:
        if oncall_person:
            print(f"\n🔔 آنکال امروز: {oncall_person}")
        if support_person:
            print(f"😴 آنکال هفته قبل (استراحت): {support_person}")
    
    # Check if it's a holiday
    holiday_support = get_holiday_support_person(date_str)
    if holiday_support:
        print(f"\n🎉 تعطیل رسمی - مسئول پشتیبانی: {holiday_support}")
        skip_for_warnings.add(holiday_support)  # Holiday support person has different hours
    
    # === 1. Late Check-ins ===
    print("\n🕐 ورود دیرهنگام (بعد از ۹:۳۰):")
    print("-" * 50)
    late_count = 0
    for name, data in sorted(attendance.items()):
        if name in skip_for_warnings:
            continue  # Skip on-call person
        if data['check_in']:
            check_in_hour = data['check_in'].hour + data['check_in'].minute / 60
            if check_in_hour > EXPECTED_CHECK_IN_LATEST:  # After 9:30 (flexible)
                late_count += 1
                print(f"  ⚠️  {name}: ورود {data['check_in'].strftime('%H:%M')}")
    if late_count == 0:
        print("  ✓ همه به موقع وارد شدن")
    
    # === 2. Early Check-outs ===
    print("\n🚪 خروج زودهنگام (قبل از ۱۷:۰۰):")
    print("-" * 50)
    early_count = 0
    for name, data in sorted(attendance.items()):
        if name in skip_for_warnings:
            continue  # Skip on-call person
        if data['check_out']:
            check_out_hour = data['check_out'].hour + data['check_out'].minute / 60
            if check_out_hour < 17:  # Before 17:00
                early_count += 1
                print(f"  ⚠️  {name}: خروج {data['check_out'].strftime('%H:%M')}")
    if early_count == 0:
        print("  ✓ کسی زود نرفته")
    
    # === 2.5. Missing Check-outs (Checked in but no goodbye) ===
    print("\n❌ خروج ثبت نشده (سلام گفتند ولی خسته نباشید نگفتند):")
    print("-" * 50)
    missing_checkout_count = 0
    for name, data in sorted(attendance.items()):
        if name in skip_for_warnings:
            continue  # Skip on-call/support
        # Person has check-in but no check-out
        if data['check_in'] and not data['check_out']:
            missing_checkout_count += 1
            check_in_time = data['check_in'].strftime('%H:%M')
            print(f"  ❌ {name}: ورود {check_in_time} - خروج ثبت نشده!")
    if missing_checkout_count == 0:
        print("  ✓ همه خروج خود را ثبت کردند")
    
    # === 3. BRB Issues ===
    print("\n⏰ BRB های بدون برگشت یا طولانی:")
    print("-" * 50)
    brb_issues = 0
    for name, data in sorted(attendance.items()):
        if name in skip_for_warnings:
            continue  # Skip on-call person
        # Unclosed BRB
        if data['current_brb']:
            brb_issues += 1
            start = data['current_brb']['start']
            print(f"  ❌ {name}: BRB از {start.strftime('%H:%M')} - هنوز برنگشته!")
        
        # Overtime BRB
        for session in data['brb_sessions']:
            if session['overtime']:
                brb_issues += 1
                overtime = session['actual_minutes'] - session['expected_minutes']
                print(f"  ⚠️  {name}: BRB {int(session['actual_minutes'])} دقیقه (مجاز: {int(session['expected_minutes'])} دقیقه) - {int(overtime)} دقیقه اضافه")
    if brb_issues == 0:
        print("  ✓ همه BRB ها درست بودن")
    
    # === 4. Work Hours ===
    print("\n📈 ساعت کاری:")
    print("-" * 50)
    for name, data in sorted(attendance.items()):
        if name in skip_for_warnings:
            # Show on-call person without warning status
            if data['check_in'] and data['check_out']:
                work_time = (data['check_out'] - data['check_in']).total_seconds() / 3600
                net_work = work_time - (data['total_brb_time'] / 60)
                print(f"  🔔 {name} (آنکال): {net_work:.1f} ساعت")
            continue
        if data['check_in'] and data['check_out']:
            work_time = (data['check_out'] - data['check_in']).total_seconds() / 3600
            net_work = work_time - (data['total_brb_time'] / 60)
            status = "✓" if net_work >= MIN_WORK_HOURS else "⚠️"
            print(f"  {status} {name}: {net_work:.1f} ساعت (ناخالص: {work_time:.1f}h, BRB: {int(data['total_brb_time'])}min)")
        elif data['check_in']:
            print(f"  ❓ {name}: ورود {data['check_in'].strftime('%H:%M')} - هنوز خارج نشده")
    
    # === 5. Leave Requests ===
    print("\n🏖️  درخواست مرخصی:")
    print("-" * 50)
    leave_count = 0
    for name, data in sorted(attendance.items()):
        if name in EXCLUDED_MEMBERS:
            continue  # Skip excluded members from leave display too
        for leave in data['leave_requests']:
            leave_count += 1
            hourly = leave.get('hourly')
            if hourly:
                start_h, start_m, end_h, end_m = hourly
                duration = leave.get('duration_minutes', 0)
                print(f"  📝 {name}: ساعتی ({start_h:02d}:{start_m:02d} تا {end_h:02d}:{end_m:02d}) = {duration} دقیقه")
            else:
                print(f"  📝 {name}: روز کامل - {leave['content'][:40]}...")
    if leave_count == 0:
        print("  (هیچ درخواست مرخصی‌ای نبود)")
    
    # === 6. No Activity ===
    print("\n👻 بدون فعالیت (صبح بخیر نگفتن):")
    print("-" * 50)
    active_names = set(attendance.keys())
    all_expected = set(TEAM_MEMBERS.values())
    missing = all_expected - active_names
    # Remove on-call person from missing list
    missing = missing - skip_for_warnings
    if missing:
        for name in sorted(missing):
            print(f"  ❓ {name}")
    else:
        print("  ✓ همه فعال بودن")
    
    print("\n" + "=" * 70)

def load_leave_log():
    """Load leave counter from file"""
    if os.path.exists(LEAVE_LOG_FILE):
        with open(LEAVE_LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_leave_log(data):
    """Save leave counter to file"""
    with open(LEAVE_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# === Leave Database Integration ===
def load_leave_database():
    """Load pre-parsed leave database"""
    if os.path.exists(LEAVE_DATABASE_FILE):
        with open(LEAVE_DATABASE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


# === Attendance Database Integration ===
# Stores check-in/check-out times and leave time ranges per date/person
# Structure: {
#   "2025-12-27": {
#     "Keivan Sadeghi": {
#       "check_in": "09:31",
#       "check_out": "17:44",
#       "leave_ranges": [{"start": "11:45", "end": "13:00", "minutes": 75}]
#     }
#   }
# }

def load_attendance_database():
    """Load attendance database from JSON file"""
    if os.path.exists(ATTENDANCE_DATABASE_FILE):
        with open(ATTENDANCE_DATABASE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_attendance_database(data):
    """Save attendance database to JSON file"""
    with open(ATTENDANCE_DATABASE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_attendance_database(date_str, attendance):
    """
    Update attendance database with check-in/out times and leave ranges.
    Called after analyzing attendance for a date.
    """
    db = load_attendance_database()
    
    if date_str not in db:
        db[date_str] = {}
    
    for name, data in attendance.items():
        if name in EXCLUDED_MEMBERS:
            continue
            
        entry = {}
        
        # Check-in/Check-out
        if data.get('check_in'):
            entry['check_in'] = data['check_in'].strftime('%H:%M')
        if data.get('check_out'):
            entry['check_out'] = data['check_out'].strftime('%H:%M')
        
        # Leave ranges
        leave_ranges = []
        for lr in data.get('leave_requests', []):
            if lr.get('hourly'):
                start_h, start_m, end_h, end_m = lr['hourly']
                leave_ranges.append({
                    'start': f'{start_h:02d}:{start_m:02d}',
                    'end': f'{end_h:02d}:{end_m:02d}',
                    'minutes': lr.get('duration_minutes', 0)
                })
        
        if leave_ranges:
            entry['leave_ranges'] = leave_ranges
        
        # BRB sessions
        if data.get('brb_sessions'):
            brb_sessions = []
            for s in data['brb_sessions']:
                brb_sessions.append({
                    'start': s['start'].strftime('%H:%M') if s.get('start') else None,
                    'end': s['end'].strftime('%H:%M') if s.get('end') else None,
                    'minutes': int(s.get('actual_minutes', 0)),
                    'is_lunch': s.get('is_lunch', False)
                })
            entry['brb_sessions'] = brb_sessions
        
        if entry:
            db[date_str][name] = entry
    
    save_attendance_database(db)
    return db


def get_leave_ranges(name, date_str):
    """
    Get leave time ranges for a person on a specific date.
    Used by Discord bot to exclude leave periods from idle tracking.
    
    Returns: list of {'start': 'HH:MM', 'end': 'HH:MM', 'minutes': int}
    """
    db = load_attendance_database()
    if date_str in db and name in db[date_str]:
        return db[date_str][name].get('leave_ranges', [])
    return []


# === Remote Work Database Integration ===
REMOTE_WORK_DB_FILE = os.path.join(SCRIPTS_DIR, 'remote_work_database.json')

def load_remote_work_database():
    """Load remote work database"""
    if os.path.exists(REMOTE_WORK_DB_FILE):
        with open(REMOTE_WORK_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def is_remote_work(name, date_str):
    """Check if person was working remotely on given date"""
    remote_db = load_remote_work_database()
    
    # Check exact name match
    if name in remote_db and date_str in remote_db[name]:
        return remote_db[name][date_str]
    
    # Also check similar names
    for db_name, dates in remote_db.items():
        if date_str in dates:
            # If first name matches
            if name.split()[0].lower() == db_name.split()[0].lower():
                return dates[date_str]
    
    return None


def get_idle_time(name, date_str):
    """Get idle time (in minutes) for person on given date from idle tracker bot"""
    if not os.path.exists(IDLE_TIME_FILE):
        return None
    
    try:
        with open(IDLE_TIME_FILE, 'r') as f:
            idle_data = json.load(f)
        
        # Load user info to map user_id to display_name
        user_info = {}
        if os.path.exists(IDLE_USERS_FILE):
            with open(IDLE_USERS_FILE, 'r') as f:
                user_info = json.load(f)
        
        # Convert date to string if it's a datetime.date object
        if hasattr(date_str, 'strftime'):
            date_key = date_str.strftime('%Y-%m-%d')
        else:
            date_key = str(date_str)
        
        if date_key not in idle_data:
            return None
        
        # Map display names to standard names
        IDLE_NAME_MAP = {
            'mohsen': 'Mohsen Roudsaz',
            'erfan': 'Erfan Heidari',
            'mahsa': 'Zeinabsadat Hejazi',
            'mari': 'Maryam Yousefi',
            # 'maryam': 'Maryam Yousefi',  # Removed - conflicts with Maryam Marefati
            'hossein shahreza': 'Hosseinali Shirali',
            'nader': 'Nader Shabibi',
            'nissay87': 'Yassin Alivand',  # Fixed: nissay87 is Yassin, not Ehsan
            'esi': 'Ehsan Yousefi',
            'masoud sereshki': 'Masoud Sereshki',
            'masoud': 'Masoud Rafiei',  # Just 'Masoud' display_name = Rafiei
            'k1 sadeghi': 'Keivan Sadeghi',
            'yassin': 'Yassin Alivand',
        }
        
        # Also map by username (after removing numbers)
        USERNAME_MAP = {
            'mohsen.roud': 'Mohsen Roudsaz',
            'erfan_heidari': 'Erfan Heidari',
            'mahsahejszi': 'Zeinabsadat Hejazi',
            'maryam.you': 'Maryam Yousefi',
            'hosseinshahreza': 'Hosseinali Shirali',
            'nader3307': 'Nader Shabibi',
            'nissay87': 'Yassin Alivand',  # Fixed
            'ehsan.yo': 'Ehsan Yousefi',
            'masoudsereshki': 'Masoud Sereshki',
            'masoudraafiee': 'Masoud Rafiei',  # Added
            'k1.sadeghi_15101': 'Keivan Sadeghi',
            # 'maryam6409': 'Maryam Marefati',  # Excluded member
        }
        
        # Get idle data for this date
        day_idle = idle_data[date_key]
        
        for user_id, minutes in day_idle.items():
            # Get display name from user_info
            info = user_info.get(user_id, {})
            display_name = info.get('display_name', '').lower()
            username = info.get('name', '').lower()
            
            # Try to match with our name
            name_lower = name.lower()
            matched_name = IDLE_NAME_MAP.get(display_name) or USERNAME_MAP.get(username)
            
            if matched_name == name:
                return round(minutes, 1)
            
            # No more fallback - the maps above should cover all cases
            # Fallback matching by first name was causing Masoud Rafiei/Sereshki confusion
        
        return None
        
    except Exception as e:
        print(f"Error loading idle time: {e}")
        return None


def get_offline_time(name, date_str):
    """Get offline time (in minutes) for person on given date from idle tracker bot"""
    if not os.path.exists(OFFLINE_TIME_FILE):
        return None
    
    try:
        with open(OFFLINE_TIME_FILE, 'r') as f:
            offline_data = json.load(f)
        
        # Load user info to map user_id to display_name
        user_info = {}
        if os.path.exists(IDLE_USERS_FILE):
            with open(IDLE_USERS_FILE, 'r') as f:
                user_info = json.load(f)
        
        # Convert date to string if it's a datetime.date object
        if hasattr(date_str, 'strftime'):
            date_key = date_str.strftime('%Y-%m-%d')
        else:
            date_key = str(date_str)
        
        if date_key not in offline_data:
            return None
        
        # Map display names to standard names (same as idle)
        IDLE_NAME_MAP = {
            'mohsen': 'Mohsen Roudsaz',
            'erfan': 'Erfan Heidari',
            'mahsa': 'Zeinabsadat Hejazi',
            'mari': 'Maryam Yousefi',
            'hossein shahreza': 'Hosseinali Shirali',
            'nader': 'Nader Shabibi',
            'nissay87': 'Yassin Alivand',  # Fixed
            'esi': 'Ehsan Yousefi',
            'masoud sereshki': 'Masoud Sereshki',
            'masoud': 'Masoud Rafiei',  # Added
            'k1 sadeghi': 'Keivan Sadeghi',
            'yassin': 'Yassin Alivand',
        }
        
        USERNAME_MAP = {
            'mohsen.roud': 'Mohsen Roudsaz',
            'erfan_heidari': 'Erfan Heidari',
            'mahsahejszi': 'Zeinabsadat Hejazi',
            'maryam.you': 'Maryam Yousefi',
            'hosseinshahreza': 'Hosseinali Shirali',
            'nader3307': 'Nader Shabibi',
            'nissay87': 'Yassin Alivand',  # Fixed
            'ehsan.yo': 'Ehsan Yousefi',
            'masoudsereshki': 'Masoud Sereshki',
            'masoudraafiee': 'Masoud Rafiei',  # Added
            'k1.sadeghi_15101': 'Keivan Sadeghi',
        }
        
        day_offline = offline_data[date_key]
        
        for user_id, minutes in day_offline.items():
            info = user_info.get(user_id, {})
            display_name = info.get('display_name', '').lower()
            username = info.get('name', '').lower()
            
            name_lower = name.lower()
            matched_name = IDLE_NAME_MAP.get(display_name) or USERNAME_MAP.get(username)
            
            if matched_name == name:
                return round(minutes, 1)
            
            # No more fallback - use explicit maps only
        
        return None
        
    except Exception as e:
        print(f"Error loading offline time: {e}")
        return None


def get_voice_time(name, date_str):
    """Get voice channel time (in minutes) for person on given date from idle tracker bot"""
    if not os.path.exists(VOICE_TIME_FILE):
        return None
    
    try:
        with open(VOICE_TIME_FILE, 'r') as f:
            voice_data = json.load(f)
        
        # Load user info to map user_id to display_name
        user_info = {}
        if os.path.exists(IDLE_USERS_FILE):
            with open(IDLE_USERS_FILE, 'r') as f:
                user_info = json.load(f)
        
        # Convert date to string if it's a datetime.date object
        if hasattr(date_str, 'strftime'):
            date_key = date_str.strftime('%Y-%m-%d')
        else:
            date_key = str(date_str)
        
        if date_key not in voice_data:
            return None
        
        # Map display names to standard names (same as idle)
        IDLE_NAME_MAP = {
            'mohsen': 'Mohsen Roudsaz',
            'erfan': 'Erfan Heidari',
            'mahsa': 'Zeinabsadat Hejazi',
            'mari': 'Maryam Yousefi',
            'hossein shahreza': 'Hosseinali Shirali',
            'nader': 'Nader Shabibi',
            'nissay87': 'Yassin Alivand',  # Fixed
            'esi': 'Ehsan Yousefi',
            'masoud sereshki': 'Masoud Sereshki',
            'masoud': 'Masoud Rafiei',  # Added
            'k1 sadeghi': 'Keivan Sadeghi',
            'yassin': 'Yassin Alivand',
        }
        
        USERNAME_MAP = {
            'mohsen.roud': 'Mohsen Roudsaz',
            'erfan_heidari': 'Erfan Heidari',
            'mahsahejszi': 'Zeinabsadat Hejazi',
            'maryam.you': 'Maryam Yousefi',
            'hosseinshahreza': 'Hosseinali Shirali',
            'nader3307': 'Nader Shabibi',
            'nissay87': 'Yassin Alivand',  # Fixed
            'ehsan.yo': 'Ehsan Yousefi',
            'masoudsereshki': 'Masoud Sereshki',
            'masoudraafiee': 'Masoud Rafiei',  # Added
            'k1.sadeghi_15101': 'Keivan Sadeghi',
        }
        
        day_voice = voice_data[date_key]
        
        for user_id, minutes in day_voice.items():
            info = user_info.get(user_id, {})
            display_name = info.get('display_name', '').lower()
            username = info.get('name', '').lower()
            
            name_lower = name.lower()
            matched_name = IDLE_NAME_MAP.get(display_name) or USERNAME_MAP.get(username)
            
            if matched_name == name:
                return round(minutes, 1)
            
            # No more fallback - use explicit maps only
        
        return None
        
    except Exception as e:
        print(f"Error loading voice time: {e}")
        return None


def is_on_leave(name, date_str):
    """Check if person is on leave for given date using pre-parsed database"""
    leave_db = load_leave_database()
    
    # Check exact name match
    if name in leave_db and date_str in leave_db[name]:
        return leave_db[name][date_str]
    
    # Also check similar names (e.g., "Maryam" -> "Maryam Yousefi")
    for db_name, dates in leave_db.items():
        if date_str in dates:
            # If first name matches
            if name.split()[0].lower() == db_name.split()[0].lower():
                return dates[date_str]
    
    return None


def update_leave_counter(attendance, date_str):
    """Update leave counter based on today's requests"""
    leave_log = load_leave_log()
    
    for name, data in attendance.items():
        for leave in data['leave_requests']:
            if name not in leave_log:
                leave_log[name] = {'total_days': 0, 'requests': []}
            
            # Check if this date already logged
            existing_dates = [r['date'] for r in leave_log[name]['requests']]
            if date_str not in existing_dates:
                leave_log[name]['requests'].append({
                    'date': date_str,
                    'content': leave['content'][:100],
                })
                leave_log[name]['total_days'] += 1
    
    save_leave_log(leave_log)
    return leave_log

def print_leave_summary():
    """Print leave summary for all team members"""
    leave_log = load_leave_log()
    
    print("\n" + "=" * 70)
    print("🏖️  خلاصه مرخصی‌ها (کل)")
    print("=" * 70)
    
    if not leave_log:
        print("  (هیچ مرخصی ثبت نشده)")
        return
    
    for name, data in sorted(leave_log.items()):
        print(f"\n  {name}: {data['total_days']} روز")
        for req in data['requests'][-5:]:  # Last 5
            print(f"    - {req['date']}: {req['content'][:40]}...")
    
    print("\n" + "=" * 70)

def main():
    import sys
    from datetime import datetime as dt
    
    # Check for date argument
    date_str = None
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            date_str = arg
            break
    
    # Use today if no date provided
    if not date_str:
        date_str = dt.now().strftime('%Y-%m-%d')
    
    # Check if weekend (Thursday=3, Friday=4 in Iran)
    report_date = dt.strptime(date_str, '%Y-%m-%d')
    weekday = report_date.weekday()  # Monday=0, Sunday=6
    is_weekend = weekday in [3, 4]  # Thursday=3, Friday=4
    
    if is_weekend and '--force' not in sys.argv:
        print(f"⏭️  {date_str} is a weekend (Thu/Fri). Skipping.")
        print("Use --force to process anyway.")
        return
    
    # Backfill mode - process multiple dates
    if '--backfill' in sys.argv:
        backfill_csv()
        return
    
    attendance, date_str = analyze_attendance(date_str)
    
    # Update attendance database with check-in/out times and leave ranges
    # This is used by Discord bot to exclude leave periods from idle tracking
    update_attendance_database(date_str, attendance)
    
    # Get on-call person for today
    oncall_person, support_person = get_oncall_person(date_str)
    
    # CSV export mode
    if '--csv' in sys.argv:
        export_daily_csv(attendance, date_str)
    # Daily table mode
    elif '--table' in sys.argv:
        print_daily_table(attendance, date_str)
    else:
        print_attendance_report(attendance, date_str, oncall_person=oncall_person, support_person=support_person)
    
    # Update leave counter
    leave_log = update_leave_counter(attendance, date_str)
    
    # Print leave summary if requested
    if '--leave-summary' in sys.argv:
        print_leave_summary()


def get_latest_email_file():
    """Get the most recent email export file"""
    files = glob.glob(os.path.join(EMAIL_DIR, 'mtn_emails_*.csv'))
    if not files:
        return None
    return max(files, key=os.path.getctime)


def get_email_counts_from_json(date_str):
    """
    Get email counts from EWS-extracted JSON file.
    Returns dict: {name: count} or None if file not found.
    """
    json_file = os.path.join(os.environ.get('EMAIL_EXPORT_DIR', os.path.join(BASE_DIR, 'email_exports')), f'email_counts_{date_str}.json')
    if not os.path.exists(json_file):
        return None
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('counts', {})
    except Exception as e:
        print(f"Error reading email JSON: {e}")
        return None


def count_emails_per_person(date_str=None):
    """
    Count emails sent by each DBA team member.
    First tries EWS-extracted JSON, then falls back to manual CSV export.
    """
    # First try the automated EWS extraction
    if date_str:
        json_counts = get_email_counts_from_json(date_str)
        if json_counts:
            return json_counts
    
    # Fall back to manual CSV export
    email_file = get_latest_email_file()
    if not email_file:
        return {}
    
    # Map email prefix OR display name to team member name
    EMAIL_TO_NAME = {
        # Email prefixes
        'alireza.aghaja': 'Alireza Aghajanzadeh',
        'maryam.ma': 'Maryam Marefati',
        'keivan.s': 'Keivan Sadeghi',
        'maryam.y': 'Maryam Yousefi',
        'ehsan.y': 'Ehsan Yousefi',
        'mohsen.r': 'Mohsen Roudsaz',
        'hossein.f': 'Hossein Feizollahi',
        'nader.sh': 'Nader Shabibi',
        'zeinabsadat.he': 'Zeinabsadat Hejazi',
        'hosseinali.s': 'Hosseinali Shirali',
        'masoud.r': 'Masoud Rafiei',
        'masoud.s': 'Masoud Sereshki',
        'yasin.aa': 'Yassin Alivand',
        'erfan.he': 'Erfan Heidari',
        # Display names (for From field)
        'hosseinali shirali': 'Hosseinali Shirali',
        'erfan heidari': 'Erfan Heidari',
        'maryam marefati': 'Maryam Marefati',
        'keivan sadeghi': 'Keivan Sadeghi',
        'maryam yousefi': 'Maryam Yousefi',
        'ehsan yousefi': 'Ehsan Yousefi',
        'mohsen roudsaz': 'Mohsen Roudsaz',
        'hossein feizollahi': 'Hossein Feizollahi',
        'nader shabibi': 'Nader Shabibi',
        'zeinabsadat hejazi': 'Zeinabsadat Hejazi',
        'masoud rafiei': 'Masoud Rafiei',
        'masoud sereshki': 'Masoud Sereshki',
        'yassin alivand': 'Yassin Alivand',
        'alireza aghajanzadeh': 'Alireza Aghajanzadeh',
    }
    
    counts = defaultdict(int)
    
    try:
        with open(email_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                sender = row.get('From', '').lower()
                recv_time = row.get('ReceivedTime', '')
                
                # Filter by date if specified
                if date_str and date_str not in recv_time:
                    continue
                
                # Match to team member
                for prefix, name in EMAIL_TO_NAME.items():
                    if prefix in sender:
                        counts[name] += 1
                        break
    except Exception as e:
        print(f"Error reading emails: {e}")
    
    return counts


def count_discord_messages(date_str=None):
    """Count Discord messages per person (excluding greetings/brb)"""
    discord_file = get_latest_discord_file()
    if not discord_file:
        return {}
    
    counts = defaultdict(int)
    
    try:
        with open(discord_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        channels = data.get('channels', {})
        
        for channel_name, channel_data in channels.items():
            if not isinstance(channel_data, dict):
                continue
            
            messages = channel_data.get('messages', [])
            
            for msg in messages:
                timestamp = msg.get('timestamp', '')
                
                # Filter by date
                if date_str and date_str not in timestamp:
                    continue
                
                author_data = msg.get('author', {})
                display_name = author_data.get('display_name', author_data.get('name', ''))
                name = normalize_name(display_name)
                content = msg.get('content', '')
                
                # Skip noise messages
                if is_greeting(content) or is_goodbye(content) or is_brb(content) or is_back(content):
                    continue
                
                # Skip empty
                if not content.strip():
                    continue
                
                counts[name] += 1
    except Exception as e:
        print(f"Error reading Discord: {e}")
    
    return counts


def print_daily_table(attendance, date_str):
    """Print daily team table with all metrics"""
    email_counts = count_emails_per_person(date_str)
    discord_counts = count_discord_messages(date_str)
    
    print("=" * 100)
    print(f"📊 جدول روزانه تیم DBA - {date_str}")
    print("=" * 100)
    print()
    
    # Headers
    headers = ['نام', 'ورود', 'خروج', 'ساعت کار', 'BRB', 'ایمیل', 'Discord', 'مرخصی']
    widths = [20, 6, 6, 9, 6, 6, 8, 8]
    
    # Print header
    header_line = '| '
    for h, w in zip(headers, widths):
        header_line += f'{h:^{w}} | '
    print(header_line)
    print('|' + '-' * (sum(widths) + 3 * len(widths) - 1) + '|')
    
    # All team members (excluding management)
    all_names = set(TEAM_MEMBERS.values()) - EXCLUDED_MEMBERS
    
    # Print each row
    for name in sorted(all_names):
        data = attendance.get(name, {
            'check_in': None,
            'check_out': None,
            'brb_sessions': [],
            'current_brb': None,
            'leave_requests': [],
            'total_brb_time': 0,
        })
        
        # Check-in
        check_in = data.get('check_in')
        check_in_str = check_in.strftime('%H:%M') if check_in else '-'
        
        # Check-out
        check_out = data.get('check_out')
        check_out_str = check_out.strftime('%H:%M') if check_out else '-'
        
        # Work hours
        if check_in and check_out:
            work_time = (check_out - check_in).total_seconds() / 3600
            net_work = work_time - (data.get('total_brb_time', 0) / 60)
            work_str = f'{net_work:.1f}h'
            if net_work < MIN_WORK_HOURS:
                work_str += '⚠'
        elif check_in:
            work_str = '...'
        else:
            work_str = '-'
        
        # BRB status
        if data.get('current_brb'):
            brb_str = '❌open'
        elif data.get('brb_sessions'):
            total_brb = data.get('total_brb_time', 0)
            brb_str = f'{int(total_brb)}m'
        else:
            brb_str = '-'
        
        # Email count
        email_count = email_counts.get(name, 0)
        email_str = str(email_count) if email_count else '-'
        
        # Discord count
        discord_count = discord_counts.get(name, 0)
        discord_str = str(discord_count) if discord_count else '-'
        
        # Leave
        leave_requests = data.get('leave_requests', [])
        if leave_requests:
            # Check if any are hourly
            total_hourly_minutes = 0
            has_full_day = False
            for lr in leave_requests:
                if lr.get('duration_minutes'):
                    total_hourly_minutes += lr['duration_minutes']
                else:
                    has_full_day = True
            
            if has_full_day:
                leave_str = 'بله'
            elif total_hourly_minutes > 0:
                hours = total_hourly_minutes // 60
                mins = total_hourly_minutes % 60
                if mins:
                    leave_str = f'{hours}h{mins}m'
                else:
                    leave_str = f'{hours}h'
            else:
                leave_str = 'بله'
        else:
            leave_str = '-'
        
        # Print row
        row = '| '
        values = [name[:20], check_in_str, check_out_str, work_str, brb_str, email_str, discord_str, leave_str]
        for v, w in zip(values, widths):
            row += f'{v:<{w}} | '
        print(row)
    
    print('|' + '-' * (sum(widths) + 3 * len(widths) - 1) + '|')
    print()
    
    # Summary stats
    print("📈 خلاصه:")
    active = [n for n in all_names if n in attendance and attendance[n].get('check_in')]
    print(f"  - فعال امروز: {len(active)} نفر از {len(all_names)}")
    
    open_brbs = [n for n in attendance if attendance[n].get('current_brb')]
    if open_brbs:
        print(f"  - BRB باز: {', '.join(open_brbs)}")
    
    early_leaves = [n for n in attendance if attendance[n].get('check_out') and attendance[n]['check_out'].hour < 17]
    if early_leaves:
        print(f"  - خروج زود: {', '.join(early_leaves)}")
    
    total_emails = sum(email_counts.values())
    print(f"  - کل ایمیل‌ها: {total_emails}")
    
    print()


# === CSV OUTPUT ===
ATTENDANCE_CSV = os.environ.get('ATTENDANCE_CSV', os.path.join(BASE_DIR, 'attendance_reports/daily_attendance.csv'))


def export_daily_csv(attendance, date_str):
    """Export daily attendance to CSV file (append or update)"""
    email_counts = count_emails_per_person(date_str)
    discord_counts = count_discord_messages(date_str)
    oncall_person, support_person = get_oncall_person(date_str)
    holiday_support = get_holiday_support_person(date_str)
    
    # Ensure directory exists
    csv_dir = os.path.dirname(ATTENDANCE_CSV)
    if not os.path.exists(csv_dir):
        os.makedirs(csv_dir)
    
    # Read existing data
    existing_data = {}
    if os.path.exists(ATTENDANCE_CSV):
        with open(ATTENDANCE_CSV, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip excluded members
                if row['Name'] in EXCLUDED_MEMBERS:
                    continue
                key = (row['Date'], row['Name'])
                existing_data[key] = row
    
    # Prepare new data (excluding management)
    all_names = set(TEAM_MEMBERS.values()) - EXCLUDED_MEMBERS
    
    for name in all_names:
        data = attendance.get(name, {
            'check_in': None,
            'check_out': None,
            'brb_sessions': [],
            'current_brb': None,
            'leave_requests': [],
            'total_brb_time': 0,
        })
        
        # Check-in
        check_in = data.get('check_in')
        
        # Check-out
        check_out = data.get('check_out')
        
        # Determine if person is on-call or support (they have special handling)
        is_new_oncall = oncall_person == name
        is_prev_oncall = support_person == name
        is_oncall_or_support = is_new_oncall or is_prev_oncall
        
        # Handle missing check-in: If person said goodbye but no greeting → set check-in to 10:00
        no_checkin = False
        if check_out and not check_in and not is_oncall_or_support:
            no_checkin = True
            # Create a 10:00 datetime on the same day as check_out
            check_in = check_out.replace(hour=10, minute=0, second=0, microsecond=0)
        
        check_in_str = check_in.strftime('%H:%M') if check_in else ''
        
        # Handle missing check-out: If person checked in but didn't say goodbye → set checkout to 17:00
        no_checkout = False
        if check_in and not check_out and not is_oncall_or_support:
            no_checkout = True
            # Create a 17:00 datetime on the same day as check_in
            check_out = check_in.replace(hour=17, minute=0, second=0, microsecond=0)
        
        check_out_str = check_out.strftime('%H:%M') if check_out else ''
        
        # Work hours
        gross_work_minutes = 0
        if check_in and check_out:
            work_time = (check_out - check_in).total_seconds() / 3600
            gross_work_minutes = work_time * 60
            net_work = work_time - (data.get('total_brb_time', 0) / 60)
            work_hours = f'{net_work:.1f}'
        else:
            work_hours = ''
        
        # Re-assign oncall flags (was computed above)
        is_new_oncall = oncall_person == name
        is_prev_oncall = support_person == name
        # BRB - separate lunch and other
        brb_total = int(data.get('total_brb_time', 0))
        brb_lunch = data.get('brb_lunch_time', 0)
        brb_other_allowed = data.get('brb_other_time', 0)  # Sum of sessions ≤30 min
        brb_other_excess_sessions = data.get('brb_other_excess', 0)  # Sum of sessions >30 min (entire session)
        brb_open = 'YES' if data.get('current_brb') else ''
        
        # Format BRB column with session breakdown: "total(s1+s2l+s3)"
        # Add 'l' suffix for lunch BRB sessions
        brb_sessions = data.get('brb_sessions', [])
        if brb_sessions:
            session_parts = []
            for s in brb_sessions:
                duration = int(s['actual_minutes'])
                suffix = 'l' if s.get('is_lunch') else ''
                session_parts.append(f"{duration}{suffix}")
            session_str = '+'.join(session_parts)
            brb_display = f"{brb_total}({session_str})"
        else:
            brb_display = brb_total if brb_total else ''
        
        # Calculate excess BRB (beyond allowed)
        # Lunch BRB: 60 min allowed total
        brb_lunch_excess = max(0, brb_lunch - 60)
        # Other BRB: sessions ≤30 min get 60 min total allowance
        #   - Sessions >30 min are already tracked as full excess in brb_other_excess_sessions
        #   - brb_other_allowed has sessions ≤30 min, check if total exceeds 60
        brb_other_total_excess = max(0, brb_other_allowed - 60)
        brb_other_excess = brb_other_excess_sessions + brb_other_total_excess
        brb_excess_total = brb_lunch_excess + brb_other_excess
        
        # Counts
        email_count = email_counts.get(name, 0)
        discord_count = discord_counts.get(name, 0)
        
        # Leave - check from pre-parsed leave database first, then fallback to message-based detection
        leave_info = is_on_leave(name, date_str)
        leave_requests = data.get('leave_requests', [])
        
        # Determine leave type: HOURLY, YES (full day), or empty
        has_leave = ''
        leave_hours = ''
        total_hourly_minutes = 0  # Initialize here to ensure it's always defined
        
        if leave_info:
            has_leave = 'YES'  # Full day from pre-parsed database
        elif leave_requests:
            # Check if any are hourly
            has_full_day = False
            for lr in leave_requests:
                if lr.get('duration_minutes'):
                    total_hourly_minutes += lr['duration_minutes']
                else:
                    has_full_day = True
            
            if has_full_day:
                has_leave = 'YES'
            elif total_hourly_minutes > 0:
                hours = total_hourly_minutes // 60
                mins = total_hourly_minutes % 60
                has_leave = 'HOURLY'
                leave_hours = f'{hours}h{mins}m' if mins else f'{hours}h'
        
        # Keep track of hourly leave minutes for offline adjustment
        hourly_leave_minutes = total_hourly_minutes
        
        # Remote work
        remote_info = is_remote_work(name, date_str)
        remote_work = remote_info.get('location', 'YES') if remote_info else ''
        
        # Idle time from Discord bot (08:00-18:30 work hours)
        idle_minutes = get_idle_time(name, date_str)
        idle_str = ''
        idle_percent = ''
        if idle_minutes is not None:
            idle_str = str(int(idle_minutes))
            # Work hours: 10.5 hours = 630 minutes
            idle_percent = f'{(idle_minutes / WORK_HOURS_TOTAL_MINUTES) * 100:.0f}%'
        
        # Offline time from Discord bot
        offline_minutes = get_offline_time(name, date_str)
        offline_str = ''
        offline_percent = ''
        if offline_minutes is not None:
            offline_str = str(int(offline_minutes))
            offline_percent = f'{(offline_minutes / WORK_HOURS_TOTAL_MINUTES) * 100:.0f}%'
        
        # Voice time from Discord bot
        voice_minutes = get_voice_time(name, date_str)
        voice_str = ''
        if voice_minutes is not None:
            voice_str = str(int(voice_minutes))
        
        # Check if this person is on-call and get bonus hours
        is_new_oncall = oncall_person == name
        is_prev_oncall = support_person == name
        oncall_result = None
        effective_bonus_hours = 0
        auto_effective_hours = 0
        if is_new_oncall or is_prev_oncall:
            oncall_result = calculate_oncall_metrics(name, date_str, data, is_new_oncall, is_prev_oncall)
            effective_bonus_hours = oncall_result.get('effective_bonus', 0)
            auto_effective_hours = oncall_result.get('auto_effective', 0)
        
        # Effective work minutes = Gross work time - BRB_EXCESS - ADJUSTED_IDLE - ADJUSTED_OFFLINE
        # BRB rules: Lunch 60min free, Other BRB 60min free, only excess counts
        # IMPORTANT: 
        # - BRB time is NOT working time, so ALL BRB should be subtracted (not just excess)
        # - During BRB time, person is expected to be idle, so don't double-count idle
        # - Hourly leave: Offline during leave hours shouldn't count
        # - Auto effective: For on-call on regular days, they get 9 hours automatic
        effective_minutes = ''
        if auto_effective_hours > 0:
            # On-call/support on regular days or prev on-call on Wednesday - automatic 9 hours
            effective_minutes = f'{auto_effective_hours:.1f}'
        elif gross_work_minutes > 0:
            # Start with gross, subtract ALL BRB time (BRB is not working)
            effective = gross_work_minutes - brb_total
            
            # Additionally subtract excess BRB (penalty for going over limits)
            effective -= brb_excess_total
            
            # Combine idle and offline - both represent unavailable time
            raw_idle = idle_minutes if idle_minutes else 0
            raw_offline = offline_minutes if offline_minutes else 0
            
            # During BRB time, person is expected to be idle/offline (they announced they're away)
            # So we should only penalize idle/offline time that exceeds BRB time
            # 
            # Logic:
            # - BRB = announced break time (already subtracted from effective)
            # - Idle + Offline = detected unavailable time
            # - If idle+offline <= BRB: no penalty (they were unavailable during their announced break)
            # - If idle+offline > BRB: penalty for the excess (unavailable outside of break)
            #
            # Example 1: BRB=60, Idle=30, Offline=20 → total=50 ≤ 60 → adjusted=0
            # Example 2: BRB=60, Idle=60, Offline=60 → total=120 > 60 → adjusted=60
            total_raw_unavailable = raw_idle + raw_offline
            adjusted_unavailable = max(0, total_raw_unavailable - brb_total)
            
            # Hourly leave adjustment:
            # If person has hourly leave, assume idle/offline during leave time is expected
            # Don't double-count: only deduct max(adjusted_unavailable, leave)
            # 
            # Logic:
            # - adjusted_unavailable = unavailable time outside of BRB
            # - leave = approved unavailable time
            # - If unavailable >= leave: deduct unavailable (they were truly away)
            # - If unavailable < leave: deduct leave (approved absence)
            # 
            # Formula: max(adjusted_unavailable, leave)
            if hourly_leave_minutes > 0:
                effective_unavailable = max(adjusted_unavailable, hourly_leave_minutes)
            else:
                effective_unavailable = adjusted_unavailable
            
            effective -= effective_unavailable
            
            # Add on-call bonus (5 hours for Wednesday on-call)
            effective += effective_bonus_hours * 60  # Convert hours to minutes
            # Convert to hours with 1 decimal
            effective_hours = max(0, effective) / 60
            effective_minutes = f'{effective_hours:.1f}'
        
        # Update or insert
        key = (date_str, name)
        existing_data[key] = {
            'Date': date_str,
            'Name': name,
            'CheckIn': check_in_str,
            'CheckOut': check_out_str,
            'WorkHours': work_hours,
            'BRB_Minutes': brb_display,
            'BRB_Open': brb_open,
            'Emails': email_count if email_count else '',
            'Discord': discord_count if discord_count else '',
            'Voice': voice_str,
            'EffectiveMinutes': effective_minutes,
            'Leave': has_leave,
            'LeaveHours': leave_hours,
            'RemoteWork': remote_work,
            'IdleMinutes': idle_str,
            'IdlePercent': idle_percent,
            'OfflineMinutes': offline_str,
            'OfflinePercent': offline_percent,
            'Weekend': 'YES' if is_weekend(date_str) else '',
            'IsOnCall': 'YES' if oncall_person == name else '',
            'IsSupport': 'YES' if support_person == name else '',
            'OnCallNotes': '',  # Will be populated below
            'IsHoliday': 'YES' if holiday_support else '',
            'HolidaySupport': 'YES' if holiday_support == name else '',
            'NoCheckout': 'YES' if no_checkout else '',  # Flag for missing goodbye
            'NoCheckin': 'YES' if no_checkin else '',  # Flag for missing greeting
        }
        
        # Add on-call notes (oncall_result already calculated above)
        if oncall_result:
            existing_data[key]['OnCallNotes'] = oncall_result.get('notes', '')
    
    # Write all data
    fieldnames = ['Date', 'Name', 'CheckIn', 'CheckOut', 'WorkHours', 
                  'BRB_Minutes', 'BRB_Open', 'Emails', 'Discord', 'Voice', 'EffectiveMinutes',
                  'Leave', 'LeaveHours', 'RemoteWork', 'IdleMinutes', 'IdlePercent', 
                  'OfflineMinutes', 'OfflinePercent', 'Weekend', 'IsOnCall', 'IsSupport', 
                  'OnCallNotes', 'IsHoliday', 'HolidaySupport', 'NoCheckout', 'NoCheckin']
    
    with open(ATTENDANCE_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # Sort by date then name
        for key in sorted(existing_data.keys()):
            writer.writerow(existing_data[key])
    
    print(f"✓ CSV exported to: {ATTENDANCE_CSV}")
    print(f"  Records for {date_str}: {len(all_names)}")


def get_all_dates_from_discord():
    """Get all unique dates from Discord export"""
    discord_file = get_latest_discord_file()
    if not discord_file:
        return []
    
    with open(discord_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    channels = data.get('channels', {})
    dates = set()
    
    if 'general_new' in channels:
        messages = channels['general_new'].get('messages', [])
        for m in messages:
            ts = m.get('timestamp', '')[:10]  # YYYY-MM-DD
            if ts:
                dates.add(ts)
    
    return sorted(dates)


def backfill_csv():
    """Backfill CSV with all dates from Discord export (Discord data only, no emails)"""
    dates = get_all_dates_from_discord()
    
    if not dates:
        print("No dates found in Discord export!")
        return
    
    print(f"Backfilling {len(dates)} days: {dates[0]} to {dates[-1]}")
    print("=" * 60)
    
    for date_str in dates:
        print(f"Processing {date_str}...", end=" ")
        try:
            attendance, _ = analyze_attendance(date_str)
            # Export without email counts (only Discord data for backfill)
            export_daily_csv_discord_only(attendance, date_str)
            print("OK")
        except Exception as e:
            print(f"Error: {e}")
    
    print("=" * 60)
    print(f"Backfill complete! CSV: {ATTENDANCE_CSV}")


def export_daily_csv_discord_only(attendance, date_str):
    """Export daily attendance to CSV (Discord data only, no email counts)"""
    discord_counts = count_discord_messages(date_str)
    oncall_person, support_person = get_oncall_person(date_str)
    
    # Ensure directory exists
    csv_dir = os.path.dirname(ATTENDANCE_CSV)
    if not os.path.exists(csv_dir):
        os.makedirs(csv_dir)
    
    # Read existing data
    existing_data = {}
    if os.path.exists(ATTENDANCE_CSV):
        with open(ATTENDANCE_CSV, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip excluded members
                if row['Name'] in EXCLUDED_MEMBERS:
                    continue
                key = (row['Date'], row['Name'])
                existing_data[key] = row
    
    # Prepare new data (excluding management)
    all_names = set(TEAM_MEMBERS.values()) - EXCLUDED_MEMBERS
    
    for name in all_names:
        data = attendance.get(name, {
            'check_in': None,
            'check_out': None,
            'brb_sessions': [],
            'current_brb': None,
            'leave_requests': [],
            'total_brb_time': 0,
        })
        
        # Check-in
        check_in = data.get('check_in')
        
        # Check-out
        check_out = data.get('check_out')
        
        # Determine if person is on-call or support (they have special handling)
        is_oncall_or_support = (oncall_person == name) or (support_person == name)
        
        # Handle missing check-in: If person said goodbye but no greeting → set check-in to 10:00
        no_checkin = False
        if check_out and not check_in and not is_oncall_or_support:
            no_checkin = True
            check_in = check_out.replace(hour=10, minute=0, second=0, microsecond=0)
        
        check_in_str = check_in.strftime('%H:%M') if check_in else ''
        
        # Handle missing check-out: If person checked in but didn't say goodbye → set checkout to 17:00
        no_checkout = False
        if check_in and not check_out and not is_oncall_or_support:
            no_checkout = True
            check_out = check_in.replace(hour=17, minute=0, second=0, microsecond=0)
        
        check_out_str = check_out.strftime('%H:%M') if check_out else ''
        
        # Work hours
        if check_in and check_out:
            work_time = (check_out - check_in).total_seconds() / 3600
            net_work = work_time - (data.get('total_brb_time', 0) / 60)
            work_hours = f'{net_work:.1f}'
        else:
            work_hours = ''
        
        # BRB with session breakdown (add 'l' suffix for lunch)
        brb_total = int(data.get('total_brb_time', 0))
        brb_sessions = data.get('brb_sessions', [])
        if brb_sessions:
            session_parts = []
            for s in brb_sessions:
                duration = int(s['actual_minutes'])
                suffix = 'l' if s.get('is_lunch') else ''
                session_parts.append(f"{duration}{suffix}")
            session_str = '+'.join(session_parts)
            brb_display = f"{brb_total}({session_str})"
        else:
            brb_display = brb_total if brb_total else ''
        brb_open = 'YES' if data.get('current_brb') else ''
        
        # Discord count only
        discord_count = discord_counts.get(name, 0)
        
        # Leave - check from pre-parsed leave database first, then fallback to message-based detection
        leave_info = is_on_leave(name, date_str)
        leave_requests = data.get('leave_requests', [])
        
        # Determine leave type: HOURLY, YES (full day), or empty
        has_leave = ''
        leave_hours = ''
        if leave_info:
            has_leave = 'YES'
        elif leave_requests:
            total_hourly_minutes = 0
            has_full_day = False
            for lr in leave_requests:
                if lr.get('duration_minutes'):
                    total_hourly_minutes += lr['duration_minutes']
                else:
                    has_full_day = True
            
            if has_full_day:
                has_leave = 'YES'
            elif total_hourly_minutes > 0:
                hours = total_hourly_minutes // 60
                mins = total_hourly_minutes % 60
                has_leave = 'HOURLY'
                leave_hours = f'{hours}h{mins}m' if mins else f'{hours}h'
        
        # Remote work
        remote_info = is_remote_work(name, date_str)
        remote_work = remote_info.get('location', 'YES') if remote_info else ''
        
        # Idle time from Discord bot (08:00-18:30 work hours)
        idle_minutes = get_idle_time(name, date_str)
        idle_str = ''
        idle_percent = ''
        if idle_minutes is not None:
            idle_str = str(int(idle_minutes))
            # Work hours: 10.5 hours = 630 minutes
            idle_percent = f'{(idle_minutes / WORK_HOURS_TOTAL_MINUTES) * 100:.0f}%'
        
        # Update or insert
        key = (date_str, name)
        existing_data[key] = {
            'Date': date_str,
            'Name': name,
            'CheckIn': check_in_str,
            'CheckOut': check_out_str,
            'WorkHours': work_hours,
            'BRB_Minutes': brb_display,
            'BRB_Open': brb_open,
            'Emails': '',  # No email data for backfill
            'Discord': discord_count if discord_count else '',
            'Leave': has_leave,
            'LeaveHours': leave_hours,
            'RemoteWork': remote_work,
            'IdleMinutes': idle_str,
            'IdlePercent': idle_percent,
            'OfflineMinutes': '',
            'OfflinePercent': '',
            'Weekend': 'YES' if is_weekend(date_str) else '',
            'IsOnCall': 'YES' if oncall_person == name else '',
            'IsSupport': 'YES' if support_person == name else '',
            'NoCheckout': 'YES' if no_checkout else '',  # Flag for missing goodbye
            'NoCheckin': 'YES' if no_checkin else '',  # Flag for missing greeting
        }
    
    # Write all data
    fieldnames = ['Date', 'Name', 'CheckIn', 'CheckOut', 'WorkHours', 
                  'BRB_Minutes', 'BRB_Open', 'Emails', 'Discord', 'Leave', 'LeaveHours',
                  'RemoteWork', 'IdleMinutes', 'IdlePercent', 'OfflineMinutes', 'OfflinePercent',
                  'Weekend', 'IsOnCall', 'IsSupport', 'NoCheckout', 'NoCheckin']
    
    with open(ATTENDANCE_CSV, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(existing_data.keys()):
            writer.writerow(existing_data[key])


if __name__ == '__main__':
    main()
