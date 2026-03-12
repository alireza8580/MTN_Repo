# POST2P Incident — Library Cache Mutex X Storm

**Date:** 18 Esfand 1404 / March 9, 2026  
**Database:** POST2P (Oracle 11.2.0.2)  
**Host:** dru104a (Solaris sparc, 100 CPUs, 512GB RAM)  
**DBID:** 2771519206  
**Incident Window:** 08:47–09:27 (storm onset at 08:47:12, full resolution by ~09:23)  
**Snap IDs:** 233938–233941  
**Ticket Subject:** Problem : @bility - dru104a - Critical CPU Utilization  

---

## 1. Executive Summary

At 08:47:12 on March 9, 2026, a single session (**SID 3082, serial# 44313**) from application server **drvl1078** triggered a cascading library cache: mutex X storm that consumed **93.36% of DB Time** (4,977,019 seconds total wait) and rendered the POST2P database effectively unavailable for ~40 minutes.

**The root blocker was an application-side operation — no DBA/infrastructure action was involved.**

---

## 2. Our Position (AHS Infrastructure DBA Team)

- **We did NOT perform any changes** on POST2P. No ALTER SYSTEM, no parameter changes, no FLUSH SHARED_POOL, no DBMS_STATS, no GRANTS, no DDLs.
- The database had been running stable since **28 Azar 1404** startup (~3 months).
- The root cause was **Session 3082/44313** — connecting from **drvl1078** (application server), user schema **ABL_DBOBJECTS**, via **sqlplus@drvl1078 (TNS V1-V3)**.
- This session held a library cache mutex while performing slow redo log reads, blocking the entire database.
- Erfan (Labs team) initially argued preUploadPK workload was normal — **he was correct on that point**. We acknowledged it. But the trigger was not the workload volume — it was a specific session operation.
- The DDLs (CREATE TABLE TMP_REVOKING_DMS_0/1) from the same machine happened **at 09:23 — 36 minutes AFTER** the storm began. They were secondary, not the trigger.

---

## 3. Timeline of Events

| Time | Event | Source |
|------|-------|--------|
| 08:30:39 | AWR snapshot 233938 begins | AWR |
| 08:30–08:46 | Normal database operation. ~20 sessions from drvl1078, ~18–23 from drum711a | ASH (query 09) |
| **08:47:12** | **STORM BEGINS.** MMON blocked by Session 3082/44313 (mutex already held from drvl1078). Hundreds of sessions instantly blocked on `library cache: mutex X`. | ASH (query 05, 06, 15) |
| 08:47:12 | MMON_SLAVE (Session 322/45335) blocked by Session 3082/44313 | ASH (query 05) |
| 08:47:33 | Session 3082/44313 observed doing `log file sequential read` on redo log# 987952 | ASH (query 07, 11) |
| 08:48 | drvl1078 sessions: 20 → 439. Cascade to drvl141, drum711a | ASH (query 09) |
| 08:49 | drvl1078: 457 sessions. Full cascade to ALL JDBC app servers | ASH (query 09) |
| 08:49:51 | Listener response time: 3,390ms (LISTENER25) | OEM alert |
| 08:50:10 | Listener response time: **20,840ms** (LISTENER0) | OEM alert |
| 08:52 | drvl1078: **545 sessions** (peak). Load average: 2628 | ASH (query 09) |
| 09:05:54 | OEM alert: Critical CPU Utilization 100% | Monitoring email |
| 09:10 | Billing-NOC forwards alert to Unix/DBA teams | Email thread |
| 09:18 | Alireza reports: "load average: 2628.47, unable to connect" | Email thread |
| 09:23:14 | DDLs begin: CREATE TABLE TMP_REVOKING_DMS_0 from drvl1078 | ASH (query 01) |
| 09:23:03 | Session 3082/44313 last ASH sample — storm subsides | ASH (query 11) |
| 09:25 | Alireza confirms: "blocker is gone, able to connect" | Email thread |
| 09:27:07 | AWR snapshot 233941 ends | AWR |

---

## 4. Root Cause Analysis

### 4.1 The Root Blocker: Session 3082/44313

| Attribute | Value |
|-----------|-------|
| SID | 3082 |
| Serial# | 44313 |
| User | ABL_DBOBJECTS (user_id 267) |
| Machine | drvl1078 |
| Program | sqlplus@drvl1078 (TNS V1-V3) |
| SQL ID | 459f3z9u4fb3u |
| SQL Text | `select value$ from props$ where name = 'GLOBAL_DB_NAME'` |
| Wait Event | `log file sequential read` (redo log# 987952–987953) + ON CPU |
| First Seen | 08:47:33 |
| Last Seen | 09:23:03 |
| Duration | ~36 minutes |

### 4.2 Session 3082 Full Timeline (from ASH)

```
08:30-08:32  serial# 29459  drvl1078  INSERT (sql 4ckpdc50q1p94)  db file sequential read
   [SESSION FREED — SID 3082 reused by other connections from drvl141]
08:37-08:40  serial# 42363/42787  drvl141  SELECT (sql 1381vc9ny18sn)  ON CPU
   [SESSION FREED — SID 3082 reallocated]
08:47:33     serial# 44313  drvl1078  SELECT (sql 459f3z9u4fb3u)  log file sequential read  ← STORM START
08:47-08:53  serial# 44313  alternating: log file sequential read + ON CPU  (reading redo logs)
08:53-09:16  serial# 44313  NOT IN ASH (idle/uncaptured — but STILL HOLDING MUTEX)
09:16-09:23  serial# 44313  ON CPU continuously
09:23:03     serial# 44313  Last sample — session ends or releases mutex
```

**Key observation:** The SQL text `select value$ from props$ where name = 'GLOBAL_DB_NAME'` is a dictionary query normally executed during session logon or database link resolution. It should complete in microseconds. This session ran it for **36 minutes** while reading archived redo logs (log# 987952-987953, block# incrementing by ~2048 per sample).

This pattern of sequential redo scanning strongly indicates the session was performing either:
- **LogMiner** (`DBMS_LOGMNR`) — mining archived redo for historical transaction data
- **Flashback Transaction Query** — requiring redo for undo reconstruction
- Some other operation requiring archived redo log access

The `props$` query is likely either part of the operation's initialization or the last SQL captured by ASH before the internal redo-scanning loop.

### 4.3 The Blocking Chain

```
Session 3082/44313 (ABL_DBOBJECTS, drvl1078)
  ├── HOLDS: library cache mutex X
  ├── Doing: log file sequential read (slow redo I/O) + ON CPU
  ├── Directly blocks: 7,141 wait events from 153 unique sessions
  │
  └── BLOCKS → Session 322/45335 (MMON_SLAVE, background)
                ├── WAITING for mutex held by 3082
                ├── HOLDS its own library cache mutex
                └── Blocks: 102,342 wait events from 2,878 unique sessions
                    │
                    └── BLOCKS → EVERYTHING ELSE
                        ├── drvl1078 sessions (20 → 560)
                        ├── drvl141 sessions
                        ├── drum711a sessions (preUploadPK)
                        ├── All JDBC application servers
                        └── New connection attempts (listener impact)
```

**P2 value confirmation:** Session 322's mutex wait P2 = 13237089206272. In Oracle 11.2: `TRUNC(13237089206272 / POWER(2,32)) = 3082`. This mathematically confirms Session 3082 was the mutex holder.

### 4.4 Session Explosion (from ASH query 09)

| Time | drvl1078 sessions | drvl141 | drum711a | Total impacted |
|------|------------------|---------|----------|----------------|
| 08:46 | ~20 | ~20 | ~20 | normal |
| **08:47** | **271** | **153** | **30** | storm begins |
| 08:48 | 439 | 172 | 95 | cascade to JDBC |
| 08:49 | 457 | 166 | 119 | full cascade |
| 08:50 | 509 | 168 | 85 | spreading |
| 08:51 | 526 | 173 | 65 | continuing |
| 08:52 | **545** | 169 | 51 | peak |

### 4.5 AWR Comparison — Same Workload, Different Outcome

|  | March 7 (normal) | March 8 (normal) | March 9 (incident) |
|--|-----------------|-----------------|-------------------|
| preUploadPK executions | 66,470,815 | 28,098,251 | 28,544,200 |
| lib cache mutex X total | 23 sec | 49 sec | **4,977,019 sec** |
| % of DB Time | 0.01% | 0.02% | **93.36%** |
| Avg mutex wait | 0 ms | 0 ms | **5,599 ms** |
| DB Time | 170,948 sec | 208,261 sec | **5,331,216 sec** |
| kgllkdl1 gets | 68,880 | — | **1,487,021,925** (21,600x) |
| kglhdgn1 gets | 78,331 | — | **936,986,368** (12,000x) |

The workload was **identical** (Erfan was correct on this). The trigger was the Session 3082 operation that held the mutex while doing slow redo I/O.

### 4.6 DDLs — Secondary Factor, NOT the Trigger

DDLs appeared in AWR from the **same machine** (drvl1078) and **same user** (ABL_DBOBJECTS):

| SQL ID | Operation | Time (from ASH) | Physical Reads |
|--------|-----------|-----------------|----------------|
| 42mg7x5zcfvk3 | `BEGIN PRC_RECON_REVOKING_DMS(); END;` | 09:23+ | — |
| 7x6qn1dz83c0k | `CREATE TABLE TMP_REVOKING_DMS_0 ...` | 09:23:14-09:24:38 | 1,600,455 |
| 265hrvacvmp0w | `CREATE TABLE TMP_REVOKING_DMS_1 ...` | 09:24:48-09:26:50 | 1,125,528 |

These DDLs started at **09:23** — 36 minutes AFTER the storm began at 08:47. They are from the same ABL_DBOBJECTS user on drvl1078, possibly part of a script that also started the redo-scanning operation. They may have prolonged the contention but **did not cause it**.

---

## 5. Investigation Results (Additional Queries — Completed)

### 5.1 Queries Executed and Findings

Six additional queries were executed against `dba_hist_active_sess_history` and `dba_source` to close evidence gaps. Results are in `ash_queries/12-17`.

| Query | File | Key Finding |
|-------|------|-------------|
| Session 3082 all SQL IDs | 12_session_3082_all_sql_ids.txt | Only ONE sql_id: `459f3z9u4fb3u` (SELECT), 59 samples, 08:47:33-09:23:03 |
| SQL text lookup | 13_sql_text_lookup.txt | `select value$ from props$ where name = 'GLOBAL_DB_NAME'` — internal Oracle recursive SQL |
| Session link 3082/1750 | 14_session_link_3082_1750.txt | Separate sessions (different serial#s), same machine/user. Session 1750 was blocked 09:16-09:23, then ran DDLs |
| MMON blocking timeline | 15_mmon_blocking_by_3082_timeline.txt | 62 ASH samples: Session 322 blocked by 3082 from 08:47:12 to 09:23:03. P2 mathematically proves SID 3082 |
| LogMiner text search | 16_logminer_search_empty.txt | No "LOGMNR" found in any sql_text — operation was internal/recursive |
| PRC_RECON_REVOKING_DMS source | 17_prc_recon_revoking_dms_source.txt | Billing procedure: creates temp tables, loops to revoke DMS suspensions. 100% application code |

### 5.2 Conclusions from Additional Evidence

1. **Session 3082 ran ONLY an internal Oracle dictionary query** (`props$`). No application SQL was visible in ASH. This means the underlying operation was internal/recursive — consistent with LogMiner, Flashback, or a similar redo-reading feature. The session performed redo scanning (query 11) with no visible calling SQL.

2. **Sessions 3082 and 1750 are SEPARATE sessions** (serial# 44313 vs 2249). Session 1750 appeared at 09:16:44 with NO sql_id (waiting for mutex release), then executed DDLs at 09:23 after Session 3082 released. Both from same machine (drvl1078), same program (sqlplus), same user (ABL_DBOBJECTS).

3. **MMON was blocked for the ENTIRE duration**: 62 consecutive ASH samples from 08:47:12 to 09:23:03, all showing P2=13237089206272 → `TRUNC(P2/2^32) = 3082`. This is irrefutable mathematical proof.

4. **PRC_RECON_REVOKING_DMS is an application billing procedure** that manages DMS suspension reactivation for subscribers. It references billing tables (CB_SUSPENDED_DTLS, V_GSM_SERVICE_MAST), change requests (CR2028), and defects (DEFECT-20418, DEFECT-20608). It does NOT contain LogMiner calls.

5. **The redo-scanning operation (Session 3082) and the DDL procedure (Session 1750) appear to be from DIFFERENT scripts/tools** running from the same application server (drvl1078).

### 5.3 Remaining Questions for Labs/Application Team

1. **What script/process ran as ABL_DBOBJECTS from drvl1078 via SQL*Plus at ~08:47 on March 9?** All ASH evidence points to an internal redo-scanning operation. Labs must identify what was executed.

2. **Was LogMiner, Flashback, or any redo-reading tool invoked from drvl1078?** The `props$` recursive SQL + `log file sequential read` pattern is characteristic of these features.

3. **Who scheduled PRC_RECON_REVOKING_DMS?** This procedure was not present in March 7, 8, or 17 Esfand AWRs. It ran for the first time during the incident window.

### 5.4 Oracle Known Issues (for DBA reference, not for email)

Oracle 11.2.0.2 has known bugs related to `library cache: mutex X`:
- Bug 9539392, 9767785, 10411618 — mutex contention under certain conditions
- LogMiner/Flashback operations can hold library cache mutexes during redo reads
- MOS Note 1298015.1: High Library Cache Mutex X Waits
- The `_kgl_bucket_count` parameter may help if the issue recurs

---

## 6. Erfan's Arguments and Our Rebuttals

### Erfan's Argument 1: "The workload is normal, preUploadPK has 66M on March 7"
**Our response:** Acknowledged. He was correct. The workload volume was normal. But the same workload produced catastrophic mutex waits because of Session 3082's operation.

### Erfan's Argument 2: "No waiting event before 9:15 AM in top activity graph"
**Our response:** The AWR snapshot at 09:00 did NOT generate because MMON was blocked (it was the #2 in the blocking chain). The graph shows only aggregated intervals. ASH per-second data proves the storm started at **08:47:12**, not 09:15. The 09:15 appearance in the graph is when the backlogged samples finally became visible.

### Erfan's Argument 3: "Listener problems since 08:50 — infrastructure issue"
**Our response:** Listener slowness (20,840ms at 08:50:10) is a **direct consequence** of the database-level mutex contention. When the library cache is serialized, new session establishment is blocked, causing listener timeouts. The listener itself had no independent problem.

### Erfan's Argument 4: "sbpost2p Data Guard issues since 3:18 AM"
**Our response:** The standby database (sbpost2p) ORA-03113 at 03:18 is unrelated to the 08:47 library cache storm. Data Guard log shipping issues don't cause library cache mutex contention on the primary.

### Erfan's Argument 5: "CPU load increased after 9:15, not before"
**Our response:** CPU was being consumed but processes were mostly WAITING (on mutexes, not running on CPU). `library cache: mutex X` is a "Concurrency" class wait — sessions spin briefly then sleep. The load average of 2628 confirms massive process pileup. The CPU spike at 09:15+ happens when the mutex releases and all queued sessions execute simultaneously.

---

## 7. What To Do Next

### Immediate (Email Response)
1. **Write email v6** with the new Session 3082 evidence (queries 12-17)
2. Key points for the email:
   - Root blocker identified: Session 3082/44313 from drvl1078, user ABL_DBOBJECTS
   - Only SQL: `select value$ from props$` — internal Oracle recursive SQL (not user-initiated)
   - 62 ASH samples proving MMON blocked by SID 3082 (P2 mathematical proof)
   - Session 1750 (DDLs) was blocked until 09:23 — DDLs are secondary, not trigger
   - PRC_RECON_REVOKING_DMS source obtained — 100% application billing procedure
   - Ask Labs: what process ran from drvl1078 at ~08:47 doing redo scanning?

### If Labs Denies (Escalation Evidence)
- 62 consecutive ASH samples with P2=13237089206272 → TRUNC(P2/2^32) = 3082 is irrefutable
- Session 3082/44313 machine=drvl1078 is an APPLICATION server, not DBA-managed
- ABL_DBOBJECTS (user_id 267) is NOT a DBA schema
- PRC_RECON_REVOKING_DMS references billing tables, CRs, and defects — application code
- Session 1750 was itself blocked by the storm (empty sql_id from 09:16-09:23)

### Prevention
- If the operation was LogMiner/Flashback, schedule outside peak hours
- Consider `_kgl_bucket_count` tuning if 11.2 mutex bug is involved
- PRC_RECON_REVOKING_DMS and its DDLs should run during maintenance window
- Monitor `library cache: mutex X` via PMM/OEM alerts with threshold

---

## 8. File Index

### emails/
| File | Description |
|------|-------------|
| 01_full_email_thread.txt | Complete email loop (all participants, bottom-up chronological) |
| 02_initial_request_to_respond.txt | Erfan's email that triggered our initial AWR investigation |
| 03_response_draft_v5.txt | Previous email draft (v5 — superseded, focused on DDLs as cause) |
| 04_response_draft_v6.txt | Previous email draft (v6 — Session 3082 evidence, P2 proof, DDLs proven secondary) |
| **05_response_draft_v7.txt** | **Current email draft (v7 — enhanced technical details, kgl stats, redo block progression, ASH gap explanation, stronger action items)** |

### awr_reports/
| File | Description |
|------|-------------|
| baseline_17esfand_snap233891_233894.html | 17 Esfand 09:00-10:30 — our baseline (normal day) |
| incident_18esfand_snap233938_233941.html | 18 Esfand 08:30-09:27 — incident window |
| erfan_march7_0800_0900.html | March 7 08:00-09:00 — Erfan's evidence (66M preUploadPK, normal) |
| erfan_march8_0800_0900.html | March 8 08:00-09:00 — Erfan's evidence (28M, normal) |
| erfan_march7_0800_0900.zip | ZIP backup of March 7 report |

### ash_queries/
| File | Description |
|------|-------------|
| 01_ddl_operations.csv | All DDL operations from ASH — CREATE TABLE at 09:23 |
| 02_ddl_session_details.csv | Session info for DDL SQL IDs (session 1750/2249) |
| 03_mutex_waiters_by_user_machine.csv | Top waiters: ABL_DBOBJECTS/drvl1078 (24,926 samples) |
| 04_timeline_ddl_vs_mutex.csv | Minute-by-minute DDL count vs mutex count |
| 05_storm_onset_0842_0848.csv | All ASH activity 08:42-08:48 — shows exact 08:47:12 explosion |
| 06_mutex_holders_blocking_sessions.txt | Who HELD the mutex: 3082 (7,141 blocks), 322 (102,342 blocks) |
| 07_blocking_sessions_activity.txt | What blocking sessions 322 and 3082 were doing |
| 08_drvl1078_activity_0830_0850.csv | All drvl1078 sessions 08:30-08:50 — shows normal → storm |
| 09_session_count_by_machine_minute.txt | Session explosion by machine per minute |
| 10_mutex_p1_p2_p3_values.txt | Mutex parameter values (P2→SID decoding) |
| 11_root_blocker_session_3082_timeline.txt | Complete ASH timeline for SID 3082 (root blocker) |
| **12_session_3082_all_sql_ids.txt** | **All SQL IDs for Session 3082/44313 — only 459f3z9u4fb3u (SELECT, 59 samples)** |
| **13_sql_text_lookup.txt** | **SQL text: `select value$ from props$ where name = 'GLOBAL_DB_NAME'` — internal recursive** |
| **14_session_link_3082_1750.txt** | **Session link: 3082 (root blocker) and 1750 (DDL executor) — separate sessions, same origin** |
| **15_mmon_blocking_by_3082_timeline.txt** | **62 ASH samples: MMON blocked by SID 3082, P2 math proof (08:47:12–09:23:03)** |
| **16_logminer_search_empty.txt** | **LogMiner search — empty result (no LOGMNR in any sql_text)** |
| **17_prc_recon_revoking_dms_source.txt** | **Full procedure source — billing/subscription management, 100% application code** |

---

## 9. Key People and Team Stances

### Teams Involved

| Team | Full Name | Role in Incident |
|------|-----------|-----------------|
| **AHS (Arya Hamrah Samaneh)** | Infrastructure DBA Team | Database administration, host management. **Our team.** Responsible for DB health, AWR analysis, performance investigation. |
| **Labs (MTNIrancell - Labs)** | Application Team | Application development, application schemas (ABL_DBOBJECTS), procedures (PRC_RECON_REVOKING_DMS), SQL*Plus scripts on app servers (drvl1078, drvl141, drum711a). |

### People

| Name | Team | Role | Stance |
|------|------|------|--------|
| **Alireza Aghajanzadeh Gheshlaghi** | **AHS (Infra DBA)** | Lead investigator | The root blocker is Session 3082 from drvl1078 (ABL_DBOBJECTS) — application-side operation. No DBA/infrastructure change was made. |
| **Mohsen Roudsaz** | **AHS (Infra DBA)** | Initial responder during incident | First to identify concurrency wait event and root cause direction. Sent initial email pointing to application concurrent DML. |
| **Masoud Rafiei** | **AHS (Infra DBA)** | DBA | Requested Service Desk to reassign incident to application team based on provided evidence. |
| **Erfan Fatemi Zadeh** | **Labs (Application)** | Application team lead for this incident | Claims: no application issue before 09:15, workload is normal (correct), listener problem is infra-side (incorrect — caused by DB contention). Provided AWR for March 7/8 to prove workload was normal. Trying to keep incident assigned to infra/DBA team. |
| **Mohammadsaleh Bayat Jozani** | **Labs (Application)** | Application team | Reported initial alert, asked DBA/Unix to check. Showed EM graph claiming "no high load at 8:58" — this is because the graph aggregation missed the per-second ASH data showing the storm. |

### Team Positions Summary

**AHS (Our Position):**
- The database was stable for 3 months (since 28 Azar startup)
- No DBA operations occurred on March 9 morning
- ASH data proves Session 3082/44313 from **drvl1078** (application server) as the root blocker
- The operation (redo scanning, likely LogMiner) held library cache mutexes causing 102K+ blocked waits
- DDLs (PRC_RECON_REVOKING_DMS, TMP_REVOKING_DMS tables) at 09:23 from same user/machine confirm application activity
- Incident should be assigned to Labs (application team)

**Labs (Their Position):**
- preUploadPK workload is normal (66M on Mar 7, 28M on Mar 8/9) — **correct, we agree**
- No application-related issues visible before 09:15 in EM top activity — **incorrect: ASH shows storm at 08:47:12, EM graph aggregation hid it**
- Listener problem since 08:50 suggests infrastructure issue — **incorrect: listener slowness is a consequence of DB contention, not a cause**
- sbpost2p Data Guard errors since 03:18 AM — **unrelated to the 08:47 library cache storm**
- CPU load only spiked after 09:15 — **misleading: the load was in WAIT state (mutex), not CPU-intensive, which is why the CPU graph looks low until sessions unblock**

---

## 10. Database Reference

```
Database:    POST2P
DBID:        2771519206
Instance:    post2p (inst_num 1, NOT RAC)
Host:        dru104a
IP:          10.132.59.67
OS:          SunOS (Solaris sparc 64-bit)
Version:     Oracle 11.2.0.2
CPUs:        100 (50 cores, 4 sockets)
RAM:         512 GB
Startup:     28 Azar 1404 (21:09)
```
