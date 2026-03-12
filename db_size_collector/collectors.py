#!/usr/bin/env python3
"""
Database Size Collector - Collector Modules
Contains functions to collect physical and logical sizes for each database platform.
"""

import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class SizeResult:
    """Result of a size collection operation."""
    hostname: str
    ip_address: str
    port: Optional[int]
    physical_size_gb: Optional[float]
    logical_size_gb: Optional[float]
    instance_name: Optional[str] = None
    db_name: Optional[str] = None
    application: Optional[str] = None
    environment: str = 'PROD'
    db_version: Optional[str] = None
    role: Optional[str] = None
    replicaset_name: Optional[str] = None
    cluster_name: Optional[str] = None
    datacenter: Optional[str] = None
    status: str = 'SUCCESS'
    error_message: Optional[str] = None


class SSHClient:
    """SSH client wrapper for executing remote commands."""
    
    def __init__(self, hostname: str, username: str, key_filename: Optional[str] = None, 
                 password: Optional[str] = None, timeout: int = 30):
        self.hostname = hostname
        self.username = username
        self.key_filename = key_filename
        self.password = password
        self.timeout = timeout
    
    def execute(self, command: str) -> Tuple[str, str, int]:
        """
        Execute a command via SSH.
        Returns: (stdout, stderr, return_code)
        """
        ssh_cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10']
        
        if self.key_filename:
            ssh_cmd.extend(['-i', self.key_filename])
        
        ssh_cmd.append(f'{self.username}@{self.hostname}')
        ssh_cmd.append(command)
        
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return '', 'SSH command timed out', -1
        except Exception as e:
            return '', str(e), -1


