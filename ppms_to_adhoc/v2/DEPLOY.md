# v2 Deployment Guide

Step-by-step instructions for deploying the refactored PPMS-to-ADHOC pipeline on production servers.

## Servers

| Role | Hostname | OS | Oracle | Install Path |
|------|----------|-----|--------|--------------|
| PPMS (source) | dru110a | Solaris 10 | 11.2.0.3 | `/oracle/ppms_to_adhoc/` |
| ADHOC (target) | t1u904 | Solaris 10 | 11.2.0.4 | `/oracle/ppms_to_adhoc/` |

## Prerequisites

Before deploying, verify:

1. **NFS mount** — both servers can access the shared dump directory:
   ```bash
   # Both servers:
   ls /net/dru112c/dba_data/RAMIN/PPMS3P/
   df -h /net/dru112c/dba_data/RAMIN/PPMS3P/
   ```

2. **Oracle directory objects** — must exist in both databases:
   ```sql
   -- On PPMS (ppms3p):
   SELECT directory_name, directory_path FROM dba_directories
   WHERE directory_name = 'RAM_EXP_DRS2';
   -- Should point to: /net/dru112c/dba_data/RAMIN/PPMS3P

   -- On ADHOC (adhoc1p):
   SELECT directory_name, directory_path FROM dba_directories
   WHERE directory_name = 'RAM_IMP_DRS2';
   -- Should point to: /net/dru112c/dba_data/RAMIN/PPMS3P
   ```

4. **mailx** — working on both servers (for email notifications):
   ```bash
   echo "test" | mailx -s "deploy test" isdcdba@mtnirancell.ir
   ```

5. **REPORT schema** — exists on ADHOC database with appropriate tablespace:
   ```sql
   -- On ADHOC (adhoc1p):
   SELECT username, default_tablespace FROM dba_users WHERE username = 'REPORT';
   ```

6. **(Optional) SSH access** — for single-side mode. Not required for NFS coordination:
   ```bash
   # From dru110a as oracle:
   ssh oracle@t1u904 'hostname'
   # If this fails, use Option A (two-server NFS mode) instead of Option B
   ```

## Step 1: Create directories

```bash
# On dru110a (PPMS) — as oracle:
mkdir -p /oracle/ppms_to_adhoc/logs /oracle/ppms_to_adhoc/sql

# On t1u904 (ADHOC) — as oracle:
mkdir -p /oracle/ppms_to_adhoc/logs /oracle/ppms_to_adhoc/sql
```

## Step 2: Deploy files to dru110a (PPMS)

Copy **all** v2 files to dru110a. This is the primary server — it runs the full pipeline.

```bash
# From the repo machine (or wherever v2/ is checked out):
scp v2/ppms_to_adhoc.conf  oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/common.sh            oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/is_jalali_first.sh   oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/run_pipeline.sh      oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/run_export.sh        oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/run_import.sh        oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/cron_pipeline.sh     oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/cron_ppms_export.sh  oracle@dru110a:/oracle/ppms_to_adhoc/
scp v2/sql/*.sql             oracle@dru110a:/oracle/ppms_to_adhoc/sql/
```

## Step 3: Deploy files to t1u904 (ADHOC)

Import scripts, shared config, and Jalali detection needed here.

```bash
scp v2/ppms_to_adhoc.conf  oracle@t1u904:/oracle/ppms_to_adhoc/
scp v2/common.sh            oracle@t1u904:/oracle/ppms_to_adhoc/
scp v2/is_jalali_first.sh   oracle@t1u904:/oracle/ppms_to_adhoc/
scp v2/run_import.sh        oracle@t1u904:/oracle/ppms_to_adhoc/
scp v2/cron_adhoc_import.sh oracle@t1u904:/oracle/ppms_to_adhoc/
scp v2/sql/*.sql             oracle@t1u904:/oracle/ppms_to_adhoc/sql/
```

## Step 4: Set permissions

```bash
# On dru110a:
ssh oracle@dru110a 'chmod 755 /oracle/ppms_to_adhoc/*.sh'

# On t1u904:
ssh oracle@t1u904 'chmod 755 /oracle/ppms_to_adhoc/*.sh'
```

## Step 5: Review configuration

Open `/oracle/ppms_to_adhoc/ppms_to_adhoc.conf` on **both servers** and verify:

| Variable | Expected Value | Check |
|----------|----------------|-------|
| `PPMS_SID` | `ppms3p` | Must match `echo $ORACLE_SID` on dru110a |
| `ADHOC_SID` | `adhoc1p` | Must match `echo $ORACLE_SID` on t1u904 |
| `PPMS_ORACLE_HOME` | `/oracle11/product/11.2.0.3/db_1` | Must exist on dru110a |
| `ADHOC_ORACLE_HOME` | `/oracle/product/11.2.0.4/db_1` | Must exist on t1u904 |
| `NFS_PATH_PPMS` | `/net/dru112c/dba_data/RAMIN/PPMS3P` | Must be accessible from dru110a |
| `NFS_PATH_ADHOC` | `/net/dru112c/dba_data/RAMIN/PPMS3P` | Must be accessible from t1u904 |
| `MAIL_DBA` | `isdcdba@mtnirancell.ir` | DBA distribution list |
| `LOCK_MAX_WAIT_HOURS` | `12` | Adjust if exports take longer |

## Step 6: Dry run (manual test)

