# Discord Bots for DBA Team Attendance

This directory contains two Discord bots:

1. **discord_exporter.py** - Exports Discord messages for attendance analysis
2. **discord_idle_bot.py** - Tracks idle/offline/voice time during work hours

---

## Part 1: Message Exporter (discord_exporter.py)

## Quick Start

### Step 1: Create Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** → Name: `DBA_Message_Exporter`
3. Go to **Bot** (left menu) → **Add Bot**
4. **IMPORTANT:** Enable these under **Privileged Gateway Intents**:
   - ✅ MESSAGE CONTENT INTENT
   - ✅ SERVER MEMBERS INTENT
5. Click **Reset Token** and copy the token

### Step 2: Invite Bot to Server

1. Go to **OAuth2** → **URL Generator**
2. Select Scopes: `bot`
3. Select Bot Permissions:
   - ✅ Read Message History
   - ✅ Read Messages/View Channels
4. Copy the generated URL and open in browser
5. Select your server and click **Authorize**

### Step 3: Set Up Token

```bash
# Option 1: Environment variable (recommended)
export DISCORD_BOT_TOKEN="your_token_here"

# Option 2: Create .env file
echo 'DISCORD_BOT_TOKEN=your_token_here' > /root/infrastructure/scripts/discord/.env
```

### Step 4: Install Dependencies

```bash
pip install discord.py
```

### Step 5: Run Export

```bash
cd /root/infrastructure/scripts/discord

# Export all channels
python discord_exporter.py

# Export last 7 days only
python discord_exporter.py --days 7

# Export specific channel
python discord_exporter.py --channel 1234567890123456789

# With token directly
python discord_exporter.py --token "your_token_here" --days 1
```

## Output Location

Exports are saved to: `/root/infrastructure/discord_exports/`

Format: `{ServerName}_{timestamp}.json`

## Automation (Cron)

To run daily:

```bash
# Edit crontab
crontab -e

# Add line (runs at 6 AM daily)
0 6 * * * cd /root/infrastructure/scripts/discord && DISCORD_BOT_TOKEN="your_token" python discord_exporter.py --days 1 >> /var/log/discord_export.log 2>&1
```

## JSON Output Structure

```json
{
  "id": "server_id",
  "name": "Server Name",
  "exported_at": "2025-12-20T12:00:00Z",
  "channels": {
    "channel-name": {
      "id": "channel_id",
      "message_count": 150,
      "messages": [
        {
          "id": "message_id",
          "author": {
            "name": "username",
            "display_name": "Display Name"
          },
          "content": "Message text",
          "timestamp": "2025-12-20T10:30:00Z",
          "attachments": [],
          "reactions": []
        }
      ]
    }
  }
}
```

## Troubleshooting

### "No permission to read channel"
- Bot needs "Read Message History" permission in that channel
- Check channel-specific permissions in Discord

### "MESSAGE CONTENT INTENT" error
- Go to Developer Portal → Bot → Enable MESSAGE CONTENT INTENT
- This is required to read message content

### Rate limited
- Discord limits how fast you can read messages
- The script handles this automatically but may take time for large exports

---

## Part 2: Idle Time Tracker (discord_idle_bot.py)

Tracks when team members are idle, offline, or in voice channels during work hours.

### Features

- Tracks idle time (08:00-18:00 Iran time only)
- Tracks offline time
- Tracks voice channel time
- Excludes specified team members (Team Lead, Owner, Seniors)
- Daily reports via Discord commands

### Setup

#### Step 1: Enable Additional Intents

In Discord Developer Portal → Bot, enable:
- ✅ PRESENCE INTENT (for idle tracking)
- ✅ SERVER MEMBERS INTENT (for member list)

#### Step 2: Update .env

```bash
# Add to existing .env file
DISCORD_GUILD_ID=680666361524912130
```

#### Step 3: Install Dependencies

```bash
pip install discord.py python-dotenv
```

### Running as Systemd Service (Recommended)

```bash
# Create service file
sudo nano /etc/systemd/system/discord-idle-tracker.service

# Content:
[Unit]
Description=Discord Idle Time Tracker Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/infrastructure/scripts/discord
ExecStart=/usr/bin/python3 /root/infrastructure/scripts/discord/discord_idle_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable discord-idle-tracker.service
sudo systemctl start discord-idle-tracker.service
```

### Discord Commands

| Command | Description |
|---------|-------------|
| `!idle` | Show today's idle time summary |
| `!voice` | Show today's voice time summary |
| `!status` | Show current user statuses |

### Data Files

| File | Purpose |
|------|---------|
| `idle_time_database.json` | Daily idle minutes per user |
| `offline_time_database.json` | Daily offline minutes per user |
| `voice_time_database.json` | Daily voice channel minutes per user |
| `idle_time_users.json` | User ID to name mapping |

---

## Part 3: Deploying to EC2 or VPS

For reliable 24/7 tracking, deploy to a cloud server.

### Prerequisites

- Ubuntu 22.04+ or Debian 12+ instance
- Python 3.10+ installed
- Open outbound HTTPS (port 443) for Discord API
- No inbound ports required (bot connects outbound only)

### Quick Deploy Script

```bash
#!/bin/bash
# Run on your EC2/VPS instance

# 1. Install Python
sudo apt update && sudo apt install -y python3 python3-pip

# 2. Install dependencies
pip3 install discord.py python-dotenv

# 3. Create bot directory
sudo mkdir -p /opt/discord-bot

# 4. Copy files (from your local machine)
# scp -r /root/infrastructure/scripts/discord/* user@server:/opt/discord-bot/

# 5. Create .env file with your tokens
cat > /opt/discord-bot/.env << 'EOF'
DISCORD_BOT_TOKEN=your_token_here
DISCORD_GUILD_ID=680666361524912130
EOF

# 6. Create systemd service
sudo cat > /etc/systemd/system/discord-idle-tracker.service << 'EOF'
[Unit]
Description=Discord Idle Time Tracker Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/discord-bot
ExecStart=/usr/bin/python3 /opt/discord-bot/discord_idle_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 7. Start the service
sudo systemctl daemon-reload
sudo systemctl enable discord-idle-tracker.service
sudo systemctl start discord-idle-tracker.service

echo "Bot deployed! Check status with: systemctl status discord-idle-tracker"
```

### Migration Checklist

When moving to a new server:

1. ✅ Copy `.env` file (contains secrets - DO NOT COMMIT!)
2. ✅ Copy `*.json` data files (historical data)
3. ✅ Install Python dependencies
4. ✅ Create systemd service
5. ✅ Test: `journalctl -u discord-idle-tracker.service -f`

### Portable Design

The bot is designed to be portable:
- All configuration is in `.env` file
- Data files are JSON (easy to move)
- No hardcoded paths except in systemd service
- Works on any Linux with Python 3.10+

### Cost-Effective Hosting Options

| Provider | Instance | Monthly Cost |
|----------|----------|--------------|
| AWS EC2 | t3.micro (free tier) | $0-8 |
| DigitalOcean | Basic Droplet | $4-6 |
| Hetzner | CX11 | €3.5 |
| Oracle Cloud | Always Free | $0 |

### Security Notes

- **Never commit `.env` file** (contains bot token)
- Token should have minimal permissions
- Bot only needs read access, not admin
- Consider using AWS Secrets Manager or similar for production
