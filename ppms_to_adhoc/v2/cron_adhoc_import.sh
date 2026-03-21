#!/bin/bash
#
# cron_adhoc_import.sh - Cron entry point for ADHOC import (t1u904)
#
# Runs daily from cron at 04:00. Checks:
#   1. Is today 1st of a Jalali month?
#   2. Is there NO SSH lock file? (if lock exists, pipeline is handling import)
#   3. Polls NFS for export done signal, then runs import.
#
# Crontab entry on t1u904 (oracle user):
#   0 4 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "${SCRIPT_DIR}/ppms_to_adhoc.conf"

# Check if today is 1st of Jalali month
${SCRIPT_DIR}/is_jalali_first.sh
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Not 1st of Jalali month, skipping."
    exit 0
fi

# Check if SSH lock exists locally — means pipeline (dru110a) is controlling import
if [ -f "${LOCK_FILE}" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') SSH lock file ${LOCK_FILE} exists — pipeline mode active. Skipping."
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') 1st of Jalali month, no SSH lock. Starting import (NFS poll)..."
exec ${SCRIPT_DIR}/run_import.sh
