#!/bin/bash
#
# cron_ppms_export.sh - Cron entry point for PPMS export
#
# Runs daily from cron. Checks if today is the 1st of a Jalali month.
# If yes, runs the export at 01:00. If no, exits silently.
#
# Crontab entry (run at 01:00 daily, Jalali check filters):
#   0 1 * * * /oracle/ppms_to_adhoc/cron_ppms_export.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Check if today is 1st of Jalali month
${SCRIPT_DIR}/is_jalali_first.sh
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Not 1st of Jalali month, skipping."
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') 1st of Jalali month detected. Starting export..."
exec ${SCRIPT_DIR}/run_export.sh --no-lock
