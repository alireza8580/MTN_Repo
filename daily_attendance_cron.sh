#!/bin/bash
# Daily DBA Attendance Report Generator
# Runs at 20:00 daily via cron
# 
# This script:
# 1. Exports today's Discord messages
# 1.5. Extracts email counts (for attendance report)
# 1.6. Extracts full emails (for mtn_update.py work analysis)
# 2. Generates attendance report and appends to CSV
# 3. Sends email report
#
# Crontab entry:
#   0 20 * * * /root/infrastructure/scripts/daily_attendance_cron.sh >> /root/infrastructure/attendance_reports/cron.log 2>&1

set -e

# Detect if running in Docker (check if /app exists and we're running from /app)
if [ -d "/app" ] && [ -f "/app/attendance_tracker.py" ]; then
    SCRIPT_DIR="/app"
    DISCORD_DIR="/app/discord"
    LOG_DIR="/app/data/logs"
    VENV_PATH=""  # No venv in Docker
else
    SCRIPT_DIR="/root/infrastructure/scripts"
    DISCORD_DIR="/root/infrastructure/scripts/discord"
    LOG_DIR="/root/infrastructure/attendance_reports"
    VENV_PATH="/root/infrastructure/venv"
fi

# Create log directory if needed
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "Daily Attendance Report - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# Activate virtual environment if exists (not in Docker)
if [ -n "$VENV_PATH" ] && [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
fi

# Step 1: Export Discord messages (today only)
echo "Step 1: Exporting Discord messages..."
cd "$DISCORD_DIR"

# Load .env file for Discord token
if [ -f "$DISCORD_DIR/.env" ]; then
    export $(cat "$DISCORD_DIR/.env" | grep -v '^#' | xargs)
fi

python3 discord_exporter.py --days 1 || {
    echo "Warning: Discord export failed, using existing data"
}

# Step 1.5: Extract email counts from Exchange
echo "Step 1.5: Extracting email counts..."
cd "$SCRIPT_DIR"

# Load SMTP password - prefer environment variable, fallback to file
if [ -z "$SMTP_PASSWORD" ]; then
    # Source .zshrc if available (for non-interactive cron)
    if [ -f "$HOME/.zshrc" ]; then
        source "$HOME/.zshrc" 2>/dev/null || true
    fi
    # Fallback to file-based password
    if [ -z "$SMTP_PASSWORD" ] && [ -f "$SCRIPT_DIR/.smtp_password" ]; then
        export SMTP_PASSWORD=$(cat "$SCRIPT_DIR/.smtp_password")
    fi
fi

# Get yesterday's email counts (report is for yesterday's attendance)
yesterday=$(date -d "yesterday" '+%Y-%m-%d')
python3 email_extractor.py --date "$yesterday" || {
    echo "Warning: Email extraction failed, continuing without email data"
}

# Step 1.6: Extract full emails for mtn_update.py analysis
echo "Step 1.6: Extracting full emails..."
python3 email_full_extractor.py --days 2 || {
    echo "Warning: Full email extraction failed, mtn_update may use stale data"
}

# Step 2: Generate attendance CSV
echo "Step 2: Generating attendance CSV..."
cd "$SCRIPT_DIR"
python3 attendance_tracker.py --csv

# Step 3: Send email report (PRODUCTION mode)
echo "Step 3: Sending email report..."

# Ensure SMTP_PASSWORD is still set (may have been lost after cd)
if [ -z "$SMTP_PASSWORD" ]; then
    if [ -f "$HOME/.zshrc" ]; then
        source "$HOME/.zshrc" 2>/dev/null || true
    fi
    if [ -z "$SMTP_PASSWORD" ] && [ -f "$SCRIPT_DIR/.smtp_password" ]; then
        export SMTP_PASSWORD=$(cat "$SCRIPT_DIR/.smtp_password")
    fi
fi

# Send daily email report - PRODUCTION mode with CC recipients
python3 email_sender.py --prod

echo "=========================================="
echo "Completed at $(date '+%H:%M:%S')"
if [ -d "/app" ]; then
    echo "CSV file: /app/data/attendance_reports/daily_attendance.csv"
else
    echo "CSV file: /root/infrastructure/attendance_reports/daily_attendance.csv"
fi
echo "=========================================="
