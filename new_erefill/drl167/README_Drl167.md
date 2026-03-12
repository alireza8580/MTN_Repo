# Drl167 EREFILL Gather Stats Scripts

**Version:** 1.0  
**Date:** 2025-01-05  
**Server:** Drl167  
**Oracle Version:** 19.25  

---

## Overview

This package contains Oracle gather stats scripts for EREFILL database on Drl167 server. The database is split across two PDBs:
- **EREFILL_EVENT** - Event data (CDR/EDR records)
- **EREFILL_CORE** - Core data and configuration

## Oracle Configuration

| Parameter | Value |
|-----------|-------|
| ORACLE_SID | erefill |
| ORACLE_HOME | /oracle/product/19.25/db_1 |
| ORACLE_PDB_SID | erefill_event / erefill_core |

## PDB and Schema Mapping

### EREFILL_EVENT PDB

| Schema | Tables |
|--------|--------|
| EVENT_DATA | RETRY_TABLE, MFS_CC, MFS_CDR_01, MFS_CDR_02, MFS_EDR_01, MFS_EDR_02, MFS_P2P_TRANSACTION_01, MFS_P2P_TRANSACTION_02, MFS_P2P_TRANSACTION_SUMMARY, MFS_ETOPUP_MERCHANT_IP_EVENTS, MFS_ETOPUP_AUDIT_LOGS, MFS_ETOPUP_PSWD_HISTORY |

### EREFILL_CORE PDB

| Schema | Tables |
|--------|--------|
| CORE_DATA | MFS_ETOPUP_ACCOUNT_MASTER, MFS_ETOPUP_TRANSACTIONS, MFS_ETOPUP_THRESHOLD_CHECK, MFS_ETOPUP_P2P_USER_DETAILS, MFS_NICKNAME_MDN_MAPPING, MFS_P2PBLOCK_MSIDN_DETAILS, MFS_P2PREQUESTED_PIN_DETAILS, MFS_ETOPUP_LOGIN_MASTER, MFS_ETOPUP_HINT_ANSWER_MASTER |
| CORE_CONFIG | MFS_ETOPUP_USER_MASTER, MFS_ETOPUP_ADDRESS_MASTER, MFS_ETOPUP_CONFIG_PARAMETERS, MFS_ETOPUP_ERROR_CODES, MFS_ETOPUP_LEVEL_ROLE_MENU_MAP, MFS_ETOPUP_LEVEL_MASTER, MFS_ETOPUP_ROLE_MASTER |

## Schedule Summary

| Schedule | Frequency | Cron Expression | Description |
|----------|-----------|-----------------|-------------|
| Schedule A | Every 3 hours | `0 2,5,8,11,14,17,20,23 * * *` | MFS_ETOPUP_USER_MASTER only |
| Schedule B | Every 6 hours | `0 5,11,17,23 * * *` | CDR/EDR tables, THRESHOLD_CHECK |
| Schedule C | Every 12 hours | `0 11,23 * * *` | Partitioned tables (dynamic) |
| Monthly | 10th of month 2AM | `0 2 10 * *` | All partitioned tables (higher DEGREE) |

## Files Included

| File | Description |
|------|-------------|
| `erefill_config.env` | Shared configuration (Oracle paths, email, PDB names) |
| `erefill_scheduleA.scr` | Schedule A wrapper script |
| `erefill_scheduleA.sql` | Schedule A SQL - USER_MASTER table |
| `erefill_scheduleB.scr` | Schedule B wrapper script |
| `erefill_scheduleB.sql` | Schedule B SQL - CDR/EDR tables (EVENT_DATA) |
| `erefill_scheduleB_core.sql` | Schedule B SQL - THRESHOLD_CHECK (CORE_DATA) |
| `erefill_scheduleC.scr` | Schedule C wrapper script |
| `erefill_scheduleC_gen_event.sql` | Schedule C dynamic SQL for EVENT_DATA |
| `erefill_scheduleC_gen_core.sql` | Schedule C dynamic SQL for CORE_DATA |
| `erefill_monthly.scr` | Monthly wrapper script |
| `erefill_monthly_gen_event.sql` | Monthly dynamic SQL for EVENT_DATA |
| `erefill_monthly_gen_core.sql` | Monthly dynamic SQL for CORE_DATA |
| `erefill_static_tables.scr` | Static tables wrapper script |
| `erefill_static_event.sql` | Static tables SQL for EVENT_DATA |
| `erefill_static_core.sql` | Static tables SQL for CORE_DATA/CORE_CONFIG |
| `crontab_drl167.txt` | Crontab entries for oracle user |
| `Drl167_EREFILL_GatherStats_v1.0.xlsx` | This documentation in Excel format |

## Installation

```bash
# 1. Extract archive to your preferred location
cd /oracle/alireza/Schedule_ORA_OS_Job/
tar xzvf drl167_erefill_gather_stats_v1.0.tgz
mv drl167 drl167  # or rename as needed

# 2. Set permissions
chmod 755 drl167/*.scr

# 3. Edit configuration - IMPORTANT!
vi drl167/erefill_config.env
# Update these two lines to match your installation path:
#   BASE_DIR=/oracle/alireza
#   SCRIPT_SUBDIR=Schedule_ORA_OS_Job/drl167

# 4. Add crontab entries
crontab -e
# Copy from crontab_drl167.txt and replace SCRIPT_PATH with your path:
#   SCRIPT_PATH -> /oracle/alireza/Schedule_ORA_OS_Job/drl167
```

## Configuration

### Path Configuration

Edit `erefill_config.env` to set your installation path:

```bash
#------------------------------------------------------------------------------
# PATH CONFIGURATION - Edit these variables to change installation location
#------------------------------------------------------------------------------
BASE_DIR=/oracle/alireza
SCRIPT_SUBDIR=Schedule_ORA_OS_Job/drl167
```

The full path is automatically derived as: `${BASE_DIR}/${SCRIPT_SUBDIR}`

### Email Configuration

Edit the same file to modify email recipients:

## Logs

All scripts log to `/oracle/Schedule_ORA_OS_Job/EREFILL/logs/`:
- `gather_stats.log` - Main log with timestamps
- `scheduleA.log` - Schedule A output
- `scheduleB.log` - Schedule B output
- `scheduleC.log` - Schedule C output
- `monthly.log` - Monthly output
- `static.log` - Static tables output

## Email Notifications

Failed jobs send email to: `isdcdba@mtnirancell.ir`

---

*Document generated: 2025-01-05*  
*MTN Irancell DBA Team*
