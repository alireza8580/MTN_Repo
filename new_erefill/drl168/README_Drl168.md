# Drl168 MFS_REPORT Gather Stats Scripts

**Version:** 1.0  
**Date:** 2025-01-05  
**Server:** Drl168  
**Oracle Version:** 19.25  

---

## Overview

This package contains Oracle gather stats scripts for MFS_REPORT database on Drl168 server. The database contains reporting tables and fact tables.

## Oracle Configuration

| Parameter | Value |
|-----------|-------|
| ORACLE_SID | report |
| ORACLE_HOME | /oracle/product/19.25/db_1 |
| ORACLE_PDB_SID | mfs_report |

## PDB and Schema Mapping

### MFS_REPORT PDB

| Schema | Tables |
|--------|--------|
| APP_USER | MFS_EDR_DAILY (partitioned), MFS_RPT_FACT, MFS_RPT_SERVICE_FACT, MFS_RPT_RECON_FACT, MFS_RPT_HOURLY_FACT |

## Schedule Summary

| Schedule | Frequency | Cron Expression | Description |
|----------|-----------|-----------------|-------------|
| Schedule C | Every 12 hours | `0 11,23 * * *` | MFS_EDR_DAILY partitions |
| Monthly | 10th of month 2AM | `0 2 10 * *` | MFS_EDR_DAILY (higher DEGREE) |

## Files Included

| File | Description |
|------|-------------|
| `mfs_report_config.env` | Shared configuration (Oracle paths, email, PDB names) |
| `mfs_report_scheduleC.scr` | Schedule C wrapper script |
| `mfs_report_scheduleC_gen.sql` | Schedule C dynamic SQL for MFS_EDR_DAILY |
| `mfs_report_monthly.scr` | Monthly wrapper script |
| `mfs_report_monthly_gen.sql` | Monthly dynamic SQL (higher DEGREE) |
| `mfs_report_static.scr` | Static tables wrapper script |
| `mfs_report_static.sql` | Static tables SQL for RPT fact tables |
| `crontab_drl168.txt` | Crontab entries for oracle user |
| `Drl168_MFS_REPORT_GatherStats_v1.0.xlsx` | This documentation in Excel format |

## Installation

```bash
# 1. Extract archive to your preferred location
cd /oracle/alireza/Schedule_ORA_OS_Job/
tar xzvf drl168_mfs_report_gather_stats_v1.0.tgz
mv drl168 drl168  # or rename as needed

# 2. Set permissions
chmod 755 drl168/*.scr

# 3. Edit configuration - IMPORTANT!
vi drl168/mfs_report_config.env
# Update these two lines to match your installation path:
#   BASE_DIR=/oracle/alireza
#   SCRIPT_SUBDIR=Schedule_ORA_OS_Job/drl168

# 4. Add crontab entries
crontab -e
# Copy from crontab_drl168.txt and replace SCRIPT_PATH with your path:
#   SCRIPT_PATH -> /oracle/alireza/Schedule_ORA_OS_Job/drl168
```

## Configuration

### Path Configuration

Edit `mfs_report_config.env` to set your installation path:

```bash
#------------------------------------------------------------------------------
# PATH CONFIGURATION - Edit these variables to change installation location
#------------------------------------------------------------------------------
BASE_DIR=/oracle/alireza
SCRIPT_SUBDIR=Schedule_ORA_OS_Job/drl168
```

The full path is automatically derived as: `${BASE_DIR}/${SCRIPT_SUBDIR}`

### Email Configuration

Edit the same file to modify email recipients:

## Logs

All scripts log to `/oracle/Schedule_ORA_OS_Job/MFS_REPORT/logs/`:
- `gather_stats.log` - Main log with timestamps
- `scheduleC.log` - Schedule C output
- `monthly.log` - Monthly output
- `static.log` - Static tables output

## Email Notifications

Failed jobs send email to: `isdcdba@mtnirancell.ir`

---

*Document generated: 2025-01-05*  
*MTN Irancell DBA Team*
