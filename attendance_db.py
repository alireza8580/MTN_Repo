#!/usr/bin/env python3
"""
Attendance SQLite Database Manager
Stores daily attendance data in a SQLite database for persistence and historical analysis.
"""
import sqlite3
import csv
import os
from datetime import datetime

# Database location
DB_PATH = os.environ.get('ATTENDANCE_DB', '/root/infrastructure/attendance_reports/attendance.db')
CSV_PATH = os.environ.get('ATTENDANCE_CSV', '/root/infrastructure/attendance_reports/daily_attendance.csv')

# Schema version for future migrations
SCHEMA_VERSION = 1

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    check_in TEXT,
    check_out TEXT,
    work_hours REAL,
    brb_minutes TEXT,
    brb_open TEXT,
    emails INTEGER,
    discord INTEGER,
    voice INTEGER,
    effective_minutes REAL,
    leave TEXT,
    leave_hours TEXT,
    remote_work TEXT,
    idle_minutes INTEGER,
    idle_percent TEXT,
    offline_minutes INTEGER,
    offline_percent TEXT,
    weekend TEXT,
    is_oncall TEXT,
    is_support TEXT,
    oncall_notes TEXT,
    is_holiday TEXT,
    holiday_support TEXT,
    no_checkout TEXT,
    no_checkin TEXT,
    absent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, name)
);

CREATE INDEX IF NOT EXISTS idx_date ON attendance(date);
CREATE INDEX IF NOT EXISTS idx_name ON attendance(name);
CREATE INDEX IF NOT EXISTS idx_date_name ON attendance(date, name);
"""

CREATE_META_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection():
    """Get SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.executescript(CREATE_TABLE_SQL)
    cursor.executescript(CREATE_META_TABLE_SQL)
    
    # Set schema version
    cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", 
                   ('schema_version', str(SCHEMA_VERSION)))
    
    conn.commit()
    conn.close()
    print(f"✓ Database initialized: {DB_PATH}")


