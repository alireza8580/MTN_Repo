#!/usr/bin/env python3
import csv
import json
import os
import glob
from datetime import datetime, timedelta
from collections import defaultdict

# === CONFIG ===
EMAIL_DIR = '/root/infrastructure/mtn_emails'
DISCORD_DIR = '/root/infrastructure/discord_exports'

# Dynamic date calculation
TODAY = datetime.now().strftime('%Y-%m-%d')
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
RECENT_DATES = [TODAY, YESTERDAY]

def get_latest_file(directory, pattern):
    """Get the most recent file matching pattern"""
    files = glob.glob(os.path.join(directory, pattern))
    if not files:
        return None
    return max(files, key=os.path.getctime)

# Get latest files
EMAIL_FILE = get_latest_file(EMAIL_DIR, 'mtn_emails_*.csv')
DISCORD_FILE = get_latest_file(DISCORD_DIR, '*.json')

if not EMAIL_FILE:
    print("❌ No email file found!")
    exit(1)
if not DISCORD_FILE:
    print("❌ No Discord file found!")
    exit(1)

print(f"📧 Email file: {os.path.basename(EMAIL_FILE)}")
print(f"💬 Discord file: {os.path.basename(DISCORD_FILE)}")
print()

# VIP senders (higher priority)
VIP_SENDERS = ['Mehdi Kheir', 'Omid Heravi', 'Amirbahram']

# DBA patterns for filtering
DBA_PATTERNS = [
    'alireza.aghaja', 'maryam.ma', 'keivan.s', 'maryam.y', 'ehsan.y',
    'mohsen.r', 'hossein.f', 'nader.sh', 'zeinabsadat.he', 'hosseinali.s',
    'masoud.r', 'masoud.s', 'yasin.aa', 'erfan.he',
    'Erfan Heidari', 'Maryam Marefati', 'Keivan Sadeghi', 'Maryam Yousefi',
    'Mohsen Roudsaz', 'Hosseinali Shirali', 'Masoud Rafiei', 'Nader Shabibi',
    'Zeinabsadat Hejazi', 'Ehsan Yousefi', 'Yassin Alivand',
    'Masoud Sereshki', 'Hossein Feizollahi', 'Samira Akherati'
]

def is_dba(sender):
    for p in DBA_PATTERNS:
        if p.lower() in sender.lower():
            return True
    return False

def normalize_subject(subj):
    s = subj.strip()
    while s.upper().startswith('RE:') or s.upper().startswith('FW:'):
        s = s[3:].strip()
    return s.lower()

