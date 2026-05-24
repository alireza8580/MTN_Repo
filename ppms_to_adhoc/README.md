# PPMS to ADHOC Data Pump Pipeline

Automated Oracle Data Pump (expdp/impdp) pipeline that replicates 15 tables from the **PPMS** (Prepaid Management System) database to the **ADHOC** reporting database every **1st of each Jalali (Persian) month**.

## Requestor

Original request from the SAEI vendor team(who is owner of adhoc1p):

> PPMS to Adhoc1p report schema: TPS01_CARDS, TPS01_LOG_CARDS, TPS11_OUTLET_CODES,
> TPS30_CARD_BOXES, TPS31_CARD_BRICKS, TPS107_DISTRIBUTOR_DETAILS, TPS73_LOGICAL_ORDERS,
> TPS6073_LOGICAL_ORDERS, TPS08_DENOMINATION_TYPES, TPS01_LOG_USED_CARDS,
> TPS09_PPAS_LOG_CARD_PARAMETERS, TPS09_PPAS_CARD_PARAMETERS, TPS145_STOCK_ORDERS,
> TPS74_LOGICAL_ORDERS_DETAIL, TPS6074_LOGICAL_ORDERS_DETAIL

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

## Tables (15 active)

All tables are exported from `PREPAID` schema and imported into `REPORT` schema (`REMAP_SCHEMA=PREPAID:REPORT`).

| # | Table | Parallel (exp/imp) | Notes |
|---|-------|--------------------|-------|
| 1 | TPS01_CARDS | 20/20 | Largest table, range-partitioned by CPS01_DATE_RECHARGE |
| 2 | TPS01_LOG_CARDS | 8/8 | Range-partitioned, similar to TPS01_CARDS |
| 3 | TPS01_LOG_USED_CARDS | 8/8 | Range-partitioned |
| 4 | TPS08_DENOMINATION_TYPES | 1/1 | Small lookup table |
| 5 | TPS107_DISTRIBUTOR_DETAILS | 1/1 | Small lookup table |
| 6 | TPS11_OUTLET_CODES | 1/1 | Small lookup table |
| 7 | TPS30_CARD_BOXES | 4/4 | |
| 8 | TPS31_CARD_BRICKS | 8/8 | |
| 9 | TPS73_LOGICAL_ORDERS | 1/1 | |
| 10 | TPS6073_LOGICAL_ORDERS | 1/1 | |
| 11 | TPS09_PPAS_LOG_CARD_PARAMETERS | 1/1 | |
| 12 | TPS09_PPAS_CARD_PARAMETERS | 1/1 | |
| 13 | TPS145_STOCK_ORDERS | 1/1 | |
| 14 | TPS74_LOGICAL_ORDERS_DETAIL | 1/1 | |
| 15 | TPS6074_LOGICAL_ORDERS_DETAIL | 1/1 | Added 2020/01/20, uses TABLE_EXISTS_ACTION=REPLACE |

> **Note:** `TPS01_USED_CARDS` was commented out in legacy (both export and import) and is not part of the pipeline.
> Its DDL is preserved in `create_tables.sql` inside a block comment for reference.

## Execution Flow

### v2 Two-Server Flow (NFS coordination, no SSH needed)

```
dru110a (PPMS)                                  t1u904 (ADHOC)
─────────────                                   ──────────────
cron at 01:00 daily                             cron at 04:00 daily
  │                                               │
  ├─ is_jalali_first.sh                           ├─ is_jalali_first.sh
  │  exit if not 1st                              │  exit if not 1st
  │                                               │
  ├─ run_export.sh --no-lock                      ├─ run_import.sh (default: NFS poll)
  │   ├─ trap handler (cleanup NFS signal)        │   ├─ polls NFS for .ppms_export_done
  │   ├─ NFS space check (>= 2.1TB)              │   │  (every 3 min, up to 16h)
  │   │   └─ ABORT if insufficient                │   │  detects .ppms_export_failed
  │   ├─ archive old logs, remove old dumps       │   │  (logs it, keeps polling)
  │   ├─ NFS: create .ppms_export_running         │   │
  │   ├─ expdp for each table                     │   └─ (continues when done signal found)
  │   ├─ check logs for ORA- errors               │       ├─ check export logs for ORA-
  │   │                                           │       ├─ validate dump count >= 30
  │   ├─ SUCCESS: NFS .ppms_export_done           │       ├─ Phase 1: Kill→DROP→Validate retry loop (up to 10min), CREATE, NOLOGGING
  │   └─ FAILURE: NFS .ppms_export_failed         │       ├─ Phase 2: impdp (2 streams)
  │                                               │       │   └─ ABORT on failure
        ┌─── NFS ──────────────────────┐          │       ├─ Phase 2b: Row count validation
        │ .dmp + .log + signal files   │          │       ├─ Phase 3: PII cleanup
        └──────────────────────────────┘          │       ├─ Phase 4: CREATE INDEX
                                                  │       ├─ Phase 5: GRANTs
                                                  │       └─ email result (with row counts)
```

