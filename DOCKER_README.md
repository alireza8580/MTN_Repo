# DBA Attendance Tracking System - Docker Deployment

This directory contains all components for the DBA team attendance tracking system.

## Quick Start (EC2/Docker)

```bash
# 1. Clone/copy the scripts directory
cd /path/to/scripts

# 2. Create .env file
cp .env.example .env
nano .env  # Fill in DISCORD_TOKEN and SMTP_PASSWORD

# 3. Copy config files
cp ../MTN_standby_shift.csv ./data/
cp ../holiday_shifts.csv ./data/

# 4. Build and start
docker-compose up -d

# 5. Check logs
docker-compose logs -f
```

## Components

| Component | Description | Schedule |
|-----------|-------------|----------|
| Discord Idle Bot | Tracks online/idle/offline presence | Real-time |
| Discord Exporter | Exports Discord messages | 18:55 daily |
| Email Extractor | Counts emails from team | Before daily report |
| Attendance Tracker | Generates attendance CSV | 19:00 daily |
| Email Sender | Sends HTML reports | 19:00 daily |
| Monthly Report | Generates monthly summary | 10:00 on 23rd |

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` | Discord bot token | Bot token from Discord Dev Portal |
| `SMTP_PASSWORD` | Exchange password for `EWS_USER` | maryam.mare domain password |
| `EWS_EMAIL` | Sender mailbox (SMTP address) | maryam.mare@mtnirancell.ir |
| `EWS_USER` | NTLM login name | maryam.mare |
| `EWS_DOMAIN` | NTLM domain | mtnirancell.ir |
| `EWS_SERVER` | Exchange server | mail.mtnirancell.ir |
| `TZ` | Timezone | Asia/Tehran |

## Data Volumes

All data is persisted in `./data/`:

```
data/
├── discord_exports/     # Discord message exports (JSON)
├── email_exports/       # Email count exports (JSON)
├── mtn_emails/          # Full email exports (CSV)
├── attendance_reports/  # Attendance CSV
└── logs/                # Cron job logs
```

## Manual Commands

```bash
# Enter container shell
docker-compose exec attendance bash

# Run attendance report manually
docker-compose exec attendance python3 attendance_tracker.py --csv

# Send test email
docker-compose exec attendance python3 email_sender.py --test

# Extract emails for specific date
docker-compose exec attendance python3 email_extractor.py --date 2025-12-22

# Export full emails (for mtn_update analysis)
docker-compose exec attendance python3 email_full_extractor.py --days 2 --no-body

# Run mtn_update for work analysis
docker-compose exec attendance python3 mtn_update.py
```

## Cron Schedule

| Time | Task | Log File |
|------|------|----------|
| 18:55 | Discord export | cron.log |
| 19:00 | Daily attendance report | cron.log |
| 10:00 | Monthly report check | monthly.log |
| 03:00 Sun | Cleanup old files | cleanup.log |

## Troubleshooting

### Discord bot not connecting
- Check `DISCORD_TOKEN` in .env
- Verify bot has correct permissions in Discord server
- Check logs: `docker-compose logs discord-bot`

### Email sending fails
- Verify `SMTP_PASSWORD` is correct
- Check EWS server connectivity
- Test manually: `docker-compose exec attendance python3 email_sender.py --test`

### Missing attendance data
- Ensure Discord exports are being generated
- Check `data/discord_exports/` for recent files
- Verify timezone is set correctly

### Rebuild after code changes
```bash
docker-compose build --no-cache
docker-compose up -d
```

## EC2 Deployment (Production)

```bash
# 1. Launch EC2 instance (Ubuntu 22.04, t3.small or larger)
# SSH to instance

# 2. Install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker

# 3. Create project directory
mkdir -p /opt/dba-attendance
cd /opt/dba-attendance

# 4. Copy project files (from local machine)
# scp -r /root/infrastructure/scripts/* ec2-user@<EC2_IP>:/opt/dba-attendance/

# 5. Create .env file
cp .env.example .env
nano .env  # Fill in DISCORD_TOKEN and SMTP_PASSWORD

# 6. Create data directories
mkdir -p data/{discord_exports,email_exports,mtn_emails,attendance_reports,logs}

# 7. Copy config files (if not in scripts directory)
# cp /path/to/MTN_standby_shift.csv .
# cp /path/to/holiday_shifts.csv .

# 8. Build and start
sudo docker-compose up -d --build

# 9. Check logs
sudo docker-compose logs -f

# 10. Verify cron jobs
sudo docker-compose exec attendance cat /etc/cron.d/dba-attendance
```

### EC2 Security Group
Allow outbound:
- Port 443 (HTTPS) - Discord API, Exchange EWS
- Port 587 (SMTP) - Email sending

### Auto-restart on reboot
Docker Compose with `restart: always` handles this automatically.

