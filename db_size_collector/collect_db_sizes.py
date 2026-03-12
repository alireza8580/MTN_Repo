#!/usr/bin/env python3
"""
Database Size Collector - Main Script
Collects database sizes from all platforms and stores in Oracle.

Usage:
    python3 collect_db_sizes.py                    # Collect all platforms
    python3 collect_db_sizes.py --platform oracle  # Collect only Oracle
    python3 collect_db_sizes.py --dry-run          # Test without storing
    python3 collect_db_sizes.py --cleanup 365      # Delete data older than 365 days

This script is designed to be run daily via cron.
"""

import os
import sys
import argparse
import logging
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ORACLE_TARGET, SSH_CONFIG, DB_CREDENTIALS, DATA_DIRECTORIES,
    INVENTORY_PATH, LOG_CONFIG, COLLECTION_CONFIG, EMAIL_CONFIG
)
from inventory_parser import InventoryParser
from collectors import (
    SizeResult, OracleCollector, MySQLCollector, MongoCollector,
    PostgresCollector, CassandraCollector, MSSQLCollector
)
from storage import OracleStorage, create_storage
from notifier import EmailNotifier, ExecutionLog, CommandExecution


# Setup logging
def setup_logging(log_file: str = None, log_level: str = 'INFO') -> logging.Logger:
    """Configure logging for the application."""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        try:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=LOG_CONFIG.get('max_bytes', 10485760),
                backupCount=LOG_CONFIG.get('backup_count', 5)
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not setup file logging: {e}")
    
    return logger


logger = setup_logging(
    log_file=LOG_CONFIG.get('log_file'),
    log_level=LOG_CONFIG.get('log_level', 'INFO')
)


