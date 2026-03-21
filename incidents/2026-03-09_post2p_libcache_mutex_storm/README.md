# POST2P Incident — Library Cache Mutex X Storm

**Date:** 18 Esfand 1404 / March 9, 2026  
**Database:** POST2P (Oracle 11.2.0.2)  
**Host:** dru104a (Solaris sparc, 100 CPUs, 512GB RAM)  
**DBID:** 2771519206  
**Incident Window:** 08:47–09:27 (storm onset at 08:47:12, full resolution by ~09:23)  
**Snap IDs:** 233938–233941  
**Ticket:** MTNI-1459453  
**Ticket Subject:** Problem : @bility - dru104a - Critical CPU Utilization  
**Previous Identical Incident:** MTNI-760378 (May 15, 2022) — same DB, same symptoms, RCA = "Application Misuse"  
**Status:** Awaiting application team response to identify Session 3082's operation. Email v8 finalized (March 14, 2026) — addressed to Omid/Mehdi, includes 2022 precedent (MTNI-760378), technical rebuttals, SOC option.  

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

### Phase 1 — March 9-10 (Initial Email Exchange)

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

### Phase 2 — March 14 (Post-Meeting Response)

After a meeting held March 14 (2:00-2:30 PM), Erfan sent a follow-up email at 4:27 PM with a strategy shift. Instead of defending application workload, he pivoted to blaming Oracle bugs and SYS internal session.

### Erfan's Argument 6: "SYS Session 322 = 68% blocking, application 3082 = only 8%"
**Our response:** This is **misleading**. Session 322 (SYS, MMON_SLAVE) is an Oracle background process that was **BLOCKED BY Session 3082**. The blocking relationship is proven mathematically:

```
Session 322 waited on "library cache: mutex X" with P2 = 13,237,089,206,272
TRUNC(13,237,089,206,272 / POWER(2,32)) = 3082
```

The upper 32 bits of P2 contain the SID of the mutex holder. Session 322 was waiting for 3082 to release the mutex. The "68%" attributed to Session 322 is **cascading impact** — like blaming a traffic jam on the second car in line while ignoring the accident ahead of it.

62 consecutive ASH samples (08:47:12–09:23:03) confirm this chain without interruption.

### Erfan's Argument 7: "ORA-00600 errors in alert log — Oracle bugs"
**Our response:** The alert log entries Erfan cited:

```
ORA-00600: [kkscxa_1]              at 08:52:43
ORA-00600: [kgh_heap_sizes:ds]     at 08:52:43
KGX cleanup, Mutex 3b1c0326a8(322, 0)
```

Key observations:
- The storm began at **08:47:12** (confirmed by ASH). These errors appeared at **08:52:43** — a full **5 minutes and 31 seconds later**.
- `[kkscxa_1]` = "kernel kompile shared cursor add" — occurs when shared pool is under extreme contention. This is exactly what happens when a mutex is held for minutes instead of microseconds.
- The mutex reference `(322, 0)` refers to Session 322 (MMON_SLAVE) — the same session our analysis showed was blocked by 3082.
- These errors are **SYMPTOMS** of prolonged mutex holding, not independent bugs. Presenting consequences as causes reverses the causality chain.

### Erfan's Argument 8: "Upgrade to Oracle 11.2.0.4 — these bugs are fixed in that release"
**Our response:** This is a deflection that shifts the burden to infrastructure. Even on 11.2.0.4, a session holding a library cache mutex for 36 minutes while scanning redo logs would produce an identical storm. The upgrade is a capacity planning topic; it does not explain WHY Session 3082 was scanning redo logs on March 9 when it never did on March 7 or March 8. 

Note: We are not opposed to the upgrade — in fact, certain blocked infrastructure tasks such as server migration depend on it. But this is not the RCA for this incident.

### Erfan's Argument 9: "No abnormal load observed compared to previous days"
**Our response:** We agree. That is precisely the point — the same normal workload produced a **100,000x increase** in mutex wait time. The only difference on March 9 was Session 3082's redo-scanning operation from drvl1078, which does not appear in any comparison AWR (March 7, March 8, 17 Esfand).

