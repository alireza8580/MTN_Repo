# EREFILL Gather Stats Scripts - New Environment

## Overview

This directory contains the gather stats scripts for the new EREFILL database environment migrated from old dru103b to new Oracle 19.25 PDB architecture.

## New Environment Details

| Server | ORACLE_SID | PDB Name | Schema | Tables |
|--------|------------|----------|--------|--------|
| Drl167 | erefill | EREFILL_EVENT | EVENT_DATA | RETRY_TABLE, MFS_CC, MFS_CDR_01/02, MFS_EDR_01/02, MFS_P2P_TRANSACTION_01/02, MFS_P2P_TRANSACTION_SUMMARY, MFS_ETOPUP_MERCHANT_IP_EVENTS, MFS_ETOPUP_AUDIT_LOGS, MFS_ETOPUP_PSWD_HISTORY |
| Drl167 | erefill | EREFILL_CORE | CORE_DATA | MFS_ETOPUP_ACCOUNT_MASTER, MFS_ETOPUP_TRANSACTIONS, MFS_ETOPUP_HINT_ANSWER_MASTER, MFS_ETOPUP_THRESHOLD_CHECK, MFS_ETOPUP_P2P_USER_DETAILS, MFS_NICKNAME_MDN_MAPPING, MFS_P2PBLOCK_MSIDN_DETAILS, MFS_P2PREQUESTED_PIN_DETAILS, MFS_ETOPUP_LOGIN_MASTER |
| Drl167 | erefill | EREFILL_CORE | CORE_CONFIG | MFS_ETOPUP_USER_MASTER, MFS_ETOPUP_ADDRESS_MASTER, MFS_ETOPUP_CONFIG_PARAMETERS, MFS_ETOPUP_ERROR_CODES, MFS_ETOPUP_LEVEL_ROLE_MENU_MAP, MFS_ETOPUP_LEVEL_MASTER, MFS_ETOPUP_ROLE_MASTER |
| Drl168 | report | MFS_REPORT | APP_USER | MFS_EDR_DAILY, MFS_RPT_FACT, MFS_RPT_SERVICE_FACT, MFS_RPT_RECON_FACT, MFS_RPT_HOURLY_FACT |

## Schedule Summary

| Schedule | Frequency | Cron Expression | Tables |
|----------|-----------|-----------------|--------|
| Schedule A | Every 3 hours | `0 2,5,8,11,14,17,20,23 * * *` | MFS_ETOPUP_USER_MASTER |
| Schedule B | Every 6 hours | `0 5,11,17,23 * * *` | MFS_CDR_01/02, MFS_EDR_01/02, MFS_ETOPUP_THRESHOLD_CHECK |
| Schedule C | Every 12 hours | `0 11,23 * * *` | Partitioned tables (RETRY_TABLE, MFS_CC, MFS_ETOPUP_TRANSACTIONS, MFS_P2P_TRANSACTION_SUMMARY, MFS_EDR_DAILY, MFS_ETOPUP_MERCHANT_IP_EVENTS) |
| Monthly | 10th of month 2AM | `0 2 10 * *` | Monthly stats for partitioned tables with higher DEGREE |

## Oracle Environment Variables

```bash
# Drl167 - EREFILL_EVENT PDB
export ORACLE_SID=erefill
export ORACLE_HOME=/oracle/product/19.25/db_1
export ORACLE_PDB_SID=erefill_event

# Drl167 - EREFILL_CORE PDB
export ORACLE_SID=erefill
export ORACLE_HOME=/oracle/product/19.25/db_1
export ORACLE_PDB_SID=erefill_core

# Drl168 - MFS_REPORT PDB
export ORACLE_SID=report
export ORACLE_HOME=/oracle/product/19.25/db_1
export ORACLE_PDB_SID=mfs_report
```

**Note:** When `ORACLE_PDB_SID` is set, sqlplus automatically connects to the specified PDB without needing `ALTER SESSION SET CONTAINER`.

## Files

### Drl167 Scripts (22 files total)