### v2 Single-Side Flow (from dru110a, requires SSH)

```
dru110a (PPMS) ─ cron at 01:00 daily
  │
  ├─ is_jalali_first.sh → exit if not 1st
  │
  ├─ run_export.sh (with SSH lock + NFS signals)
  │   ├─ trap handler (cleanup lock + NFS signal on SIGTERM)
  │   ├─ NFS space check (>= 2.1TB)
  │   ├─ SSH lock file on t1u904
  │   ├─ NFS: create .ppms_export_running
  │   ├─ email "export started" (table list, NFS space)
  │   ├─ expdp for each table (from HEAVY_TABLES + LIGHT_TABLES arrays)
  │   ├─ check logs for ORA- errors
  │   ├─ NFS: create .ppms_export_done (or .ppms_export_failed)
  │   ├─ email result (elapsed time, dump count/sizes)
  │   └─ remove SSH lock file
  │
  └─ ssh oracle@t1u904 run_import.sh --skip-wait
      ├─ check export logs for ORA- errors
      ├─ validate dump count >= 30
      ├─ Phase 1: Kill→DROP→Validate retry loop (up to 10min), CREATE, NOLOGGING
      ├─ Phase 2: impdp (2 parallel streams: HEAVY + LIGHT from conf)
      │   └─ ABORT on failure (no indexes on broken data)
      ├─ Phase 2b: Row count validation (warn on empty tables)
      ├─ Phase 3: SET UNUSED on PII columns (from PII_TABLES conf)
      ├─ Phase 4: CREATE INDEX (2 parallel streams)
      ├─ Phase 5: ALTER INDEX PARALLEL 2 + GRANTs
      └─ email result (elapsed times, row counts per table)
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
| `.ppms_export_failed` | `run_export.sh` on failure | Export failed (includes reason text) |

- `run_import.sh` (default mode) polls for `.ppms_export_done` every 3 minutes
- On export failure, `.ppms_export_failed` is written with a reason (e.g. insufficient NFS space)
- Import detects the failure signal and logs it, but **keeps polling** — if someone fixes the issue and re-runs export, import picks up the success signal automatically
- Stale timeout: import aborts after `LOCK_MAX_WAIT_HOURS` (16h)

### SSH Lock File (alternative — requires firewall whitelist)

SSH-based lock on t1u904 (`/tmp/exp.lock`), created/polled/removed via SSH:

- `run_export.sh` (without `--no-lock`): creates lock before export, removes after
- `run_import.sh --wait-ssh`: polls lock until it disappears, then starts import
- Currently blocked by firewall between dru110a ↔ t1u904

### Dump File Validation

Import validates dump files in two ways before proceeding:
1. **Export log check**: Scans `exp_PREPAID*.log` for ORA- errors — aborts if any found
2. **Minimum dump count**: At least `MIN_DUMP_COUNT` (30) `.dmp` files must exist (mtime < 3 days)

### NFS Space Check

Before starting export, `run_export.sh` checks that at least `MIN_NFS_FREE_GB` (2100 GB / ~2.1 TB) of free space is available on the NFS mount. If space is insufficient:
- Export aborts **before** touching any existing files (old dumps remain intact)
- An NFS failure signal is written with the reason
- An email is sent to the DBA group

## PII Handling

After import, sensitive columns are removed from the REPORT tables:

```sql
ALTER TABLE REPORT.TPS01_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
ALTER TABLE REPORT.TPS01_LOG_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
ALTER TABLE REPORT.TPS01_LOG_USED_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
```

## Email Notifications

All emails include contextual details (elapsed time, table lists, row counts, dump sizes, NFS space).

| Event | Recipients | Details Included |
|-------|-----------|------------------|
| Export started | isdcdba@ | Table list, NFS space, parallelism |
| Export success | isdcdba@ | Elapsed time, dump count/sizes, remaining space |
| Export failure | isdcdba@ | Elapsed time, ORA- errors, failed log files |
| Import started | isdcdba@ | Dump count/size, table list, phase overview |
| Import data loading | isdcdba@ | Stream details (heavy/light) |
| Import success | alireza.aghaja@ + isdcdba@ | Total elapsed, data/index times, row counts |
| Import failure | isdcdba@ | Elapsed times, row counts, ORA- errors |
| Index creation started | isdcdba@ | — |
| Index creation finished | isdcdba@ | Elapsed time, stream return codes |
| Row count warning | isdcdba@ | List of empty tables |

## How to Run

### Option A: v2 Two-Server with NFS Coordination (Current Setup)

Both servers have independent cron jobs. Export at 01:00, import at 04:00 (polls NFS). No SSH needed.

**Crontab on dru110a (oracle user):**
```bash
0 1 * * * /oracle/ppms_to_adhoc/cron_ppms_export.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