def parse_time(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    except:
        return datetime.min

def is_valid_email(e):
    subject = e.get('Subject', '')
    sender = e.get('From', '')
    if '[iCare]' in subject or 'Alert' in subject:
        return False
    if 'icare@' in sender or 'Oracle User' in sender or sender == 'oracle' or sender == 'root':
        return False
    if 'MongoDB Ops Manager' in sender:
        return False
    return True

# === LOAD EMAILS ===
emails = []
with open(EMAIL_FILE, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        emails.append(row)

valid_emails = [e for e in emails if is_valid_email(e)]
valid_emails.sort(key=lambda x: parse_time(x.get('ReceivedTime', '')), reverse=True)

# Group by normalized subject
threads = defaultdict(list)
for e in valid_emails:
    key = normalize_subject(e.get('Subject', ''))
    threads[key].append(e)

for k in threads:
    threads[k].sort(key=lambda x: parse_time(x.get('ReceivedTime', '')))

# === 1. IMPORTANT EMAILS ===
print("=" * 60)
print("۱. خلاصه مهم‌ترین ایمیل‌ها")
print("=" * 60)
print()
print("| Subject | From | Time |")
print("|---------|------|------|")

shown = set()
count = 0

# VIP first
for e in valid_emails:
    sender = e.get('From', '')
    if any(v.lower() in sender.lower() for v in VIP_SENDERS):
        subj = e.get('Subject', '')
        time = e.get('ReceivedTime', '')[-8:-3] if len(e.get('ReceivedTime', '')) > 8 else ''
        key = subj
        if key not in shown and count < 10:
            print(f"| {subj} | {sender[:40]} | {time} |")
            shown.add(key)
            count += 1

# Then recent
for e in valid_emails[:15]:
    sender = e.get('From', '')
    subj = e.get('Subject', '')
    time = e.get('ReceivedTime', '')[-8:-3] if len(e.get('ReceivedTime', '')) > 8 else ''
    key = subj
    if key not in shown and count < 10:
        print(f"| {subj} | {sender[:40]} | {time} |")
        shown.add(key)
        count += 1

# === 2. ALIREZA MUST RESPOND ===
print()
print("=" * 60)
print("۲. کارهایی که علیرضا باید جواب بده")
print("=" * 60)

# Thread pattern
print("\n📧 Email (Thread Pattern - Alireza sent, someone replied):")
thread_pattern_found = False
for key, thread in threads.items():
    if len(thread) >= 2:
        second_last = thread[-2]
        last = thread[-1]
        sender_second = second_last.get('From', '')
        sender_last = last.get('From', '')
        
        if 'alireza.aghaja' in sender_second.lower() or 'Alireza Aghajanzadeh' in sender_second:
            if not is_dba(sender_last):
                thread_pattern_found = True
                print(f"  - {last.get('Subject', '')}")
                print(f"    From: {sender_last}, Time: {last.get('ReceivedTime', '')[-5:]}")

if not thread_pattern_found:
    print("  هیچ موردی نیست")

# Direct TO Alireza
print("\n📧 Email (Direct TO Alireza):")
direct_found = False
for key, thread in threads.items():
    last = thread[-1]
    to_field = last.get('To', '')
    sender = last.get('From', '')
    
    if 'Alireza Aghajanzadeh' in to_field:
        # Not from Alireza, not from any DBA
        if 'alireza.aghaja' not in sender.lower() and 'Alireza Aghajanzadeh' not in sender:
            # Check body for done patterns
            body = last.get('Body', '').lower()
            if 'done' not in body and "it's done" not in body and 'in progress' not in body:
                # Skip if it's to Alireza Maleki context
                if 'Alireza Maleki' in to_field:
                    continue
                direct_found = True
                print(f"  - {last.get('Subject', '')}")
                print(f"    From: {sender[:50]}, Time: {last.get('ReceivedTime', '')[-5:]}")

if not direct_found:
    print("  هیچ موردی نیست")

# === DISCORD PART ===
print("\n💬 Discord (منتظر جواب علیرضا):")
try:
    with open(DISCORD_FILE, 'r', encoding='utf-8') as f:
        discord_data = json.load(f)
    
    # New structure: channels -> channel_name -> messages
    channels = discord_data.get('channels', {})
    alireza_patterns = ['alireza', 'علیرضا', 'قشلاقی']
    alireza_username = 'dba_alireza'
    
    found_any = False
    for channel_name, channel_data in channels.items():
        if not isinstance(channel_data, dict):
            continue
        
        messages = channel_data.get('messages', [])
        for i, msg in enumerate(messages):
            author_data = msg.get('author', {})
            author = author_data.get('name', '') if isinstance(author_data, dict) else str(author_data)
            content = msg.get('content', '').lower()
            
            # Skip Alireza's own messages
            if alireza_username in author.lower():
                continue
            
            # Check if mentions alireza
            if any(p in content for p in alireza_patterns):
                # Check if in last 2 days (dynamic)
                timestamp = msg.get('timestamp', '')
                if any(d in timestamp for d in RECENT_DATES):
                    # Check if Alireza replied after
                    replied = False
                    for j in range(i+1, min(i+10, len(messages))):
                        next_author = messages[j].get('author', {})
                        next_name = next_author.get('name', '') if isinstance(next_author, dict) else str(next_author)
                        if alireza_username in next_name.lower():
                            replied = True
                            break
                    
                    if not replied:
                        found_any = True
                        time = timestamp[11:16] if timestamp else ''
                        display_content = msg.get('content', '')[:60]
                        print(f"  - [{channel_name}] {author}: {display_content}...")
                        print(f"    Time: {time}")
    
    if not found_any:
        print("  هیچ موردی نیست")
except Exception as e:
    print(f"  Error reading Discord: {e}")

# === 3. TEAM PENDING ===
print()
print("=" * 60)
print("۳. کارهای باز مانده تیم (کسی جواب نداده)")
print("=" * 60)
print()

# Find threads where last email is TO DBA but no DBA replied
team_pending = []
for key, thread in threads.items():
    last = thread[-1]
    to_field = last.get('To', '')
    sender = last.get('From', '')
    
    # Check if TO contains any DBA
    if any(p in to_field for p in ['DBA', 'Maryam Marefati', 'Keivan Sadeghi', 'Erfan Heidari', 'Hosseinali Shirali']):
        # Check if any DBA replied in thread
        dba_replied = False
        last_time = parse_time(last.get('ReceivedTime', ''))
        for e in thread:
            e_time = parse_time(e.get('ReceivedTime', ''))
            if e_time > last_time and is_dba(e.get('From', '')):
                dba_replied = True
                break
        
        if not dba_replied and not is_dba(sender):
            team_pending.append({
                'subject': last.get('Subject', ''),
                'to': to_field[:50],
                'from': sender,
                'time': last.get('ReceivedTime', '')[-8:-3]
            })

if team_pending:
    for item in team_pending[:5]:
        print(f"  - {item['subject']}")
        print(f"    To: {item['to']}, From: {item['from'][:40]}, Time: {item['time']}")
else:
    print("  هیچ موردی نیست")

# === 4. DISCORD DISCUSSIONS (filtered) ===
print()
print("=" * 60)
print("۴. بحث‌های Discord (بدون سلام/خداحافظی/brb)")
print("=" * 60)
print()

def is_noise_message(content):
    """Filter out greetings, brb, and goodbyes"""
    content_lower = content.lower().strip()
    noise_patterns = [
        'salam', 'صبح', 'sobh', 'روز بخیر', 'rooz', 'bekheir', 'bkheir', 'be kheir',
        'khaste nabashid', 'خسته نباشید', 'felan', 'shb khosh', 'شب خوش', 'khodafez',
        'brb', '@everyone'
    ]
    # Check if content is just noise
    if content_lower in ['b', 'back']:
        return True
    for pattern in noise_patterns:
        if pattern in content_lower and len(content_lower) < 100:
            return True
    return False

try:
    with open(DISCORD_FILE, 'r', encoding='utf-8') as f:
        discord_data = json.load(f)
    
    channels = discord_data.get('channels', {})
    
    if 'general_new' in channels:
        messages = channels['general_new'].get('messages', [])
        recent = [m for m in messages if any(d in m.get('timestamp', '') for d in RECENT_DATES)]
        
        # Filter out noise
        filtered = [m for m in recent if not is_noise_message(m.get('content', ''))]
        
        print(f"پیام‌های مهم (فیلتر شده): {len(filtered)} از {len(recent)} پیام")
        for msg in filtered[-15:]:
            author_data = msg.get('author', {})
            author = author_data.get('display_name', author_data.get('name', '')) if isinstance(author_data, dict) else str(author_data)
            content = msg.get('content', '')[:100].replace('\n', ' ')
            time = msg.get('timestamp', '')[11:16] if msg.get('timestamp') else ''
            if content.strip():
                print(f"  [{time}] {author}: {content}")
except Exception as e:
    print(f"  Error: {e}")

print()
print("=" * 60)

# === 5. TEAM DAILY TABLE ===
print()
print("=" * 60)
print("۵. جدول روزانه تیم")
print("=" * 60)
print()

# Import and run attendance tracker
try:
    import sys
    sys.path.insert(0, '/root/infrastructure/scripts')
    from attendance_tracker import analyze_attendance, print_daily_table
    
    attendance, date_str = analyze_attendance()
    print_daily_table(attendance, date_str)
except Exception as e:
    print(f"  Error: {e}")
    print("  برای گزارش کامل:")
    print("    python3 scripts/attendance_tracker.py --table")

print()
print("=" * 60)
