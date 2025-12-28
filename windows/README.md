# Outlook Email Export Script for WSL

## Purpose
This script runs on Windows and automatically exports Outlook emails to a location accessible by WSL, so the AI assistant can read and learn from your communication patterns.

## Files

| File | Description |
|------|-------------|
| `export_outlook_emails.ps1` | Main PowerShell script |
| `run_export.bat` | Quick-run batch file |

## Setup Instructions

### Step 1: Copy Scripts to Windows

From WSL, copy the scripts to Windows:
```bash
# Create Windows scripts folder
mkdir -p /mnt/c/scripts

# Copy scripts
cp /root/infrastructure/scripts/windows/export_outlook_emails.ps1 /mnt/c/scripts/
cp /root/infrastructure/scripts/windows/run_export.bat /mnt/c/scripts/
```

### Step 2: Create Output Directory

The script exports to `\\wsl$\Ubuntu\root\infrastructure\mtn_emails\`

If your WSL distro name is different, edit the script:
```powershell
$OutputPath = "\\wsl$\YOUR_DISTRO_NAME\root\infrastructure\mtn_emails"
```

### Step 3: Manual Test

1. Double-click `C:\scripts\run_export.bat`
2. Check if CSV file appears in `/root/infrastructure/mtn_emails/`

### Step 4: Schedule Automatic Export

1. Press `Win+R` → type `taskschd.msc` → Enter
2. Click "Create Basic Task..."
3. Name: `Export Outlook Emails`
4. Trigger: `Daily` at `08:00`
5. Action: `Start a program`
6. Program: `powershell.exe`
7. Arguments: `-ExecutionPolicy Bypass -File "C:\scripts\export_outlook_emails.ps1"`
8. Check "Open Properties dialog" → Finish
9. In Properties:
   - Check "Run whether user is logged on or not"
   - Check "Run with highest privileges"

## Configuration

Edit `export_outlook_emails.ps1` to change:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `$DaysBack` | 7 | Number of days to export |
| `$OutputPath` | `\\wsl$\Ubuntu\root\infrastructure\mtn_emails` | Output directory |

## Output Format

The script exports emails as CSV with these columns:
- `Folder` - Inbox or Sent
- `Subject` - Email subject
- `From` - Sender name
- `FromEmail` - Sender email address
- `To` - Recipients
- `CC` - CC recipients
- `ReceivedTime` - Date and time
- `Body` - Email body (truncated to 5000 chars)
- `Importance` - High/Normal/Low

## Cleanup

The script automatically deletes exports older than 7 days to save space.

## Troubleshooting

### Script doesn't run
- Ensure Outlook is installed and configured
- Run PowerShell as Administrator for first test
- Check execution policy: `Get-ExecutionPolicy`

### WSL path not found
- Check your distro name: `wsl -l -v`
- Update `$OutputPath` in the script

### No emails exported
- Check `export_log.txt` in the output folder
- Verify Outlook is not in offline mode
- Increase `$DaysBack` parameter

### Permission denied
- Run Task Scheduler with highest privileges
- Check WSL directory permissions: `chmod 777 /root/infrastructure/mtn_emails`

## Usage with AI Assistant

After export, the AI assistant can read the emails:
```
# In VS Code Copilot Chat:
Read the latest MTN emails from /root/infrastructure/mtn_emails/ and help me draft a response
```