**Crontab on t1u904 (oracle user):**
```bash
0 4 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

Both check Jalali 1st-of-month. Export creates NFS signal files; import polls for them.
The t1u904 cron also checks for SSH lock file — if present (pipeline mode), it skips.

**Manual run (force, bypass Jalali check):**
```bash
# On dru110a:
/oracle/ppms_to_adhoc/run_export.sh --no-lock

# On t1u904 (after export finishes, or let it poll):
/oracle/ppms_to_adhoc/run_import.sh              # polls NFS signal
/oracle/ppms_to_adhoc/run_import.sh --skip-wait   # skip polling, start immediately
```

### Option B: v2 Smart Pipeline (SSH with NFS Fallback)

Single cron on dru110a. Probes SSH — if available, runs full pipeline. If SSH fails, export completes with NFS signals and import is deferred to t1u904 cron.

**Crontab on dru110a (oracle user):**
```bash
0 1 * * * /oracle/ppms_to_adhoc/cron_pipeline.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

**Crontab on t1u904 (oracle user) — fallback for SSH failure:**
```bash
0 4 * * * /oracle/ppms_to_adhoc/cron_adhoc_import.sh >> /oracle/ppms_to_adhoc/logs/cron.log 2>&1
```

If SSH works: dru110a handles everything, t1u904 cron sees SSH lock and skips.
If SSH fails: dru110a exports with NFS signals, t1u904 cron at 04:00 picks up import.

**Manual run:**
```bash
# Full pipeline (auto-detects SSH)
/oracle/ppms_to_adhoc/run_pipeline.sh
```

### Option C: Legacy Two-Server Execution (Deprecated)

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
| `run_pipeline.sh` | dru110a | Smart orchestrator: probes SSH → full pipeline or export-only with NFS |
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

- **Drop retry loop with session killing** (`run_import.sh` Phase 1): Before dropping tables, enters a retry loop (up to 10 minutes, every 30 seconds) that: (1) kills sessions holding locks (`v$locked_object`) or open references (`v$access`) on target tables, (2) attempts DROP TABLE with `WHENEVER SQLERROR EXIT SQL.SQLCODE`, (3) validates via `dba_tables` that all tables are gone. If a DROP fails with ORA-00054 (resource busy), the loop retries — killing reconnected sessions and re-attempting the DROP. Only aborts after 10 minutes of continuous failure. This prevents the catastrophic scenario where importing into tables with existing data+indexes took 32+ hours in production.
- **NFS space pre-check** (`run_export.sh`): Verifies at least `MIN_NFS_FREE_GB` (2.1 TB) free space before touching any files. If insufficient, aborts with email — old dumps remain intact.
- **NFS signal coordination** (`run_export.sh` + `run_import.sh`): Export writes `.ppms_export_running` / `.ppms_export_done` / `.ppms_export_failed` signal files on shared NFS. Import polls NFS — no SSH required between servers.
- **NFS failure signal** (`run_export.sh`): On failure, writes `.ppms_export_failed` with reason text. Import detects this and logs it, but keeps polling — if export is re-run successfully, import proceeds.
- **Trap handler** (`run_export.sh`): Catches SIGINT/SIGTERM/SIGHUP — writes NFS failure signal and removes SSH lock (if active), sends email before exit.
- **Stale lock timeout** (`run_import.sh`): Both NFS and SSH wait loops abort after `LOCK_MAX_WAIT_HOURS` (default: 16h) instead of waiting forever.
- **Export log validation** (`run_import.sh`): Scans export logs for ORA- errors before importing — catches export-side issues the return code might miss.
- **Minimum dump count** (`run_import.sh`): Verifies at least `MIN_DUMP_COUNT` (30) dump files exist to catch catastrophic export failures.
- **Phase 2 abort** (`run_import.sh`): If either import stream fails, the pipeline aborts immediately — no wasting hours building indexes on broken data.
- **Row count validation** (`run_import.sh`): After Phase 2, queries every imported table. Warns (with email) if any table has 0 rows, catching partial imports.
- **Index creation logging** (`run_import.sh` Phase 4): Both index creation streams log output to `index_stream1_YYYYMMDD.log` and `index_stream2_YYYYMMDD.log` in the log directory for troubleshooting.
- **Rich email notifications**: All emails include contextual details (elapsed time, table lists, row counts, dump sizes, ORA- errors, NFS space).
- **Table lists in conf**: All table names, parallelism, PII columns, and special-case tables are defined in `ppms_to_adhoc.conf`. Adding/removing a table only requires editing the conf — no script changes needed.