**Schedule A (Every 3 hours):**
- `erefill_scheduleA.scr` - Wrapper script
- `erefill_scheduleA.sql` - MFS_ETOPUP_USER_MASTER (CORE_CONFIG)

**Schedule B (Every 6 hours):**
- `erefill_scheduleB.scr` - Wrapper script (runs both PDBs)
- `erefill_scheduleB.sql` - CDR/EDR tables (EVENT_DATA)
- `erefill_scheduleB_core.sql` - MFS_ETOPUP_THRESHOLD_CHECK (CORE_DATA)

**Schedule C (Every 12 hours - partitioned tables):**
- `erefill_scheduleC.scr` - Wrapper script (runs both PDBs)
- `erefill_scheduleC_gen_event.sql` - Dynamic SQL generator for EVENT_DATA
- `erefill_scheduleC_gen_core.sql` - Dynamic SQL generator for CORE_DATA

**Monthly (10th of month at 2AM):**
- `erefill_monthly.scr` - Wrapper script (runs both PDBs)
- `erefill_monthly_gen_event.sql` - Dynamic SQL generator for EVENT_DATA
- `erefill_monthly_gen_core.sql` - Dynamic SQL generator for CORE_DATA

**Static Tables (non-partitioned):**
- `erefill_static_tables.scr` - Wrapper script (runs both PDBs)
- `erefill_static_event.sql` - Static tables in EVENT_DATA
- `erefill_static_core.sql` - Static tables in CORE_DATA + CORE_CONFIG

### Drl168 Scripts (6 files)

**Schedule C (Every 12 hours):**
- `mfs_report_scheduleC.scr` - Wrapper script
- `mfs_report_scheduleC_gen.sql` - MFS_EDR_DAILY partitions (APP_USER)

**Monthly (10th of month at 2AM):**
- `mfs_report_monthly.scr` - Wrapper script
- `mfs_report_monthly_gen.sql` - MFS_EDR_DAILY with higher DEGREE

**Static Tables:**
- `mfs_report_static.scr` - Wrapper script
- `mfs_report_static.sql` - RPT fact tables (APP_USER)

### Crontab Files
- `crontab_drl167.txt` - Ready to paste into Drl167 oracle user crontab
- `crontab_drl168.txt` - Ready to paste into Drl168 oracle user crontab

## Crontab Entries

### Drl167 (oracle user)
```cron
# EREFILL Gather Stats - Schedule A (every 3 hours)
0 2,5,8,11,14,17,20,23 * * * /oracle/Schedule_ORA_OS_Job/EREFILL/erefill_scheduleA.scr

# EREFILL Gather Stats - Schedule B (every 6 hours)
0 5,11,17,23 * * * /oracle/Schedule_ORA_OS_Job/EREFILL/erefill_scheduleB.scr

# EREFILL Gather Stats - Schedule C (every 12 hours - partitioned tables)
0 11,23 * * * /oracle/Schedule_ORA_OS_Job/EREFILL/erefill_scheduleC.scr

# EREFILL Gather Stats - Monthly (10th of month at 2AM)
0 2 10 * * /oracle/Schedule_ORA_OS_Job/EREFILL/erefill_monthly.scr
```

### Drl168 (oracle user)
```cron
# MFS_REPORT Gather Stats - Schedule C (every 12 hours)
0 11,23 * * * /oracle/Schedule_ORA_OS_Job/MFS_REPORT/mfs_report_scheduleC.scr

# MFS_REPORT Gather Stats - Monthly (10th of month at 2AM)
0 2 10 * * /oracle/Schedule_ORA_OS_Job/MFS_REPORT/mfs_report_monthly.scr
```

## Deployment Instructions

### Archive Files

Pre-packaged archives ready to copy to servers:
- `drl167_erefill_gather_stats_v1.1.tgz` - All scripts for Drl167 with email notifications
- `drl168_mfs_report_gather_stats_v1.1.tgz` - All scripts for Drl168 with email notifications

### 1. Copy archives to servers