def import_csv(csv_path=None, replace=False):
    """
    Import CSV data into database.
    
    Args:
        csv_path: Path to CSV file (defaults to ATTENDANCE_CSV)
        replace: If True, replace existing records. If False, skip duplicates.
    """
    if csv_path is None:
        csv_path = CSV_PATH
    
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        return 0
    
    conn = get_connection()
    cursor = conn.cursor()
    
    imported = 0
    skipped = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Parse numeric fields
                work_hours = float(row['WorkHours']) if row.get('WorkHours') else None
                effective = float(row['EffectiveMinutes']) if row.get('EffectiveMinutes') else None
                emails = int(row['Emails']) if row.get('Emails') else None
                discord = int(row['Discord']) if row.get('Discord') else None
                voice = int(row['Voice']) if row.get('Voice') else None
                idle = int(row['IdleMinutes']) if row.get('IdleMinutes') else None
                offline = int(row['OfflineMinutes']) if row.get('OfflineMinutes') else None
                
                if replace:
                    sql = """
                    INSERT OR REPLACE INTO attendance (
                        date, name, check_in, check_out, work_hours, brb_minutes, brb_open,
                        emails, discord, voice, effective_minutes, leave, leave_hours,
                        remote_work, idle_minutes, idle_percent, offline_minutes, offline_percent,
                        weekend, is_oncall, is_support, oncall_notes, is_holiday, holiday_support,
                        no_checkout, no_checkin, absent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                else:
                    sql = """
                    INSERT OR IGNORE INTO attendance (
                        date, name, check_in, check_out, work_hours, brb_minutes, brb_open,
                        emails, discord, voice, effective_minutes, leave, leave_hours,
                        remote_work, idle_minutes, idle_percent, offline_minutes, offline_percent,
                        weekend, is_oncall, is_support, oncall_notes, is_holiday, holiday_support,
                        no_checkout, no_checkin, absent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                
                cursor.execute(sql, (
                    row['Date'],
                    row['Name'],
                    row.get('CheckIn', ''),
                    row.get('CheckOut', ''),
                    work_hours,
                    row.get('BRB_Minutes', ''),
                    row.get('BRB_Open', ''),
                    emails,
                    discord,
                    voice,
                    effective,
                    row.get('Leave', ''),
                    row.get('LeaveHours', ''),
                    row.get('RemoteWork', ''),
                    idle,
                    row.get('IdlePercent', ''),
                    offline,
                    row.get('OfflinePercent', ''),
                    row.get('Weekend', ''),
                    row.get('IsOnCall', ''),
                    row.get('IsSupport', ''),
                    row.get('OnCallNotes', ''),
                    row.get('IsHoliday', ''),
                    row.get('HolidaySupport', ''),
                    row.get('NoCheckout', ''),
                    row.get('NoCheckin', ''),
                    row.get('Absent', ''),
                ))
                
                if cursor.rowcount > 0:
                    imported += 1
                else:
                    skipped += 1
                    
            except Exception as e:
                print(f"ERROR importing row: {row} - {e}")
    
    conn.commit()
    conn.close()
    
    print(f"✓ Imported {imported} records, skipped {skipped} duplicates")
    return imported


def get_date_range():
    """Get the date range of records in the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as count FROM attendance")
    row = cursor.fetchone()
    conn.close()
    
    return {
        'min_date': row['min_date'],
        'max_date': row['max_date'],
        'count': row['count']
    }


def get_by_date(date_str):
    """Get all attendance records for a specific date."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM attendance WHERE date = ? ORDER BY name", (date_str,))
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_by_name(name, start_date=None, end_date=None):
    """Get attendance records for a specific person, optionally within a date range."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if start_date and end_date:
        cursor.execute(
            "SELECT * FROM attendance WHERE name = ? AND date BETWEEN ? AND ? ORDER BY date",
            (name, start_date, end_date)
        )
    else:
        cursor.execute("SELECT * FROM attendance WHERE name = ? ORDER BY date", (name,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_summary_by_name(name, start_date=None, end_date=None):
    """Get summary statistics for a person."""
    conn = get_connection()
    cursor = conn.cursor()
    
    base_query = """
    SELECT 
        name,
        COUNT(*) as total_days,
        SUM(CASE WHEN check_in != '' THEN 1 ELSE 0 END) as days_present,
        SUM(CASE WHEN leave = 'YES' THEN 1 ELSE 0 END) as full_leave_days,
        SUM(CASE WHEN leave = 'HOURLY' THEN 1 ELSE 0 END) as hourly_leave_days,
        SUM(CASE WHEN absent = 'YES' THEN 1 ELSE 0 END) as absent_days,
        AVG(effective_minutes) as avg_effective_hours,
        SUM(emails) as total_emails,
        SUM(discord) as total_discord,
        SUM(voice) as total_voice_minutes
    FROM attendance
    WHERE name = ?
    """
    
    if start_date and end_date:
        cursor.execute(base_query + " AND date BETWEEN ? AND ?", (name, start_date, end_date))
    else:
        cursor.execute(base_query, (name,))
    
    row = cursor.fetchone()
    conn.close()
    
    return dict(row) if row else None


def get_absent_count(start_date=None, end_date=None):
    """Get total absent days by person."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if start_date and end_date:
        cursor.execute("""
            SELECT name, COUNT(*) as absent_days
            FROM attendance
            WHERE absent = 'YES' AND date BETWEEN ? AND ?
            GROUP BY name
            ORDER BY absent_days DESC
        """, (start_date, end_date))
    else:
        cursor.execute("""
            SELECT name, COUNT(*) as absent_days
            FROM attendance
            WHERE absent = 'YES'
            GROUP BY name
            ORDER BY absent_days DESC
        """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def stats():
    """Print database statistics."""
    info = get_date_range()
    print(f"Database: {DB_PATH}")
    print(f"Records: {info['count']}")
    print(f"Date range: {info['min_date']} to {info['max_date']}")
    
    # Absent summary
    absent = get_absent_count()
    if absent:
        print(f"\nAbsent days by person:")
        for row in absent:
            print(f"  {row['name']}: {row['absent_days']} days")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Attendance Database Manager')
    parser.add_argument('--init', action='store_true', help='Initialize database')
    parser.add_argument('--import', dest='import_csv', action='store_true', help='Import CSV to database')
    parser.add_argument('--replace', action='store_true', help='Replace existing records during import')
    parser.add_argument('--csv', type=str, help='Path to CSV file')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')
    parser.add_argument('--date', type=str, help='Query by date (YYYY-MM-DD)')
    parser.add_argument('--name', type=str, help='Query by name')
    
    args = parser.parse_args()
    
    if args.init:
        init_db()
    
    if args.import_csv:
        init_db()  # Ensure DB exists
        import_csv(args.csv, replace=args.replace)
    
    if args.stats:
        stats()
    
    if args.date:
        records = get_by_date(args.date)
        for r in records:
            print(f"{r['name']}: check_in={r['check_in']}, check_out={r['check_out']}, effective={r['effective_minutes']}")
    
    if args.name:
        summary = get_summary_by_name(args.name)
        if summary:
            print(f"Summary for {args.name}:")
            print(f"  Total days: {summary['total_days']}")
            print(f"  Present: {summary['days_present']}")
            print(f"  Full leave: {summary['full_leave_days']}")
            print(f"  Hourly leave: {summary['hourly_leave_days']}")
            print(f"  Absent: {summary['absent_days']}")
            print(f"  Avg effective hours: {summary['avg_effective_hours']:.1f}" if summary['avg_effective_hours'] else "")