Test the Jalali detection first:

```bash
# On dru110a as oracle:
/oracle/ppms_to_adhoc/is_jalali_first.sh
echo $?
# 0 = today is Jalali 1st, 1 = not

# Test a known Jalali 1st date:
/oracle/ppms_to_adhoc/is_jalali_first.sh 20260321
echo $?
# Should print 0 (Farvardin 1, 1405)
```

Test the export (one table only — modify conf temporarily):

```bash
# Quick test: export just one small table
# Edit conf temporarily — set HEAVY_TABLES to empty, LIGHT_TABLES to one table:
#   HEAVY_TABLES=()
#   LIGHT_TABLES=("PREPAID.TPS08_DENOMINATION_TYPES")
# Then:
/oracle/ppms_to_adhoc/run_export.sh --no-lock
```

If export works, test the import on t1u904:

```bash
/oracle/ppms_to_adhoc/run_import.sh --skip-wait
```

**After testing, restore the original table lists in conf.**

## Step 7: Install crontab

### Option A: Two-Server NFS Mode (recommended — no SSH required)

Independent cron on both servers. Import polls NFS signal files.

```bash
# On dru110a (oracle crontab):
crontab -e
```
Add:
```
0 1 * * * /oracle/ppms_to_adhoc/cron_ppms_export.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

```bash
# On t1u904 (oracle crontab):
crontab -e
```
Add:
```
0 4 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

Export at 01:00, import at 04:00. Both check Jalali 1st.
Import also checks: no SSH lock file → NFS done signal → start.

### Option B: Smart Pipeline (auto SSH detection)

Single cron on dru110a + fallback cron on t1u904.

```bash
# On dru110a (oracle crontab):
0 1 * * * /oracle/ppms_to_adhoc/cron_pipeline.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1

# On t1u904 (oracle crontab) — fallback:
0 4 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

If SSH works: dru110a runs everything, SSH lock prevents t1u904 cron from running.
If SSH fails: dru110a exports only, t1u904 cron at 04:00 handles import via NFS.

## Step 8: Disable legacy scripts

Once v2 is working, disable the old scheduling mechanism:

```bash
# On dru110a — comment out or remove old cron entries:
crontab -l | grep ppms_to_adhoc_time

# On t1u904 — same:
crontab -l | grep ppms_to_adhoc_time
```

Do **not** delete the legacy files — keep them for reference.

## Monitoring After Deployment

### Check cron ran

```bash
# On dru110a:
tail -50 /oracle/ppms_to_adhoc/logs/cron.log
```

### Check pipeline log

```bash
# On dru110a (for export):
ls -lt /oracle/ppms_to_adhoc/logs/export_*.log | head -3

# On t1u904 (for import):
ls -lt /oracle/ppms_to_adhoc/logs/import_*.log | head -3
```

### Check Data Pump logs on NFS

```bash
# Export logs:
ls -lt /net/dru112c/dba_data/RAMIN/PPMS3P/exp_PREPAID*.log | head -5

# Import logs:
ls -lt /net/dru112c/dba_data/RAMIN/PPMS3P/imp_PREPAID*.log | head -5
```

### Check for stale signals / lock

```bash
# NFS signal files:
ls -la /net/dru112c/dba_data/RAMIN/PPMS3P/.ppms_export_*
cat /net/dru112c/dba_data/RAMIN/PPMS3P/.ppms_export_done   # shows date + timestamp

# SSH lock (if using single-side mode):
ssh oracle@t1u904 'ls -la /tmp/exp.lock 2>/dev/null && echo "LOCK EXISTS" || echo "No lock"'
```

### Email — expected notifications per run

| Order | Subject | Meaning |
|-------|---------|---------|
| 1 | `PPMS_EXPORT_STARTED` | Export kicked off |
| 2 | `PPMS_EXPORT_COMPLETED` | Export finished OK |
| 3 | `PPMS_IMPORT_STARTED` | Import kicked off |
| 4 | `PPMS_IMPORT_DATA_LOADING` | Phase 2 started |
| 5 | `PPMS_INDEX_CREATION_STARTED` | Phase 4 started |
| 6 | `PPMS_INDEX_CREATION_FINISHED` | Phase 4 done |
| 7 | `PPMS_IMPORT_COMPLETED` | Everything done |

If you see `PPMS_IMPORT_FAILED` or `PPMS_EXPORT_FAILED`, check the logs.

## Rollback

To revert to the legacy scripts:

1. Remove the v2 cron entry
2. Re-enable the old entries (if they were commented out)
3. Edit `ppms_to_adhoc_time.sql` on both servers with the next run date
4. Start both wrapper scripts manually

The v2 files can stay in place — they won't interfere if the cron is disabled.

## Updating Configuration

To **add a new table** to the pipeline:

1. Edit `ppms_to_adhoc.conf` on both servers
2. Add the table to `HEAVY_TABLES` or `LIGHT_TABLES` array
3. Add the table's DDL to `sql/create_tables.sql`
4. Add indexes to `sql/create_indexes_1.sql` or `sql/create_indexes_2.sql`
5. If the table has PII columns, add to `PII_TABLES` array
6. Update `EXPECTED_DUMP_COUNT` if the table produces multiple dump files

To **remove a table**: reverse the above (remove from arrays, comment out DDL).

No changes needed in `run_export.sh`, `run_import.sh`, or any other script.