### Pattern of Deflection

The application team has produced three successive misdirections over the course of the investigation:

| # | Deflection | When | Debunked |
|---|-----------|------|----------|
| 1 | "Listener problems since 08:50" | March 9-10 | Listener degradation is consequence of DB mutex, not cause |
| 2 | "ORA-00600 errors = Oracle bugs" | March 14 | Errors at 08:52:43, 5 min AFTER storm at 08:47:12. Symptoms, not causes. |
| 3 | "Upgrade Oracle to 11.2.0.4" | March 14 | Deflection to infra. Doesn't explain Session 3082's behavior. Same issue occurred in 2022 — classified as "Application Misuse" |

---

## 7. Past Incident: MTNI-760378 (May 15, 2022)

### Overview

The **exact same issue** occurred on POST2P (dru104a) on May 15, 2022 — documented as JIRA ticket MTNI-760378.

| Attribute | 2022 Incident (MTNI-760378) | 2026 Incident (MTNI-1459453) |
|-----------|---------------------------|------------------------------|
| Database | POST2P, dru104a | POST2P, dru104a |
| Primary Wait Event | library cache: mutex X | library cache: mutex X |
| Symptoms | Mass blocking sessions, DB inaccessible | Mass blocking sessions, DB inaccessible |
| Services Impacted | DPOS, CLM, UMS IVR, MFS, iChat, NGPG, eShop, MyIrancell, AAT lending | @bility (Billing/CBS) and dependents |
| Resolution | Kill blocking sessions + DB bounce (CAT1 Emergency Change MTNI-760463) | Kill blocker at 09:23 + DB recovered |
| **Official RCA Cause** | **"Application Misuse"** | Pending (disputed by Labs team) |
| Cause Detail | "huge load on Ability database caused oracle background processes to fail" | Session 3082 from drvl1078 holding mutex for 36 min |
| Final RCA Comment | "Due to high version count error number of blocking session on Ability database were increased and caused inaccessibility" | Investigation complete, application team not examining |
| Application Team | Tecnotree (Benyamin Teimouri) | Labs (Erfan Fatemi Zadeh) |
| Application Team Response | Examined evidence, acknowledged issue, engaged constructively | 3 successive deflections over 5 days |

### 2022 Email Thread (MTNI-760378) — Key Exchanges

**Our email (May 15, 2022 — same day):**
> "There are huge amount of blocking session on DB. DB is going to crash with this load. load average: 3094.62, 2653.15, 1720.68"

**Our follow-up (May 15, 2022):**
> "High concurrency of library cache: mutex X impacted the DB. This concurrency is due to high hard parse which we have no control over it. Could you please advice to reassign the ticket."

**Benyamin Teimouri (Tecnotree DBA, May 16, 2022) — same defense as Erfan:**
> "As we checked, our load and also the hard pars did not increase" — provided TPS data and hard parse counts for comparison

Key data from Benyamin's analysis (comparing 4 Sundays):

| Date | Parse | Hard Parse | library cache: mutex X |
|------|-------|------------|----------------------|
| 1400/10/26 | 2,195 | 32.5 | 409,429 |
| 1400/11/03 | 2,356 | 26 | 732,246 |
| 1401/02/11 | 2,355 | 32.9 | 539,820 |
| 1401/02/25 (incident) | 2,095 | 29 | 539,806 |

**Benyamin (May 18, 2022):**
> "based on when high load happen, DB do not generate snapshot, please generate it manually on issue time then we can focus on issue to fix it."

This is the exact same diagnostic gap as 2026 — AWR snapshot didn't generate because MMON was blocked. They recognized the problem but didn't solve it.

**Our final response (May 18, 2022):**
> "We need a symptom to predict the upcoming issue... You can prepare a query which detects abnormal usage/load and share it with zabbix team and set it trigger on it. For instance, if blocking session exceed 300 sessions, a notification gets generated."

**P&C (Zeinab Salehi) asked Labs in the JIRA ticket comments:**
- To investigate the root cause of "library cache: mutex X"
- To implement a solution to prevent recurrence

