#!/usr/bin/env python3
"""
Leave Request Parser
Parses complex leave requests and extracts actual dates

Examples handled:
1. "5-6-7-8-9-12-13-16 khordad" -> multiple specific dates
2. "morakhasi mikhastam ta akhare time" -> from today until Wednesday
3. "۳۰ و ۳۱ اردیبهشت مرخصی" -> specific Persian dates
4. "2 saat morakhasi" -> hourly leave (recorded as partial)
5. "se shanbe va 4 shanbe" -> Tuesday and Wednesday of current week
"""

import re
from datetime import datetime, timedelta
import jdatetime

# Persian month names to numbers
PERSIAN_MONTHS = {
    'فروردین': 1, 'farvardin': 1,
    'اردیبهشت': 2, 'ordibehesht': 2,
    'خرداد': 3, 'khordad': 3,
    'تیر': 4, 'tir': 4,
    'مرداد': 5, 'mordad': 5,
    'شهریور': 6, 'shahrivar': 6,
    'مهر': 7, 'mehr': 7,
    'آبان': 8, 'aban': 8,
    'آذر': 9, 'اذر': 9, 'azar': 9,  # Added "اذر" without dots
    'دی': 10, 'dey': 10, 'di': 10,
    'بهمن': 11, 'bahman': 11,
    'اسفند': 12, 'esfand': 12,
}

# Group month variants for regex matching
MONTH_VARIANTS = {
    1: ['فروردین', 'farvardin'],
    2: ['اردیبهشت', 'ordibehesht'],
    3: ['خرداد', 'khordad'],
    4: ['تیر', 'tir'],
    5: ['مرداد', 'mordad'],
    6: ['شهریور', 'shahrivar'],
    7: ['مهر', 'mehr'],
    8: ['آبان', 'aban'],
    9: ['آذر', 'اذر', 'azar'],  # Multiple Persian variants
    10: ['دی', 'dey', 'di'],
    11: ['بهمن', 'bahman'],
    12: ['اسفند', 'esfand'],
}

# Persian day names to weekday numbers (Saturday=0 in Iran, but we use Python's Monday=0)
# We calculate based on week context
PERSIAN_DAYS = {
    'شنبه': 'saturday', 'shanbe': 'saturday',
    'یکشنبه': 'sunday', '1shanbe': 'sunday', 'yekshanbe': 'sunday',
    'دوشنبه': 'monday', '2shanbe': 'monday', 'doshanbe': 'monday',
    'سه‌شنبه': 'tuesday', 'سه شنبه': 'tuesday', '3shanbe': 'tuesday', 
    'seshanbe': 'tuesday', 'se shanbe': 'tuesday',
    'چهارشنبه': 'wednesday', 'چهار شنبه': 'wednesday', '4shanbe': 'wednesday',
    '4 shanbe': 'wednesday', 'chaharshanbe': 'wednesday',
    'پنجشنبه': 'thursday', '5shanbe': 'thursday', 'panjshanbe': 'thursday',
    'جمعه': 'friday', 'jome': 'friday',
}

DAY_TO_WEEKDAY = {
    'saturday': 5,
    'sunday': 6,
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
}


def persian_to_gregorian(year, month, day):
    """Convert Persian date to Gregorian"""
    try:
        # If year is 2-digit, add 1400
        if year < 100:
            year = 1400 + year
        elif year < 1000:
            year = 1400  # Default to 1404 era
        
        jd = jdatetime.date(year, month, day)
        gd = jd.togregorian()
        return gd.strftime('%Y-%m-%d')
    except Exception as e:
        return None


def get_weekday_date(weekday_name, reference_date):
    """Get the date of a weekday relative to reference date (same or next week)"""
    if weekday_name not in DAY_TO_WEEKDAY:
        return None
    
    target_weekday = DAY_TO_WEEKDAY[weekday_name]
    ref = datetime.strptime(reference_date, '%Y-%m-%d')
    
    # Find the next occurrence of this weekday
    days_ahead = target_weekday - ref.weekday()
    if days_ahead < 0:  # Target day already happened this week
        days_ahead += 7
    
    target = ref + timedelta(days=days_ahead)
    return target.strftime('%Y-%m-%d')