class BaseCollector(ABC):
    """Base class for database size collectors."""
    
    def __init__(self, ssh_config: Dict):
        self.ssh_config = ssh_config
    
    @abstractmethod
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """Collect physical size in GB via SSH du command."""
        pass
    
    @abstractmethod
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """Collect logical size in GB via database query."""
        pass
    
    @abstractmethod
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect both physical and logical sizes."""
        pass
    
    def _get_ssh_client(self, host_info: Dict, username_key: str = 'username') -> SSHClient:
        """Create SSH client for a host."""
        return SSHClient(
            hostname=host_info.get('ansible_host', host_info.get('ip_address')),
            username=self.ssh_config.get(username_key, 'root'),
            key_filename=self.ssh_config.get('key_filename'),
            timeout=self.ssh_config.get('timeout', 30)
        )
    
    def _parse_du_output(self, output: str) -> Optional[float]:
        """Parse du output and convert to GB."""
        try:
            # du -sb returns bytes, du -sk returns KB, du -sm returns MB
            # We'll use du -sb for accuracy
            parts = output.split()
            if parts:
                bytes_val = int(parts[0])
                return round(bytes_val / (1024 ** 3), 2)
        except (ValueError, IndexError):
            pass
        return None


class OracleCollector(BaseCollector):
    """Collector for Oracle databases."""
    
    def __init__(self, ssh_config: Dict, db_credentials: Dict):
        super().__init__(ssh_config)
        self.db_credentials = db_credentials
    
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """
        Oracle Physical Size = datafiles + tempfiles + 100GB buffer (for redo, etc.)
        Query: SELECT sum(bytes)/1024/1024/1024 gb_df FROM v$datafile
                + SELECT sum(bytes)/1024/1024/1024 gb_temp FROM v$tempfile
                + 100
        """
        ssh = self._get_ssh_client(host_info, 'username')
        instance = host_info.get('oracle_application', host_info.get('instance_name', 'ORCL'))
        
        # Get credentials for this host
        creds = self.db_credentials.get(host_info.get('hostname'), 
                                        self.db_credentials.get('default', {}))
        db_user = creds.get('user', 'system')
        db_pass = creds.get('password', '')
        as_sysdba = 'as sysdba' if creds.get('as_sysdba') else ''
        
        query = """
        SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF
        SELECT TO_CHAR(gb_df + gb_temp + 100, '999999.99')
        FROM (SELECT SUM(bytes)/1024/1024/1024 gb_df FROM v\\$datafile),
             (SELECT SUM(bytes)/1024/1024/1024 gb_temp FROM v\\$tempfile);
        EXIT;
        """
        
        # Build sqlplus command
        sqlplus_cmd = f'''export ORACLE_SID={instance}; echo "{query}" | sqlplus -S {db_user}/{db_pass} {as_sysdba}'''
        
        stdout, stderr, rc = ssh.execute(sqlplus_cmd)
        
        if rc == 0 and stdout:
            try:
                return round(float(stdout.strip()), 2)
            except ValueError:
                logger.warning(f"Could not parse Oracle physical size for {host_info.get('hostname')}: {stdout}")
        
        return None
    
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """
        Oracle Logical Size = sum of all segments
        Query: SELECT sum(bytes)/1024/1024/1024 gb FROM dba_segments
        """
        ssh = self._get_ssh_client(host_info, 'username')
        instance = host_info.get('oracle_application', host_info.get('instance_name', 'ORCL'))
        
        creds = self.db_credentials.get(host_info.get('hostname'),
                                        self.db_credentials.get('default', {}))
        db_user = creds.get('user', 'system')
        db_pass = creds.get('password', '')
        as_sysdba = 'as sysdba' if creds.get('as_sysdba') else ''
        
        query = """
        SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF
        SELECT TO_CHAR(SUM(bytes)/1024/1024/1024, '999999.99') FROM dba_segments;
        EXIT;
        """
        
        sqlplus_cmd = f'''export ORACLE_SID={instance}; echo "{query}" | sqlplus -S {db_user}/{db_pass} {as_sysdba}'''
        
        stdout, stderr, rc = ssh.execute(sqlplus_cmd)
        
        if rc == 0 and stdout:
            try:
                return round(float(stdout.strip()), 2)
            except ValueError:
                logger.warning(f"Could not parse Oracle logical size for {host_info.get('hostname')}: {stdout}")
        
        return None
    
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect both sizes for Oracle database."""
        hostname = host_info.get('hostname', 'unknown')
        
        try:
            physical = self.collect_physical_size(host_info)
            logical = self.collect_logical_size(host_info)
            
            status = 'SUCCESS' if (physical is not None or logical is not None) else 'FAILED'
            error = None if status == 'SUCCESS' else 'Could not collect sizes'
            
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=1521,
                physical_size_gb=physical,
                logical_size_gb=logical,
                instance_name=host_info.get('oracle_application'),
                application=host_info.get('oracle_application'),
                environment=host_info.get('environment', 'PROD'),
                db_version=host_info.get('oracle_version'),
                status=status,
                error_message=error
            )
        except Exception as e:
            logger.error(f"Error collecting Oracle sizes for {hostname}: {e}")
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=1521,
                physical_size_gb=None,
                logical_size_gb=None,
                status='FAILED',
                error_message=str(e)
            )


