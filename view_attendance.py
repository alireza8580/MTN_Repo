#!/usr/bin/env python3
"""
View CSV attendance report in a formatted table
Usage: ./view_attendance.py [date]
"""
import csv
import sys

CSV_FILE = '/root/infrastructure/attendance_reports/daily_attendance.csv'

def main():
    date_filter = sys.argv[1] if len(sys.argv) > 1 else None
    
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if date_filter:
        rows = [r for r in rows if r['Date'] == date_filter]
    
    if not rows:
        print(f"No data found" + (f" for {date_filter}" if date_filter else ""))
        return
    
    # Print header
    print(f"{'Date':<12} {'Name':<22} {'In':>6} {'Out':>6} {'Work':>6} {'BRB':>5} {'BO':>3} {'Em':>3} {'Dc':>3} {'Lv':>3}")
    print("-" * 82)
    
    current_date = None
    for r in rows:
        date = r['Date']
        if date != current_date:
            if current_date:
                print("-" * 82)
            current_date = date
        
        name = r['Name'][:21]
        check_in = r['CheckIn'] or '-'
        check_out = r['CheckOut'] or '-'
        work = r['WorkHours'] or '-'
        brb = r['BRB_Minutes'] or '-'
        brb_open = 'Y' if r['BRB_Open'] == 'YES' else '-'
        emails = r['Emails'] or '-'
        discord = r['Discord'] or '-'
        leave = 'Y' if r['Leave'] == 'YES' else '-'
        
        print(f"{date:<12} {name:<22} {check_in:>6} {check_out:>6} {work:>6} {brb:>5} {brb_open:>3} {emails:>3} {discord:>3} {leave:>3}")

if __name__ == '__main__':
    main()