class DatabaseSizeCollector:
    """Main collector that orchestrates size collection across all platforms."""
    
    PLATFORMS = ['oracle', 'mysql', 'mongo', 'postgres', 'cassandra', 'mssql']
    
    def __init__(self, inventory_path: str, dry_run: bool = False, send_email: bool = True):
        """
        Initialize the collector.
        
        Args:
            inventory_path: Path to Ansible inventory directory
            dry_run: If True, collect but don't store results
            send_email: If True, send email notification on completion
        """
        self.inventory_path = inventory_path
        self.dry_run = dry_run
        self.send_email = send_email
        self.parser = InventoryParser(inventory_path)
        
        # Initialize execution log for tracking commands
        self.exec_log = ExecutionLog()
        
        # Initialize collectors
        self.collectors = {
            'oracle': OracleCollector(SSH_CONFIG, DB_CREDENTIALS.get('oracle', {})),
            'mysql': MySQLCollector(SSH_CONFIG, DB_CREDENTIALS.get('mysql', {}), DATA_DIRECTORIES.get('mysql', {})),
            'mongo': MongoCollector(SSH_CONFIG, DB_CREDENTIALS.get('mongo', {}), DATA_DIRECTORIES.get('mongo', {})),
            'postgres': PostgresCollector(SSH_CONFIG, DB_CREDENTIALS.get('postgres', {}), DATA_DIRECTORIES.get('postgres', {})),
            'cassandra': CassandraCollector(SSH_CONFIG, DATA_DIRECTORIES.get('cassandra', {})),
            'mssql': MSSQLCollector(SSH_CONFIG)
        }
        
        # Initialize storage (if not dry run)
        self.storage = None
        if not dry_run:
            try:
                self.storage = create_storage(ORACLE_TARGET)
            except Exception as e:
                logger.error(f"Could not initialize Oracle storage: {e}")
        
        # Initialize email notifier
        self.notifier = EmailNotifier(EMAIL_CONFIG) if send_email else None
    
    def collect_host(self, platform: str, host_info: Dict) -> SizeResult:
        """Collect sizes for a single host."""
        collector = self.collectors.get(platform)
        hostname = host_info.get('hostname', host_info.get('ansible_host', 'unknown'))
        
        if not collector:
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=None,
                physical_size_gb=None,
                logical_size_gb=None,
                status='FAILED',
                error_message=f'No collector for platform: {platform}'
            )
        
        # Track command execution
        cmd_start = datetime.now()
        command_desc = f"collect_{platform}_size({hostname})"
        
        try:
            result = collector.collect(host_info)
            cmd_end = datetime.now()
            
            # Log command execution
            self.exec_log.add_command(CommandExecution(
                platform=platform,
                hostname=hostname,
                command=command_desc,
                start_time=cmd_start,
                end_time=cmd_end,
                success=(result.status == 'SUCCESS'),
                output=f"physical={result.physical_size_gb}GB, logical={result.logical_size_gb}GB" if result.status == 'SUCCESS' else '',
                error=result.error_message or ''
            ))
            
            return result
            
        except Exception as e:
            cmd_end = datetime.now()
            self.exec_log.add_command(CommandExecution(
                platform=platform,
                hostname=hostname,
                command=command_desc,
                start_time=cmd_start,
                end_time=cmd_end,
                success=False,
                error=str(e)
            ))
            raise
    
    def collect_platform(self, platform: str) -> List[SizeResult]:
        """
        Collect sizes for all hosts of a platform.
        
        Args:
            platform: Platform name (oracle, mysql, etc.)
        
        Returns:
            List of SizeResult objects
        """
        hosts = self.parser.get_hosts(platform)
        
        if not hosts:
            logger.warning(f"No hosts found for {platform}")
            return []
        
        logger.info(f"Collecting {platform}: {len(hosts)} hosts")
        
        results = []
        workers = COLLECTION_CONFIG.get('parallel_workers', 5)
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_host = {
                executor.submit(self.collect_host, platform, host): host
                for host in hosts
            }
            
            for future in as_completed(future_to_host):
                host = future_to_host[future]
                try:
                    result = future.result(timeout=COLLECTION_CONFIG.get('timeout_per_host', 120))
                    results.append(result)
                    
                    status_icon = '✓' if result.status == 'SUCCESS' else '✗'
                    logger.debug(f"  {status_icon} {result.hostname}: physical={result.physical_size_gb}GB, logical={result.logical_size_gb}GB")
                    
                except Exception as e:
                    hostname = host.get('hostname', 'unknown')
                    logger.error(f"  ✗ {hostname}: {e}")
                    results.append(SizeResult(
                        hostname=hostname,
                        ip_address=host.get('ansible_host', ''),
                        port=None,
                        physical_size_gb=None,
                        logical_size_gb=None,
                        status='FAILED',
                        error_message=str(e)
                    ))
        
        return results
    
    def collect_all(self, platforms: Optional[List[str]] = None) -> Dict[str, List[SizeResult]]:
        """
        Collect sizes for all (or specified) platforms.
        
        Args:
            platforms: List of platforms to collect (None = all)
        
        Returns:
            Dictionary of platform -> results
        """
        if platforms is None:
            platforms = self.PLATFORMS
        
        all_results = {}
        collection_date = date.today()
        
        for platform in platforms:
            if platform not in self.PLATFORMS:
                logger.warning(f"Unknown platform: {platform}")
                continue
            
            start_time = datetime.now()
            results = self.collect_platform(platform)
            end_time = datetime.now()
            
            all_results[platform] = results
            
            # Store results
            if results and self.storage and not self.dry_run:
                try:
                    self.storage.store_results(platform, results, collection_date)
                    self.storage.store_summary(platform, results, start_time, end_time, collection_date)
                except Exception as e:
                    logger.error(f"Error storing {platform} results: {e}")
            
            # Calculate summary metrics
            successful = len([r for r in results if r.status == 'SUCCESS'])
            total_physical = sum(r.physical_size_gb or 0 for r in results if r.status == 'SUCCESS')
            total_logical = sum(r.logical_size_gb or 0 for r in results if r.status == 'SUCCESS')
            elapsed_seconds = (end_time - start_time).total_seconds()
            
            # Format elapsed time
            if elapsed_seconds < 60:
                elapsed_str = f"{elapsed_seconds:.1f}s"
            elif elapsed_seconds < 3600:
                elapsed_str = f"{int(elapsed_seconds // 60)}m {int(elapsed_seconds % 60)}s"
            else:
                elapsed_str = f"{int(elapsed_seconds // 3600)}h {int((elapsed_seconds % 3600) // 60)}m"
            
            # Add platform summary to execution log
            self.exec_log.add_platform_summary(platform, {
                'total': len(results),
                'successful': successful,
                'physical_gb': total_physical,
                'logical_gb': total_logical,
                'elapsed_seconds': elapsed_seconds,
                'elapsed_str': elapsed_str,
                'start_time': start_time.strftime('%H:%M:%S'),
                'end_time': end_time.strftime('%H:%M:%S')
            })
            
            logger.info(f"{platform.upper()} Summary: {successful}/{len(results)} hosts, "
                       f"Physical: {total_physical:.2f}GB, Logical: {total_logical:.2f}GB, "
                       f"Elapsed: {elapsed_str}")
        
        return all_results
    
    def send_notification(self, results: Dict[str, List[SizeResult]], success: bool = True, error: str = None) -> bool:
        """Send email notification with execution details."""
        if not self.notifier:
            return False
        
        self.exec_log.finish()
        
        if success:
            return self.notifier.send_success_notification(self.exec_log, results)
        else:
            return self.notifier.send_failure_notification(self.exec_log, error or 'Unknown error')
    
    def cleanup_old_data(self, days_to_keep: int = 365) -> None:
        """Delete data older than specified days."""
        if self.storage:
            self.storage.delete_old_data(days_to_keep)
        else:
            logger.warning("No storage configured - cannot cleanup")