class MySQLCollector(BaseCollector):
    """Collector for MySQL databases."""
    
    def __init__(self, ssh_config: Dict, db_credentials: Dict, data_dirs: Dict):
        super().__init__(ssh_config)
        self.db_credentials = db_credentials
        self.data_dirs = data_dirs
    
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """
        MySQL Physical Size = du on data directory + binlog directory
        """
        ssh = self._get_ssh_client(host_info, 'mysql_username')
        
        data_dir = host_info.get('mysql_data_dir', self.data_dirs.get('data_dir', '/var/lib/mysql'))
        binlog_dir = host_info.get('mysql_binlog_dir', self.data_dirs.get('binlog_dir', data_dir))
        
        # If they're the same, only count once
        if data_dir == binlog_dir:
            cmd = f"du -sb {data_dir} 2>/dev/null | cut -f1"
        else:
            cmd = f"echo $(( $(du -sb {data_dir} 2>/dev/null | cut -f1) + $(du -sb {binlog_dir} 2>/dev/null | cut -f1) ))"
        
        stdout, stderr, rc = ssh.execute(cmd)
        
        if rc == 0 and stdout:
            try:
                bytes_val = int(stdout.strip())
                return round(bytes_val / (1024 ** 3), 2)
            except ValueError:
                logger.warning(f"Could not parse MySQL physical size for {host_info.get('hostname')}: {stdout}")
        
        return None
    
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """
        MySQL Logical Size = SUM(data_length + index_length) from information_schema
        """
        ssh = self._get_ssh_client(host_info, 'mysql_username')
        
        port = host_info.get('mysql_port', 3306)
        creds = self.db_credentials.get(host_info.get('hostname'),
                                        self.db_credentials.get('default', {}))
        db_user = creds.get('user', 'root')
        db_pass = creds.get('password', '')
        
        query = '''SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024 / 1024, 2) AS size_gb FROM information_schema.tables;'''
        
        mysql_cmd = f'''mysql -u{db_user} -p'{db_pass}' -P{port} -h127.0.0.1 -N -B -e "{query}"'''
        
        stdout, stderr, rc = ssh.execute(mysql_cmd)
        
        if rc == 0 and stdout:
            try:
                val = stdout.strip()
                if val and val.lower() != 'null':
                    return round(float(val), 2)
            except ValueError:
                logger.warning(f"Could not parse MySQL logical size for {host_info.get('hostname')}: {stdout}")
        
        return None
    
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect both sizes for MySQL database."""
        hostname = host_info.get('hostname', 'unknown')
        
        try:
            physical = self.collect_physical_size(host_info)
            logical = self.collect_logical_size(host_info)
            
            status = 'SUCCESS' if (physical is not None or logical is not None) else 'FAILED'
            error = None if status == 'SUCCESS' else 'Could not collect sizes'
            
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('mysql_port', 3306),
                physical_size_gb=physical,
                logical_size_gb=logical,
                application=host_info.get('mysql_application'),
                environment=host_info.get('environment', 'PROD'),
                db_version=host_info.get('mysql_version'),
                role=host_info.get('mysql_role'),
                status=status,
                error_message=error
            )
        except Exception as e:
            logger.error(f"Error collecting MySQL sizes for {hostname}: {e}")
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('mysql_port', 3306),
                physical_size_gb=None,
                logical_size_gb=None,
                status='FAILED',
                error_message=str(e)
            )


class MongoCollector(BaseCollector):
    """Collector for MongoDB databases."""
    
    def __init__(self, ssh_config: Dict, db_credentials: Dict, data_dirs: Dict):
        super().__init__(ssh_config)
        self.db_credentials = db_credentials
        self.data_dirs = data_dirs
    
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """MongoDB Physical Size = du on data directory"""
        ssh = self._get_ssh_client(host_info, 'mongo_username')
        
        data_dir = host_info.get('mongo_data_dir', self.data_dirs.get('data_dir', '/var/lib/mongodb'))
        cmd = f"du -sb {data_dir} 2>/dev/null | cut -f1"
        
        stdout, stderr, rc = ssh.execute(cmd)
        
        if rc == 0 and stdout:
            try:
                bytes_val = int(stdout.strip())
                return round(bytes_val / (1024 ** 3), 2)
            except ValueError:
                pass
        
        return None
    
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """MongoDB Logical Size = sum of all databases dataSize"""
        ssh = self._get_ssh_client(host_info, 'mongo_username')
        
        port = host_info.get('mongo_port', 27017)
        creds = self.db_credentials.get(host_info.get('hostname'),
                                        self.db_credentials.get('default', {}))
        db_user = creds.get('user', '')
        db_pass = creds.get('password', '')
        auth_db = creds.get('auth_db', 'admin')
        
        # Build mongo command
        if db_user and db_pass:
            auth_str = f"-u '{db_user}' -p '{db_pass}' --authenticationDatabase {auth_db}"
        else:
            auth_str = ""
        
        # Script to sum all database sizes
        js_script = '''
        var totalSize = 0;
        db.adminCommand('listDatabases').databases.forEach(function(d) {
            var stats = db.getSiblingDB(d.name).stats();
            totalSize += stats.dataSize || 0;
        });
        print((totalSize / 1024 / 1024 / 1024).toFixed(2));
        '''
        
        mongo_cmd = f'''mongosh --quiet --port {port} {auth_str} --eval "{js_script.replace(chr(10), ' ')}"'''
        
        stdout, stderr, rc = ssh.execute(mongo_cmd)
        
        # Fallback to legacy mongo command if mongosh fails
        if rc != 0:
            mongo_cmd = f'''mongo --quiet --port {port} {auth_str} --eval "{js_script.replace(chr(10), ' ')}"'''
            stdout, stderr, rc = ssh.execute(mongo_cmd)
        
        if rc == 0 and stdout:
            try:
                return round(float(stdout.strip()), 2)
            except ValueError:
                pass
        
        return None
    
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect both sizes for MongoDB."""
        hostname = host_info.get('hostname', 'unknown')
        
        try:
            physical = self.collect_physical_size(host_info)
            logical = self.collect_logical_size(host_info)
            
            status = 'SUCCESS' if (physical is not None or logical is not None) else 'FAILED'
            
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('mongo_port', 27017),
                physical_size_gb=physical,
                logical_size_gb=logical,
                replicaset_name=host_info.get('replicaset_name'),
                role=host_info.get('mongo_role'),
                application=host_info.get('mongo_application'),
                environment=host_info.get('environment', 'PROD'),
                db_version=host_info.get('mongo_version'),
                status=status,
                error_message=None if status == 'SUCCESS' else 'Could not collect sizes'
            )
        except Exception as e:
            logger.error(f"Error collecting MongoDB sizes for {hostname}: {e}")
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('mongo_port', 27017),
                physical_size_gb=None,
                logical_size_gb=None,
                status='FAILED',
                error_message=str(e)
            )