**Outcome:** Four years later, the identical scenario recurred — same database, same wait event, same type of blocking sessions, same service impact — confirming those preventive measures were never implemented.

### Key Parallels

1. **Same defense:** In 2022, Benyamin said "our load and hard parse did not increase." In 2026, Erfan says "no abnormal load observed." Both correct, both irrelevant — the trigger was a specific session, not aggregate workload.
2. **Same missing AWR:** In 2022, AWR snapshots didn't generate during the incident. In 2026, snap 233939 at 09:00 was missed because MMON was blocked.
3. **Same resolution:** Kill blocking sessions + wait for recovery.
4. **Different team behavior:** In 2022, Tecnotree engaged constructively (provided data, committed to investigation). In 2026, Labs has produced 3 misdirections over 5 days.
5. **Official RCA in 2022 was "Application Misuse"** — the exact classification the current incident should receive.

### Source Files

| File | Description |
|------|-------------|
| MTNI-760378.doc | JIRA ticket export (HTML format) — contains RCA fields, comments, action items |
| check status of post2p  MTNI-760378.msg | Full Outlook email thread (4MB) — complete investigation correspondence |
| RE Problem  @bility - dru104a - Critical CPU Utilization  MTNI-1459453.msg | Current incident Outlook email thread (1.3MB) |

---

## 8. What To Do Next

### Current Status (as of March 14, 2026)
- Email v8 finalized in `emails/06_response_draft_v8.txt` — addressed to Omid/Mehdi (account managers)
- References 2022 precedent first, highlights lack of TT handover, counters all 3 new arguments
- Mentions 2 attachments: MTNI-760378 Icare ticket + email thread
- SOC logs option suggested for drvl1078 verification

### Remaining Actions
1. **Send email v8** with attachments (MTNI-760378.doc and MTNI-760378.msg)
2. **Wait for application team** to identify what Session 3082 was running from drvl1078
3. If no response: escalate to Mehdi Kheir Andish with full evidence package

### If Labs Continues to Deflect (Escalation Evidence)
- 62 consecutive ASH samples with P2=13237089206272 → TRUNC(P2/2^32) = 3082 is irrefutable
- Session 3082/44313 machine=drvl1078 is an APPLICATION server, not DBA-managed
- ABL_DBOBJECTS (user_id 267) is NOT a DBA schema
- PRC_RECON_REVOKING_DMS references billing tables, CRs, and defects — application code
- Session 1750 was itself blocked by the storm (empty sql_id from 09:16-09:23)
- **MTNI-760378 precedent** — same issue in 2022 was classified as "Application Misuse"

### Prevention
- If the operation was LogMiner/Flashback, schedule outside peak hours
- Consider `_kgl_bucket_count` tuning if 11.2 mutex bug is involved
- PRC_RECON_REVOKING_DMS and its DDLs should run during maintenance window
- Monitor `library cache: mutex X` via PMM/OEM alerts with threshold

---

## 9. File Index

### Root Directory
| File | Description |
|------|-------------|
| README.md | This file — master investigation document |
| full_loop_incident.txt | Complete email thread (all participants, newest-first). Updated March 14 with Erfan's post-meeting response. |
| oem_screenshot.png | OEM screenshot of Critical CPU Utilization alert |
| MTNI-760378.doc | **Past Incident (2022):** JIRA ticket export in HTML format — RCA = "Application Misuse" |
| check status of post2p  MTNI-760378.msg | **Past Incident (2022):** Full Outlook email thread (4MB) — investigation correspondence with Tecnotree |
| RE Problem  @bility - dru104a - Critical CPU Utilization  MTNI-1459453.msg | **Current Incident:** Outlook email thread (1.3MB) — includes Erfan's March 14 response |

