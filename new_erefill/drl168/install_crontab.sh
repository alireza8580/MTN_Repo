#!/bin/bash
#===============================================================================
# MFS_REPORT Crontab Generator - Drl168
# This script appends gather stats crontab entries to the current user's crontab
# Usage: ./install_crontab.sh
#===============================================================================

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== MFS_REPORT Crontab Generator ==="
echo "Script directory: ${SCRIPT_DIR}"
echo ""

# Create temporary file with new cron entries
TEMP_CRON=$(mktemp)

cat >> ${TEMP_CRON} << EOF
#===============================================================================
# MFS_REPORT Gather Stats - Drl168 (Added: $(date '+%Y-%m-%d %H:%M:%S'))
#===============================================================================

# Schedule C (every 12 hours) - MFS_EDR_DAILY partitions
0 11,23 * * * ${SCRIPT_DIR}/mfs_report_scheduleC.scr

# Monthly (10th of month at 2AM) - MFS_EDR_DAILY with higher DEGREE
0 2 10 * * ${SCRIPT_DIR}/mfs_report_monthly.scr

EOF

echo "New crontab entries to be added:"
echo "================================="
cat ${TEMP_CRON}
echo "================================="
echo ""

read -p "Do you want to append these entries to your crontab? (y/n): " confirm

if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
    # Get current crontab and append new entries
    (crontab -l 2>/dev/null; cat ${TEMP_CRON}) | crontab -
    echo "Crontab entries added successfully!"
    echo ""
    echo "Current crontab:"
    crontab -l
else
    echo "Crontab not modified."
fi

# Cleanup
rm -f ${TEMP_CRON}
