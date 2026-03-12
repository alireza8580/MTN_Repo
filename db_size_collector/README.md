# Database Size Collector

A Python-based tool for collecting database sizes across multiple platforms and storing the data in an Oracle database for historical tracking and reporting.

## Features

- **Multi-platform support**: Oracle, MySQL, MongoDB, PostgreSQL, Cassandra (SQL Server placeholder)
- **Dual size collection**: Physical (disk) and Logical (data) sizes
- **Inventory-based**: Uses Ansible inventory files for host discovery
- **Parallel collection**: Configurable worker threads for faster collection
- **Oracle storage**: Stores historical data with daily granularity
- **Email notifications**: Sends HTML report on job completion with execution details
- **Automatic cleanup**: Optional data retention management
- **Cron-ready**: Includes wrapper script for scheduled execution

## Platforms & Metrics

| Platform   | Physical Size                        | Logical Size                              |
|------------|--------------------------------------|-------------------------------------------|
| Oracle     | datafiles + tempfiles + 100GB buffer | sum(dba_segments.bytes)                   |
| MySQL      | du on data_dir + binlog_dir          | sum(information_schema.tables)            |
| MongoDB    | du on data_dir                       | sum(db.stats().dataSize)                  |
| PostgreSQL | du on data_dir                       | sum(pg_database_size())                   |
| Cassandra  | du on data_dir                       | N/A (no logical size concept)             |
| SQL Server | Placeholder                          | Placeholder (not implemented)             |

## Installation

### Prerequisites

```bash
# Python 3.8+
python3 --version

# Required packages
pip install pyyaml oracledb

# Or use cx_Oracle if preferred
pip install pyyaml cx_Oracle
```

### Setup

1. **Clone/Copy the collector**:
   ```bash
   cd /path/to/MTN_Repo
   ls db_size_collector/
   ```

2. **Configure credentials** (IMPORTANT - edit config.py):
   ```bash
   vi db_size_collector/config.py
   ```
   
   Update the following:
   - `ORACLE_TARGET`: Oracle connection for storing data
   - `SSH_CONFIG`: SSH settings for remote connections
   - `DB_CREDENTIALS`: Database credentials per platform
   - `DATA_DIRECTORIES`: Custom data directory paths

3. **Create Oracle schema**:
   ```bash
   # Connect to Oracle as dba_db_size user
   sqlplus dba_db_size/AlirEza_1234Bdas@127.0.0.1:1521/ORCL
   
   # Run the schema script
   @/path/to/db_size_collector/schema.sql
   ```

4. **Test the collector**:
   ```bash
   # Dry run (no storage)
   python3 db_size_collector/collect_db_sizes.py --dry-run --verbose
   
   # Test single platform
   python3 db_size_collector/collect_db_sizes.py --platform mysql --dry-run
   ```

## Usage

### Command Line

```bash
# Collect all platforms
python3 collect_db_sizes.py

# Collect specific platforms
python3 collect_db_sizes.py --platform oracle mysql

# Dry run (test without storing)
python3 collect_db_sizes.py --dry-run

# Verbose output
python3 collect_db_sizes.py --verbose

# Disable email notification
python3 collect_db_sizes.py --no-email

# Send email to test recipient only
python3 collect_db_sizes.py --email-test

# Clean up old data (keep 365 days)
python3 collect_db_sizes.py --cleanup 365

# Custom inventory path
python3 collect_db_sizes.py --inventory /path/to/inventory
```

### Email Notifications

The collector sends an HTML email report when a job completes. The email includes:

- **Job summary**: Total elapsed time, hosts collected, total sizes
- **Platform breakdown**: Success rate, sizes, elapsed time per platform
- **Command log**: All executed commands with individual elapsed times

**Configuration** (in `config.py`):

```python
EMAIL_CONFIG = {
    'enabled': True,
    'smtp_server': 'outlook.office365.com',
    'smtp_port': 587,
    'use_tls': True,
    'username': 'your.email@mtnirancell.ir',
    'password': '',  # Set via EMAIL_PASSWORD environment variable
    'from_address': 'your.email@mtnirancell.ir',
    'to_addresses': ['recipient@mtnirancell.ir'],
    'test_mode': False,
    'test_recipient': 'test@mtnirancell.ir',
    'subject_prefix': '[DB Size Collector]'
}
```

**Security**: Store the email password in an environment variable or a secure file:

```bash
# Option 1: Environment variable
export EMAIL_PASSWORD='your_password'
python3 collect_db_sizes.py

# Option 2: Secure file (used by run_collector.sh)
echo 'your_password' > /path/to/db_size_collector/.email_password
chmod 600 /path/to/db_size_collector/.email_password
```

### Cron Setup

```bash
# Make wrapper executable
chmod +x /path/to/db_size_collector/run_collector.sh

# Edit crontab
crontab -e

# Add entry (run daily at 2:00 AM)
0 2 * * * /path/to/db_size_collector/run_collector.sh >> /var/log/db_size_collector_cron.log 2>&1

# With email notification
MAILTO=dba@mtnirancell.ir
0 2 * * * /path/to/db_size_collector/run_collector.sh
```

