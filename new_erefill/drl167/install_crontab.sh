#!/bin/bash
#===============================================================================
# EREFILL Crontab Generator - Drl167
# This script appends gather stats crontab entries to the current user's crontab
# Usage: ./install_crontab.sh
#===============================================================================

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== EREFILL Crontab Generator ==="
echo "Script directory: ${SCRIPT_DIR}"
echo ""

# Create temporary file with new cron entries
TEMP_CRON=$(mktemp)

cat >> ${TEMP_CRON} << EOF
#===============================================================================
# EREFILL Gather Stats - Drl167 (Added: $(date '+%Y-%m-%d %H:%M:%S'))
#===============================================================================

# Schedule A (every 3 hours) - MFS_ETOPUP_USER_MASTER
0 2,5,8,11,14,17,20,23 * * * ${SCRIPT_DIR}/erefill_scheduleA.scr

# Schedule B (every 6 hours) - CDR/EDR, THRESHOLD_CHECK
0 5,11,17,23 * * * ${SCRIPT_DIR}/erefill_scheduleB.scr

# Schedule C (every 12 hours) - Partitioned tables
0 11,23 * * * ${SCRIPT_DIR}/erefill_scheduleC.scr

# Monthly EVENT (10th of month at 2AM) - 12 EVENT_DATA tables
0 2 10 * * ${SCRIPT_DIR}/erefill_monthly_event.scr

# Monthly CORE (15th of month at 2AM) - 16 CORE tables
0 2 15 * * ${SCRIPT_DIR}/erefill_monthly_core.scr

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
