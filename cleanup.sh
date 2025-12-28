#!/bin/bash
# Cleanup script for DBA attendance tracking system
# Removes old exports and temporary files
# Schedule: Weekly on Sunday at 03:00

set -e

# Configuration
DISCORD_EXPORTS_DIR="/root/infrastructure/discord_exports"
ATTENDANCE_REPORTS_DIR="/root/infrastructure/attendance_reports"
MTN_EMAILS_DIR="/root/infrastructure/mtn_emails"
RETENTION_DAYS_EXPORTS=30      # Discord exports and emails: 30 days
RETENTION_DAYS_CSV=60          # Attendance CSV data: 60 days for monthly reports

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting cleanup..."

# Clean old Discord exports (keep last 30 days)
if [ -d "$DISCORD_EXPORTS_DIR" ]; then
    count=$(find "$DISCORD_EXPORTS_DIR" -type f -name "*.json" -mtime +$RETENTION_DAYS_EXPORTS 2>/dev/null | wc -l)
    find "$DISCORD_EXPORTS_DIR" -type f -name "*.json" -mtime +$RETENTION_DAYS_EXPORTS -delete 2>/dev/null
    echo "  Discord exports: removed $count files older than $RETENTION_DAYS_EXPORTS days"
fi

# Clean old email exports (keep last 30 days)
if [ -d "$MTN_EMAILS_DIR" ]; then
    count=$(find "$MTN_EMAILS_DIR" -type f -name "*.csv" -mtime +$RETENTION_DAYS_EXPORTS 2>/dev/null | wc -l)
    find "$MTN_EMAILS_DIR" -type f -name "*.csv" -mtime +$RETENTION_DAYS_EXPORTS -delete 2>/dev/null
    echo "  Email exports: removed $count files older than $RETENTION_DAYS_EXPORTS days"
fi

# Note: Daily attendance CSV is a single file that gets appended to
# We don't delete it, but we can archive old data if needed in the future

# Clean Python cache
find /root/infrastructure/scripts -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "  Python cache: cleaned"

# Clean empty log files
find /root/infrastructure -type f -name "*.log" -empty -delete 2>/dev/null || true

# Show disk usage
echo ""
echo "Current disk usage:"
du -sh "$DISCORD_EXPORTS_DIR" 2>/dev/null || echo "  Discord exports: N/A"
du -sh "$ATTENDANCE_REPORTS_DIR" 2>/dev/null || echo "  Attendance reports: N/A"
du -sh "$MTN_EMAILS_DIR" 2>/dev/null || echo "  MTN emails: N/A"

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleanup completed"
