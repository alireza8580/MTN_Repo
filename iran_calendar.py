#!/usr/bin/env python3
"""
Iranian working-day calendar.

A day is a working day unless it is a weekend (Thursday/Friday) or an official
public holiday listed in holidays_iran.csv. The CSV is the only thing that needs
maintaining - lunar holidays move every year, so refresh it each Persian new year.
"""
import csv
import os
from datetime import datetime

BASE_DIR = os.environ.get('APP_BASE_DIR', '/root/infrastructure')
SCRIPTS_DIR = os.environ.get('SCRIPTS_DIR', os.path.join(BASE_DIR, 'scripts'))
HOLIDAYS_FILE = os.environ.get(
    'IRAN_HOLIDAYS_FILE', os.path.join(SCRIPTS_DIR, 'holidays_iran.csv')
)

# Iran's weekend: Thursday (Mon=0 .. Thu=3) and Friday
WEEKEND_WEEKDAYS = (3, 4)


def _to_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def load_holidays(path=None):
    """Read holidays_iran.csv -> {'YYYY-MM-DD': name}. Missing file = no holidays."""
    path = path or HOLIDAYS_FILE
    holidays = {}
    if not os.path.exists(path):
        print(f"WARNING: holiday file not found: {path} (holidays will be ignored)")
        return holidays

    with open(path, newline='', encoding='utf-8') as f:
        rows = (line for line in f if not line.lstrip().startswith('#'))
        for row in csv.DictReader(rows):
            gregorian = (row.get('gregorian') or '').strip()
            if not gregorian:
                continue
            holidays[gregorian] = (row.get('name') or 'Public holiday').strip()
    return holidays


def is_weekend(date_str):
    return _to_date(date_str).weekday() in WEEKEND_WEEKDAYS


def is_holiday(date_str, path=None):
    """Return the holiday name for date_str, or None if it is not a holiday."""
    return load_holidays(path).get(date_str)


def non_working_reason(date_str, path=None):
    """Return why date_str is off ('Weekend (Thursday)', a holiday name), else None."""
    if is_weekend(date_str):
        day_name = _to_date(date_str).strftime('%A')
        return f"Weekend ({day_name})"
    return is_holiday(date_str, path)


def is_working_day(date_str, path=None):
    return non_working_reason(date_str, path) is None


if __name__ == '__main__':
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime('%Y-%m-%d')
    reason = non_working_reason(day)
    print(f"{day}: {'WORKING DAY' if reason is None else 'OFF - ' + reason}")
