# DBA Attendance Tracking System - All-in-One Docker Image
# This image contains all components for the attendance tracking system
#
# Build: docker build -t dba-attendance .
# Run:   docker-compose up -d

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set timezone to Iran
ENV TZ=Asia/Tehran
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python dependencies
RUN pip install --no-cache-dir \
    discord.py \
    python-dotenv \
    exchangelib \
    jdatetime \
    pytz

# Copy all scripts
COPY attendance_tracker.py .
COPY email_sender.py .
COPY email_extractor.py .
COPY email_full_extractor.py .
COPY monthly_report.py .
COPY mtn_update.py .
COPY remote_work_tracker.py .
COPY view_attendance.py .
COPY leave_parser.py .
COPY build_leave_database.py .
COPY discord/discord_idle_bot.py ./discord/
COPY discord/discord_exporter.py ./discord/

# Copy JSON database files
COPY leave_database.json .
COPY leave_log.json .
COPY remote_work_database.json .
COPY ATTENDANCE_PROTOCOL.md .

# Copy cron scripts
COPY daily_attendance_cron.sh .
COPY monthly_attendance_cron.sh .
COPY cleanup.sh .

# Make scripts executable
RUN chmod +x *.sh
# Create data directories
RUN mkdir -p /app/data/discord_exports \
             /app/data/email_exports \
             /app/data/mtn_emails \
             /app/data/attendance_reports

# Set up cron jobs
RUN echo "# DBA Attendance Cron Jobs" > /etc/cron.d/dba-attendance \
    && echo "55 18 * * * root cd /app && ./daily_attendance_cron.sh >> /app/data/logs/cron.log 2>&1" >> /etc/cron.d/dba-attendance \
    && echo "0 10 * * * root cd /app && ./monthly_attendance_cron.sh >> /app/data/logs/monthly.log 2>&1" >> /etc/cron.d/dba-attendance \
    && echo "0 3 * * 0 root cd /app && ./cleanup.sh >> /app/data/logs/cleanup.log 2>&1" >> /etc/cron.d/dba-attendance \
    && chmod 0644 /etc/cron.d/dba-attendance

# Create log directory
RUN mkdir -p /app/data/logs

# Environment variables (override with docker-compose or -e)
ENV DISCORD_TOKEN=""
ENV SMTP_PASSWORD=""
ENV EWS_EMAIL="maryam.mare@mtnirancell.ir"
ENV EWS_USER="maryam.mare"
ENV EWS_DOMAIN="mtnirancell.ir"
ENV EWS_SERVER="mail.mtnirancell.ir"

# Base directory for application paths (attendance_tracker.py uses this)
ENV APP_BASE_DIR=/app
ENV SCRIPTS_DIR=/app

# Data directories (can be mounted as volumes)
ENV DISCORD_EXPORT_DIR=/app/data/discord_exports
ENV EMAIL_EXPORT_DIR=/app/data/email_exports
ENV MTN_EMAIL_DIR=/app/data/mtn_emails
ENV ATTENDANCE_CSV=/app/data/attendance_reports/daily_attendance.csv
ENV STANDBY_SHIFT_FILE=/app/MTN_standby_shift.csv
ENV HOLIDAY_SHIFT_FILE=/app/holiday_shifts.csv

# Entrypoint script
COPY docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["cron", "-f"]