def parse_leave_duration(content):
    """Parse hourly leave duration from message"""
    content_lower = content.lower()
    
    # Patterns for hourly leave
    patterns = [
        r'(\d+)\s*saat\s*morakhasi',
        r'(\d+)\s*ساعت\s*مرخصی',
        r'morakhasi\s*(\d+)\s*saat',
    ]
    
    for p in patterns:
        match = re.search(p, content_lower)
        if match:
            return int(match.group(1))
    
    return None


def extract_dates_from_number_list(content, reference_date):
    """Extract dates from patterns like '18 اذر' or '19 اذر تا 28 آذر'"""
    
    # Convert Persian numerals to Arabic
    persian_nums = '۰۱۲۳۴۵۶۷۸۹'
    content_converted = content
    for i, p in enumerate(persian_nums):
        content_converted = content_converted.replace(p, str(i))
    
    content_lower = content_converted.lower()
    dates = []
    
    # Determine year from reference date
    ref = datetime.strptime(reference_date, '%Y-%m-%d')
    jref = jdatetime.date.fromgregorian(date=ref)
    
    # For each month number, check all variants
    for month_num, variants in MONTH_VARIANTS.items():
        # Build regex pattern for all variants of this month
        month_pattern = '(?:' + '|'.join(re.escape(v.lower()) for v in variants) + ')'
        
        # Check if any variant exists in content
        if not re.search(month_pattern, content_lower):
            continue
        
        # Use reference year, or next year if month is before current month
        year = jref.year
        if month_num < jref.month:
            year += 1
        
        # Pattern 1: "number month" like "18 اذر"
        pattern1 = r'(\d+)\s*' + month_pattern
        for match in re.finditer(pattern1, content_lower):
            day = int(match.group(1))
            if 1 <= day <= 31:
                gdate = persian_to_gregorian(year, month_num, day)
                if gdate:
                    dates.append(gdate)
        
        # Pattern 2: Range like "19 اذر تا 28 آذر" or "19 اذر تا 28-29-30 آذر"
        # Match: number + month + anything + تا + anything + numbers with separators + month
        # The end can be multiple numbers like "28-29-30"
        range_pattern = r'(\d+)\s*' + month_pattern + r'[^\d]*تا[^\d]*([\d\-\s]+)\s*' + month_pattern
        for match in re.finditer(range_pattern, content_lower):
            start_day = int(match.group(1))
            # End could be "28" or "28-29-30" - extract all numbers
            end_str = match.group(2)
            end_numbers = [int(n) for n in re.findall(r'\d+', end_str)]
            if end_numbers:
                # For range, use highest number as end
                end_day = max(end_numbers)
                if 1 <= start_day <= 31 and 1 <= end_day <= 31 and start_day <= end_day:
                    for day in range(start_day, end_day + 1):
                        gdate = persian_to_gregorian(year, month_num, day)
                        if gdate:
                            dates.append(gdate)
                        dates.append(gdate)
    
    return list(set(dates))


def extract_weekday_dates(content, reference_date):
    """Extract dates from weekday mentions"""
    content_lower = content.lower()
    dates = []
    
    for persian_day, english_day in PERSIAN_DAYS.items():
        if persian_day.lower() in content_lower:
            date = get_weekday_date(english_day, reference_date)
            if date:
                dates.append(date)
    
    return list(set(dates))


