#!/usr/bin/env python3
"""
Email Sender for DBA Attendance Reports
Sends daily/monthly reports via Exchange Web Services (EWS)
"""
import os
import sys
from datetime import datetime
import csv
import jdatetime

# Exchange Web Services
from exchangelib import Credentials, Account, Configuration, DELEGATE, Message, Mailbox, FileAttachment, HTMLBody

# === CONFIG ===
EWS_SERVER = os.environ.get('EWS_SERVER', 'mail.mtnirancell.ir')
EWS_EMAIL = os.environ.get('EWS_EMAIL', 'alireza.aghaja@mtnirancell.ir')
EWS_PASSWORD = os.environ.get('SMTP_PASSWORD', '')  # Use same env var

# Recipients
FROM_EMAIL = EWS_EMAIL

# TEST mode - only internal team
TO_EMAILS_TEST = ['alireza.aghaja@mtnirancell.ir', 'maryam.mare@mtnirancell.ir']
CC_EMAILS_TEST = []
BCC_EMAILS_TEST = []

# PROD mode - Daily report
TO_EMAILS_PROD = ['alireza.aghaja@mtnirancell.ir', 'maryam.mare@mtnirancell.ir']
CC_EMAILS_PROD = ['amirbahram.b@mtnirancell.ir', 'hossein.mog@mtnirancell.ir']
BCC_EMAILS_PROD = []

# PROD mode - Monthly report (adds manager + account manager to CC)
CC_EMAILS_MONTHLY = ['mehdi.kheir@mtnirancell.ir', 'omid.her@mtnirancell.ir']

# File paths
ATTENDANCE_CSV = os.environ.get('ATTENDANCE_CSV', '/root/infrastructure/attendance_reports/daily_attendance.csv')
ATTENDANCE_REPORTS_DIR = os.path.dirname(ATTENDANCE_CSV)


def create_date_specific_csv(date_str):
    """
    Create a date-specific CSV file from the main attendance CSV.
    Returns the path to the date-specific CSV file.
    Filename format: daily_attendance_YYYY-MM-DD.csv
    """
    if not os.path.exists(ATTENDANCE_CSV):
        return None
    
    # Create date-specific filename
    output_file = os.path.join(ATTENDANCE_REPORTS_DIR, f"daily_attendance_{date_str}.csv")
    
    # Read rows for this date from main CSV
    rows_for_date = []
    fieldnames = None
    
    with open(ATTENDANCE_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row['Date'] == date_str:
                rows_for_date.append(row)
    
    if not rows_for_date or not fieldnames:
        return None
    
    # Write date-specific CSV
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_for_date)
    
    print(f"✓ Created date-specific CSV: {output_file} ({len(rows_for_date)} rows)")
    return output_file


def get_ews_account():
    """Connect to Exchange using EWS"""
    if not EWS_PASSWORD:
        print("ERROR: SMTP_PASSWORD environment variable not set!")
        return None
    
    try:
        credentials = Credentials(EWS_EMAIL, EWS_PASSWORD)
        config = Configuration(server=EWS_SERVER, credentials=credentials)
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


