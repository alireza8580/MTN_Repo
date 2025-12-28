#!/bin/bash
# Docker entrypoint script for DBA Attendance System

set -e

# Create symbolic links from data volume to expected paths
mkdir -p /root/infrastructure/discord_exports
mkdir -p /root/infrastructure/email_exports
mkdir -p /root/infrastructure/mtn_emails
mkdir -p /root/infrastructure/attendance_reports

ln -sf /app/data/discord_exports /root/infrastructure/discord_exports 2>/dev/null || true
ln -sf /app/data/email_exports /root/infrastructure/email_exports 2>/dev/null || true
ln -sf /app/data/mtn_emails /root/infrastructure/mtn_emails 2>/dev/null || true
ln -sf /app/data/attendance_reports /root/infrastructure/attendance_reports 2>/dev/null || true

# Validate required environment variables
if [ -z "$DISCORD_TOKEN" ]; then
    echo "WARNING: DISCORD_TOKEN not set - Discord bot will not work"
fi

if [ -z "$SMTP_PASSWORD" ]; then
    echo "WARNING: SMTP_PASSWORD not set - Email sending will not work"
fi

# Store SMTP password for cron jobs
if [ -n "$SMTP_PASSWORD" ]; then
    echo "$SMTP_PASSWORD" > /app/.smtp_password
    chmod 600 /app/.smtp_password
fi

# Store Discord token for cron jobs
if [ -n "$DISCORD_TOKEN" ]; then
    echo "DISCORD_TOKEN=$DISCORD_TOKEN" > /app/discord/.env
fi

# Start cron daemon in foreground or run the specified command
echo "Starting DBA Attendance System..."
echo "Timezone: $(date '+%Z %z')"
echo "Current time: $(date)"

exec "$@"