### emails/
| File | Description |
|------|-------------|
| 01_full_email_thread.txt | Complete email loop (all participants, bottom-up chronological) — original version pre-March 14 |
| 02_initial_request_to_respond.txt | Erfan's email that triggered our initial AWR investigation |
| 03_response_draft_v5.txt | Email draft v5 (superseded — focused on DDLs as cause) |
| 04_response_draft_v6.txt | Email draft v6 (Session 3082 evidence, P2 proof, DDLs proven secondary) |
| 05_response_draft_v7.txt | Email draft v7 (enhanced: kgl stats, redo block progression, ASH gap explanation) — targets Erfan |
| 05_response_draft_v7.html | HTML version of v7 |
| **06_response_draft_v8.txt** | **Final email v8 — targets Omid/Mehdi (account managers). Opens with 2022 precedent comparison, highlights lack of TT handover, counters 3 new arguments (68%/8%, ORA-600, upgrade), suggests SOC logs. 2 attachments.** |
| **07_past_incident_MTNI-760378_email_thread.txt** | **Extracted text from .msg — Complete 2022 email thread (578K chars). Key exchanges between Alireza, Benyamin (TT DBA), Mohammadali, Zeinab (P&C). Shows "Application Misuse" RCA process.** |
| **08_current_incident_MTNI-1459453_email_thread.txt** | **Extracted text from .msg — Current incident email thread (68K chars). Includes Erfan's March 14 post-meeting response and all prior exchanges.** |
| **09_past_incident_MTNI-760378_jira_ticket.txt** | **Extracted text from .doc — JIRA ticket export showing RCA fields, cause="Application Misuse", comments, action items, impacted services.** |
| email_post2p_response_draft.txt | Legacy working draft |
| email_post2p_to_respond.txt. | Legacy initial request |

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
| **18_session_3082_osuser.csv** | **OS user for Session 3082 — confirms application-level access** |
| query_1_post_incident.csv | Legacy: First post-incident query |
| query_2_post_incident.csv | Legacy: Second post-incident query |
| query_2_5_post_incident.csv | Legacy: Extended second query |
| query_2_8_post_incident.csv | Legacy: Extended second query (variant) |
| query_3_post_incident.csv | Legacy: Third post-incident query |
| query_4_post_incident.csv | Legacy: Fourth post-incident query |
| query_6.txt | Legacy: Query 6 results |
| query_7.txt | Legacy: Query 7 results |
| query_9.txt | Legacy: Query 9 results |
| query_10.txt | Legacy: Query 10 results |
| session_id_3082.txt | Legacy: Initial Session 3082 identification |

---

## 10. Key People and Team Stances

### Teams Involved

| Team | Full Name | Role in Incident |
|------|-----------|-----------------|
| **AHS (Arya Hamrah Samaneh)** | Infrastructure DBA Team | Database administration, host management. **Our team.** Responsible for DB health, AWR analysis, performance investigation. |
| **Labs (MTNIrancell - Labs)** | Application Team | Application development, application schemas (ABL_DBOBJECTS), procedures (PRC_RECON_REVOKING_DMS), SQL*Plus scripts on app servers (drvl1078, drvl141, drum711a). |
| **ITS Service Desk** | Incident Management | Ticket routing, meeting coordination |
| **P&C** | Performance & Capacity Management | RCA review, action item tracking |

### People

| Name | Team | Role | Stance |
|------|------|------|--------|
| **Alireza Aghajanzadeh Gheshlaghi** | **AHS (Infra DBA)** | Lead investigator | Root blocker is Session 3082 from drvl1078 — application-side operation. No DBA/infrastructure change was made. |
| **Mohsen Roudsaz** | **AHS (Infra DBA)** | Initial responder | First to identify concurrency wait event and root cause direction. |
| **Masoud Rafiei** | **AHS (Infra DBA)** | DBA | Requested SD to reassign incident to application team. |
| **Erfan Fatemi Zadeh** | **Labs (Application)** | Application team lead | Claims no application issue, workload normal. 3 deflections: listener → ORA-600 → upgrade. |
| **Pardis Goudarzi** | **Labs** | Billing & CRM Operations Senior Manager | Claimed PRC_RECON_REVOKING_DMS runs daily at 9AM, said we gave "3 different root causes." Requested meeting. |
| **Mohammadsaleh Bayat Jozani** | **Labs (Application)** | Application team | Reported initial alert, showed EM graph claiming "no high load at 8:58." |
| **Omid Heravi** | **ITS** | Account Manager | Asked SD to assign to infra DBA. Supports investigation from technical evidence. |
| **Mehdi Kheir Andish** | **ITS** | Manager / Account Manager | DBA team manager. Approves changes. |
| **Ali Davachi** | **ITS Service Desk** | Team Leader | Coordinated ticket routing, set meeting for March 14. |
| **Hamidreza Saadat Pour** | **Labs** | — | CC'd on all emails, meeting organizer. |