## Configuration

### config.py

```python
# Oracle target for storing data
ORACLE_TARGET = {
    'host': '127.0.0.1',
    'port': 1521,
    'service_name': 'ORCL',
    'user': 'dba_db_size',
    'password': 'AlirEza_1234Bdas'
}

# SSH settings
SSH_CONFIG = {
    'timeout': 30,
    'key_filename': '/path/to/ssh/key',  # Optional
    'username': 'oracle',                 # Default for Oracle
    'mysql_username': 'mysql',
    'mongo_username': 'mongod',
    'postgres_username': 'postgres',
    'cassandra_username': 'cassandra'
}

# Database credentials
DB_CREDENTIALS = {
    'oracle': {
        'default': {'user': 'system', 'password': 'xxx'},
        'dru103b': {'user': 'sys', 'password': 'xxx', 'as_sysdba': True}
    },
    'mysql': {
        'default': {'user': 'root', 'password': 'xxx'}
    },
    ...
}
```

## Database Schema

Tables created in Oracle:

- `oracle_db_sizes` - Oracle database sizes
- `mysql_db_sizes` - MySQL database sizes
- `mongo_db_sizes` - MongoDB database sizes
- `postgres_db_sizes` - PostgreSQL database sizes
- `cassandra_db_sizes` - Cassandra sizes (physical only)
- `mssql_db_sizes` - SQL Server sizes (placeholder)
- `collection_summary` - Daily collection summaries

Views:

- `v_daily_db_sizes` - Daily totals by platform
- `v_latest_oracle_sizes` - Latest size per Oracle instance
- `v_latest_mysql_sizes` - Latest size per MySQL instance
- `v_weekly_growth` - Weekly growth trends

## Reporting Queries

```sql
-- Today's collection summary
SELECT * FROM collection_summary WHERE collection_date = TRUNC(SYSDATE);

-- Platform totals for last 30 days
SELECT collection_date, platform, total_physical_gb, total_logical_gb
FROM collection_summary
WHERE collection_date >= TRUNC(SYSDATE) - 30
ORDER BY collection_date DESC, platform;

-- Top 10 largest MySQL databases
SELECT hostname, port, physical_size_gb, logical_size_gb, application
FROM mysql_db_sizes
WHERE collection_date = TRUNC(SYSDATE)
  AND collection_status = 'SUCCESS'
ORDER BY physical_size_gb DESC
FETCH FIRST 10 ROWS ONLY;

-- Week-over-week growth
SELECT 
    platform,
    week_start,
    physical_growth_gb,
    logical_growth_gb
FROM v_weekly_growth
WHERE week_start >= TRUNC(SYSDATE) - 28;
```

## Inventory Structure

The collector reads from Ansible inventory YAML files:

```
ansible/inventory/mtn_databases/
├── oracle_hosts.yml
├── mysql_hosts.yml
├── mongo_hosts.yml
├── postgres_hosts.yml
├── cassandra_hosts.yml
└── mssql_hosts.yml
```

Each file follows Ansible inventory format:

```yaml
all:
  children:
    mysql_servers:
      children:
        mysql_prod:
          hosts:
            server1:
              ansible_host: 10.0.0.1
              mysql_port: 3306
              mysql_role: Master
              mysql_application: MyApp
```

## Troubleshooting

### SSH Connection Issues

```bash
# Test SSH manually
ssh -o ConnectTimeout=10 oracle@10.0.0.1 "echo OK"

# Check SSH key permissions
chmod 600 ~/.ssh/id_rsa
```

### Oracle Connection Issues

```python
# Test Oracle connection
import oracledb
conn = oracledb.connect(user='dba_db_size', password='xxx', dsn='127.0.0.1:1521/ORCL')
print(conn.version)
```

### Missing Inventory

```bash
# Check inventory exists
ls -la ansible/inventory/mtn_databases/

# Parse inventory manually
python3 db_size_collector/inventory_parser.py /path/to/inventory
```

## Files

```
db_size_collector/
├── collect_db_sizes.py    # Main script
├── collectors.py          # Platform collectors
├── inventory_parser.py    # Ansible inventory parser
├── storage.py             # Oracle storage module
├── config.py              # Configuration (EDIT THIS!)
├── schema.sql             # Oracle DDL
├── run_collector.sh       # Cron wrapper
└── README.md              # This file
```

## Security Notes

1. **Protect config.py**: Contains database credentials
   ```bash
   chmod 600 config.py
   ```

2. **Use SSH keys**: Avoid password-based SSH where possible

3. **Use Oracle Wallet**: Consider using Oracle Wallet instead of plaintext passwords

4. **Encrypt secrets**: Consider using environment variables or a secrets manager

## Author

MTN DBA Team

## Version

1.0.0 - 2026-01-05
