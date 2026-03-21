#!/bin/bash
#
# cron_pipeline.sh - Cron entry point for single-side pipeline
#
# Runs daily from cron on dru110a (PPMS). Checks if today is the 1st of
# a Jalali month. If yes, runs the full pipeline (export + SSH import).
#
# Crontab entry (oracle user on dru110a):
#   0 1 * * * /oracle/ppms_to_adhoc/cron_pipeline.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# Check if today is 1st of Jalali month
${SCRIPT_DIR}/is_jalali_first.sh
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Not 1st of Jalali month, skipping."
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') 1st of Jalali month detected. Starting full pipeline..."
exec ${SCRIPT_DIR}/run_pipeline.sh
