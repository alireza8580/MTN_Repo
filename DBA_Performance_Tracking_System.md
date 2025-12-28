# DBA Team Performance Tracking System

## Executive Summary

This document describes the automated performance tracking system implemented for the DBA team at MTN Irancell. The system provides objective metrics for evaluating team productivity and attendance through Discord activity monitoring, email tracking, and automated reporting.

---

## 1. Background

The DBA team coordinates primarily through Discord. To address productivity monitoring needs and provide objective performance data, an automated tracking system was developed.

### Objectives
- Track daily attendance (check-in/check-out times)
- Monitor active work hours and break durations
- Measure engagement through Discord activity
- Track email communications
- Generate automated reports for management review

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DBA Performance Tracking System                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  Discord Bot    │    │ Discord Export  │    │  Email Extract  │         │
│  │  (Real-time)    │    │  (Daily)        │    │  (Daily)        │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │                    SQLite Database                          │           │
│  │  attendance.db (idle, offline, voice, leave, remote_work)  │           │
│  └───────────────────────────┬─────────────────────────────────┘           │
│                              │                                              │
│                              ▼                                              │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │              Attendance Tracker                             │           │
│  │  (attendance_tracker.py)                                    │           │
│  └───────────────────────────┬─────────────────────────────────┘           │
│                              │                                              │
│           ┌──────────────────┼──────────────────┐                          │
│           ▼                  ▼                  ▼                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                    │
│  │ Daily CSV    │   │ Email Report │   │ Monthly      │                    │
│  │ Export       │   │ (HTML)       │   │ Report       │                    │
│  └──────────────┘   └──────────────┘   └──────────────┘                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. File Structure

### 3.1 Core Files

| File | Description |
|------|-------------|
| `attendance_tracker.py` | Main attendance analysis and reporting engine. Parses Discord messages, calculates work hours, generates CSV and SQLite exports |
| `email_sender.py` | Sends HTML email reports with CSV attachments via Exchange |
| `monthly_report.py` | Generates monthly aggregated reports in Persian (Jalali calendar) |
| `attendance_db.py` | SQLite database manager with CLI for queries |
| `migrate_to_sqlite.py` | One-time migration script from JSON to SQLite |

### 3.2 Data Collection Files

| File | Description |
|------|-------------|
| `discord/discord_idle_bot.py` | Real-time Discord status monitoring bot. Tracks idle/offline/voice time |
| `discord/discord_exporter.py` | Exports Discord channel messages to JSON files |
| `email_extractor.py` | Extracts email counts from Exchange (for attendance metrics) |
| `email_full_extractor.py` | Exports full email content (for mtn_update.py analysis) |

### 3.3 Support Files

| File | Description |
|------|-------------|
| `build_leave_database.py` | Parses historical Discord exports to build leave request database |
| `remote_work_tracker.py` | Parses and manages remote work records |
| `leave_parser.py` | Parses leave request messages from Discord |
| `mtn_update.py` | Analyzes received emails for work metrics |
| `view_attendance.py` | CLI tool to view attendance data |

### 3.4 Automation Scripts

| File | Description |
|------|-------------|
| `daily_attendance_cron.sh` | Main cron script that orchestrates daily reporting |
| `monthly_attendance_cron.sh` | Monthly report generation script |
| `cleanup.sh` | Cleanup temporary files |

### 3.5 Data Storage

| File/Table | Description |
|------------|-------------|
| `attendance_reports/attendance.db` | Main SQLite database with all attendance data |
| `attendance_reports/daily_attendance.csv` | Historical CSV with all daily records |
| `discord/activity.db` | Discord bot session-level tracking |
| `*.json` | Legacy JSON files (kept as fallback) |

---

## 4. Discord Bot (`discord_idle_bot.py`)

### 4.1 Purpose
Real-time monitoring of Discord presence status for all team members.

### 4.2 Tracked Statuses

| Status | Description |
|--------|-------------|
| Online | User is active on Discord |
| Idle | Discord shows user as idle (yellow dot) |
| Offline | User is not connected to Discord |
| Voice | User is in a voice channel |

### 4.3 Features

- **Presence Tracking**: Monitors status changes in real-time
- **Voice Channel Tracking**: Records time spent in voice channels
- **Session Persistence**: Saves open sessions to survive bot restarts
- **SQLite Sync**: Syncs daily data to the unified SQLite database
- **Work Hours Only**: Only tracks during work hours (08:00-18:00)

