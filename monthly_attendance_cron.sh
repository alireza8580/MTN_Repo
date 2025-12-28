#!/bin/bash
# Monthly DBA Attendance Report Generator
# Runs daily but only executes on 24th of Jalali month
#
# Crontab entry:
#   0 10 * * * /root/infrastructure/scripts/monthly_attendance_cron.sh >> /root/infrastructure/attendance_reports/monthly_cron.log 2>&1

set -e

SCRIPT_DIR="/root/infrastructure/scripts"
VENV_PATH="/root/infrastructure/venv"

echo "=========================================="
echo "Monthly Attendance Check - $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# Activate virtual environment if exists
if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
fi

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

# Run monthly report (will check if today is 24th) - PRODUCTION mode with BCC
python3 monthly_report.py --check-24th --prod

echo "=========================================="
echo "Completed at $(date '+%H:%M:%S')"
echo "=========================================="
