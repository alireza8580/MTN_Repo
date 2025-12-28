#!/usr/bin/env python3
"""
Discord Message Exporter for DBA Team
Exports messages from specified channels to JSON files for AI learning.

Setup:
1. Create bot at https://discord.com/developers/applications
2. Enable MESSAGE CONTENT INTENT in Bot settings
3. Invite bot to server with Read Message History permission
4. Set DISCORD_BOT_TOKEN environment variable

Usage:
    python discord_exporter.py --export-all          # Export all accessible channels
    python discord_exporter.py --channel CHANNEL_ID  # Export specific channel
    python discord_exporter.py --days 7              # Export last 7 days only
"""

import os
import json
import asyncio
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import discord
except ImportError:
    print("Installing discord.py...")
    os.system("pip install discord.py")
    import discord

# Configuration
BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
EXPORT_DIR = Path('/root/infrastructure/discord_exports')
EXPORT_DIR.mkdir(exist_ok=True)

# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

client = discord.Client(intents=intents)


def serialize_message(msg: discord.Message) -> dict:
    """Convert Discord message to serializable dict."""
    return {
        'id': str(msg.id),
        'author': {
            'id': str(msg.author.id),
            'name': msg.author.name,
            'display_name': msg.author.display_name,
            'bot': msg.author.bot
        },
        'content': msg.content,
        'timestamp': msg.created_at.isoformat(),
        'channel': {
            'id': str(msg.channel.id),
            'name': getattr(msg.channel, 'name', 'DM')
        },
        'guild': {
            'id': str(msg.guild.id) if msg.guild else None,
            'name': msg.guild.name if msg.guild else None
        },
        'attachments': [
            {'filename': a.filename, 'url': a.url}
            for a in msg.attachments
        ],
        'embeds': [e.to_dict() for e in msg.embeds],
        'reactions': [
            {'emoji': str(r.emoji), 'count': r.count}
            for r in msg.reactions
        ],
        'reply_to': str(msg.reference.message_id) if msg.reference else None
    }


async def export_channel(channel: discord.TextChannel, days: int = None) -> list:
    """Export messages from a channel."""
    messages = []
    after = None
    
    if days:
        after = datetime.now(timezone.utc) - timedelta(days=days)
    
    try:
        async for msg in channel.history(limit=None, after=after, oldest_first=True):
            messages.append(serialize_message(msg))
            if len(messages) % 100 == 0:
                print(f"  Exported {len(messages)} messages from #{channel.name}")
    except discord.Forbidden:
        print(f"  No permission to read #{channel.name}")
    except Exception as e:
        print(f"  Error reading #{channel.name}: {e}")
    
    return messages


async def export_guild(guild: discord.Guild, days: int = None) -> dict:
    """Export all text channels from a guild."""
    guild_data = {
        'id': str(guild.id),
        'name': guild.name,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'channels': {}
    }
    
    for channel in guild.text_channels:
        print(f"Exporting #{channel.name}...")
        messages = await export_channel(channel, days)
        if messages:
            guild_data['channels'][channel.name] = {
                'id': str(channel.id),
                'messages': messages,
                'message_count': len(messages)
            }
            print(f"  Total: {len(messages)} messages")
    
    return guild_data


def save_export(data: dict, filename: str):
    """Save export to JSON file."""
    filepath = EXPORT_DIR / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved to {filepath}")
    return filepath


@client.event
async def on_ready():
    print(f"Bot logged in as {client.user}")
    print(f"Connected to {len(client.guilds)} server(s)")
    
    args = client._export_args
    
    for guild in client.guilds:
        print(f"\n=== Exporting {guild.name} ===")
        
        if args.channel:
            # Export specific channel
            channel = guild.get_channel(int(args.channel))
            if channel:
                messages = await export_channel(channel, args.days)
                data = {
                    'guild': guild.name,
                    'channel': channel.name,
                    'exported_at': datetime.now(timezone.utc).isoformat(),
                    'messages': messages
                }
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                save_export(data, f"{guild.name}_{channel.name}_{timestamp}.json")
        else:
            # Export all channels
            data = await export_guild(guild, args.days)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_export(data, f"{guild.name}_{timestamp}.json")
    
    print("\nExport complete!")
    await client.close()


def main():
    parser = argparse.ArgumentParser(description='Discord Message Exporter')
    parser.add_argument('--channel', help='Specific channel ID to export')
    parser.add_argument('--days', type=int, help='Only export last N days')
    parser.add_argument('--token', help='Bot token (or use DISCORD_BOT_TOKEN env var)')
    args = parser.parse_args()
    
    token = args.token or BOT_TOKEN
    if not token:
        print("Error: No bot token provided!")
        print("Set DISCORD_BOT_TOKEN environment variable or use --token")
        print("\nTo get a bot token:")
        print("1. Go to https://discord.com/developers/applications")
        print("2. Create New Application → Bot → Reset Token")
        print("3. Enable MESSAGE CONTENT INTENT")
        print("4. Invite bot with Read Message History permission")
        return
    
    # Store args for on_ready to access
    client._export_args = args
    
    print("Starting Discord exporter...")
    client.run(token)


if __name__ == '__main__':
    main()