def read_daily_summary(date_str):
    """Read today's attendance summary from CSV"""
    if not os.path.exists(ATTENDANCE_CSV):
        return None
    
    summary = {
        'total': 0,
        'checked_in': 0,
        'on_leave_full': 0,
        'on_leave_hourly': 0,
        'absent': 0,  # Absent count (غیبت)
        'on_call': None,
        'support': None,
        'details': []
    }
    
    with open(ATTENDANCE_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Date'] != date_str:
                continue
            
            summary['total'] += 1
            
            if row.get('CheckIn'):
                summary['checked_in'] += 1
            
            if row.get('Leave') == 'YES':
                summary['on_leave_full'] += 1
            elif row.get('Leave') == 'HOURLY':
                summary['on_leave_hourly'] += 1
            
            if row.get('Absent') == 'YES':
                summary['absent'] += 1
            
            if row.get('IsOnCall') == 'YES':
                summary['on_call'] = row['Name']
            
            if row.get('IsSupport') == 'YES':
                summary['support'] = row['Name']
            
            summary['details'].append({
                'name': row['Name'],
                'check_in': row.get('CheckIn', ''),
                'check_out': row.get('CheckOut', ''),
                'work_hours': row.get('WorkHours', ''),
                'brb': row.get('BRB_Minutes', ''),
                'idle': row.get('IdleMinutes', ''),
                'offline': row.get('OfflineMinutes', ''),
                'leave': row.get('Leave', ''),
                'leave_hours': row.get('LeaveHours', ''),
                'is_oncall': row.get('IsOnCall', ''),
                'is_support': row.get('IsSupport', ''),
                'oncall_notes': row.get('OnCallNotes', ''),
                'emails': row.get('Emails', ''),
                'discord': row.get('Discord', ''),
                'voice': row.get('Voice', ''),
                'effective': row.get('EffectiveMinutes', ''),
                'no_checkout': row.get('NoCheckout', ''),  # Flag for missing goodbye
                'no_checkin': row.get('NoCheckin', ''),  # Flag for missing greeting
                'absent': row.get('Absent', ''),  # Flag for absence (غیبت)
            })
    
    return summary


def create_daily_email_body(date_str, summary):
    """Create HTML email body for daily report"""
    
    # Convert to Jalali for display
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    jalali_date = jdatetime.date.fromgregorian(date=date_obj)
    jalali_str = jalali_date.strftime('%Y/%m/%d')
    
    # Jalali month names
    jalali_months = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                     'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']
    jalali_weekdays = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه']
    
    weekday_name = jalali_weekdays[jalali_date.weekday()]
    month_name = jalali_months[jalali_date.month - 1]
    jalali_full = f"{weekday_name} {jalali_date.day} {month_name} {jalali_date.year}"
    
    # Find people without checkout (excluding oncall/support)
    no_checkout_people = [d['name'] for d in summary['details'] 
                          if d.get('no_checkout') == 'YES' and d.get('is_oncall') != 'YES' and d.get('is_support') != 'YES']
    
    # Find people without check-in (excluding oncall/support)
    no_checkin_people = [d['name'] for d in summary['details'] 
                         if d.get('no_checkin') == 'YES' and d.get('is_oncall') != 'YES' and d.get('is_support') != 'YES']
    
    # Find absent people (غیبت)
    absent_people = [d['name'] for d in summary['details'] if d.get('absent') == 'YES']
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Tahoma, Arial, sans-serif; direction: rtl; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: right; }}
            th {{ background-color: #4CAF50; color: white; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .summary {{ background-color: #e7f3fe; padding: 15px; border-radius: 5px; margin: 10px 0; }}
            .warning {{ background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 10px 0; }}
            .absent-warning {{ background-color: #dc3545; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; }}
            .oncall {{ background-color: #fff3cd; }}
            .leave {{ background-color: #f8d7da; }}
            .no-checkout {{ background-color: #ffcccc; }}
            .no-checkin {{ background-color: #ffe6cc; }}
            .absent {{ background-color: #8b0000; color: white; }}
        </style>
    </head>
    <body>
        <h2>گزارش حضور و غیاب تیم DBA</h2>
        <p>تاریخ: {jalali_full} ({date_str})</p>
        
        <div class="summary">
            <strong>خلاصه:</strong><br>
            تعداد کل: {summary['total']} نفر<br>
            حاضر (check-in): {summary['checked_in']} نفر<br>
            مرخصی روزانه: {summary['on_leave_full']} نفر<br>
            مرخصی ساعتی: {summary['on_leave_hourly']} نفر<br>
            غیبت: {summary['absent']} نفر<br>
            آنکال: {summary['on_call'] or '-'}<br>
            آنکال هفته قبل (استراحت): {summary['support'] or '-'}
        </div>
    """
    
    # Add warning section for absent people (most critical - at top)
    if absent_people:
        html += f"""
        <div class="absent-warning">
            <strong>غیبت کاری:</strong><br>
            (افرادی که هیچ ورود، خروج یا مرخصی ثبت نکردند)<br><br>
            {', '.join(absent_people)}
        </div>
        """
    
    # Add warning section for people without checkout
    if no_checkout_people:
        html += f"""
        <div class="warning">
            <strong>افرادی که ساعت خروج ثبت نکردند:</strong><br>
            (خروج آنها ساعت ۱۷:۰۰ ثبت شده)<br><br>
            {', '.join(no_checkout_people)}
        </div>
        """
    
    # Add warning section for people without check-in
    if no_checkin_people:
        html += f"""
        <div class="warning" style="background-color: #ffe6cc;">
            <strong>افرادی که ساعت ورود ثبت نکردند:</strong><br>
            (ورود آنها ساعت ۱۰:۰۰ ثبت شده)<br><br>
            {', '.join(no_checkin_people)}
        </div>
        """
    
    html += """
        <table>
            <tr>
                <th>نام</th>
                <th>ورود</th>
                <th>خروج</th>
                <th>ساعت کاری</th>
                <th>ساعت کاری مفید</th>
                <th>BRB (دقیقه)</th>
                <th>Idle (دقیقه)</th>
                <th>Offline (دقیقه)</th>
                <th>ایمیل</th>
                <th>دیسکورد</th>
                <th>ویس (دقیقه)</th>
                <th>مرخصی</th>
                <th>آنکال</th>
            </tr>
    """
    
    for d in sorted(summary['details'], key=lambda x: x['name']):
        row_class = ''
        is_oncall_or_support = d['is_oncall'] == 'YES' or d['is_support'] == 'YES'
        is_no_checkout = d.get('no_checkout') == 'YES'
        is_no_checkin = d.get('no_checkin') == 'YES'
        is_absent = d.get('absent') == 'YES'
        
        if is_absent:
            row_class = 'absent'  # Highest priority - dark red for absence (غیبت)
        elif is_no_checkin:
            row_class = 'no-checkin'  # Highlight people without greeting (different color)
        elif is_no_checkout:
            row_class = 'no-checkout'  # Highlight people without goodbye
        elif is_oncall_or_support:
            row_class = 'oncall'  # Both current and previous on-call get same color
        elif d['leave'] in ['YES', 'HOURLY']:
            row_class = 'leave'
        
        # Format leave column
        leave_display = ''
        if d['leave'] == 'YES':
            leave_display = 'بله'
        elif d['leave'] == 'HOURLY':
            # Use Persian format for hours to avoid RTL display issues
            # Convert 3h10m to "۳ ساعت ۱۰ دقیقه" or shorter
            if d['leave_hours']:
                # Parse hours and minutes from format like "3h10m" or "3h"
                leave_str = d['leave_hours']
                hours = 0
                mins = 0
                if 'h' in leave_str:
                    parts = leave_str.replace('m', '').split('h')
                    hours = int(parts[0]) if parts[0] else 0
                    mins = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                if mins:
                    leave_display = f'ساعتی ({hours}:{mins:02d})'
                else:
                    leave_display = f'ساعتی ({hours}:00)'
            else:
                leave_display = 'ساعتی'
        
        # For on-call people, handle display differently
        # Previous on-call (support): Show effective (9.0 automatic) but rest is -
        # Current on-call on Wednesday: Show effective time (includes +5 bonus) and checkout
        is_oncall = d['is_oncall'] == 'YES'
        is_support = d['is_support'] == 'YES'
        is_oncall_or_support = is_oncall or is_support
        
        if is_support:
            # Previous on-call - effective is automatic 9 hours, rest is -
            display_effective = d['effective']  # Will be 9.0 from auto_effective
            display_brb = '-'
            display_idle = '-'
            display_offline = '-'
            display_work_hours = '-'
            display_check_out = '-'
        elif is_oncall:
            # Current on-call (Wednesday) - show effective time and checkout
            display_effective = d['effective']  # Includes +5 bonus
            display_brb = '-'
            display_idle = '-'
            display_offline = '-'
            display_work_hours = '-'  # Work hours not relevant, effective is what matters
            display_check_out = d['check_out']
        else:
            display_effective = d['effective']
            display_brb = d['brb']
            display_idle = d['idle']
            display_offline = d['offline']
            display_work_hours = d['work_hours']
            display_check_out = d['check_out']
        
        # For Wednesday on-call, show second check-in in the same cell
        display_check_in = d['check_in']
        oncall_notes = d.get('oncall_notes', '')
        if oncall_notes and 'ورود دوم:' in oncall_notes:
            # Extract second check-in time and add to check_in cell
            second_checkin = oncall_notes.replace('ورود دوم:', '').strip()
            if display_check_in:
                display_check_in = f"{d['check_in']}<br>{second_checkin}"
            else:
                display_check_in = second_checkin
        
        html += f"""
            <tr class="{row_class}">
                <td>{d['name']}</td>
                <td>{display_check_in}</td>
                <td>{display_check_out}</td>
                <td>{display_work_hours}</td>
                <td>{display_effective}</td>
                <td>{display_brb}</td>
                <td>{display_idle}</td>
                <td>{display_offline}</td>
                <td>{d['emails']}</td>
                <td>{d['discord']}</td>
                <td>{d['voice']}</td>
                <td>{leave_display}</td>
                <td>{'آنکال' if d['is_oncall'] == 'YES' else ('آنکال قبلی' if d['is_support'] == 'YES' else '')}</td>
            </tr>
        """
        
        # If there are oncall notes (other than second check-in), add them as a subtitle row
        if oncall_notes and 'ورود دوم:' not in oncall_notes:
            html += f"""
            <tr class="{row_class}" style="font-size: 10px;">
                <td colspan="13" style="text-align: left; padding-left: 20px; color: #666;">
                    {oncall_notes}
                </td>
            </tr>
            """
    
    html += """
        </table>
        
        <p style="font-size: 11px; color: #666;">
            این گزارش به صورت خودکار تولید شده است.<br>
            فایل CSV کامل پیوست شده است.
        </p>
    </body>
    </html>
    """
    
    return html


def send_email(subject, body_html, to_emails, cc_emails=None, bcc_emails=None, attachment_path=None):
    """Send email via Exchange Web Services (EWS)"""
    
    account = get_ews_account()
    if not account:
        return False
    
    try:
        # Create message
        m = Message(
            account=account,
            subject=subject,
            body=HTMLBody(body_html),
            to_recipients=[Mailbox(email_address=e) for e in to_emails]
        )
        
        # Add CC recipients
        if cc_emails:
            m.cc_recipients = [Mailbox(email_address=e) for e in cc_emails]
        
        # Add BCC recipients
        if bcc_emails:
            m.bcc_recipients = [Mailbox(email_address=e) for e in bcc_emails]
        
        # Attach file if provided
        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                content = f.read()
            filename = os.path.basename(attachment_path)
            attachment = FileAttachment(name=filename, content=content)
            m.attach(attachment)
        
        # Send
        m.send()
        
        print(f"✓ Email sent to: {', '.join(to_emails)}")
        if cc_emails:
            print(f"  CC: {', '.join(cc_emails)}")
        if bcc_emails:
            print(f"  BCC: {', '.join(bcc_emails)}")
        return True
    
    except Exception as e:
        print(f"ERROR sending email: {e}")
        return False


def send_daily_report(date_str=None, test_mode=True):
    """Send daily attendance report"""
    
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    summary = read_daily_summary(date_str)
    if not summary:
        print(f"No data found for {date_str}")
        return False
    
    subject = f"گزارش حضور DBA - {date_str}"
    body = create_daily_email_body(date_str, summary)
    
    if test_mode:
        recipients = TO_EMAILS_TEST
        cc_emails = CC_EMAILS_TEST
        bcc_emails = BCC_EMAILS_TEST
    else:
        recipients = TO_EMAILS_PROD
        cc_emails = CC_EMAILS_PROD
        bcc_emails = BCC_EMAILS_PROD
    
    # Create date-specific CSV for attachment
    attachment_csv = create_date_specific_csv(date_str)
    if not attachment_csv:
        print(f"Warning: Could not create date-specific CSV, using main file")
        attachment_csv = ATTENDANCE_CSV
    
    return send_email(
        subject=subject,
        body_html=body,
        to_emails=recipients,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        attachment_path=attachment_csv
    )


def send_monthly_report(date_str=None, test_mode=True):
    """Send monthly attendance report - includes BCC to manager"""
    
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    # Get Jalali date for subject
    try:
        jd = jdatetime.date.today()
        jalali_month = jd.strftime('%B %Y')
        subject = f"گزارش ماهیانه DBA - {jalali_month}"
    except:
        subject = f"گزارش ماهیانه DBA - {date_str}"
    
    # For now, reuse daily body - can be customized later
    summary = read_daily_summary(date_str)
    if not summary:
        print(f"No data found for {date_str}")
        return False
    
    body = create_daily_email_body(date_str, summary)
    
    if test_mode:
        recipients = TO_EMAILS_TEST
        cc_emails = CC_EMAILS_TEST
        bcc_emails = BCC_EMAILS_TEST
    else:
        recipients = TO_EMAILS_PROD
        # Monthly report adds manager and account manager to CC
        cc_emails = CC_EMAILS_PROD + CC_EMAILS_MONTHLY
        bcc_emails = BCC_EMAILS_PROD
    
    return send_email(
        subject=subject,
        body_html=body,
        to_emails=recipients,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        attachment_path=ATTENDANCE_CSV
    )


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Send DBA attendance report via email')
    parser.add_argument('--date', help='Date to report (YYYY-MM-DD), default: today')
    parser.add_argument('--test', action='store_true', help='Test mode (exclude amirbahram)')
    parser.add_argument('--prod', action='store_true', help='Production mode (include all recipients)')
    parser.add_argument('--monthly', action='store_true', help='Send monthly report (adds BCC to manager)')
    parser.add_argument('--force', action='store_true', help='Force send even on weekends (Thu/Fri)')
    args = parser.parse_args()
    
    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    test_mode = not args.prod  # Default to test mode
    
    # Check if today is a weekend (Thursday=3, Friday=4 in Iran)
    from datetime import datetime as dt
    report_date = dt.strptime(date_str, '%Y-%m-%d')
    weekday = report_date.weekday()  # Monday=0, Sunday=6
    is_weekend = weekday in [3, 4]  # Thursday=3, Friday=4
    
    if is_weekend and not args.force:
        print(f"⏭️  {date_str} is a weekend (Thu/Fri). Skipping email.")
        print("Use --force to send anyway.")
        sys.exit(0)
    
    if args.monthly:
        print(f"Sending MONTHLY report for {date_str}")
    else:
        print(f"Sending daily report for {date_str}")
    
    print(f"Mode: {'TEST' if test_mode else 'PRODUCTION'}")
    print(f"To: {TO_EMAILS_TEST if test_mode else TO_EMAILS_PROD}")
    if args.monthly and not test_mode:
        print(f"CC: {CC_EMAILS_PROD + CC_EMAILS_MONTHLY}")
    else:
        print(f"CC: {CC_EMAILS_TEST if test_mode else CC_EMAILS_PROD}")
    print("-" * 40)
    
    if args.monthly:
        success = send_monthly_report(date_str, test_mode)
    else:
        success = send_daily_report(date_str, test_mode)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
