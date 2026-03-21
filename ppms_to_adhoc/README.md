# PPMS to ADHOC Data Pump Pipeline

Automated Oracle Data Pump (expdp/impdp) pipeline that replicates 15 tables from the **PPMS** (Prepaid Management System) database to the **ADHOC** reporting database every **1st of each Jalali (Persian) month**.

## Servers

| Role | Hostname | SID | Oracle Home | OS |
|------|----------|-----|-------------|----|
| Source (expdp) | dru110a | `ppms3p` | `/oracle11/product/11.2.0.3/db_1` | Solaris 10 |
| Target (impdp) | t1u904 | `adhoc1p` | `/oracle/product/11.2.0.4/db_1` | Solaris 10 |

SSH connectivity: `oracle@dru110a` → `oracle@t1u904` (currently blocked by firewall — whitelist pending).

## Shared NFS Storage

Both servers access the same NFS storage through the same mount point:

| Server | Hostname | Mount Point | Oracle Directory |
|--------|----------|-------------|-----------------|
| PPMS (export) | dru110a | `/net/dru112c/dba_data/RAMIN/PPMS3P` | `RAM_EXP_DRS2` |
| ADHOC (import) | t1u904 | `/net/dru112c/dba_data/RAMIN/PPMS3P` | `RAM_IMP_DRS2` |

> **Note:** The old ADHOC mount path `/net/drst002/data/RAMIN/PPMS3P` is deprecated and no longer exists. Both servers now access NFS via the dru112c mount.

## Schedule

Runs on the **1st of each Jalali (Persian/Solar Hijri) month** at **01:00** local time.

- **v2 (recommended):** Automatic Jalali detection via cron. Single crontab entry on dru110a.
- **Legacy:** Manual timestamp editing in `ppms_to_adhoc_time.sql` before each run, with scripts started on both servers.

## Tables (15 active, 1 commented out)

All tables are exported from `PREPAID` schema and imported into `REPORT` schema (`REMAP_SCHEMA=PREPAID:REPORT`).

| # | Table | Parallel (exp/imp) | Notes |
|---|-------|--------------------|-------|
| 1 | TPS01_CARDS | 20/20 | Largest table, range-partitioned by CPS01_DATE_RECHARGE |
| 2 | TPS01_LOG_CARDS | 8/8 | Range-partitioned, similar to TPS01_CARDS |
| 3 | TPS01_LOG_USED_CARDS | 8/8 | Range-partitioned |
| 4 | TPS01_USED_CARDS | — | **Commented out** in both export and import |
| 5 | TPS08_DENOMINATION_TYPES | 1/1 | Small lookup table |
| 6 | TPS107_DISTRIBUTOR_DETAILS | 1/1 | Small lookup table |
| 7 | TPS11_OUTLET_CODES | 1/1 | Small lookup table |
| 8 | TPS30_CARD_BOXES | 4/4 | |
| 9 | TPS31_CARD_BRICKS | 8/8 | |
| 10 | TPS73_LOGICAL_ORDERS | 1/1 | |
| 11 | TPS6073_LOGICAL_ORDERS | 1/1 | |
| 12 | TPS09_PPAS_LOG_CARD_PARAMETERS | 1/1 | |
| 13 | TPS09_PPAS_CARD_PARAMETERS | 1/1 | |
| 14 | TPS145_STOCK_ORDERS | 1/1 | |
| 15 | TPS74_LOGICAL_ORDERS_DETAIL | 1/1 | |
| 16 | TPS6074_LOGICAL_ORDERS_DETAIL | 1/1 | Added 2020/01/20, uses TABLE_EXISTS_ACTION=REPLACE |

## Execution Flow

### v2 Two-Server Flow (NFS coordination, no SSH needed)

