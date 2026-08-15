#!/usr/bin/env python3
"""
Email Full Extractor for DBA Work Analysis
Extracts full email content (Subject, From, To, Body) using EWS
Outputs CSV compatible with mtn_update.py

Author: Alireza Aghajanzadeh Gheshlaghi
"""
import os
import sys
import csv
from datetime import datetime, timedelta
from exchangelib import (
    Credentials, Account, Configuration, DELEGATE, NTLM,
    EWSDateTime, EWSTimeZone
)
import pytz

# === CONFIG ===
# Mailbox is the DBA team lead's (maryam.mare). Exchange has Basic auth disabled,
# so the login must be the NTLM domain form DOMAIN\samaccountname.
EWS_SERVER = os.environ.get('EWS_SERVER', 'mail.mtnirancell.ir')
EWS_DOMAIN = os.environ.get('EWS_DOMAIN', 'mtnirancell.ir')
EWS_USER = os.environ.get('EWS_USER', 'maryam.mare')
EWS_EMAIL = os.environ.get('EWS_EMAIL', 'maryam.mare@mtnirancell.ir')
EWS_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

# Output directory
BASE_DIR = os.environ.get('APP_BASE_DIR', '/root/infrastructure')
EMAIL_DIR = os.environ.get('MTN_EMAIL_DIR', os.path.join(BASE_DIR, 'mtn_emails'))

# Skip patterns (noise emails)
SKIP_SENDERS = ['icare@', 'Oracle User', 'oracle@', 'root@']
SKIP_SUBJECTS = ['[iCare]', 'Alert - ', 'ORA-', 'MongoDB Ops Manager']


def get_ews_account():
    """Connect to Exchange"""
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


def should_skip(email):
    """Check if email should be skipped (noise)"""
    sender = ''
    subject = ''
    
    try:
        if email.sender:
            sender = getattr(email.sender, 'email_address', '') or ''
        subject = email.subject or ''
    except:
        pass
    
    for pattern in SKIP_SENDERS:
        if pattern.lower() in sender.lower():
            return True
    
    for pattern in SKIP_SUBJECTS:
        if pattern.lower() in subject.lower():
            return True
    
    return False


def extract_body(email, max_chars=2000):
    """Extract email body (plain text preferred)"""
    try:
        if hasattr(email, 'text_body') and email.text_body:
            body = email.text_body
        elif hasattr(email, 'body') and email.body:
            body = email.body
        else:
            body = ''
        
        # Clean and truncate
        if body:
            body = body.strip()
            if len(body) > max_chars:
                body = body[:max_chars] + '...'
        return body
    except:
        return ''


def get_recipients(email):
    """Get TO recipients as string"""
    try:
        if email.to_recipients:
            return '; '.join([
                getattr(r, 'email_address', str(r)) 
                for r in email.to_recipients
            ])
        return ''
    except:
        return ''


def extract_emails(days=2, output_file=None, skip_body=False):
    """
    Extract emails from the last N days.
    Outputs CSV with columns: ReceivedTime, From, To, Subject, Body
    
    Args:
        days: Number of days to extract
        output_file: Output CSV path
        skip_body: If True, skip body extraction (much faster)
    """
    print(f"Extracting emails from last {days} days...")
    if skip_body:
        print("(Skipping body extraction for speed)")
    
    account = get_ews_account()
    if not account:
        return False
    
    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    tz = account.default_timezone
    start = EWSDateTime(
        start_date.year, start_date.month, start_date.day,
        0, 0, 0,
        tzinfo=tz
    )
    end = EWSDateTime(
        end_date.year, end_date.month, end_date.day,
        23, 59, 59,
        tzinfo=tz
    )
    
    print(f"Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    # Query inbox - fetch only specific fields for performance
    print("Querying inbox (this may take a moment)...")
    
    # Specify fields to fetch - body is slowest
    if skip_body:
        # Fast mode - only metadata
        emails = account.inbox.filter(datetime_received__range=(start, end)).only(
            'datetime_received', 'sender', 'to_recipients', 'subject'
        )
    else:
        # Full mode - include body (slower)
        emails = account.inbox.filter(datetime_received__range=(start, end)).only(
            'datetime_received', 'sender', 'to_recipients', 'subject', 'text_body'
        )
    
    # Get count first (separate query)
    try:
        email_count = emails.count()
        print(f"Found {email_count} emails to process")
    except Exception as e:
        print(f"Could not get count: {e}")
        email_count = "unknown"
    
    # Prepare output
    if output_file is None:
        os.makedirs(EMAIL_DIR, exist_ok=True)
        output_file = os.path.join(
            EMAIL_DIR, 
            f"mtn_emails_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    
    # Write to CSV
    count = 0
    skipped = 0
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ReceivedTime', 'From', 'To', 'Subject', 'Body'])
        
        print("Processing emails...", flush=True)
        for email in emails:
            if should_skip(email):
                skipped += 1
                if (count + skipped) % 20 == 0:
                    print(f"  Progress: {count} saved, {skipped} skipped...", flush=True)
                continue
            
            try:
                received = email.datetime_received.strftime('%Y-%m-%d %H:%M:%S') if email.datetime_received else ''
                sender = getattr(email.sender, 'email_address', '') if email.sender else ''
                sender_name = getattr(email.sender, 'name', '') if email.sender else ''
                
                # Combine name and email
                if sender_name and sender:
                    from_field = f"{sender_name} <{sender}>"
                else:
                    from_field = sender or sender_name
                
                to_field = get_recipients(email)
                subject = email.subject or ''
                
                # Body extraction is slow - skip if --no-body
                if skip_body:
                    body = ''
                else:
                    body = extract_body(email)
                
                writer.writerow([received, from_field, to_field, subject, body])
                count += 1
                
                # Progress logging every 20 emails
                if count % 20 == 0:
                    print(f"  Progress: {count} saved, {skipped} skipped...", flush=True)
                
            except Exception as e:
                print(f"  Error processing email: {e}", flush=True)
                continue
    
    print(f"\nExtracted {count} emails (skipped {skipped} noise)")
    print(f"Output: {output_file}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Extract full emails for work analysis')
    parser.add_argument('--days', '-d', type=int, default=2, help='Number of days to extract (default: 2)')
    parser.add_argument('--output', '-o', help='Output CSV file path')
    parser.add_argument('--no-body', action='store_true', help='Skip extracting email body (faster)')
    
    args = parser.parse_args()
    extract_emails(days=args.days, output_file=args.output, skip_body=args.no_body)


if __name__ == '__main__':
    main()