### 2022 Incident People (MTNI-760378)

| Name | Team | Role in 2022 |
|------|------|-------------|
| **Benyamin Teimouri** | **Tecnotree (TT DBA)** | Application DBA — examined evidence, provided data, engaged constructively |
| **Zeinab Salehi** | **P&C** | RCA reviewer — asked Labs to investigate and prevent recurrence |
| **Mohammadali Arab Yar Mohammadi** | **ITS SD** | Supervisor — asked for follow-up from DBA team |

### Team Positions Summary

**AHS (Our Position):**
- The database was stable for 3 months (since 28 Azar startup)
- No DBA operations occurred on March 9 morning
- ASH data proves Session 3082/44313 from **drvl1078** (application server) as the root blocker
- The operation (redo scanning, likely LogMiner) held library cache mutexes causing 102K+ blocked waits
- DDLs (PRC_RECON_REVOKING_DMS, TMP_REVOKING_DMS tables) at 09:23 from same user/machine confirm application activity
- Same incident in 2022 (MTNI-760378) was classified as "Application Misuse"
- Incident should be assigned to Labs (application team)

**Labs (Their Position — evolving):**
- Phase 1: preUploadPK workload is normal, listener problem since 08:50 is infra issue, Data Guard errors since 03:18
- Phase 2: SYS/322 = 68% blocking (misleading — 322 is victim of 3082), ORA-600 errors = Oracle bugs (symptoms not causes), upgrade to 11.2.0.4 (deflection)
- **Key omission:** Labs has never examined what Session 3082 was doing, despite being asked since March 9

---

## 11. Database Reference

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

---

## 12. Email Communication Log

| Date | From | Action | Key Content |
|------|------|--------|-------------|
| Mar 9, 09:10 | Billing-NOC | Alert forwarded | "Critical CPU Utilization" on dru104a |
| Mar 9, 09:18 | Alireza | Response | "load average: 2628, unable to connect, huge blocking sessions" |
| Mar 9, 09:25 | Alireza | Update | "blocker is gone, able to connect" |
| Mar 9, 11:05 | Mohammadsaleh (Labs) | EM graph | "No high load before 09:15" — misleading (missing AWR snap) |
| Mar 9, 12:50 | Erfan (Labs) | First defense | preUploadPK workload normal, listener problem since 08:50, Data Guard errors |
| Mar 9, 21:25 | Alireza | Session 3082 evidence | Full ASH analysis, P2 proof, DDL timeline, action items |
| Mar 10, 16:15 | Pardis (Labs) | Pushback | "PRC_RECON runs daily at 9AM, you gave 3 different root causes" |
| Mar 10, 17:08 | Alireza | Clarification | "Session 3082 caused it. This is application-side. We are helping, not responsible." |
| Mar 10, 17:38 | Erfan (Labs) | GSM workload | "gsm_background_process 66M/28M normal, why are you ignoring this" |
| Mar 11, 13:28 | Omid Heravi (ITS) | Support | "Please assign to Application team" |
| Mar 11, 15:21 | Ali Davachi (SD) | Meeting set | March 14, 2:00-2:30 PM meeting organized |
| **Mar 14, 16:27** | **Erfan (Labs)** | **Post-meeting** | **New strategy: SYS/322=68%, ORA-600 bugs, upgrade to 11.2.0.4** |
| **Mar 14 (draft)** | **Alireza** | **Email v8 to Omid/Mehdi** | **Frustration, 2022 precedent, technical rebuttals, attachments** |