def extract_persian_dates(content, reference_date):
    """Extract dates from Persian format like ۳۰ و ۳۱ اردیبهشت"""
    # Convert Persian numerals
    persian_nums = '۰۱۲۳۴۵۶۷۸۹'
    content_converted = content
    for i, p in enumerate(persian_nums):
        content_converted = content_converted.replace(p, str(i))
    
    dates = []
    
    # Pattern: number + month name
    for month_name, month_num in PERSIAN_MONTHS.items():
        if month_name.lower() in content.lower() or month_name in content:
            # Find numbers before month name
            pattern = r'(\d+)[^\d]*' + re.escape(month_name)
            matches = re.findall(pattern, content_converted, re.IGNORECASE)
            
            if not matches:
                # Try finding all numbers near the month
                numbers = re.findall(r'\d+', content_converted)
                for n in numbers:
                    day = int(n)
                    if 1 <= day <= 31:
                        matches.append(str(day))
            
            ref = datetime.strptime(reference_date, '%Y-%m-%d')
            jref = jdatetime.date.fromgregorian(date=ref)
            year = jref.year
            
            for m in matches:
                day = int(m)
                if 1 <= day <= 31:
                    gdate = persian_to_gregorian(year, month_num, day)
                    if gdate:
                        dates.append(gdate)
    
    return dates


def parse_until_end_of_week(content, reference_date):
    """Parse 'ta akhare time' (until end of week) - means until Wednesday"""
    content_lower = content.lower()
    
    if 'ta akhar' in content_lower or 'تا آخر' in content_lower:
        # From reference date until Wednesday
        ref = datetime.strptime(reference_date, '%Y-%m-%d')
        dates = []
        
        # Wednesday is weekday 2
        current = ref
        while current.weekday() <= 2:  # Until Wednesday
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        # Make sure we include at least the reference date
        if not dates:
            dates = [reference_date]
        
        return dates
    
    return []


def parse_leave_request(content, message_date):
    """
    Main function to parse a leave request message
    Returns: {
        'dates': [list of YYYY-MM-DD dates],
        'hours': optional hours if hourly leave,
        'type': 'full_day' | 'hourly' | 'multi_day',
        'raw': original content
    }
    """
    result = {
        'dates': [],
        'hours': None,
        'type': 'full_day',
        'raw': content[:200]
    }
    
    # Check for hourly leave first
    hours = parse_leave_duration(content)
    if hours:
        result['hours'] = hours
        result['type'] = 'hourly'
        result['dates'] = [message_date]
        return result
    
    # Try extracting number lists with months
    dates = extract_dates_from_number_list(content, message_date)
    if dates:
        result['dates'] = dates
        result['type'] = 'multi_day' if len(dates) > 1 else 'full_day'
        return result
    
    # Try extracting Persian dates
    dates = extract_persian_dates(content, message_date)
    if dates:
        result['dates'] = dates
        result['type'] = 'multi_day' if len(dates) > 1 else 'full_day'
        return result
    
    # Try extracting weekday mentions
    dates = extract_weekday_dates(content, message_date)
    if dates:
        result['dates'] = dates
        result['type'] = 'multi_day' if len(dates) > 1 else 'full_day'
        return result
    
    # Check for "until end of week"
    dates = parse_until_end_of_week(content, message_date)
    if dates:
        result['dates'] = dates
        result['type'] = 'multi_day'
        return result
    
    # Default: just the message date (emrooz/today)
    if 'emrooz' in content.lower() or 'امروز' in content or 'today' in content.lower():
        result['dates'] = [message_date]
        return result
    
    # If no specific dates found, assume it's for the message date
    result['dates'] = [message_date]
    return result


# === TEST ===
if __name__ == '__main__':
    test_cases = [
        ("5-6-7-8-9-12-13-16 khordad", "2025-05-20"),
        ("۳۰ و ۳۱ اردیبهشت مرخصی", "2025-05-15"),
        ("morakhasi mikhastam ta akhare time", "2025-12-01"),  # Monday Dec 1
        ("2 saat morakhasi mikham", "2025-12-03"),
        ("man emrooz morakhasi basham", "2025-09-02"),
        ("se shanbe va 4 shanbe morakhasi", "2025-08-30"),
        ("man shanbe ro morakhasi begiram", "2025-10-16"),
    ]
    
    for content, date in test_cases:
        result = parse_leave_request(content, date)
        print(f"\nInput: {content}")
        print(f"  Date: {date}")
        print(f"  Result: {result}")
