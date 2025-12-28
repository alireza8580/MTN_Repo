@echo off
REM Run this script to manually export Outlook emails
REM Or schedule it via Task Scheduler

echo Exporting Outlook emails to WSL...
powershell.exe -ExecutionPolicy Bypass -File "%~dp0export_outlook_emails.ps1"
echo Done!
pause
