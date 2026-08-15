#!/usr/bin/env python3
"""
Email Extractor for DBA Attendance Reports
Extracts sent email counts per team member using Exchange Web Services (EWS)

Approach: Count emails RECEIVED FROM team members in the DBA shared mailbox
This works because most team emails go through the shared DBA mailbox.

Author: Alireza Aghajanzadeh Gheshlaghi
"""
import os
import sys
import json
from datetime import datetime, timedelta
from exchangelib import (
    Credentials, Account, Configuration, DELEGATE, IMPERSONATION, NTLM,
    EWSDateTime, EWSTimeZone, UTC
)
from exchangelib.folders import SentItems
from exchangelib.errors import UnauthorizedError
import pytz

# === CONFIG ===
# Mailbox is the DBA team lead's (maryam.mare). Exchange has Basic auth disabled,
# so the login must be the NTLM domain form DOMAIN\samaccountname.
EWS_SERVER = os.environ.get('EWS_SERVER', 'mail.mtnirancell.ir')
EWS_DOMAIN = os.environ.get('EWS_DOMAIN', 'mtnirancell.ir')
EWS_USER = os.environ.get('EWS_USER', 'maryam.mare')
EWS_EMAIL = os.environ.get('EWS_EMAIL', 'maryam.mare@mtnirancell.ir')
EWS_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

# DBA shared mailbox - most team emails go here
DBA_SHARED_MAILBOX = '#ITSDCDBA@mtnirancell.ir'

# Output directory for email exports
BASE_DIR = os.environ.get('APP_BASE_DIR', '/root/infrastructure')
EMAIL_EXPORT_DIR = os.environ.get('EMAIL_EXPORT_DIR', os.path.join(BASE_DIR, 'email_exports'))

# Timezone for Iran
IRAN_TZ = pytz.timezone('Asia/Tehran')

# DBA Team members - email addresses (using short form as seen in Exchange)
# The system uses shortened email addresses (firstname.last3chars@...)
DBA_TEAM_EMAILS = {
    'Keivan Sadeghi': 'keivan.sad',
    'Ehsan Yousefi': 'ehsan.you',
    'Mohsen Roudsaz': 'mohsen.rou',
    'Nader Shabibi': 'nader.sha',
    'Zeinabsadat Hejazi': 'zeinabsadat.he',
    'Hosseinali Shirali': 'hosseinali.s',
    'Masoud Rafiei': 'masoud.raf',
    'Masoud Sereshki': 'masoud.ser',
    'Yassin Alivand': 'yassin.ali',
    'Erfan Heidari': 'erfan.hei',
    'Maryam Yousefi': 'maryam.you',
    # Excluded from tracking (owner, team lead, senior)
    # 'Alireza Aghajanzadeh Gheshlaghi': 'alireza.aghaja',
    # 'Maryam Marefati': 'maryam.mare',
    # 'Hossein Feizollahi': 'hossein.fei',
}

# Reverse mapping for lookup
EMAIL_TO_NAME = {v: k for k, v in DBA_TEAM_EMAILS.items()}


def get_my_account():
    """Connect to Exchange for own account"""
    if not EWS_PASSWORD:
        print("ERROR: SMTP_PASSWORD environment variable not set!")
        return None
    
    try:
        credentials = Credentials(f"{EWS_DOMAIN}\\{EWS_USER}", EWS_PASSWORD)
        config = Configuration(server=EWS_SERVER, credentials=credentials, auth_type=NTLM)
        account = Account(
            primary_smtp_address=EWS_EMAIL,
            config=config,
            autodiscover=False,
            access_type=DELEGATE
        )
        return account
    except Exception as e:
        print(f"ERROR connecting to Exchange: {e}")
        return None


def get_shared_mailbox_account(shared_email):
    """
    Connect to a shared mailbox using delegate access.
    Requires that the user has been granted access to the shared mailbox.
    """
    if not EWS_PASSWORD:
        print("ERROR: SMTP_PASSWORD environment variable not set!")
        return None
    
    try:
        credentials = Credentials(f"{EWS_DOMAIN}\\{EWS_USER}", EWS_PASSWORD)
        config = Configuration(server=EWS_SERVER, credentials=credentials, auth_type=NTLM)
        account = Account(
            primary_smtp_address=shared_email,
            config=config,
            autodiscover=False,
            access_type=DELEGATE
        )
        # Account() is lazy - touch a folder so a missing mailbox or a denied
        # delegation fails here instead of much later at the call site.
        account.inbox.total_count
        return account
    except Exception as e:
        print(f"ERROR connecting to shared mailbox {shared_email}: {e}")
        return None


def count_emails_from_sender(account, sender_email, date_str, folder='inbox'):
    """
    Count emails FROM a specific sender on a specific date.
    Returns tuple: (count, list of subjects for verification)
    """
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Date range: start of day to end of day
        start = EWSDateTime(
            target_date.year, target_date.month, target_date.day,
            0, 0, 0,
            tzinfo=account.default_timezone
        )
        end = EWSDateTime(
            target_date.year, target_date.month, target_date.day,
            23, 59, 59,
            tzinfo=account.default_timezone
        )
        
        # Get the folder
        if folder == 'inbox':
            target_folder = account.inbox
        elif folder == 'sent':
            target_folder = account.sent
        else:
            target_folder = account.inbox
        
        # Query emails within date range only (filter sender locally)
        # The sender filter causes "No mailbox with such guid" errors
        emails = target_folder.filter(datetime_received__range=(start, end))
        
        count = 0
        subjects = []
        sender_prefix = sender_email.split('@')[0].lower()
        
        for email in emails:
            # Check if sender matches
            if hasattr(email, 'sender') and email.sender:
                sender_addr = getattr(email.sender, 'email_address', '')
                if sender_addr and sender_prefix in sender_addr.lower():
                    count += 1
                    if hasattr(email, 'subject') and email.subject:
                        subjects.append(email.subject[:50])
        
        return count, subjects
    
    except Exception as e:
        print(f"  ! Error counting emails: {e}")
        return 0, []


