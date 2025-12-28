# Discord Idle Tracker Bot
# Build: docker build -t discord-idle-bot .
# Run: docker run -d --name discord-bot --env-file .env discord-idle-bot

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir discord.py python-dotenv

# Copy bot files
COPY discord_idle_bot.py .
COPY discord_exporter.py .

# Create data directory
RUN mkdir -p /app/data

# Set data directory (can be mounted as volume)
ENV DATA_DIR=/app/data

# Run the bot
CMD ["python", "discord_idle_bot.py"]