def print_results_table(results: Dict[str, List[SizeResult]]) -> None:
    """Print results in a formatted table."""
    print("\n" + "=" * 80)
    print("DATABASE SIZE COLLECTION RESULTS")
    print("=" * 80)
    print(f"Collection Date: {date.today()}")
    print("-" * 80)
    
    for platform, platform_results in results.items():
        if not platform_results:
            continue
        
        print(f"\n{platform.upper()}")
        print("-" * 40)
        print(f"{'Hostname':<20} {'IP':<15} {'Physical(GB)':<12} {'Logical(GB)':<12} {'Status':<10}")
        print("-" * 69)
        
        for r in sorted(platform_results, key=lambda x: x.hostname):
            physical = f"{r.physical_size_gb:.2f}" if r.physical_size_gb else "N/A"
            logical = f"{r.logical_size_gb:.2f}" if r.logical_size_gb else "N/A"
            print(f"{r.hostname:<20} {r.ip_address:<15} {physical:<12} {logical:<12} {r.status:<10}")
        
        # Platform totals
        successful = [r for r in platform_results if r.status == 'SUCCESS']
        total_physical = sum(r.physical_size_gb or 0 for r in successful)
        total_logical = sum(r.logical_size_gb or 0 for r in successful)
        
        print("-" * 69)
        print(f"{'TOTAL':<20} {'':15} {total_physical:<12.2f} {total_logical:<12.2f} {len(successful)}/{len(platform_results)}")
    
    print("\n" + "=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Collect database sizes and store in Oracle',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Collect all platforms
  %(prog)s --platform oracle mysql  # Collect Oracle and MySQL only
  %(prog)s --dry-run                # Test collection without storing
  %(prog)s --cleanup 90             # Delete data older than 90 days
  %(prog)s --verbose                # Show detailed output
  %(prog)s --no-email               # Disable email notification
        """
    )
    
    parser.add_argument(
        '--platform', '-p',
        nargs='+',
        choices=['oracle', 'mysql', 'mongo', 'postgres', 'cassandra', 'mssql'],
        help='Platforms to collect (default: all)'
    )
    
    parser.add_argument(
        '--dry-run', '-n',
        action='store_true',
        help='Collect but do not store results'
    )
    
    parser.add_argument(
        '--cleanup',
        type=int,
        metavar='DAYS',
        help='Delete data older than DAYS days'
    )
    
    parser.add_argument(
        '--inventory', '-i',
        default=None,
        help='Path to inventory directory (default: from config)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Minimal output'
    )
    
    parser.add_argument(
        '--no-email',
        action='store_true',
        help='Disable email notification on completion'
    )
    
    parser.add_argument(
        '--email-test',
        action='store_true',
        help='Send email to test recipient only'
    )
    
    args = parser.parse_args()
    
    # Adjust log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # Determine inventory path
    if args.inventory:
        inventory_path = args.inventory
    else:
        # Default to relative path from script location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        inventory_path = os.path.join(script_dir, '..', INVENTORY_PATH)
    
    # Validate inventory path
    if not os.path.exists(inventory_path):
        logger.error(f"Inventory path not found: {inventory_path}")
        sys.exit(1)
    
    logger.info(f"Using inventory: {inventory_path}")
    
    # Update email config if test mode requested
    if args.email_test:
        EMAIL_CONFIG['test_mode'] = True
    
    # Create collector
    send_email = not args.no_email and not args.dry_run
    collector = DatabaseSizeCollector(inventory_path, dry_run=args.dry_run, send_email=send_email)
    
    # Handle cleanup
    if args.cleanup:
        logger.info(f"Cleaning up data older than {args.cleanup} days")
        collector.cleanup_old_data(args.cleanup)
        return
    
    # Collect sizes
    try:
        start_time = datetime.now()
        results = collector.collect_all(platforms=args.platform)
        end_time = datetime.now()
        
        # Print results
        if not args.quiet:
            print_results_table(results)
        
        # Summary
        total_hosts = sum(len(r) for r in results.values())
        successful_hosts = sum(len([x for x in r if x.status == 'SUCCESS']) for r in results.values())
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"Collection complete: {successful_hosts}/{total_hosts} hosts in {duration:.1f}s")
        
        if args.dry_run:
            logger.info("DRY RUN - Results were not stored")
        
        # Send success notification
        if send_email:
            if collector.send_notification(results, success=True):
                logger.info("Email notification sent successfully")
            else:
                logger.warning("Failed to send email notification")
        
        # Exit code based on success rate
        if successful_hosts == 0 and total_hosts > 0:
            sys.exit(1)  # All failed
        elif successful_hosts < total_hosts:
            sys.exit(2)  # Partial failure
            
    except Exception as e:
        logger.error(f"Collection failed with error: {e}")
        
        # Send failure notification
        if send_email:
            collector.send_notification({}, success=False, error=str(e))
        
        sys.exit(1)


if __name__ == '__main__':
    main()
