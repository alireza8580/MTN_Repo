#!/usr/bin/env python3
"""
Configuration for Database Size Collector
Contains credentials and paths - KEEP SECURE!
"""

# Oracle target database for storing collected metrics
ORACLE_TARGET = {
    'host': '127.0.0.1',
    'port': 1521,
    'service_name': 'ORCL',  # or SID
    'user': 'dba_db_size',
    'password': 'AlirEza_1234Bdas'
}

# SSH Configuration for remote servers
SSH_CONFIG = {
    'timeout': 30,
    'key_filename': None,  # Set if using SSH key: '/path/to/id_rsa'
    'username': 'oracle',  # Default username for Oracle servers
    'mysql_username': 'mysql',  # Default for MySQL servers
    'mongo_username': 'mongod',  # Default for MongoDB servers
    'postgres_username': 'postgres',  # Default for PostgreSQL servers
    'cassandra_username': 'cassandra'  # Default for Cassandra servers
}

# Database credentials for collecting sizes
DB_CREDENTIALS = {
    # Oracle credentials (can be overridden per server)
    'oracle': {
        'default': {
            'user': 'system',
            'password': 'oracle123'  # Replace with actual
        },
        # Per-server overrides
        # 'dru103b': {'user': 'sys', 'password': 'xxx', 'as_sysdba': True}
    },
    
    # MySQL credentials
    'mysql': {
        'default': {
            'user': 'root',
            'password': 'mysql123'  # Replace with actual
        }
    },
    
    # MongoDB credentials
    'mongo': {
        'default': {
            'user': 'admin',
            'password': 'mongo123',  # Replace with actual
            'auth_db': 'admin'
        }
    },
    
    # PostgreSQL credentials
    'postgres': {
        'default': {
            'user': 'postgres',
            'password': 'postgres123'  # Replace with actual
        }
    }
}

# Default data directories for physical size calculation
DATA_DIRECTORIES = {
    'mysql': {
        'data_dir': '/var/lib/mysql',
        'binlog_dir': '/var/lib/mysql',  # Often same as data_dir
        # Some MTN servers use /data/3306/mysqlDB
    },
    'mongo': {
        'data_dir': '/var/lib/mongodb'
    },
    'postgres': {
        'data_dir': '/var/lib/postgresql'
    },
    'cassandra': {
        'data_dir': '/data'
    }
}

# Inventory paths (relative to MTN_Repo directory)
INVENTORY_PATH = 'ansible/inventory/mtn_databases'

# Logging configuration
LOG_CONFIG = {
    'log_file': '/var/log/db_size_collector.log',
    'log_level': 'INFO',
    'max_bytes': 10485760,  # 10 MB
    'backup_count': 5
}

# Collection settings
COLLECTION_CONFIG = {
    'parallel_workers': 5,  # Number of parallel connections
    'timeout_per_host': 120,  # Seconds
    'retry_count': 2,
    'retry_delay': 10  # Seconds
}

# Email notification settings
EMAIL_CONFIG = {
    'enabled': True,
    'smtp_server': 'outlook.office365.com',
    'smtp_port': 587,
    'use_tls': True,
    
    # Credentials (use environment variables in production)
    'username': 'alireza.aghaja@mtnirancell.ir',
    'password': '',  # Set via environment variable EMAIL_PASSWORD
    
    # Recipients
    'from_address': 'alireza.aghaja@mtnirancell.ir',
    'to_addresses': ['alireza.aghaja@mtnirancell.ir'],
    'cc_addresses': [],
    
    # Test mode (single recipient)
    'test_mode': False,
    'test_recipient': 'alireza.aghaja@mtnirancell.ir',
    
    # Subject prefix
    'subject_prefix': '[DB Size Collector]'
}
