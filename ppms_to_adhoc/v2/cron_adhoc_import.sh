#!/bin/bash
#
# cron_adhoc_import.sh - Cron entry point for ADHOC import
#
# Runs daily from cron. Checks if today is the 1st of a Jalali month.
# If yes, runs the import (waits for export lock to clear). If no, exits silently.
#
# Crontab entry (run at 01:00 daily, same as export - import waits for lock):
#   0 1 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Check if today is 1st of Jalali month
${SCRIPT_DIR}/is_jalali_first.sh
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Not 1st of Jalali month, skipping."
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') 1st of Jalali month detected. Starting import..."
exec ${SCRIPT_DIR}/run_import.sh
