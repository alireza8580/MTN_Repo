# MTN_Repo

Working repository for the **MTN Irancell ITS DC DBA** team (AHS vendor side).

Two unrelated bodies of work live here:

1. **The DBA attendance / performance tracking system** — the Discord-driven attendance
   parser, its e-mail reporting, and the Docker deployment. This is the repo's main product.
2. **Day-to-day DBA operations material** — Oracle/MySQL/Mongo scripts, Ansible inventory
   generated from the master DB list, per-system runbooks, incident dossiers, and the RFC
   (change request) archive.

The repo is consumed as a git submodule of `infrastructure`, and is symlinked as
`infrastructure/scripts -> MTN_Repo`. Production paths inside the scripts are absolute
(`/root/infrastructure/...`), so **do not relocate files at the repo root** — the cron
wrappers and the container entrypoint resolve them by path.

---

## Directory index

| Directory | What it holds |
|---|---|
| [`RFCs/`](RFCs/) | Archive of 47 submitted MTNI change requests (`.xlsx`), plus [`RFC_RUNBOOK.md`](RFCs/RFC_RUNBOOK.md) — how to fill one out. The spreadsheets are git-ignored (internal hostnames + personal mobile numbers); the runbook is tracked. |
| [`ansible/`](ansible/) | Ansible control tree for the MTNI DB fleet: per-engine inventories under `inventory/mtn_databases/` (oracle, mysql, mongo, postgres, cassandra, mssql), the `mysql_install` role, and playbooks. Inventories are generated from the master DB list by `parse_db_inventory.py`. |
| [`db_size_collector/`](db_size_collector/) | Cross-engine database size collector — per-engine collectors, inventory parser, notifier, installer. Feeds the capacity reporting. |
| [`discord/`](discord/) | Discord side of the attendance system: the idle/offline/voice presence bot, the message exporter, its systemd unit and container files. Plumbing details live in the `discord` skill. |
| [`incidents/`](incidents/) | Per-incident dossiers, one directory per event (`YYYY-MM-DD_<slug>`), each with a `README.md`, the ASH/AWR evidence, and the correspondence. Currently: `2026-03-09_post2p_libcache_mutex_storm`. |
| [`lock_account/`](lock_account/) | Oracle account lock/unlock helper and the shell profile that exposes it. |
| [`new_erefill/`](new_erefill/) | E-refill migration material for `drl167` / `drl168` — stats-gathering SQL, monthly core/event scripts, crontabs, and per-host READMEs. |
| [`ppms_to_adhoc/`](ppms_to_adhoc/) | PPMS → adhoc export/import pipeline: `expdp`/`impdp` drivers, index rebuild, timing SQL, and a `v2/` rewrite. |
| [`windows/`](windows/) | Outlook export helpers (PowerShell + `.bat`) used to pull sent-mail counts for the attendance report. |

---

## Root files

### Attendance & performance tracking

| File | Purpose |
|---|---|
| `attendance_tracker.py` | Main parser and report generator — reads the Discord exports, applies the BRB/leave/on-call rules, writes the daily CSV and syncs to SQLite. |
| `attendance_db.py` | SQLite manager for `attendance.db` (import, stats, per-date and per-person queries). |
| `email_sender.py` | Sends the daily HTML report mail with the CSV attached. |
| `email_extractor.py` | Counts sent mails per team member over EWS (counts mails received *from* members in the shared DBA mailbox). |
| `email_full_extractor.py` | Pulls full mail bodies over EWS into a CSV for `mtn_update.py`. |
| `mtn_update.py` | Work-content analysis over the extracted mail + attendance CSVs. |
| `monthly_report.py` | Monthly aggregation, generated on the 24th of each Jalali month. |
| `view_attendance.py` | Prints a daily CSV report as a formatted table. |
| `leave_parser.py` | Parses complex leave requests (date lists, ranges, hourly forms) out of Discord messages. |
| `build_leave_database.py` | Scans all Discord history and builds `leave_database.json`. |
| `remote_work_tracker.py` | Tracks declared remote-work days from Discord. |
| `migrate_to_sqlite.py` | One-off migration of the JSON databases into the unified `attendance.db`. |
| `sync_json_to_sqlite.py` | Ongoing sync of the bot's idle/offline/voice JSON into SQLite. |
| `iran_calendar.py`, `holidays_iran.csv` | Jalali calendar and Iranian public-holiday table used by the work-hour maths. |
| `daily_attendance_cron.sh` | 19:00 wrapper — export, generate, send. |
| `monthly_attendance_cron.sh` | Monthly report wrapper. |
| `cleanup.sh` | Weekly (Sunday 03:00) removal of old exports and temp files. |
| `leave_database.json`, `leave_log.json`, `remote_work_database.json` | Persisted leave / remote-work state. (`attendance_database.json` is git-ignored.) |