### 4.4 Data Storage

```python
# Data structures in memory
daily_idle_time = {date_str: {user_id: minutes}}
daily_offline_time = {date_str: {user_id: minutes}}
daily_voice_time = {date_str: {user_id: minutes}}

# Synced to SQLite tables
idle_tracking (date, name, idle_minutes)
offline_tracking (date, name, offline_minutes)
voice_tracking (date, name, voice_minutes)
```

### 4.5 Running the Bot

```bash
# Start the bot
cd /root/infrastructure/MTN_Repo/discord
source .env
python3 discord_idle_bot.py

# Or as a systemd service
sudo systemctl start discord-idle-tracker
```

---

## 5. Attendance Tracker (`attendance_tracker.py`)

### 5.1 Purpose
Parse Discord messages to extract attendance data and calculate work metrics.

### 5.2 Message Detection Patterns

**Greetings (Check-in):**
- `salam`, `sobh bekheir`, `rooz bekheir`, `hi`, `vorud`

**Farewells (Check-out):**
- `khaste nabashid`, `felan`, `shab bekheir`, `bye`, `khodafez`

**Breaks (BRB):**
- `brb` - Start break
- `brb nahar` - Lunch break (1 hour)
- `b`, `back` - Return from break

**Leave Requests:**
- `morekhasi farda` - Full day tomorrow
- `morekhasi az 14 ta 16` - Hourly leave
- `off`, `morakhasi` with date ranges

### 5.3 Metrics Calculation

```
Gross Work Time = Check-out - Check-in
BRB Excess = BRB_total - Free_allowance (60 min)
Effective Hours = Gross - BRB - max(Idle, HourlyLeave) - Offline + Bonus
```

### 5.4 Command Line Usage

```bash
# Generate today's report
python3 attendance_tracker.py

# Export to CSV
python3 attendance_tracker.py --csv

# Backfill historical data
python3 attendance_tracker.py --backfill --from 2025-04-21

# Analyze specific date
python3 attendance_tracker.py --date 2025-12-28
```

---

## 6. Email Reports

### 6.1 Daily Report (`email_sender.py`)

Sent at 20:00 containing:
- Attendance table for all team members
- Check-in/check-out times
- Work hours and BRB time
- Idle/Offline percentages
- Email and Discord message counts
- Warnings for late arrival, early departure, low hours

**Recipients:**
- Production: alireza.aghaja@, maryam.mare@, amirbahram.b@, hossein.mog@
- Test: alireza.aghaja@, maryam.mare@ only

### 6.2 Monthly Report (`monthly_report.py`)

Generated on 24th of each Jalali month containing:
- Aggregated attendance data
- Total work hours per person
- Leave summary
- Average daily metrics
- Trend analysis

---

## 7. Database Schema

### 7.1 Main Attendance Table

```sql
CREATE TABLE attendance (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    check_in TEXT,
    check_out TEXT,
    work_hours REAL,
    brb_minutes TEXT,
    emails INTEGER,
    discord INTEGER,
    voice INTEGER,
    effective_minutes REAL,
    leave TEXT,
    leave_hours TEXT,
    idle_minutes INTEGER,
    offline_minutes INTEGER,
    is_oncall TEXT,
    is_support TEXT,
    absent TEXT,
    UNIQUE(date, name)
);
```

### 7.2 Tracking Tables

```sql
CREATE TABLE idle_tracking (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    idle_minutes REAL,
    UNIQUE(date, name)
);

CREATE TABLE offline_tracking (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    offline_minutes REAL,
    UNIQUE(date, name)
);

CREATE TABLE voice_tracking (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    voice_minutes REAL,
    UNIQUE(date, name)
);
```

### 7.3 Leave and Remote Work

```sql
CREATE TABLE leave_records (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    leave_type TEXT,
    start_hour INTEGER,
    end_hour INTEGER,
    UNIQUE(date, name, leave_type, start_hour, end_hour)
);

CREATE TABLE remote_work (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    location TEXT,
    UNIQUE(date, name)
);
```

---

## 8. Working Hours Policy

### 8.1 Flexible Hours

| Parameter | Value |
|-----------|-------|
| Entry Window | 08:00 - 09:30 |
| Exit Window | 17:00 - 18:30 |
| Working Days | Saturday - Wednesday |
| Weekend | Thursday, Friday |
| Total Work Hours | 9 hours (including 1 hour lunch) |

