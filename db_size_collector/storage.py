#!/usr/bin/env python3
"""
Database Size Collector - Oracle Storage Module
Handles storing collected data into the Oracle target database.
"""

import logging
from datetime import date, datetime
from typing import List, Dict, Optional
from contextlib import contextmanager

try:
    import oracledb
    ORACLEDB_AVAILABLE = True
except ImportError:
    ORACLEDB_AVAILABLE = False
    oracledb = None

try:
    import cx_Oracle
    CX_ORACLE_AVAILABLE = True
except ImportError:
    CX_ORACLE_AVAILABLE = False
    cx_Oracle = None

from collectors import SizeResult

logger = logging.getLogger(__name__)


class OracleStorage:
    """Store collected database sizes in Oracle database."""
    
    # Insert statements for each platform
    INSERT_STATEMENTS = {
        'oracle': """
            INSERT INTO oracle_db_sizes (
                collection_date, hostname, ip_address, instance_name, db_name,
                physical_size_gb, logical_size_gb, application, environment,
                db_version, collection_status, error_message
            ) VALUES (
                :collection_date, :hostname, :ip_address, :instance_name, :db_name,
                :physical_size_gb, :logical_size_gb, :application, :environment,
                :db_version, :collection_status, :error_message
            )
        """,
        'mysql': """
            INSERT INTO mysql_db_sizes (
                collection_date, hostname, ip_address, port,
                physical_size_gb, logical_size_gb, application, environment,
                db_version, role, collection_status, error_message
            ) VALUES (
                :collection_date, :hostname, :ip_address, :port,
                :physical_size_gb, :logical_size_gb, :application, :environment,
                :db_version, :role, :collection_status, :error_message
            )
        """,
        'mongo': """
            INSERT INTO mongo_db_sizes (
                collection_date, hostname, ip_address, port,
                physical_size_gb, logical_size_gb, replicaset_name, role,
                application, environment, db_version, collection_status, error_message
            ) VALUES (
                :collection_date, :hostname, :ip_address, :port,
                :physical_size_gb, :logical_size_gb, :replicaset_name, :role,
                :application, :environment, :db_version, :collection_status, :error_message
            )
        """,
        'postgres': """
            INSERT INTO postgres_db_sizes (
                collection_date, hostname, ip_address, port,
                physical_size_gb, logical_size_gb, role,
                application, environment, db_version, collection_status, error_message
            ) VALUES (
                :collection_date, :hostname, :ip_address, :port,
                :physical_size_gb, :logical_size_gb, :role,
                :application, :environment, :db_version, :collection_status, :error_message
            )
        """,
        'cassandra': """
            INSERT INTO cassandra_db_sizes (
                collection_date, hostname, ip_address, port,
                physical_size_gb, cluster_name, datacenter,
                application, environment, db_version, collection_status, error_message
            ) VALUES (
                :collection_date, :hostname, :ip_address, :port,
                :physical_size_gb, :cluster_name, :datacenter,
                :application, :environment, :db_version, :collection_status, :error_message
            )
        """,
        'mssql': """
            INSERT INTO mssql_db_sizes (
                collection_date, hostname, ip_address, port,
                physical_size_gb, logical_size_gb, instance_name,
                application, environment, db_version, collection_status, error_message
            ) VALUES (
                :collection_date, :hostname, :ip_address, :port,
                :physical_size_gb, :logical_size_gb, :instance_name,
                :application, :environment, :db_version, :collection_status, :error_message
            )
        """
    }
    
    INSERT_SUMMARY = """
        INSERT INTO collection_summary (
            collection_date, platform, total_hosts, successful_hosts, failed_hosts,
            total_physical_gb, total_logical_gb, start_time, end_time, duration_seconds
        ) VALUES (
            :collection_date, :platform, :total_hosts, :successful_hosts, :failed_hosts,
            :total_physical_gb, :total_logical_gb, :start_time, :end_time, :duration_seconds
        )
    """
    
    def __init__(self, host: str, port: int, service_name: str, user: str, password: str):
        """Initialize Oracle storage connection parameters."""
        self.host = host
        self.port = port
        self.service_name = service_name
        self.user = user
        self.password = password
        self._connection = None
        
        if not ORACLEDB_AVAILABLE and not CX_ORACLE_AVAILABLE:
            raise ImportError("Neither oracledb nor cx_Oracle is available. Install with: pip install oracledb")
    
    @contextmanager
    def get_connection(self):
        """Get database connection as context manager."""
        conn = None
        try:
            dsn = f"{self.host}:{self.port}/{self.service_name}"
            
            if ORACLEDB_AVAILABLE:
                conn = oracledb.connect(user=self.user, password=self.password, dsn=dsn)
            elif CX_ORACLE_AVAILABLE:
                conn = cx_Oracle.connect(user=self.user, password=self.password, dsn=dsn)
            
            yield conn
            conn.commit()
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def _result_to_dict(self, result: SizeResult, collection_date: date, platform: str) -> Dict:
        """Convert SizeResult to dictionary for database insert."""
        base_dict = {
            'collection_date': collection_date,
            'hostname': result.hostname,
            'ip_address': result.ip_address,
            'port': result.port,
            'physical_size_gb': result.physical_size_gb,
            'logical_size_gb': result.logical_size_gb,
            'application': result.application[:200] if result.application else None,
            'environment': result.environment,
            'db_version': result.db_version[:50] if result.db_version else None,
            'collection_status': result.status,
            'error_message': result.error_message[:500] if result.error_message else None
        }
        
        # Add platform-specific fields
        if platform == 'oracle':
            base_dict['instance_name'] = result.instance_name
            base_dict['db_name'] = result.db_name
        elif platform == 'mysql':
            base_dict['role'] = result.role
        elif platform == 'mongo':
            base_dict['replicaset_name'] = result.replicaset_name
            base_dict['role'] = result.role
        elif platform == 'postgres':
            base_dict['role'] = result.role
        elif platform == 'cassandra':
            base_dict['cluster_name'] = result.cluster_name
            base_dict['datacenter'] = result.datacenter
            # Remove logical_size_gb as Cassandra doesn't have it
            del base_dict['logical_size_gb']
        elif platform == 'mssql':
            base_dict['instance_name'] = result.instance_name
        
        return base_dict
    
    def store_results(self, platform: str, results: List[SizeResult], 
                      collection_date: Optional[date] = None) -> int:
        """
        Store collection results for a platform.
        
        Args:
            platform: Database platform name
            results: List of SizeResult objects
            collection_date: Date of collection (defaults to today)
        
        Returns:
            Number of rows inserted
        """
        if not results:
            return 0
        
        if collection_date is None:
            collection_date = date.today()
        
        if platform not in self.INSERT_STATEMENTS:
            raise ValueError(f"Unknown platform: {platform}")
        
        sql = self.INSERT_STATEMENTS[platform]
        
        rows_inserted = 0
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for result in results:
                try:
                    data = self._result_to_dict(result, collection_date, platform)
                    cursor.execute(sql, data)
                    rows_inserted += 1
                except Exception as e:
                    logger.error(f"Error inserting {result.hostname}: {e}")
            
            conn.commit()
        
        logger.info(f"Inserted {rows_inserted}/{len(results)} rows for {platform}")
        return rows_inserted
    
    def store_summary(self, platform: str, results: List[SizeResult],
                      start_time: datetime, end_time: datetime,
                      collection_date: Optional[date] = None) -> None:
        """Store collection summary."""
        if collection_date is None:
            collection_date = date.today()
        
        successful = [r for r in results if r.status == 'SUCCESS']
        failed = [r for r in results if r.status != 'SUCCESS']
        
        total_physical = sum(r.physical_size_gb or 0 for r in successful)
        total_logical = sum(r.logical_size_gb or 0 for r in successful)
        
        duration = (end_time - start_time).total_seconds()
        
        data = {
            'collection_date': collection_date,
            'platform': platform,
            'total_hosts': len(results),
            'successful_hosts': len(successful),
            'failed_hosts': len(failed),
            'total_physical_gb': total_physical,
            'total_logical_gb': total_logical,
            'start_time': start_time,
            'end_time': end_time,
            'duration_seconds': duration
        }
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(self.INSERT_SUMMARY, data)
            conn.commit()
        
        logger.info(f"Stored summary for {platform}: {len(successful)} success, {len(failed)} failed")
    
    def delete_old_data(self, days_to_keep: int = 365) -> Dict[str, int]:
        """
        Delete data older than specified days.
        
        Args:
            days_to_keep: Number of days of data to retain
        
        Returns:
            Dictionary of table name -> rows deleted
        """
        tables = [
            'oracle_db_sizes', 'mysql_db_sizes', 'mongo_db_sizes',
            'postgres_db_sizes', 'cassandra_db_sizes', 'mssql_db_sizes',
            'collection_summary'
        ]
        
        deleted = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for table in tables:
                sql = f"DELETE FROM {table} WHERE collection_date < TRUNC(SYSDATE) - :days"
                cursor.execute(sql, {'days': days_to_keep})
                deleted[table] = cursor.rowcount
            
            conn.commit()
        
        logger.info(f"Deleted old data: {deleted}")
        return deleted
    
    def get_latest_collection(self, platform: str) -> Optional[date]:
        """Get the date of the latest collection for a platform."""
        table_map = {
            'oracle': 'oracle_db_sizes',
            'mysql': 'mysql_db_sizes',
            'mongo': 'mongo_db_sizes',
            'postgres': 'postgres_db_sizes',
            'cassandra': 'cassandra_db_sizes',
            'mssql': 'mssql_db_sizes'
        }
        
        if platform not in table_map:
            return None
        
        table = table_map[platform]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT MAX(collection_date) FROM {table}")
            row = cursor.fetchone()
            if row and row[0]:
                return row[0].date() if hasattr(row[0], 'date') else row[0]
        
        return None


def create_storage(config: Dict) -> OracleStorage:
    """
    Create OracleStorage instance from config dictionary.
    
    Args:
        config: Dictionary with keys: host, port, service_name, user, password
    
    Returns:
        OracleStorage instance
    """
    return OracleStorage(
        host=config['host'],
        port=config['port'],
        service_name=config['service_name'],
        user=config['user'],
        password=config['password']
    )