```
dru110a (PPMS)                                  t1u904 (ADHOC)
─────────────                                   ──────────────
cron at 01:00 daily                             cron at 01:00 daily
  │                                               │
  ├─ is_jalali_first.sh                           ├─ is_jalali_first.sh
  │  exit if not 1st                              │  exit if not 1st
  │                                               │
  ├─ run_export.sh --no-lock                      ├─ run_import.sh (default: NFS poll)
  │   ├─ trap handler (cleanup NFS signal)        │   ├─ polls NFS for .ppms_export_done
  │   ├─ NFS: create .ppms_export_running         │   │  (every 3 min, up to 12h)
  │   ├─ NFS space check                          │   │
  │   ├─ expdp for each table                     │   └─ (continues when done signal found)
  │   ├─ check logs for ORA- errors               │       ├─ validate dump count >= 58
  │   │                                           │       ├─ Phase 1: DROP + CREATE, NOLOGGING
  │   ├─ SUCCESS: NFS .ppms_export_done           │       ├─ Phase 2: impdp (2 streams)
  │   └─ FAILURE: remove .ppms_export_running     │       │   └─ ABORT on failure
  │                                               │       ├─ Phase 2b: Row count validation
        ┌─── NFS ──────────────────────┐          │       ├─ Phase 3: PII cleanup
        │ .dmp + .log + signal files   │          │       ├─ Phase 4: CREATE INDEX
        └──────────────────────────────┘          │       ├─ Phase 5: GRANTs
                                                  │       └─ email result
```

### v2 Single-Side Flow (from dru110a, requires SSH)

```
dru110a (PPMS) ─ cron at 01:00 daily
  │
  ├─ is_jalali_first.sh → exit if not 1st
  │
  ├─ run_export.sh (with SSH lock + NFS signals)
  │   ├─ trap handler (cleanup lock + NFS signal on SIGTERM)
  │   ├─ NFS space check
  │   ├─ SSH lock file on t1u904
  │   ├─ NFS: create .ppms_export_running
  │   ├─ email "export started"
  │   ├─ expdp for each table (from HEAVY_TABLES + LIGHT_TABLES arrays)
  │   ├─ check logs for ORA- errors
  │   ├─ NFS: create .ppms_export_done (or remove running on failure)
  │   ├─ email result
  │   └─ remove SSH lock file
  │
  └─ ssh oracle@t1u904 run_import.sh --skip-wait
      ├─ validate dump count >= 58
      ├─ Phase 1: DROP + CREATE tables (DDL), NOLOGGING
      ├─ Phase 2: impdp (2 parallel streams: HEAVY + LIGHT from conf)
      │   └─ ABORT on failure (no indexes on broken data)
      ├─ Phase 2b: Row count validation (warn on empty tables)
      ├─ Phase 3: SET UNUSED on PII columns (from PII_TABLES conf)
      ├─ Phase 4: CREATE INDEX (2 parallel streams)
      ├─ Phase 5: ALTER INDEX PARALLEL 2 + GRANTs
      └─ email result
```

### Legacy Two-Server Flow

```
                 PPMS Server (dru110a)                    ADHOC Server (t1u904)
                 ─────────────────────                    ─────────────────────

1. ppms_to_adhoc_time_ppms.sh              1. ppms_to_adhoc_time_adhoc.sh
   polls ppms_to_adhoc_time.sql               polls ppms_to_adhoc_time.sql
   (waits for scheduled time)                 (waits for scheduled time)
              │                                          │
              ▼                                          ▼
2. expdp_ppms_to_adhoc.sh                  2. impdp_ppms_to_adhoc.sh
   - checks NFS free space                    - waits for /tmp/exp.lock
   - creates /tmp/exp.lock on t1u904            to disappear (export done)
   - emails DBA team "started"                 - validates dump count >= 58
   - calls ram_exp                             - calls ramram1.sql via sqlplus
   - checks logs for errors                              │
   - emails success/failure                              ▼
   - removes lock file                     3. ramram1.sql (SQL*Plus)
                                               - DROP 15 REPORT.* tables
         ┌─── NFS ──────────────┐              - CREATE 15 tables with DDL
         │ .dmp + .log files    │                (partitioned tables included)
         └──────────────────────┘              - ALTER ... NOLOGGING
                                               - !/oracle/do_imp.sh  ──────┐
                                               - SET UNUSED (PII cols)     │
                                               - !/oracle/do_index.sh ─┐   │
                                               - ALTER INDEX PARALLEL 2│   │
                                               - GRANT SELECT          │   │
                                                                       │   │
                                                    ┌──────────────────┘   │
                                                    ▼                      │
                                            4. do_index.sh           ┌─────┘
                                               runs in parallel:     ▼
                                               - ramram2.sql &    4. do_imp.sh
                                               - ramram3.sql &       runs in parallel:
                                               wait                  - ram_imp1a &
                                                                       (CARDS + LOG_CARDS)
                                                                     - ram_imp2a &
                                                                       (14 other tables)
                                                                     wait
```