class PostgresCollector(BaseCollector):
    """Collector for PostgreSQL databases."""
    
    def __init__(self, ssh_config: Dict, db_credentials: Dict, data_dirs: Dict):
        super().__init__(ssh_config)
        self.db_credentials = db_credentials
        self.data_dirs = data_dirs
    
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """PostgreSQL Physical Size = du on data directory"""
        ssh = self._get_ssh_client(host_info, 'postgres_username')
        
        data_dir = host_info.get('postgres_data_dir', self.data_dirs.get('data_dir', '/var/lib/postgresql'))
        cmd = f"du -sb {data_dir} 2>/dev/null | cut -f1"
        
        stdout, stderr, rc = ssh.execute(cmd)
        
        if rc == 0 and stdout:
            try:
                bytes_val = int(stdout.strip())
                return round(bytes_val / (1024 ** 3), 2)
            except ValueError:
                pass
        
        return None
    
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """PostgreSQL Logical Size = sum of pg_database_size for all databases"""
        ssh = self._get_ssh_client(host_info, 'postgres_username')
        
        port = host_info.get('postgres_port', 5432)
        creds = self.db_credentials.get(host_info.get('hostname'),
                                        self.db_credentials.get('default', {}))
        db_user = creds.get('user', 'postgres')
        db_pass = creds.get('password', '')
        
        query = '''SELECT ROUND(SUM(pg_database_size(datname))::numeric / 1024 / 1024 / 1024, 2) FROM pg_database WHERE datistemplate = false;'''
        
        if db_pass:
            psql_cmd = f'''PGPASSWORD='{db_pass}' psql -U {db_user} -p {port} -h 127.0.0.1 -t -A -c "{query}"'''
        else:
            psql_cmd = f'''psql -U {db_user} -p {port} -t -A -c "{query}"'''
        
        stdout, stderr, rc = ssh.execute(psql_cmd)
        
        if rc == 0 and stdout:
            try:
                val = stdout.strip()
                if val:
                    return round(float(val), 2)
            except ValueError:
                pass
        
        return None
    
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect both sizes for PostgreSQL."""
        hostname = host_info.get('hostname', 'unknown')
        
        try:
            physical = self.collect_physical_size(host_info)
            logical = self.collect_logical_size(host_info)
            
            status = 'SUCCESS' if (physical is not None or logical is not None) else 'FAILED'
            
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('postgres_port', 5432),
                physical_size_gb=physical,
                logical_size_gb=logical,
                role=host_info.get('postgres_role'),
                application=host_info.get('postgres_application'),
                environment=host_info.get('environment', 'PROD'),
                db_version=host_info.get('postgres_version'),
                status=status,
                error_message=None if status == 'SUCCESS' else 'Could not collect sizes'
            )
        except Exception as e:
            logger.error(f"Error collecting PostgreSQL sizes for {hostname}: {e}")
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('postgres_port', 5432),
                physical_size_gb=None,
                logical_size_gb=None,
                status='FAILED',
                error_message=str(e)
            )


class CassandraCollector(BaseCollector):
    """Collector for Cassandra databases (physical size only)."""
    
    def __init__(self, ssh_config: Dict, data_dirs: Dict):
        super().__init__(ssh_config)
        self.data_dirs = data_dirs
    
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """Cassandra Physical Size = du on data directory"""
        ssh = self._get_ssh_client(host_info, 'cassandra_username')
        
        data_dir = host_info.get('cassandra_data_dir', self.data_dirs.get('data_dir', '/data'))
        cmd = f"du -sb {data_dir} 2>/dev/null | cut -f1"
        
        stdout, stderr, rc = ssh.execute(cmd)
        
        if rc == 0 and stdout:
            try:
                bytes_val = int(stdout.strip())
                return round(bytes_val / (1024 ** 3), 2)
            except ValueError:
                pass
        
        return None
    
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """Cassandra does not have a logical size concept - return None."""
        return None
    
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect physical size for Cassandra (no logical size)."""
        hostname = host_info.get('hostname', 'unknown')
        
        try:
            physical = self.collect_physical_size(host_info)
            
            status = 'SUCCESS' if physical is not None else 'FAILED'
            
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('cassandra_port', 9042),
                physical_size_gb=physical,
                logical_size_gb=None,  # Cassandra doesn't have logical size
                cluster_name=host_info.get('cassandra_application'),
                application=host_info.get('cassandra_application'),
                environment=host_info.get('environment', 'PROD'),
                db_version=host_info.get('cassandra_version'),
                status=status,
                error_message=None if status == 'SUCCESS' else 'Could not collect physical size'
            )
        except Exception as e:
            logger.error(f"Error collecting Cassandra sizes for {hostname}: {e}")
            return SizeResult(
                hostname=hostname,
                ip_address=host_info.get('ansible_host', ''),
                port=host_info.get('cassandra_port', 9042),
                physical_size_gb=None,
                logical_size_gb=None,
                status='FAILED',
                error_message=str(e)
            )


