#!/usr/bin/env python3
"""
Database Size Collector - Email Notification Module
Sends email notifications on job completion with execution details.
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CommandExecution:
    """Record of a command execution."""
    platform: str
    hostname: str
    command: str
    start_time: datetime
    end_time: datetime
    success: bool
    output: str = ''
    error: str = ''
    
    @property
    def elapsed_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def elapsed_str(self) -> str:
        """Format elapsed time as human readable string."""
        seconds = self.elapsed_seconds
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"


@dataclass
class ExecutionLog:
    """Log of all executions during a collection run."""
    job_start: datetime = field(default_factory=datetime.now)
    job_end: Optional[datetime] = None
    commands: List[CommandExecution] = field(default_factory=list)
    platform_summaries: Dict[str, Dict] = field(default_factory=dict)
    
    def add_command(self, cmd: CommandExecution):
        """Add a command execution record."""
        self.commands.append(cmd)
    
    def add_platform_summary(self, platform: str, summary: Dict):
        """Add platform collection summary."""
        self.platform_summaries[platform] = summary
    
    def finish(self):
        """Mark job as finished."""
        self.job_end = datetime.now()
    
    @property
    def total_elapsed_seconds(self) -> float:
        if self.job_end:
            return (self.job_end - self.job_start).total_seconds()
        return 0
    
    @property
    def total_elapsed_str(self) -> str:
        seconds = self.total_elapsed_seconds
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}h {minutes}m {secs}s"
    
    @property
    def success_count(self) -> int:
        return sum(1 for cmd in self.commands if cmd.success)
    
    @property
    def failure_count(self) -> int:
        return sum(1 for cmd in self.commands if not cmd.success)


class EmailNotifier:
    """Send email notifications for job completion."""
    
    def __init__(self, config: Dict):
        self.enabled = config.get('enabled', True)
        self.smtp_server = config.get('smtp_server', 'smtp.office365.com')
        self.smtp_port = config.get('smtp_port', 587)
        self.use_tls = config.get('use_tls', True)
        
        self.username = config.get('username', '')
        # Password from environment variable or config
        self.password = os.environ.get('EMAIL_PASSWORD', config.get('password', ''))
        
        self.from_address = config.get('from_address', '')
        self.to_addresses = config.get('to_addresses', [])
        self.cc_addresses = config.get('cc_addresses', [])
        
        self.test_mode = config.get('test_mode', False)
        self.test_recipient = config.get('test_recipient', '')
        
        self.subject_prefix = config.get('subject_prefix', '[DB Size Collector]')
    
    def _get_recipients(self) -> List[str]:
        """Get recipients based on test mode."""
        if self.test_mode and self.test_recipient:
            return [self.test_recipient]
        return self.to_addresses
    
    def send_success_notification(self, exec_log: ExecutionLog, results: Dict) -> bool:
        """Send success notification with execution details."""
        if not self.enabled:
            logger.info("Email notifications disabled")
            return False
        
        if not self.password:
            logger.warning("Email password not configured - skipping notification")
            return False
        
        subject = f"{self.subject_prefix} Collection Completed Successfully - {date.today()}"
        html_body = self._build_success_html(exec_log, results)
        
        return self._send_email(subject, html_body)
    
    def send_failure_notification(self, exec_log: ExecutionLog, error: str) -> bool:
        """Send failure notification."""
        if not self.enabled:
            return False
        
        if not self.password:
            logger.warning("Email password not configured - skipping notification")
            return False
        
        subject = f"{self.subject_prefix} Collection FAILED - {date.today()}"
        html_body = self._build_failure_html(exec_log, error)
        
        return self._send_email(subject, html_body)
    
    def _build_success_html(self, exec_log: ExecutionLog, results: Dict) -> str:
        """Build HTML email body for success notification."""
        
        # Calculate totals
        total_hosts = sum(len(r) for r in results.values())
        successful_hosts = sum(len([x for x in r if x.status == 'SUCCESS']) for r in results.values())
        total_physical_gb = sum(
            sum(x.physical_size_gb or 0 for x in r if x.status == 'SUCCESS') 
            for r in results.values()
        )
        total_logical_gb = sum(
            sum(x.logical_size_gb or 0 for x in r if x.status == 'SUCCESS') 
            for r in results.values()
        )
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #2e7d32; border-bottom: 2px solid #2e7d32; padding-bottom: 10px; }}
        h2 {{ color: #1976d2; margin-top: 25px; }}
        .summary-box {{ background: #e8f5e9; padding: 15px; border-radius: 5px; margin: 15px 0; }}
        .summary-item {{ display: inline-block; margin-right: 30px; }}
        .summary-label {{ color: #666; font-size: 12px; }}
        .summary-value {{ font-size: 24px; font-weight: bold; color: #2e7d32; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th {{ background: #1976d2; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f5f5f5; }}
        .success {{ color: #2e7d32; }}
        .failed {{ color: #c62828; }}
        .elapsed {{ color: #666; font-family: monospace; }}
        .command {{ font-family: 'Courier New', monospace; font-size: 12px; background: #f5f5f5; padding: 2px 5px; border-radius: 3px; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Database Size Collection - Completed Successfully</h1>
        
        <div class="summary-box">
            <div class="summary-item">
                <div class="summary-label">Total Elapsed Time</div>
                <div class="summary-value">{exec_log.total_elapsed_str}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Hosts Collected</div>
                <div class="summary-value">{successful_hosts}/{total_hosts}</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Physical Size</div>
                <div class="summary-value">{total_physical_gb/1024:.2f} TB</div>
            </div>
            <div class="summary-item">
                <div class="summary-label">Total Logical Size</div>
                <div class="summary-value">{total_logical_gb/1024:.2f} TB</div>
            </div>
        </div>
        
        <h2>Platform Summary</h2>
        <table>
            <tr>
                <th>Platform</th>
                <th>Hosts</th>
                <th>Success</th>
                <th>Physical (GB)</th>
                <th>Logical (GB)</th>
                <th>Elapsed</th>
            </tr>
"""
        
        for platform, summary in exec_log.platform_summaries.items():
            success_rate = summary.get('successful', 0)
            total = summary.get('total', 0)
            physical = summary.get('physical_gb', 0)
            logical = summary.get('logical_gb', 0)
            elapsed = summary.get('elapsed_str', 'N/A')
            
            status_class = 'success' if success_rate == total else 'failed'
            
            html += f"""
            <tr>
                <td><strong>{platform.upper()}</strong></td>
                <td>{total}</td>
                <td class="{status_class}">{success_rate}/{total}</td>
                <td>{physical:,.2f}</td>
                <td>{logical:,.2f}</td>
                <td class="elapsed">{elapsed}</td>
            </tr>
"""
        
        html += """
        </table>
        
        <h2>Executed Commands</h2>
        <table>
            <tr>
                <th>Platform</th>
                <th>Host</th>
                <th>Command</th>
                <th>Status</th>
                <th>Elapsed</th>
            </tr>
"""
        
        # Group commands by platform
        for cmd in exec_log.commands:
            status_class = 'success' if cmd.success else 'failed'
            status_text = 'OK' if cmd.success else 'FAIL'
            
            # Truncate long commands
            cmd_display = cmd.command if len(cmd.command) <= 60 else cmd.command[:57] + '...'
            
            html += f"""
            <tr>
                <td>{cmd.platform}</td>
                <td>{cmd.hostname}</td>
                <td class="command" title="{cmd.command}">{cmd_display}</td>
                <td class="{status_class}">{status_text}</td>
                <td class="elapsed">{cmd.elapsed_str}</td>
            </tr>
"""
        
        html += f"""
        </table>
        
        <div class="footer">
            <strong>Job Details:</strong><br>
            Started: {exec_log.job_start.strftime('%Y-%m-%d %H:%M:%S')}<br>
            Finished: {exec_log.job_end.strftime('%Y-%m-%d %H:%M:%S') if exec_log.job_end else 'N/A'}<br>
            Total Commands: {len(exec_log.commands)}<br>
            Successful: {exec_log.success_count} | Failed: {exec_log.failure_count}<br>
            <br>
            <em>This is an automated notification from DB Size Collector.</em>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def _build_failure_html(self, exec_log: ExecutionLog, error: str) -> str:
        """Build HTML email body for failure notification."""
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        h1 {{ color: #c62828; border-bottom: 2px solid #c62828; padding-bottom: 10px; }}
        .error-box {{ background: #ffebee; padding: 15px; border-radius: 5px; margin: 15px 0; border-left: 4px solid #c62828; }}
        .error-text {{ font-family: 'Courier New', monospace; white-space: pre-wrap; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th {{ background: #c62828; color: white; padding: 10px; text-align: left; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #ddd; }}
        .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ddd; color: #666; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Database Size Collection - FAILED</h1>
        
        <div class="error-box">
            <strong>Error:</strong>
            <div class="error-text">{error}</div>
        </div>
        
        <h2>Executed Commands Before Failure</h2>
        <table>
            <tr>
                <th>Platform</th>
                <th>Host</th>
                <th>Command</th>
                <th>Elapsed</th>
            </tr>
"""
        
        for cmd in exec_log.commands:
            html += f"""
            <tr>
                <td>{cmd.platform}</td>
                <td>{cmd.hostname}</td>
                <td>{cmd.command[:60]}...</td>
                <td>{cmd.elapsed_str}</td>
            </tr>
"""
        
        html += f"""
        </table>
        
        <div class="footer">
            Started: {exec_log.job_start.strftime('%Y-%m-%d %H:%M:%S')}<br>
            Failed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
            Commands executed: {len(exec_log.commands)}
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def _send_email(self, subject: str, html_body: str) -> bool:
        """Send email via SMTP."""
        try:
            recipients = self._get_recipients()
            if not recipients:
                logger.warning("No email recipients configured")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_address
            msg['To'] = ', '.join(recipients)
            if self.cc_addresses and not self.test_mode:
                msg['Cc'] = ', '.join(self.cc_addresses)
            
            # Attach HTML body
            msg.attach(MIMEText(html_body, 'html'))
            
            # Connect and send
            logger.info(f"Sending email to {recipients}")
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                
                all_recipients = recipients + (self.cc_addresses if not self.test_mode else [])
                server.sendmail(self.from_address, all_recipients, msg.as_string())
            
            logger.info("Email sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