### 8.2 Break Rules

| Break Type | Allowance |
|------------|-----------|
| Short Break (BRB) | 30 min per session, 60 min total |
| Lunch Break (brb nahar) | 60 minutes free |

If a break exceeds the allowed duration, excess time is deducted from effective hours.

### 8.3 On-Call Rules

| Day Type | Role | Effective Hours |
|----------|------|-----------------|
| Regular Day | On-call | 9 hours automatic |
| Regular Day | Support (previous on-call) | 9 hours automatic |
| Wednesday | On-call | Actual + 5 hour bonus |

---

## 9. Automation Schedule (Cron)

| Time | Task | Script |
|------|------|--------|
| 20:00 daily | Export Discord, generate report, send email | `daily_attendance_cron.sh` |
| 10:00 on 24th | Generate monthly report | `monthly_attendance_cron.sh` |

**Crontab Entry:**
```cron
0 20 * * * /root/infrastructure/scripts/daily_attendance_cron.sh >> /root/infrastructure/attendance_reports/cron.log 2>&1
0 10 * * * /root/infrastructure/scripts/monthly_attendance_cron.sh >> /root/infrastructure/attendance_reports/monthly_cron.log 2>&1
```

---

## 10. Team Members

### 10.1 Active Members

| Name | Discord Username | Status |
|------|-----------------|--------|
| Keivan Sadeghi | k1.sadeghi_15101 | Active |
| Ehsan Yousefi | ehsan.yo | Active |
| Mohsen Roudsaz | mohsen.roud | Active |
| Nader Shabibi | nader3307 | Active |
| Zeinabsadat Hejazi | mahsahejszi | Active |
| Hosseinali Shirali | hosseinshahreza | Active |
| Masoud Rafiei | masoudraafiee | Active |
| Masoud Sereshki | masoudsereshki | Active |
| Yassin Alivand | nissay87 | Active |
| Erfan Heidari | erfan_heidari | Active |
| Maryam Yousefi | maryam.you | Active |

### 10.2 Excluded from Tracking

| Name | Role | Reason |
|------|------|--------|
| Alireza Aghajanzadeh | System Owner | Excluded |
| Maryam Marefati | Team Lead | Excluded |
| Hossein Feizollahi | Senior DBA | Excluded |

---

## 11. Setup and Installation

### 11.1 Requirements

```bash
pip install discord.py exchangelib jdatetime pandas
```

### 11.2 Environment Variables

```bash
# Discord Bot
DISCORD_BOT_TOKEN=your_bot_token

# Email (Exchange)
SMTP_PASSWORD=your_exchange_password
```

### 11.3 Initial Setup

```bash
# Clone repository
git clone github.com/alireza8580/MTN_Repo

# Create symlink for backward compatibility
ln -s /root/infrastructure/MTN_Repo /root/infrastructure/scripts

# Install systemd service for Discord bot
sudo cp discord/discord-idle-tracker.service /etc/systemd/system/
sudo systemctl enable discord-idle-tracker
sudo systemctl start discord-idle-tracker
```

### 11.4 Migration from JSON to SQLite

```bash
# Run migration (one-time)
python3 migrate_to_sqlite.py
```

---

## 12. Troubleshooting

### 12.1 Common Issues

| Issue | Solution |
|-------|----------|
| Bot shows offline users as idle | Check Discord presence intent permissions |
| Email not sending | Verify SMTP_PASSWORD environment variable |
| Missing attendance data | Check Discord export files in discord_exports/ |
| SQLite errors | Ensure attendance.db has correct permissions |

### 12.2 Log Locations

| Log | Location |
|-----|----------|
| Daily cron | `/root/infrastructure/attendance_reports/cron.log` |
| Monthly cron | `/root/infrastructure/attendance_reports/monthly_cron.log` |
| Discord bot | stdout when running in terminal |

---

## 13. Future Enhancements

- Integration with ticketing system (iCare) for task tracking
- Outlook calendar integration for meeting tracking
- Dashboard for real-time monitoring
- Expansion to other teams
- Machine learning for anomaly detection

---

*Document Version: 2.0*
*Date: December 2025*
*Author: Alireza Aghajanzadeh Gheshlaghi*
*Department: ITS Infrastructure Operation*