class MSSQLCollector(BaseCollector):
    """Collector for SQL Server databases - PLACEHOLDER"""
    
    def collect_physical_size(self, host_info: Dict) -> Optional[float]:
        """SQL Server physical size - NOT IMPLEMENTED"""
        # TODO: Implement when needed
        # Would use xp_cmdshell or SQLCMD to get file sizes
        logger.warning("SQL Server physical size collection not implemented")
        return None
    
    def collect_logical_size(self, host_info: Dict) -> Optional[float]:
        """SQL Server logical size - NOT IMPLEMENTED"""
        # TODO: Implement when needed
        # Query: SELECT SUM(size * 8 / 1024 / 1024) FROM sys.master_files
        logger.warning("SQL Server logical size collection not implemented")
        return None
    
    def collect(self, host_info: Dict) -> SizeResult:
        """Collect sizes for SQL Server - PLACEHOLDER"""
        hostname = host_info.get('hostname', 'unknown')
        
        return SizeResult(
            hostname=hostname,
            ip_address=host_info.get('ansible_host', ''),
            port=host_info.get('mssql_port', 1433),
            physical_size_gb=None,
            logical_size_gb=None,
            instance_name=host_info.get('mssql_instance'),
            application=host_info.get('mssql_application'),
            environment=host_info.get('environment', 'PROD'),
            db_version=host_info.get('mssql_version'),
            status='NOT_IMPLEMENTED',
            error_message='SQL Server collection not implemented yet'
        )