## File Inventory (Legacy — for reference only)

> The legacy files in the repository root are the **original unmodified scripts**. They are kept for reference. Use the **v2/** scripts for production.

### Scheduling & Wrapper Scripts

| File | Server | Description |
|------|--------|-------------|
| `ppms_to_adhoc_time.sql` | Both | SQL that returns the scheduled run timestamp. **Edit this before each run.** |
| `ppms_to_adhoc_time_ppms.sh` | PPMS | Top-level wrapper: polls time, then launches export |
| `ppms_to_adhoc_time_adhoc.sh` | ADHOC | Top-level wrapper: polls time, then launches import |

### Export Side (PPMS)

| File | Description |
|------|-------------|
| `expdp_ppms_to_adhoc.sh` | Export orchestrator: lock file, NFS space check, email notifications, error checking |
| `ram_exp` | ksh script with 16 sequential `expdp` commands, EXCLUDE=STATISTICS on all |

### Import Side (ADHOC)

| File | Description |
|------|-------------|
| `impdp_ppms_to_adhoc.sh` | Import orchestrator: waits for lock, validates dump count, calls SQL*Plus |
| `ramram1.sql` | 3088-line SQL*Plus: DROP/CREATE tables, NOLOGGING, shell-out to do_imp/do_index, PII cleanup, GRANTs |
| `do_imp.sh` | Runs ram_imp1a and ram_imp2a in parallel |
| `ram_imp1a` | impdp for 2 big tables (TPS01_CARDS, TPS01_LOG_CARDS) |
| `ram_imp2a` | impdp for 14 smaller tables |
| `do_index.sh` | Runs ramram2.sql and ramram3.sql in parallel |
| `ramram2.sql` | Index creation: TPS01_LOG_CARDS, USED_CARDS, TPS11, TPS30, TPS31, TPS08, LOG_USED |
| `ramram3.sql` | Index creation: TPS73, TPS107, TPS01_CARDS, TPS09, TPS145, TPS74, TPS6073 |
| `impdp_ppms_to_adhoc_mail.sh` | Email notification helper (subject + body via mailx) |

### File Deployment Locations

| File | Deployed To |
|------|-------------|
| `ppms_to_adhoc_time.sql` | PPMS: `/oracle/admin/dba/sql/` and ADHOC: `/oracle/admin/dba/sql/` |
| `ppms_to_adhoc_time_ppms.sh` | PPMS server (run manually or via cron) |
| `ppms_to_adhoc_time_adhoc.sh` | ADHOC server (run manually or via cron) |
| `expdp_ppms_to_adhoc.sh` | PPMS: `/oracle/` |
| `ram_exp` | NFS: `/net/dru112c/dba_data/RAMIN/PPMS3P/` |
| `impdp_ppms_to_adhoc.sh` | ADHOC: `/oracle/` |
| `ramram1.sql` | ADHOC: `/oracle/admin/dba/sql/` |
| `do_imp.sh` | ADHOC: `/oracle/` |
| `ram_imp1a`, `ram_imp2a` | NFS: `/net/dru112c/dba_data/RAMIN/PPMS3P/` |
| `do_index.sh` | ADHOC: `/oracle/` |
| `ramram2.sql`, `ramram3.sql` | ADHOC: `/oracle/admin/dba/sql/` |
| `impdp_ppms_to_adhoc_mail.sh` | ADHOC: `/oracle/` |

## Coordination Mechanisms

### NFS Signal Files (default — no SSH required)

Signal files on the shared NFS directory coordinate export and import without SSH:

| Signal File | Created By | Meaning |
|-------------|------------|--------|
| `.ppms_export_running` | `run_export.sh` at start | Export is in progress |
| `.ppms_export_done` | `run_export.sh` on success | Export completed, import can proceed |

- `run_import.sh` (default mode) polls for `.ppms_export_done` every 3 minutes
- On export failure, `.ppms_export_running` is removed but `.ppms_export_done` is NOT created
- Stale timeout: import aborts after `LOCK_MAX_WAIT_HOURS` (12h)

### SSH Lock File (alternative — requires firewall whitelist)

SSH-based lock on t1u904 (`/tmp/exp.lock`), created/polled/removed via SSH:

- `run_export.sh` (without `--no-lock`): creates lock before export, removes after
- `run_import.sh --wait-ssh`: polls lock until it disappears, then starts import
- Currently blocked by firewall between dru110a ↔ t1u904

### Dump File Validation

Both modes validate that at least 58 `.dmp` files exist (mtime < 3 days) before importing.

## PII Handling

After import, sensitive columns are removed from the REPORT tables:

```sql
ALTER TABLE REPORT.TPS01_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
ALTER TABLE REPORT.TPS01_LOG_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
ALTER TABLE REPORT.TPS01_LOG_USED_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
```

## Email Notifications

| Event | Recipients |
|-------|-----------|
| Export started (with NFS space) | isdcdba@mtnirancell.ir |
| Export success/failure | isdcdba@mtnirancell.ir |
| Import started | isdcdba@mtnirancell.ir |
| Import success | alireza.aghaja@mtnirancell.ir |
| Import failure | isdcdba@mtnirancell.ir |
| Index creation started/finished | isdcdba@mtnirancell.ir |
| Dump count validation failure | (via impdp_ppms_to_adhoc_mail.sh) |

## How to Run

### Option A: v2 Two-Server with NFS Coordination (Current Setup)

Both servers have independent cron jobs. The import polls NFS signal files — no SSH needed.

**Crontab on dru110a (oracle user):**
```bash
0 1 * * * /oracle/ppms_to_adhoc/cron_ppms_export.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

**Crontab on t1u904 (oracle user):**
```bash
0 1 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

Both fire at 01:00 daily. Each checks Jalali 1st-of-month. Export creates NFS signal files; import polls for them.

**Manual run (force, bypass Jalali check):**
```bash
# On dru110a:
/oracle/ppms_to_adhoc/run_export.sh --no-lock

# On t1u904 (after export finishes, or let it poll):
/oracle/ppms_to_adhoc/run_import.sh              # polls NFS signal
/oracle/ppms_to_adhoc/run_import.sh --skip-wait   # skip polling, start immediately
```

### Option B: v2 Single-Side via SSH (Requires Firewall Whitelist)

Runs everything from dru110a, SSHing to t1u904 for import. Requires SSH connectivity.

**Crontab on dru110a (oracle user):**
```bash
0 1 * * * /oracle/ppms_to_adhoc/cron_pipeline.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

**Manual run:**
```bash
# Full pipeline (export + SSH import)
/oracle/ppms_to_adhoc/run_pipeline.sh

# Or separately
/oracle/ppms_to_adhoc/run_export.sh
ssh oracle@t1u904 '/oracle/ppms_to_adhoc/run_import.sh --skip-wait'
```

### Option B: Legacy Two-Server Execution

Uses `ppms_to_adhoc_time.sql` timestamp polling. Requires starting scripts on both servers manually.

**1. Update the schedule time** — edit `ppms_to_adhoc_time.sql` on **both** servers:
```sql
select to_char(TO_DATE('2026-04-21 01:00:00','YYYY-MM-DD HH24:MI:SS'),'yyyymmddhh24miss') from dual;
```

**2. Start both wrapper scripts:**
```bash
# On PPMS (dru110a):
nohup /path/to/ppms_to_adhoc_time_ppms.sh &

# On ADHOC (t1u904):
nohup /path/to/ppms_to_adhoc_time_adhoc.sh &
```

### Monitor

- Export logs: `ls -la /net/dru112c/dba_data/RAMIN/PPMS3P/exp_PREPAID*.log`
- Import logs: `ls -la /net/dru112c/dba_data/RAMIN/PPMS3P/imp_PREPAID*.log`
- Pipeline log: `/oracle/ppms_to_adhoc/logs/pipeline_YYYYMMDD.log`
- Lock file: `ssh oracle@t1u904 'ls -la /tmp/exp.lock'`
- Email inbox for status notifications

## Jalali Calendar Note

The pipeline must run on the **1st of each Jalali month**. The Jalali (Solar Hijri) calendar months don't align with Gregorian months. The approximate Gregorian dates for Jalali 1st days in 1405 (2026-2027):

| Jalali Month | Jalali Date | Gregorian Date |
|--------------|-------------|----------------|
| Farvardin | 1405/01/01 | 2026-03-21 |
| Ordibehesht | 1405/02/01 | 2026-04-21 |
| Khordad | 1405/03/01 | 2026-05-22 |
| Tir | 1405/04/01 | 2026-06-22 |
| Mordad | 1405/05/01 | 2026-07-23 |
| Shahrivar | 1405/06/01 | 2026-08-23 |
| Mehr | 1405/07/01 | 2026-09-23 |
| Aban | 1405/08/01 | 2026-10-23 |
| Azar | 1405/09/01 | 2026-11-22 |
| Dey | 1405/10/01 | 2026-12-22 |
| Bahman | 1405/11/01 | 2027-01-21 |
| Esfand | 1405/12/01 | 2027-02-20 |

## v2 Refactored Scripts

The `v2/` directory contains the refactored pipeline with single-side execution support.

### Deployment

Copy all v2 files to `/oracle/ppms_to_adhoc/` on **dru110a** (PPMS). The import scripts also need to be deployed on **t1u904** (ADHOC).

```bash
# On dru110a (PPMS):
scp -r v2/* oracle@dru110a:/oracle/ppms_to_adhoc/

# On t1u904 (ADHOC) - only import-related files needed:
scp v2/ppms_to_adhoc.conf v2/common.sh v2/run_import.sh oracle@t1u904:/oracle/ppms_to_adhoc/
scp -r v2/sql oracle@t1u904:/oracle/ppms_to_adhoc/
```

### v2 File Inventory

| File | Server | Description |
|------|--------|-------------|
| `ppms_to_adhoc.conf` | Both | Central configuration (SIDs, paths, table arrays, parallelism, PII, email) |
| `common.sh` | Both | Shared functions (logging, email, SSH lock, NFS signals, parallelism, helpers) |
| `is_jalali_first.sh` | Both | Jalali 1st-of-month detection (FarsiWeb algorithm) |
| `run_pipeline.sh` | dru110a | Single-side orchestrator: export + SSH import (Option B) |
| `run_export.sh` | dru110a | Export orchestrator (trap, NFS signals, optional SSH lock, expdp) |
| `run_import.sh` | t1u904 | Import orchestrator (NFS/SSH wait, DDL, impdp, validation, indexes, PII, grants) |
| `cron_pipeline.sh` | dru110a | Cron wrapper: Jalali check → run_pipeline.sh (Option B) |
| `cron_ppms_export.sh` | dru110a | Cron wrapper: Jalali check → run_export.sh (Option A) |
| `cron_adhoc_import.sh` | t1u904 | Cron wrapper: Jalali check → run_import.sh (Option A) |
| `sql/create_tables.sql` | t1u904 | DDL for all 15 REPORT tables |
| `sql/create_indexes_1.sql` | t1u904 | Index stream 1 (LOG_CARDS, USED_CARDS, TPS11, etc.) |
| `sql/create_indexes_2.sql` | t1u904 | Index stream 2 (TPS73, TPS107, TPS01_CARDS, etc.) |
| `sql/post_import.sql` | t1u904 | ALTER INDEX PARALLEL 2 + GRANT SELECT to AIDA_A |

### v2 Safety Features

- **NFS signal coordination** (`run_export.sh` + `run_import.sh`): Export writes `.ppms_export_running` / `.ppms_export_done` signal files on shared NFS. Import polls NFS — no SSH required between servers.
- **Trap handler** (`run_export.sh`): Catches SIGINT/SIGTERM/SIGHUP — removes NFS running signal and SSH lock (if active), sends email before exit. Prevents orphaned signals.
- **Stale lock timeout** (`run_import.sh`): Both NFS and SSH wait loops abort after `LOCK_MAX_WAIT_HOURS` (default: 12h) instead of waiting forever.
- **Phase 2 abort** (`run_import.sh`): If either import stream fails, the pipeline aborts immediately — no wasting hours building indexes on broken data.
- **Row count validation** (`run_import.sh`): After Phase 2, queries every imported table. Warns (with email) if any table has 0 rows, catching partial imports.
- **Table lists in conf**: All table names, parallelism, PII columns, and special-case tables are defined in `ppms_to_adhoc.conf`. Adding/removing a table only requires editing the conf — no script changes needed.