```bash
# From local machine
scp drl167_erefill_gather_stats.tgz oracle@drl167:/oracle/Schedule_ORA_OS_Job/
scp drl168_mfs_report_gather_stats.tgz oracle@drl168:/oracle/Schedule_ORA_OS_Job/
```

### 2. Extract and setup on Drl167

```bash
ssh oracle@drl167
cd /oracle/Schedule_ORA_OS_Job/
tar xzvf drl167_erefill_gather_stats.tgz
mv drl167 EREFILL
chmod 755 /oracle/Schedule_ORA_OS_Job/EREFILL/*.scr
rm drl167_erefill_gather_stats.tgz
```

### 3. Extract and setup on Drl168

```bash
ssh oracle@drl168
cd /oracle/Schedule_ORA_OS_Job/
tar xzvf drl168_mfs_report_gather_stats.tgz
mv drl168 MFS_REPORT
chmod 755 /oracle/Schedule_ORA_OS_Job/MFS_REPORT/*.scr
rm drl168_mfs_report_gather_stats.tgz
```

### 4. Add crontab entries

```bash
# On Drl167
crontab -e
# Paste contents from /oracle/Schedule_ORA_OS_Job/EREFILL/crontab_drl167.txt

# On Drl168
crontab -e
# Paste contents from /oracle/Schedule_ORA_OS_Job/MFS_REPORT/crontab_drl168.txt
```

## Migration Notes

1. **Old database used `PGWDB` schema** - now split across multiple PDBs and schemas
2. **Old server was dru103b (Oracle 12.2)** - new servers are Drl167/Drl168 (Oracle 19.25)
3. **Scripts use `ORACLE_PDB_SID`** for direct PDB connection (no `ALTER SESSION` needed)
4. **Email notifications** sent to `isdcdba@mtnirancell.ir`
5. **Each wrapper script** handles multiple PDBs by changing `ORACLE_PDB_SID` between sqlplus calls

## Email Notifications (v1.1)

Each script now sends **HTML email notifications** on successful completion, including:

- **Job name and status** (Schedule A, B, C, Monthly, Static)
- **Elapsed time** formatted as `Xh Ym Zs`
- **Tables processed** listed in the email
- **SQL Execution Timing** - Actual timing from sqlplus `SET TIMING ON` output (e.g., `Elapsed: 00:01:23.45`)

### Success Email Sample

```
Subject: [Drl167 EREFILL] Schedule B - SUCCESS (1m 23s)

✓ Schedule B Completed Successfully

Server: drl167
Timestamp: 2025-01-06 23:45:00
Total Elapsed: 1m 23s

Tables Processed:
- MFS_CDR_01
- MFS_CDR_02
- MFS_EDR_01
- MFS_EDR_02
- MFS_ETOPUP_THRESHOLD_CHECK

SQL Execution Timing:
=== EREFILL_EVENT PDB ===
EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> 'EVENT_DATA', TABNAME => 'MFS_CDR_01' ...
PL/SQL procedure successfully completed.
Elapsed: 00:00:15.23

EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> 'EVENT_DATA', TABNAME => 'MFS_CDR_02' ...
PL/SQL procedure successfully completed.
Elapsed: 00:00:12.45

=== EREFILL_CORE PDB ===
EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> 'CORE_DATA', TABNAME => 'MFS_ETOPUP_THRESHOLD_CHECK' ...
PL/SQL procedure successfully completed.
Elapsed: 00:00:08.67
```

### Email Configuration

Edit the `*_config.env` file to configure recipients:

```bash
# Test mode - sends only to test recipient
TEST_MODE=1

# Production recipients
MAIL_RECIPIENT_PROD="alireza.aghaja@mtnirancell.ir,isdcdba@mtnirancell.ir,#saeidbsupport@mtnirancell.ir"

# Test recipient
MAIL_RECIPIENT_TEST="alireza.aghaja@mtnirancell.ir"
```

### Functions Added (v1.1)

| Function | Description |
|----------|-------------|
| `format_duration seconds` | Converts seconds to `Xh Ym Zs` format |
| `send_success_email name secs "tables" [log_file]` | Sends HTML email with job details and SQL timing |
