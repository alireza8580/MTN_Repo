#!/bin/bash
# Database Size Collector - Cron Wrapper Script
# This script is designed to be run from cron
# 
# Suggested cron entry (run daily at 2:00 AM):
#   0 2 * * * /path/to/db_size_collector/run_collector.sh >> /var/log/db_size_collector_cron.log 2>&1
#
# Environment variables:
#   EMAIL_PASSWORD - Password for SMTP authentication (required for email notifications)

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Log file
LOG_DIR="/var/log"
LOG_FILE="${LOG_DIR}/db_size_collector.log"
CRON_LOG="${LOG_DIR}/db_size_collector_cron.log"

# Python interpreter
PYTHON="/usr/bin/python3"

# Date for logging
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "=========================================="
echo "Database Size Collector - ${DATE}"
echo "=========================================="

# Check if Python is available
if [ ! -x "$PYTHON" ]; then
    echo "ERROR: Python3 not found at $PYTHON"
    exit 1
fi

# Check if the collector script exists
COLLECTOR="${SCRIPT_DIR}/collect_db_sizes.py"
if [ ! -f "$COLLECTOR" ]; then
    echo "ERROR: Collector script not found: $COLLECTOR"
    exit 1
fi

# Load email password from secure file if exists
EMAIL_PASS_FILE="${SCRIPT_DIR}/.email_password"
if [ -f "$EMAIL_PASS_FILE" ]; then
    export EMAIL_PASSWORD=$(cat "$EMAIL_PASS_FILE")
fi

# Change to script directory
cd "$SCRIPT_DIR"

# Parse command line options
NO_EMAIL=""
QUIET="--quiet"
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-email)
            NO_EMAIL="--no-email"
            shift
            ;;
        --verbose|-v)
            QUIET=""
            VERBOSE="--verbose"
            shift
            ;;
        --email-test)
            EMAIL_TEST="--email-test"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Run the collector
echo "Starting collection..."
echo "Command: $PYTHON $COLLECTOR $QUIET $VERBOSE $NO_EMAIL $EMAIL_TEST"
$PYTHON "$COLLECTOR" $QUIET $VERBOSE $NO_EMAIL $EMAIL_TEST

# Check exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Collection completed successfully"
    echo "Email notification sent (if configured)"
elif [ $EXIT_CODE -eq 2 ]; then
    echo "WARNING: Collection completed with some failures"
    echo "Email notification sent (if configured)"
else
    echo "ERROR: Collection failed with exit code $EXIT_CODE"
fi

# Optional: Cleanup old data (keep 1 year)
# Uncomment to enable automatic cleanup
# echo "Cleaning up old data..."
# $PYTHON "$COLLECTOR" --cleanup 365 --quiet --no-email

echo "Done at $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

exit $EXIT_CODE
