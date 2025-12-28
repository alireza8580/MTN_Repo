# DBA Team Performance Tracking System

## Executive Summary

This document describes the automated performance tracking system implemented for the DBA team at MTN Irancell. The system provides objective metrics for evaluating team productivity and attendance.

---

## 1. Background

The DBA team coordinates primarily through Discord. To address productivity monitoring needs and provide objective performance data, an automated tracking system was developed.

### Objectives
- Track daily attendance (check-in/check-out times)
- Monitor active work hours and break durations
- Measure engagement through Discord activity
- Generate automated reports for management review

---

## 2. System Components

### 2.1 Discord Activity Bot

A custom Discord bot monitors team activity in real-time:

| Metric | Description |
|--------|-------------|
| Idle Time | Minutes spent with Discord status "idle" |
| Offline Time | Minutes with Discord status "offline" |
| Voice Channel Time | Time spent in voice channels |

The bot runs continuously (24/7) and records activity every minute.

### 2.2 Attendance Tracker

Parses Discord messages to extract:

- Check-in time (greetings: "salam", "sobh bekheir", etc.)
- Check-out time (farewells: "felan", "khaste nabashid", etc.)
- Break periods (BRB/back pairs)
- Leave requests (hourly and daily)

### 2.3 Email Report Generator

Sends formatted HTML reports with CSV attachments:

| Report Type | Schedule | Recipients |
|-------------|----------|------------|
| Daily Report | 19:00 | DBA Management |
| Monthly Summary | 24th of Jalali month | Finance/HR |

---

## 3. Working Hours Policy

### 3.1 Flexible Hours

| Parameter | Value |
|-----------|-------|
| Entry Window | 08:00 - 09:30 |
| Exit Window | 17:00 - 18:30 |
| Working Days | Saturday - Wednesday |
| Total Work Hours | 9 hours (including 1 hour lunch) |

### 3.2 Break Rules

| Break Type | Maximum Duration |
|------------|------------------|
| Short Break (BRB) | 30 minutes |
| Lunch Break | 1 hour |

If a break exceeds the allowed duration, it should be logged as hourly leave.

### 3.3 Voice Channel Requirement

Team members are expected to be available in Discord voice channels until 10:00 AM for coordination purposes.

---

## 4. Tracked Metrics

### 4.1 Daily Report Fields

| Field | Description |
|-------|-------------|
| Name | Team member name |
| Check-in | First activity time |
| Check-out | Last activity time |
| Work Hours | Duration between check-in and check-out minus breaks |
| BRB Time | Total break duration |
| Idle Minutes | Time with "idle" Discord status |
| Offline Minutes | Time with "offline" Discord status |
| Voice Minutes | Time in voice channels |
| Discord Messages | Number of messages sent (excluding greetings) |
| Email Count | Emails sent (from Outlook export) |

### 4.2 Alert Conditions

The system flags the following conditions:

| Condition | Threshold |
|-----------|-----------|
| Late Arrival | After 09:30 |
| Early Departure | Before 17:00 (adjusted for entry time) |
| Extended BRB | Over 30 minutes |
| Low Work Hours | Under 8 hours |
| High Idle Time | Over 20% of work hours |

Note: On-call personnel are excluded from attendance warnings.

---

## 5. Leave Management

### 5.1 Leave Types

| Type | Format Example |
|------|----------------|
| Full Day | "morakhasi farda" or "morakhasi 25" |
| Date Range | "morakhasi az 25 ta 28" |
| Hourly Leave | "morakhasi az 14 ta 17" |
| Remote Work | "remote shiraz" |

### 5.2 Leave Calculation

For partial day leave until end of work, the exit time is calculated as:
**Exit Time = Entry Time + 9 hours**

Example:
- Entry at 08:00 → Expected exit at 17:00
- Entry at 09:30 → Expected exit at 18:30

---

## 6. Report Distribution

### 6.1 Daily Reports

Sent at 19:00 containing:
- Attendance summary for all team members
- Warnings and alerts
- On-call schedule reference

### 6.2 Monthly Aggregated Report

Generated on the 24th of each Jalali month for payroll reference:
- Total work hours per person
- Average daily hours
- Leave summary
- Activity metrics

---

## 7. Excluded Personnel

The following roles are excluded from standard tracking metrics:

| Role | Reason |
|------|--------|
| Team Lead | Different responsibilities |
| Senior Consultants | Variable schedules |
| On-Call (daily) | Special duty hours |

---

## 8. Technical Implementation

### 8.1 Infrastructure

| Component | Technology |
|-----------|------------|
| Discord Bot | Python (discord.py) |
| Attendance Parser | Python |
| Email Sender | Python (exchangelib) |
| Data Storage | JSON files |
| Scheduler | Linux cron |

### 8.2 Data Flow

```
Discord Messages → Export (18:55) → Parse → Generate Report → Email (19:00)
       ↓
Discord Bot (real-time) → Idle/Offline/Voice tracking → JSON database
```

### 8.3 Automation Schedule

| Time | Task |
|------|------|
| 18:55 | Export Discord messages |
| 19:00 | Generate and send daily report |
| 10:00 (24th) | Generate monthly summary |

---

## 9. Limitations

1. **Project Work**: Deep work on major projects (research, documentation) may not reflect in message counts
2. **External Communication**: Phone calls and in-person meetings are not tracked
3. **Network Issues**: Discord status may be inaccurate during network problems

These edge cases should be noted by the Team Lead in monthly summaries.

---

## 10. Future Enhancements

- Integration with ticketing system (iCare) for task tracking
- Outlook calendar integration for meeting tracking
- Dashboard for real-time monitoring
- Expansion to other teams

---

*Document Version: 1.0*
*Date: December 2025*
*Author: Alireza Aghajanzadeh Gheshlaghi*
*Department: ITS Infrastructure Operation*
