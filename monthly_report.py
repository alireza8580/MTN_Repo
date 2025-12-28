#!/usr/bin/env python3
"""
Monthly Attendance Aggregator
Generates monthly summary on 24th of each Jalali month
"""
import os
import sys
import csv
from datetime import datetime, timedelta
from collections import defaultdict
import jdatetime

# Import email sender
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from email_sender import send_email, ATTENDANCE_CSV, TO_EMAILS_TEST, TO_EMAILS_PROD


def get_reporting_period_range(jalali_year, jalali_month):
    """
    Get Gregorian date range for reporting period (23rd of prev month to 23rd of this month)
    Note: Report is generated on 24th for period ending on 23rd
    Returns: (start_date, end_date) as datetime objects
    """
    # Start: 23rd of previous month
    if jalali_month == 1:
        start_jalali = jdatetime.date(jalali_year - 1, 12, 23)
    else:
        start_jalali = jdatetime.date(jalali_year, jalali_month - 1, 23)
    
    # End: 23rd of this month
    end_jalali = jdatetime.date(jalali_year, jalali_month, 23)
    
    start_gregorian = start_jalali.togregorian()
    end_gregorian = end_jalali.togregorian()
    
    return start_gregorian, end_gregorian


def get_jalali_month_range(jalali_year, jalali_month):
    """
    Get Gregorian date range for a full Jalali month (1st to last day)
    Returns: (start_date, end_date) as datetime objects
    """
    # First day of the Jalali month
    start_jalali = jdatetime.date(jalali_year, jalali_month, 1)
    start_gregorian = start_jalali.togregorian()
    
    # Last day of the Jalali month
    if jalali_month <= 6:
        days_in_month = 31
    elif jalali_month <= 11:
        days_in_month = 30
    else:
        # Esfand - check leap year
        days_in_month = 30 if jdatetime.date.isleap(jalali_year) else 29
    
    end_jalali = jdatetime.date(jalali_year, jalali_month, days_in_month)
    end_gregorian = end_jalali.togregorian()
    
    return start_gregorian, end_gregorian


def get_previous_jalali_month():
    """Get the previous Jalali month (year, month)"""
    today_jalali = jdatetime.date.today()
    
    if today_jalali.month == 1:
        return today_jalali.year - 1, 12
    else:
        return today_jalali.year, today_jalali.month - 1


def get_jalali_month_name(month):
    """Get Persian name of Jalali month"""
    names = {
        1: 'فروردین',
        2: 'اردیبهشت',
        3: 'خرداد',
        4: 'تیر',
        5: 'مرداد',
        6: 'شهریور',
        7: 'مهر',
        8: 'آبان',
        9: 'آذر',
        10: 'دی',
        11: 'بهمن',
        12: 'اسفند',
    }
    return names.get(month, str(month))