def count_sent_emails_from_own(account, date_str):
    """
    Count emails in MY sent folder on a specific date.
    Only works for the authenticated user's own mailbox.
    """
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        start = EWSDateTime(
            target_date.year, target_date.month, target_date.day,
            0, 0, 0,
            tzinfo=account.default_timezone
        )
        end = EWSDateTime(
            target_date.year, target_date.month, target_date.day,
            23, 59, 59,
            tzinfo=account.default_timezone
        )
        
        emails = account.sent.filter(datetime_sent__range=(start, end))
        
        count = emails.count()
        return count
    
    except Exception as e:
        print(f"  ! Error counting sent emails: {e}")
        return 0


def count_all_emails_by_sender(account, date_str):
    """
    Count all emails received on a date, grouped by sender.
    Much more efficient than querying per sender.
    Returns dict: {sender_email_prefix: count}
    """
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Date range: start of day to end of day
        start = EWSDateTime(
            target_date.year, target_date.month, target_date.day,
            0, 0, 0,
            tzinfo=account.default_timezone
        )
        end = EWSDateTime(
            target_date.year, target_date.month, target_date.day,
            23, 59, 59,
            tzinfo=account.default_timezone
        )
        
        # Query all emails within date range
        emails = account.inbox.filter(datetime_received__range=(start, end))
        
        # Count by sender
        sender_counts = {}
        for email in emails:
            if hasattr(email, 'sender') and email.sender:
                sender_addr = getattr(email.sender, 'email_address', '')
                if sender_addr:
                    sender_lower = sender_addr.lower()
                    if sender_lower not in sender_counts:
                        sender_counts[sender_lower] = 0
                    sender_counts[sender_lower] += 1
        
        return sender_counts
    
    except Exception as e:
        print(f"  ! Error counting emails: {e}")
        return {}


def extract_emails_for_date(date_str, output_file=None):
    """
    Extract email counts for all team members for a specific date.
    
    Strategy:
    1. Use personal inbox (shared mailbox access is tricky)
    2. Fetch all emails for the date
    3. Count how many are FROM each team member
    
    Returns dict: {name: count}
    """
    print(f"Extracting email counts for: {date_str}")
    
    results = {}
    
    # Use personal inbox (more reliable than shared mailbox)
    account = get_my_account()
    if not account:
        print("ERROR: Cannot access mailbox!")
        return {}
    
    print("Using personal inbox")
    
    # Fetch all emails and count by sender
    print(f"\nFetching emails for {date_str}...")
    sender_counts = count_all_emails_by_sender(account, date_str)
    
    total_emails = sum(sender_counts.values())
    print(f"Total emails received: {total_emails}")
    
    # Map to team members using prefix matching
    print(f"\nCounting per team member:")
    for name, email_prefix in DBA_TEAM_EMAILS.items():
        count = 0
        for sender, cnt in sender_counts.items():
            if email_prefix in sender:
                count += cnt
        results[name] = count
        if count > 0:
            print(f"  {name}: {count} emails")
    
    # Show non-zero results
    team_with_emails = {k: v for k, v in results.items() if v > 0}
    team_without_emails = {k: v for k, v in results.items() if v == 0}
    
    if team_without_emails:
        print(f"\nNo emails from: {', '.join(team_without_emails.keys())}")
    
    # Save results to JSON
    if output_file is None:
        os.makedirs(EMAIL_EXPORT_DIR, exist_ok=True)
        output_file = os.path.join(EMAIL_EXPORT_DIR, f"email_counts_{date_str}.json")
    
    export_data = {
        'date': date_str,
        'extracted_at': datetime.now().isoformat(),
        'source': 'personal_inbox',
        'total_emails': total_emails,
        'counts': results,
        'note': 'Counts emails received FROM each team member in your inbox'
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {output_file}")
    return results


def check_access():
    """Check what mailboxes we can access"""
    print("Checking mailbox access...")
    print(f"User: {EWS_EMAIL}")
    
    # Own account
    my_account = get_my_account()
    if my_account:
        print("✓ Personal mailbox: OK")
        # Test a query
        today = datetime.now().strftime('%Y-%m-%d')
        count = count_sent_emails_from_own(my_account, today)
        print(f"  Your sent emails today: {count}")
    else:
        print("✗ Personal mailbox: FAILED")
        return
    
    # Shared mailbox
    print(f"\nChecking shared mailbox: {DBA_SHARED_MAILBOX}")
    shared = get_shared_mailbox_account(DBA_SHARED_MAILBOX)
    if shared:
        print("✓ DBA shared mailbox: OK")
        print("  This will be used to count team emails.")
    else:
        print("✗ DBA shared mailbox: NOT ACCESSIBLE")
        print("  Will fall back to your personal inbox (less accurate).")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Extract email counts for DBA team')
    parser.add_argument('--date', '-d', help='Date to extract (YYYY-MM-DD), default: yesterday')
    parser.add_argument('--check', action='store_true', help='Check mailbox access')
    parser.add_argument('--output', '-o', help='Output JSON file path')
    
    args = parser.parse_args()
    
    if args.check:
        check_access()
        return
    
    # Default to yesterday
    if args.date:
        date_str = args.date
    else:
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%Y-%m-%d')
    
    extract_emails_for_date(date_str, args.output)


if __name__ == '__main__':
    main()