### Documentation

| File | Purpose |
|---|---|
| `ATTENDANCE_PROTOCOL.md` | The team-facing protocol, in Persian — hours, BRB, leave, remote work, on-call. |
| `DBA_Performance_Tracking_System.md` / `.pdf` | Full system design document for the tracking system. |
| `LEAVE_REQUESTS.md` | Free-form notes on outstanding leave requests. |
| `DOCKER_README.md` | Container deployment: build, env vars, volumes, cron schedule, troubleshooting. |

### Deployment

| File | Purpose |
|---|---|
| `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh` | Container build and runtime for the attendance stack. |

### DBA operations

| File | Purpose |
|---|---|
| `parse_db_inventory.py` | Parses `DB_LIST_MTN.xlsx` into the Ansible inventories, skipping rows highlighted red (decommissioned). |
| `auto_skip_repl_error.py` | Finds the failing GTID from `performance_schema` and skips it to restart a stopped MySQL SQL thread. |
| `backup_partition_dwbs_range.sh` | Dumps daily partitions of the dwbs CDR tables (`pm_rated_cdrs`, `pm_tap_cdrs`) over a date range, one gzip per partition. |
| `ddl_pm_rated_cdrs.sql`, `ddl_pm_tap_cdrs.sql` | DDL for those two CDR tables. |
| `check_asm_ods1p.sh` | Queries ARCHGRP free space on ods1p and mails the result. |
| `ora10567_watcher_al.sh` | ORA-10567 watcher on `t3ods1p`. |
| `kthread.sh` | MySQL thread/connection probe against a target host:port. |
| `mysql_installation_manual_8.4_20251130_enhanced.txt` | Step-by-step MySQL 8.4 installation manual. |
| `new_database_oracle_home.txt`, `EREFILL_old_crontab.txt` | Reference notes: Oracle home layout for new DBs; the pre-migration E-refill crontab. |

### Reference data

| File | Purpose |
|---|---|
| `DB_LIST_MTN.xlsx`, `DB_LIST_MTN_2026_01_05.xlsx` | Master MTNI database inventory (current + dated snapshot). Source for the Ansible inventories. |
| `Gather_Stat_V202512.xlsx`, `Gather_Stat_V20260105.xlsx` | Stats-gathering coverage sheets. |
| `t3vl717.mtnirancell.ir-report-20260104T083037Z.html` | CIS Benchmark scan result for MySQL EE 8.4 on `t3vl717`. |

---

## Conventions

- **Absolute production paths.** Scripts reference `/root/infrastructure/...`; the repo is
  checked out there in production and symlinked as `scripts`.
- **Data files are git-ignored, code is not.** The bot's presence databases, the daily CSVs,
  the mail exports and `attendance_database.json` all stay out of git — see `.gitignore`.
- **Secrets never land here.** `.smtp_password` and `.env` are ignored; credentials for the
  fleet live in the parent repo's Ansible vault (`vault-id mtn`).
- **Every subdirectory carries its own `README.md`.** Add one when you add a directory.