def aggregate_monthly_data(start_date, end_date):
    """
    Aggregate attendance data for a date range
    Returns: dict with per-person monthly stats
    """
    if not os.path.exists(ATTENDANCE_CSV):
        return {}
    
    # EXPECTED_HOURS_PER_DAY: 8 hours is the target for effective work
    EXPECTED_HOURS_PER_DAY = 8
    
    stats = defaultdict(lambda: {
        'work_days': 0,
        'present_days': 0,
        'leave_days': 0,           # Full daily leaves
        'hourly_leave_minutes': 0, # Hourly leaves (separate from daily)
        'oncall_days': 0,
        'support_days': 0,
        'total_work_hours': 0.0,
        'total_effective_minutes': 0,
        'total_brb_minutes': 0,
        'total_idle_minutes': 0,
        'total_offline_minutes': 0,
        'total_voice_minutes': 0,
        'total_emails': 0,
        'total_discord': 0,
        'total_communication': 0,  # Discord + Emails combined
        'weekends': 0,
        'no_checkout_days': 0,
        'no_checkin_days': 0,
        'expected_hours_per_day': EXPECTED_HOURS_PER_DAY,
    })
    
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')
    
    with open(ATTENDANCE_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row['Date']
            
            # Check if date is in range
            if date_str < start_str or date_str > end_str:
                continue
            
            name = row['Name']
            
            # Count work days (non-weekend)
            if row.get('Weekend') != 'YES':
                stats[name]['work_days'] += 1
            else:
                stats[name]['weekends'] += 1
            
            # Present days (has check-in)
            if row.get('CheckIn'):
                stats[name]['present_days'] += 1
            
            # Leave days
            if row.get('Leave') == 'YES':
                stats[name]['leave_days'] += 1
            
            # On-call days
            if row.get('IsOnCall') == 'YES':
                stats[name]['oncall_days'] += 1
            
            # Support days
            if row.get('IsSupport') == 'YES':
                stats[name]['support_days'] += 1
            
            # Work hours
            try:
                stats[name]['total_work_hours'] += float(row.get('WorkHours') or 0)
            except ValueError:
                pass
            
            # BRB minutes
            try:
                stats[name]['total_brb_minutes'] += int(row.get('BRB_Minutes') or 0)
            except ValueError:
                pass
            
            # Idle minutes
            try:
                stats[name]['total_idle_minutes'] += int(row.get('IdleMinutes') or 0)
            except ValueError:
                pass
            
            # Emails
            try:
                email_count = int(row.get('Emails') or 0)
                stats[name]['total_emails'] += email_count
                stats[name]['total_communication'] += email_count
            except ValueError:
                pass
            
            # Discord messages
            try:
                discord_count = int(row.get('Discord') or 0)
                stats[name]['total_discord'] += discord_count
                stats[name]['total_communication'] += discord_count
            except ValueError:
                pass
            
            # Effective hours (column is named EffectiveMinutes but stores hours as decimal)
            try:
                effective_val = row.get('EffectiveMinutes', '').strip()
                if effective_val:
                    stats[name]['total_effective_minutes'] += float(effective_val) * 60  # Convert hours to minutes
            except ValueError:
                pass
            
            # Offline minutes (NEW)
            try:
                stats[name]['total_offline_minutes'] += int(row.get('OfflineMinutes') or 0)
            except ValueError:
                pass
            
            # Voice minutes (NEW)
            try:
                stats[name]['total_voice_minutes'] += int(row.get('Voice') or 0)
            except ValueError:
                pass
            
            # NoCheckout count (NEW)
            if row.get('NoCheckout') == 'YES':
                stats[name]['no_checkout_days'] += 1
            
            # NoCheckin count (NEW)
            if row.get('NoCheckin') == 'YES':
                stats[name]['no_checkin_days'] += 1
            
            # Hourly leave parsing (NEW) - e.g., "2h30m" or "1h" or "30m"
            leave_hours_str = row.get('LeaveHours', '').strip()
            if leave_hours_str and leave_hours_str != '-':
                leave_minutes = 0
                import re
                hours_match = re.search(r'(\d+)h', leave_hours_str)
                mins_match = re.search(r'(\d+)m', leave_hours_str)
                if hours_match:
                    leave_minutes += int(hours_match.group(1)) * 60
                if mins_match:
                    leave_minutes += int(mins_match.group(1))
                stats[name]['hourly_leave_minutes'] += leave_minutes
    
    return dict(stats)


def calculate_performance_grade(effective_hours, expected_hours, idle_pct, attendance_pct):
    """Calculate performance grade based on metrics"""
    if expected_hours == 0:
        return 'N/A', '#888'
    
    effective_ratio = effective_hours / expected_hours
    
    # Grade based on effective hours ratio and attendance
    if effective_ratio >= 0.95 and attendance_pct >= 90 and idle_pct <= 15:
        return 'A', '#4CAF50'  # Excellent - green
    elif effective_ratio >= 0.85 and attendance_pct >= 80:
        return 'B', '#8BC34A'  # Good - light green
    elif effective_ratio >= 0.70 and attendance_pct >= 70:
        return 'C', '#FF9800'  # Needs improvement - orange
    else:
        return 'D', '#F44336'  # Concern - red


def create_monthly_email_body(jalali_year, jalali_month, stats, start_date, end_date):
    """Create HTML email body for monthly report with enhanced formatting"""
    
    EXPECTED_HOURS_PER_DAY = 8  # Target for effective work per day
    
    month_name = get_jalali_month_name(jalali_month)
    prev_month = jalali_month - 1 if jalali_month > 1 else 12
    prev_month_name = get_jalali_month_name(prev_month)
    
    # Convert dates to Jalali for display
    start_jalali = jdatetime.date.fromgregorian(date=start_date)
    end_jalali = jdatetime.date.fromgregorian(date=end_date)
    
    # Calculate aggregate stats for summary cards
    total_people = len(stats)
    avg_effective = sum(s['total_effective_minutes'] for s in stats.values()) / total_people / 60 if total_people > 0 else 0
    avg_attendance = sum(s['present_days'] / s['work_days'] * 100 if s['work_days'] > 0 else 0 for s in stats.values()) / total_people if total_people > 0 else 0
    avg_idle_pct = sum(s['total_idle_minutes'] / (s['total_work_hours'] * 60) * 100 if s['total_work_hours'] > 0 else 0 for s in stats.values()) / total_people if total_people > 0 else 0
    total_voice = sum(s['total_voice_minutes'] for s in stats.values())
    total_communication = sum(s['total_communication'] for s in stats.values())
    total_daily_leaves = sum(s['leave_days'] for s in stats.values())
    total_hourly_leave_hours = sum(s['hourly_leave_minutes'] for s in stats.values()) / 60
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ 
                font-family: 'Segoe UI', Tahoma, Arial, sans-serif; 
                direction: rtl; 
                background-color: #f5f5f5;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                overflow: hidden;
            }}
            .header {{ 
                background: linear-gradient(135deg, #1976D2, #1565C0);
                color: white; 
                padding: 30px; 
                text-align: center;
            }}
            .header h2 {{
                margin: 0 0 10px 0;
                font-size: 24px;
            }}
            .header p {{
                margin: 5px 0;
                opacity: 0.9;
            }}
            
            /* Summary Cards */
            .stats-cards {{
                display: flex;
                justify-content: space-around;
                padding: 20px;
                background: #e3f2fd;
                flex-wrap: wrap;
                gap: 15px;
            }}
            .stat-card {{
                background: white;
                border-radius: 10px;
                padding: 20px;
                min-width: 150px;
                text-align: center;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            }}
            .stat-card .number {{
                font-size: 32px;
                font-weight: bold;
                color: #1976D2;
            }}
            .stat-card .label {{
                font-size: 12px;
                color: #666;
                margin-top: 5px;
            }}
            
            /* Main Table */
            table {{ 
                border-collapse: collapse; 
                width: 100%; 
                margin: 0;
                font-size: 13px;
            }}
            th {{ 
                background-color: #37474F; 
                color: white; 
                padding: 12px 8px;
                font-weight: 600;
                position: sticky;
                top: 0;
            }}
            td {{ 
                border-bottom: 1px solid #e0e0e0; 
                padding: 10px 8px; 
                text-align: center; 
            }}
            tr:hover {{ background-color: #f5f5f5; }}
            
            /* Grade badges */
            .grade {{
                display: inline-block;
                width: 28px;
                height: 28px;
                line-height: 28px;
                border-radius: 50%;
                color: white;
                font-weight: bold;
            }}
            
            /* Progress bars */
            .progress-bar {{
                width: 100%;
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
                overflow: hidden;
            }}
            .progress-fill {{
                height: 100%;
                border-radius: 4px;
            }}
            
            /* Difference colors */
            .positive {{ color: #4CAF50; font-weight: bold; }}
            .negative {{ color: #F44336; font-weight: bold; }}
            
            /* Summary section */
            .summary {{ 
                background: linear-gradient(135deg, #e8f5e9, #c8e6c9);
                padding: 25px; 
                margin: 20px;
                border-radius: 10px;
            }}
            .summary h3 {{
                margin: 0 0 15px 0;
                color: #2E7D32;
            }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
            }}
            .summary-item {{
                background: white;
                padding: 15px;
                border-radius: 8px;
            }}
            .summary-item .value {{
                font-size: 24px;
                font-weight: bold;
                color: #333;
            }}
            .summary-item .label {{
                font-size: 12px;
                color: #666;
            }}
            
            .footer {{
                text-align: center;
                padding: 20px;
                font-size: 11px;
                color: #999;
                border-top: 1px solid #eee;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>گزارش ماهانه حضور و غیاب تیم DBA</h2>
                <p>از ۲۴ {prev_month_name} تا ۲۴ {month_name} {jalali_year}</p>
                <p style="font-size: 12px; opacity: 0.8;">
                    {start_jalali.strftime('%Y/%m/%d')} تا {end_jalali.strftime('%Y/%m/%d')}
                    ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})
                </p>
            </div>
            
            <!-- Summary Cards -->
            <div class="stats-cards">
                <div class="stat-card">
                    <div class="number">{total_people}</div>
                    <div class="label">تعداد نفرات</div>
                </div>
                <div class="stat-card">
                    <div class="number">{avg_attendance:.0f}%</div>
                    <div class="label">میانگین حضور</div>
                </div>
                <div class="stat-card">
                    <div class="number">{avg_effective:.1f}h</div>
                    <div class="label">میانگین ساعت مفید</div>
                </div>
                <div class="stat-card">
                    <div class="number">{avg_idle_pct:.0f}%</div>
                    <div class="label">میانگین Idle</div>
                </div>
                <div class="stat-card">
                    <div class="number">{total_voice // 60}h</div>
                    <div class="label">جمع Voice</div>
                </div>
                <div class="stat-card">
                    <div class="number">{total_communication}</div>
                    <div class="label">جمع پیام (Discord+Email)</div>
                </div>
                <div class="stat-card">
                    <div class="number">{total_daily_leaves}</div>
                    <div class="label">روز-نفر مرخصی کامل</div>
                </div>
                <div class="stat-card">
                    <div class="number">{total_hourly_leave_hours:.1f}h</div>
                    <div class="label">جمع مرخصی ساعتی</div>
                </div>
            </div>
            
            <table>
                <tr>
                    <th>نام</th>
                    <th>رتبه</th>
                    <th>روز کاری</th>
                    <th>حضور</th>
                    <th>مرخصی روزانه</th>
                    <th>مرخصی ساعتی</th>
                    <th>آنکال</th>
                    <th>ساعت مفید</th>
                    <th>انتظار ({EXPECTED_HOURS_PER_DAY}h/day)</th>
                    <th>اختلاف</th>
                    <th>Idle%</th>
                    <th>پیام‌ها</th>
                    <th>Voice</th>
                </tr>
    """
    
    total_present = 0
    total_leave = 0
    total_oncall = 0
    total_expected = 0
    total_effective = 0
    
    for name in sorted(stats.keys()):
        s = stats[name]
        total_present += s['present_days']
        total_leave += s['leave_days']
        total_oncall += s['oncall_days']
        
        # Calculate attendance percentage
        if s['work_days'] > 0:
            attendance_pct = (s['present_days'] / s['work_days']) * 100
        else:
            attendance_pct = 0
        
        # Calculate expected and effective hours
        expected_hours = s['work_days'] * EXPECTED_HOURS_PER_DAY  # 8 hours per work day
        effective_hours = s['total_effective_minutes'] / 60
        difference = effective_hours - expected_hours
        
        total_expected += expected_hours
        total_effective += effective_hours
        
        # Calculate idle percentage
        if s['total_work_hours'] > 0:
            idle_pct = (s['total_idle_minutes'] / (s['total_work_hours'] * 60)) * 100
        else:
            idle_pct = 0
        
        # Get performance grade
        grade, grade_color = calculate_performance_grade(effective_hours, expected_hours, idle_pct, attendance_pct)
        
        # Format hourly leave
        hourly_leave_hours = s['hourly_leave_minutes'] // 60
        hourly_leave_mins = s['hourly_leave_minutes'] % 60
        hourly_leave_str = f"{hourly_leave_hours}h{hourly_leave_mins}m" if s['hourly_leave_minutes'] > 0 else "-"
        
        # Format difference with color class
        diff_class = "positive" if difference >= 0 else "negative"
        
        # Progress bar for attendance
        attendance_bar_color = "#4CAF50" if attendance_pct >= 80 else ("#FF9800" if attendance_pct >= 60 else "#F44336")
        
        # Idle bar color
        idle_bar_color = "#4CAF50" if idle_pct <= 15 else ("#FF9800" if idle_pct <= 30 else "#F44336")
        
        # Voice time in hours
        voice_hours = s['total_voice_minutes'] / 60
        
        # Communication breakdown (Discord + Email)
        comm_str = f"{s['total_discord']}D+{s['total_emails']}E"
        
        html += f"""
            <tr>
                <td style="text-align: right; font-weight: 500;">{name}</td>
                <td><span class="grade" style="background-color: {grade_color};">{grade}</span></td>
                <td>{s['work_days']}</td>
                <td>
                    {s['present_days']} ({attendance_pct:.0f}%)
                    <div class="progress-bar"><div class="progress-fill" style="width: {min(attendance_pct, 100)}%; background: {attendance_bar_color};"></div></div>
                </td>
                <td>{s['leave_days']}</td>
                <td>{hourly_leave_str}</td>
                <td>{s['oncall_days']}</td>
                <td>{effective_hours:.1f}h</td>
                <td>{expected_hours:.0f}h</td>
                <td class="{diff_class}">{difference:+.1f}h</td>
                <td>
                    {idle_pct:.0f}%
                    <div class="progress-bar"><div class="progress-fill" style="width: {min(idle_pct, 100)}%; background: {idle_bar_color};"></div></div>
                </td>
                <td title="Discord+Email">{comm_str}</td>
                <td>{voice_hours:.1f}h</td>
            </tr>
        """
    
    # Calculate team totals
    team_effective_pct = (total_effective / total_expected * 100) if total_expected > 0 else 0
    
    html += f"""
        </table>
        
        <div class="summary">
            <h3>خلاصه عملکرد تیم</h3>
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="value">{total_present}</div>
                    <div class="label">مجموع روز-نفر حضور</div>
                </div>
                <div class="summary-item">
                    <div class="value">{total_leave}</div>
                    <div class="label">مجموع روز-نفر مرخصی</div>
                </div>
                <div class="summary-item">
                    <div class="value">{total_oncall}</div>
                    <div class="label">مجموع روز-نفر آنکال</div>
                </div>
                <div class="summary-item">
                    <div class="value">{total_effective:.0f}h</div>
                    <div class="label">ساعات مفید کلی</div>
                </div>
                <div class="summary-item">
                    <div class="value">{total_expected:.0f}h</div>
                    <div class="label">ساعات مورد انتظار</div>
                </div>
                <div class="summary-item">
                    <div class="value" style="color: {'#4CAF50' if total_effective >= total_expected else '#F44336'}">
                        {(total_effective - total_expected):+.0f}h
                    </div>
                    <div class="label">اختلاف کلی</div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            این گزارش به صورت خودکار در تاریخ ۲۴ هر ماه شمسی تولید می‌شود.<br>
            فایل CSV کامل پیوست شده است.
        </div>
        </div>
    </body>
    </html>
    """
    
    return html


def export_monthly_csv(stats, jalali_year, jalali_month, start_date, end_date):
    """Export monthly summary to separate CSV file"""
    
    month_name = get_jalali_month_name(jalali_month)
    filename = f'/root/infrastructure/attendance_reports/monthly_{jalali_year}_{jalali_month:02d}_{month_name}.csv'
    
    EXPECTED_HOURS_PER_DAY = 8  # Target for effective work per day
    
    fieldnames = [
        'Name', 'WorkDays', 'PresentDays', 'AttendancePercent', 
        'LeaveDays', 'HourlyLeaveMinutes', 'OnCallDays', 'SupportDays',
        'TotalWorkHours', 'TotalEffectiveMinutes', 'ExpectedHours', 'DifferenceHours',
        'TotalBRB', 'TotalIdle', 'TotalOffline', 'TotalVoice',
        'NoCheckinDays', 'NoCheckoutDays',
        'TotalEmails', 'TotalDiscord', 'TotalCommunication'
    ]
    
    with open(filename, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for name in sorted(stats.keys()):
            s = stats[name]
            attendance_pct = (s['present_days'] / s['work_days'] * 100) if s['work_days'] > 0 else 0
            expected_hours = s['work_days'] * EXPECTED_HOURS_PER_DAY  # 8 hours per day
            effective_hours = s['total_effective_minutes'] / 60
            difference = effective_hours - expected_hours
            
            writer.writerow({
                'Name': name,
                'WorkDays': s['work_days'],
                'PresentDays': s['present_days'],
                'AttendancePercent': f'{attendance_pct:.1f}%',
                'LeaveDays': s['leave_days'],
                'HourlyLeaveMinutes': s['hourly_leave_minutes'],
                'OnCallDays': s['oncall_days'],
                'SupportDays': s['support_days'],
                'TotalWorkHours': f'{s["total_work_hours"]:.1f}',
                'TotalEffectiveMinutes': round(s['total_effective_minutes']),
                'ExpectedHours': expected_hours,
                'DifferenceHours': f'{difference:+.1f}',
                'TotalBRB': s['total_brb_minutes'],
                'TotalIdle': s['total_idle_minutes'],
                'TotalOffline': s['total_offline_minutes'],
                'TotalVoice': s['total_voice_minutes'],
                'NoCheckinDays': s['no_checkin_days'],
                'NoCheckoutDays': s['no_checkout_days'],
                'TotalEmails': s['total_emails'],
                'TotalDiscord': s['total_discord'],
                'TotalCommunication': s['total_communication'],
            })
    
    print(f"✓ Monthly CSV exported: {filename}")
    return filename


def send_monthly_report(jalali_year=None, jalali_month=None, test_mode=True):
    """Generate and send monthly report for period 24th prev month to 24th this month"""
    
    # Default to current month (report covers 24th prev to 24th current)
    if jalali_year is None or jalali_month is None:
        today = jdatetime.date.today()
        jalali_year = today.year
        jalali_month = today.month
    
    month_name = get_jalali_month_name(jalali_month)
    prev_month = jalali_month - 1 if jalali_month > 1 else 12
    prev_month_name = get_jalali_month_name(prev_month)
    
    print(f"Generating report for: 24 {prev_month_name} to 24 {month_name} {jalali_year}")
    
    # Get date range (24th to 24th)
    start_date, end_date = get_reporting_period_range(jalali_year, jalali_month)
    print(f"Gregorian range: {start_date} to {end_date}")
    
    # Aggregate data
    stats = aggregate_monthly_data(start_date, end_date)
    if not stats:
        print("No data found for this period")
        return False
    
    print(f"Found data for {len(stats)} people")
    
    # Export monthly CSV
    monthly_csv = export_monthly_csv(stats, jalali_year, jalali_month, start_date, end_date)
    
    # Create email
    subject = f"گزارش ماهانه DBA - {prev_month_name} ۲۴ تا {month_name} ۲۴ - {jalali_year}"
    body = create_monthly_email_body(jalali_year, jalali_month, stats, start_date, end_date)
    
    recipients = TO_EMAILS_TEST if test_mode else TO_EMAILS_PROD
    
    return send_email(
        subject=subject,
        body_html=body,
        to_emails=recipients,
        attachment_path=monthly_csv
    )


def is_24th_jalali():
    """Check if today is 24th of Jalali month"""
    today = jdatetime.date.today()
    return today.day == 24


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate monthly DBA attendance report')
    parser.add_argument('--year', type=int, help='Jalali year (e.g., 1403)')
    parser.add_argument('--month', type=int, help='Jalali month (1-12)')
    parser.add_argument('--test', action='store_true', help='Test mode')
    parser.add_argument('--prod', action='store_true', help='Production mode')
    parser.add_argument('--check-24th', action='store_true', help='Only run if today is 24th')
    args = parser.parse_args()
    
    # Check if should run today
    if args.check_24th and not is_24th_jalali():
        today = jdatetime.date.today()
        print(f"Today is {today.day}th, not 24th. Skipping.")
        sys.exit(0)
    
    jalali_year = args.year
    jalali_month = args.month
    test_mode = not args.prod
    
    print("=" * 50)
    print("Monthly Attendance Report Generator")
    print("=" * 50)
    
    success = send_monthly_report(jalali_year, jalali_month, test_mode)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
