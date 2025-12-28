# Export Outlook Emails to CSV
# This script runs on Windows and exports emails to WSL-accessible path
# 
# Setup:
# 1. Save this file to: C:\scripts\export_outlook_emails.ps1
# 2. Create Task Scheduler task (see instructions below)
# 3. Emails will be exported to \\wsl$\Ubuntu\root\infrastructure\mtn_emails\
#
# Task Scheduler Setup:
# - Open: taskschd.msc
# - Create Basic Task
# - Trigger: Daily at 8:00 AM (or your preferred time)
# - Action: Start a program
# - Program: powershell.exe
# - Arguments: -ExecutionPolicy Bypass -File "C:\scripts\export_outlook_emails.ps1"

param(
    [int]$DaysBack = 1,
    [string]$OutputPath = "\\wsl$\Ubuntu\root\infrastructure\mtn_emails"
)

# Ensure output directory exists
if (-not (Test-Path $OutputPath)) {
    New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null
}

# Output file with timestamp
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$csvFile = Join-Path $OutputPath "mtn_emails_$timestamp.csv"
$logFile = Join-Path $OutputPath "export_log.txt"

# Log function
function Write-Log {
    param([string]$Message)
    $logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message"
    Add-Content -Path $logFile -Value $logEntry
    Write-Host $logEntry
}

try {
    Write-Log "Starting Outlook email export..."
    
    # Connect to Outlook
    Add-Type -Assembly "Microsoft.Office.Interop.Outlook" -ErrorAction Stop
    $outlook = New-Object -ComObject Outlook.Application
    $namespace = $outlook.GetNamespace("MAPI")
    
    # Get Inbox folder
    $inbox = $namespace.GetDefaultFolder(6)  # 6 = olFolderInbox
    
    # Also get Sent Items
    $sentItems = $namespace.GetDefaultFolder(5)  # 5 = olFolderSentMail
    
    Write-Log "Connected to Outlook. Inbox: $($inbox.Items.Count) items, Sent: $($sentItems.Items.Count) items"
    
    # Calculate date threshold
    $dateThreshold = (Get-Date).AddDays(-$DaysBack)
    
    # Collect emails
    $emails = @()
    
    # Process Inbox
    Write-Log "Processing Inbox..."
    $count = 0
    foreach ($item in $inbox.Items) {
        try {
            if ($item.ReceivedTime -gt $dateThreshold) {
                # Clean body text (remove excessive whitespace, limit length)
                $bodyClean = $item.Body -replace '\s+', ' '
                $bodyClean = $bodyClean.Substring(0, [Math]::Min(5000, $bodyClean.Length))
                
                $emails += [PSCustomObject]@{
                    Folder = "Inbox"
                    Subject = $item.Subject
                    From = $item.SenderName
                    FromEmail = $item.SenderEmailAddress
                    To = $item.To
                    CC = $item.CC
                    ReceivedTime = $item.ReceivedTime.ToString("yyyy-MM-dd HH:mm:ss")
                    Body = $bodyClean
                    Importance = $item.Importance
                }
                $count++
            }
        } catch {
            # Skip problematic items
        }
    }
    Write-Log "Processed $count emails from Inbox"
    
    # Process Sent Items (your replies)
    Write-Log "Processing Sent Items..."
    $count = 0
    foreach ($item in $sentItems.Items) {
        try {
            if ($item.SentOn -gt $dateThreshold) {
                $bodyClean = $item.Body -replace '\s+', ' '
                $bodyClean = $bodyClean.Substring(0, [Math]::Min(5000, $bodyClean.Length))
                
                $emails += [PSCustomObject]@{
                    Folder = "Sent"
                    Subject = $item.Subject
                    From = "Alireza Aghajanzadeh Gheshlaghi"
                    FromEmail = "alireza.aghaja@mtnirancell.ir"
                    To = $item.To
                    CC = $item.CC
                    ReceivedTime = $item.SentOn.ToString("yyyy-MM-dd HH:mm:ss")
                    Body = $bodyClean
                    Importance = $item.Importance
                }
                $count++
            }
        } catch {
            # Skip problematic items
        }
    }
    Write-Log "Processed $count emails from Sent Items"
    
    # Export to CSV
    if ($emails.Count -gt 0) {
        $emails | Sort-Object ReceivedTime -Descending | Export-Csv -Path $csvFile -NoTypeInformation -Encoding UTF8
        Write-Log "Exported $($emails.Count) emails to: $csvFile"
        
        # Clean up old files (keep last 7 days)
        $oldFiles = Get-ChildItem -Path $OutputPath -Filter "mtn_emails_*.csv" | 
                    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) }
        foreach ($oldFile in $oldFiles) {
            Remove-Item $oldFile.FullName -Force
            Write-Log "Deleted old export: $($oldFile.Name)"
        }
    } else {
        Write-Log "No emails found in the last $DaysBack days"
    }
    
    Write-Log "Export completed successfully"
    
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    exit 1
}
