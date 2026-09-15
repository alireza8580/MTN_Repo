# RFC Runbook — how to fill out an MTN Irancell change request

Operator-facing runbook, reverse-engineered from the **47 submitted RFCs** in this
directory (2019-11 → 2025-09). Everything below is what the accepted forms actually
contain, not what the blank template suggests.

An **RFC** at MTNI is an Excel workbook submitted to ITS Change Management and approved at
the CAB. It is the only sanctioned way to touch a production database. It is *not* an Icare
ticket — an Icare ticket (`MTNI-XXXXXXX`) may be the *reason* for an RFC and gets
referenced from it, but the change itself lives in this workbook.

---

## 0. Never start from a blank template

All 47 archived RFCs share the **identical 9-sheet workbook**. Every one of them was made
by copying an earlier RFC and editing it. Do the same:

1. Find the closest prior change in [§7 Pattern library](#7-pattern-library-by-change-type).
2. Copy that `.xlsx` to a new name.
3. Edit the **Information** sheet, then **Detail Plan**, **Rollback Plan**, **test plan**,
   **Resource management**. Nothing else.

**File naming** follows the change, lower case, underscores or spaces both accepted:
`<action>_<db>_to_<target>.xlsx` — e.g. `pgdb_ererfill switchover to dru842b.xlsx`,
`enable_archive_log_ods1p_2.xlsx`, `fix CLM t1l043 corruption .xlsx`. A rejected one keeps
its name with a `_not_accepted_` prefix (`_not_accepted_post2p_crash_recovery_process.xlsx`);
the revised version that went to CAB gets `_final` (`Restart_post2p_final.xlsx`,
`dblink_change_edw_from_post2p_to_sbpost_final.xlsx`). Keep both — the pair is the record of
what CAB pushed back on.

---

## 1. Workbook anatomy — which sheets you touch

| # | Sheet | Fill it? | Notes |
|---|---|---|---|
| 1 | `Summary` | **NO — formulas** | Auto-pulls from `Information`. Marked *"Do Not Print the Summary Sheet"*. See the `#REF!` trap below. |
| 2 | `Cover Page` | **NO** | Approval/signature block. `C3` = `=Information!D5`. Signed on paper/in the CAB, never typed. |
| 3 | `Detail Description` | **NO** | Guidance prose only. **Not one of the 47 has a single character added to it.** Do not waste effort here. |
| 4 | `Information` | **YES — this is the RFC** | The one-page form CAB reads. Full cell map in §2. |
| 5 | `Resource management` | **YES** | Who is on the bridge and their mobile. §5. |
| 6 | `Detail Plan` | **YES** | Step-by-step execution table. §3. |
| 7 | `test plan` | **YES (thin)** | Post-change verification. In practice 1–2 lines. §4. |
| 8 | `Rollback Plan` | **YES** | Back-out steps. §6. |
| 9 | `Post Implementation Review` | **NO — after the fact** | **Empty in all 47 archived copies.** Filled only when Change Management asks for the PIR after execution. |

### ⚠️ The `#REF!` trap

`Summary` and `Cover Page` are **formula-linked** to `Information`:

```
Summary!B2 = Information!D5      (Description)
Summary!C2 = Information!D8      (Motivation)
Summary!D2 = Information!J11     (Schedule Start)
Summary!E2 = Information!J12     (Schedule End)
Summary!H2 = Information!N28     (Change Reason)
Summary!Q2 = Summary!R2 = Summary!T2 = Information!K8   (Incident / Problem / CER)
Cover Page!C3 = Information!D5   (Description)
```

If the `Information` sheet is ever deleted and re-inserted (or the workbook is rebuilt by a
converter), these break to `#REF!` — which is exactly what happened to `Restart_post2p.xlsx`
and `Restart_post2p_final.xlsx`. **After editing, open `Summary` and confirm B2/C2/D2/E2
show your real text.** If they show `#REF!`, retype the five formulas above.

---

## 2. The `Information` sheet — cell-by-cell

This is the whole RFC as far as the reviewer is concerned. Exact cells:

| Cell | Field | What to write |
|---|---|---|
| `K3` | UAT | `No` for production changes. `Yes` only if a UAT run preceded it (2 of 47). |
| `D5` | **Description** | One sentence: what changes, on which host/DB, to what. Drives `Summary` and `Cover Page`. |
| `D8` | **Motivation** | Why. Usually a near-copy of `D5` with the driver in front: *"due to critical HW condition, we have to …"*. |
| `K8` | Incident / Problem no. | The Icare id — `MTNI-1327082`. Blank if the change is not incident-driven (34 of 47 are blank). |
| `N8` | Effect on Network | Always `NO` — this is a DB change, not a network change. All 47. |
| `D11` | **Category** | `1`–`4`, or `Emergency`. See §2.1. |
| `D12` | **Environment** | `PROD`, `UAT`, or **`primary/standby`** — the last is the convention for any Data Guard / replica-role change, and it is used in 13 of 47. |
| `D13` | Requestor | Who asked. The *other* team, not you: `Infra Team`, `NGPG Team`, `TT`, `Mehdi Kheirandish`, `Irancell-Labs`, `Subex-SAEI`. Only put `DBA/AHS` when DBA genuinely originated it. |
| `D14` | Coordinator | You. `Alireza Aghajanzadeh Gheshlaghi` or `DBA/AHS`. |
| `D15` | Implementor | Usually the same person/team as coordinator. |
| `J11` | **Start Datetime** | See §2.2 on the date-format trap. |
| `J12` | **End Datetime** | Must equal `J11` + the total of the Detail Plan durations. Reviewers check this. |
| `J13` | Down time | Despite the label, the observed answer is `Yes` / `No`, not a duration (`Yes` ×19, `No`/`NO` ×12). A duration (`1 hours`, `30 min`) is accepted but rarer. |
| `J14` | Add Support | The other teams that must be on the bridge, as their handles: `#itsdcunix`, `#ITS Support Payment Gateway`, `#TTDBA`, `#itsdcintel`, `EDW Team`, `Subex-SAEI`, `CSS DBA`. Get this right — it is how the other teams get invited. |
| `J15` | Affect on DR | `YES` for any switchover/failover (you are consuming the standby). Blank/`No` otherwise. |
| `C19`…`C22` | Affected **Servers** | For a role change write both sides: `dru103b/dru842b`. |
| `E19`…`E22` | Affected **Databases** | Same shape: `pgdb+erefill/spgdb+erefill`. |
| `F19` | Other | `No` normally. |
| `J18` | **Service Outage** | The customer-visible blast radius, in business terms. This is the field CAB argues about — see §8 for the reusable text. |
| `C24` | **Impact Analysis** | Technical impact. Default line: *"during the change users/apps can not connect to database"*. |
| `F24` | Impact on **EDW** | Always answer — EDW has its own reviewer. `No Impact`, or the real consequence: *"In case of outage no report will generate to send to BIB/Big Data/EDS"*. |
| `H24` | **Risk Analysis** | The residual risk *after* your mitigation. `No risk` is accepted for routine role changes; anything non-obvious must name the failure mode. |
| `E28` | Plan Summary | One line — usually `D5` restated as an action. |
| `E31` | Test Plan Summary | One line — `check DB on <target host>`, `checking databases status`. |
| `N28` | **Change Reason** | Drop-down: `Maintenance` (37 of 47), `Fix`, `Release`, `Upgrade`, `Enhancement`, `New Functionality`. Watch the truncation — several archived copies read `Maintenan`; type the full word. |

Cells `Q6:T7` are the category legend and are part of the template — leave them.

### 2.1 Category — pick it from the risk legend, not from habit

The legend is printed on the sheet at `Q7:T7`:

| Category | Meaning | Window |
|---|---|---|
| **CAT 1** | very high risk **and** very high impact | agreed change window only |
| **CAT 2** | high risk **and** high impact | agreed change window only |
| **CAT 3** | medium risk and/or medium impact | weekend |
| **CAT 4** | very low risk **and** very low impact | weekday, non-production hours; CAB may delegate approval |
| **Emergency** | incident-driven, cannot wait for CAB | raised during/after the fact |

Observed usage: `2` ×17, `3` ×15, `Emergency` ×8, `CAT 3` ×3, `CAT 1` ×1, `4` ×1. The
archive writes it inconsistently (`2` vs `CAT 2`) — **write `CAT 2` style** for clarity.

Rules of thumb from the archive:
- **Data Guard switchover of a customer-facing DB** (pgdb/erefill, lcms, mdx5p, conc1p) → **CAT 2**.
- **Adding/removing replicas, corruption re-seed, archiving, parameter change on a non-core DB** → **CAT 3**.
- **Anything on POST2P** → **CAT 1 or Emergency**; POST2P's blast radius is the whole BSS.
- **Failover after the primary is already gone** → **Emergency** (there is no window to wait for).

### 2.2 ⚠️ The date-format trap

The archive mixes three formats in the *same field*:

```
2025-09-29 02:00:00        ISO         (unambiguous)
18/7/2025  22:00:00        d/m/yyyy
8/22/2025  22:00:00 PM     m/d/yyyy    ← and note the nonsensical "22:00 PM"
02/30/2020  11:00:00 PM    ← 30 February; a typo nobody caught
```

`J11`/`J12` are read by a human reviewer *and* mirrored onto `Summary`. **Write ISO
`YYYY-MM-DD HH:MM:SS`** and drop the AM/PM suffix when using 24-hour time. Check the end
time is after the start time — `switchover mdx5p to smdx5p.xlsx` shipped with
start `2025-08-21 23:00` / end `2025-08-21 00:40`, i.e. an end *before* the start.

---

## 3. `Detail Plan` — the execution table

Header row 2/3; steps start at **row 4**. Columns:

| Col | Field |
|---|---|
| `A` | Serial (1, 2, 3 …) |
| `B` / `C` / `D` | Production **Begin** / **Finish** / **Duration** |
| `E` | Server / Database |
| `F` | Task |
| `G` | Command / Script |
| `H` | Responsible |

Conventions the archive follows:

- **Duration is the column that matters.** `Begin`/`Finish` clock times are filled only on
  the first and last row (or not at all); `D` is filled on every row. Write `30M`, `20M`,
  `1h`, `15 min` — the archive is not consistent, pick one and hold it within a workbook.
- **Duration total must reconcile with `Information!J11→J12`.** The totals block sits a few
  rows below the last step (`Total … minutes / hours`, then `Downtime … from line # to line #`).
  Fill the downtime line numbers — that is how CAB reads which steps are the outage.
- **Every step names a Responsible**, and it is frequently *not* DBA: `TTDBA`, `PGDBA`,
  `app`, `EDW team`, `UNIX`, `NGPG support`, `UMS team`, `DMS team`, `Storage TEAM`. A plan
  where DBA owns every row is a plan that will stall waiting for an app team nobody invited.
- **`Command / Script` may be left blank** for coordination steps (`stop application`), but
  **must contain the real statement** for anything that changes DB state — CAB accepted
  `alter system set log_archive_dest_1='+archgrp';`, `rs.add(hostportstr)`,
  `ALTER DATABASE CONVERT TO PHYSICAL STANDBY;`. Multi-line is fine inside the cell.

---

## 4. `test plan`

Steps start at **row 9**. Same shape as Detail Plan but with both a **UAT** block
(`C`/`D`/`E` = Begin/Finish/Duration) and a **Production** block (`F`/`G`/`H`), then
`I` Server/Database, `J` Task, `K` Command, `L` Responsible.

In practice this sheet is thin — one or two rows:

```
B9 = 15 min | I9 = dru104a/post2p | J9 = DB status | K9 = db status | L9 = DBA
```

Fill `Information!E31` (Test Plan Summary) properly even if this sheet stays thin; that is
the line the reviewer reads. Acceptable summaries from the archive: `check DB on dru842b`,
`checking databases status`, `Check the application session in new replicas`,
`check the parameter to be set correctly`, `check status of db and backup log`.
`there is no test plan` was accepted for a decommission.

---

## 5. `Resource management`

Rows start at **row 8**: `B`=SN, `C`=Resource name, `D`=Vendor, `E`=On-site,
`F`=Contact Number, `G`=Alternative, `H`/`I`=availability window.

Standing values:

| Entry | Value |
|---|---|
| Resource name | `Alireza Aghajanzadeh Gheshlaghi` (or `DBA team`) |
| Vendor | `AHS` |
| On-site | `No` (remote) unless you will be at the DC |
| Contact | `9121488580` — Alireza's number as filed on 20 of the archived RFCs |
| DBA standby line | `9352106621` — used when the entry is the team rather than a person |

Add a row per extra person who must be reachable, with their own mobile.

---

## 6. `Rollback Plan`

Steps start at **row 8**: `B`=Expected Duration, `C`/`D`/`E`=Begin/Finish/Duration,
`F`=Server/Database, `G`=Task, `H`=Command/Script, `I`=Responsible.

Two rows is the norm, and for a role change they are the mirror of the Detail Plan:

```
1 | 20 min | convert dru103a to primary  | DBA Team
2 | 20 min | convert dru841b to standby  | DBA Team
```

**"No rollback" is a legitimate answer** and was accepted 9 times — but only where a
rollback is genuinely undefined: a restart (`no rollback plan`), a decommission
(`there is no rollback plan`), a failover onto an already-corrupt primary. In those cases
the *recovery* path belongs in `Information!H24` (Risk Analysis) instead — e.g.
*"restore latest backup on t1 since t2 binaries got corrupted"*.

Standard rollback texts by change type are in §7.

---

## 7. Pattern library by change type

Pick the closest and clone it.

### 7.1 Data Guard switchover (planned) — the most common change

Base file: `pgdb_ererfill switchover to dru842b.xlsx`, `lcms switchover to stlcms.xlsx`,
`switchover mdx5p to smdx5p.xlsx`, `conc1p-switchover.xlsx`.
Category **2**, Environment **primary/standby**, Affect on DR **YES**.

| # | Dur | Host | Task | Responsible |
|---|---|---|---|---|
| 1 | 30M | `<primary>` | stop application | app team (`TTDBA` / `PGDBA`) |
| 2 | 20M | `<standby>` | change db role of standby to primary | DBA |
| 3 | 30M | `oid servers` | update all OID servers | *(only where OID resolves the DB)* |
| 4 | 30M | `<new primary>` | start application | app team |
| 5 | 20M | `<old primary>` | change db role of primary to standby | DBA |

Rollback: `convert <old primary> to primary` / `convert <new primary> to standby`, 20 min each.
Impact `C24`: *"during the change users/apps can not connect to database"*. Risk `H24`:
`No risk`, or the dependency warning — *"Application team must check any external dependency
and dblinks pointing to `<db>` need to be mentioned"*.

### 7.2 Failover (primary already lost)

Base: `pgdb_ererfill failover to dru103b.xlsx`, `ums_failover.xlsx`, `enm_failover.xlsx`,
`dms2p_failover.xlsx`. Category **Emergency**. No "stop application" step — the primary is
already down.

| # | Dur | Task |
|---|---|---|
| 1 | 5–10M | finish SRL apply / activate standby and promote it to primary |
| 2 | 10M | update all OID servers |
| 3 | 10–35M | start application on the new site |

Rollback is honest: *"restore latest backup on t1 since t2 was down"*.

### 7.3 Database / server restart or bounce

Base: `Restart_post2p_final.xlsx`, `Restart_RAUSG_RAREF.xlsx`, `bounce_selfcare_highload.xlsx`,
`bounce_post2p_database_and_Server.xlsx`.

`stop app (app team)` → `restart DB (DBA)` → `start app (app team)`, 1 h total. For an
OS bounce, interleave UNIX: `Stop DB (DBA)` → `Bounce OS (UNIX TEAM)` → `Start DB, check
health (DBA)`. Rollback: `no rollback plan`. Risk must state the honest limit — *"The DB
restart may not fix the SMON issue"*.

### 7.4 Instance parameter change

Base: `Changing PROCESS parameter on POST2P database_2.xlsx`, `Restart_Rocfm_to_change_sga.xlsx`,
`RFC increase procesee parameter on ods1p - Copy.xlsx`.

`stop app` → `change parameter and bounce DB` (`alter system set <param>=<value> scope=both;` or
`scope=spfile` + restart) → `start app` → `monitor app`. Rollback is always
`set parameter to its previous value` with the explicit reverse statement — **write the old
value into the rollback cell**, not "revert".

### 7.5 Mongo replica add / remove / switch (CLM, Website)

Base: `Adding_new_t2_replicas_to_CLM.xlsx`, `Switch_CLM_to_New_Nodes.xlsx`,
`remove hidden replicas of CLM in T1.xlsx`, `fix CLM t1l043 corruption .xlsx`.

Commands are the shell one-liners: `rs.add(hostportstr)`, `rs.remove(host:port)`,
`rs.stepDown()`, `rs.reconfig()`. Durations here are **long and honest** — `120Min`, `12days`,
`1month` for an initial sync. Rollback mirrors: `remove new replicas` / `rs.remove(hostportstr)`.

The standing impact text for this family, reused verbatim across six RFCs:

> Generally it doesn't have impact on current primaries but some slowness will push over
> secondary's and also network bandwidths will be under pressure till end of migrations, we
> will try to set non-primary dbs as source for building the new ones, but if we can't set
> non-primary as source then we have to stop the change. we will add shards one by one to
> reduce risk

And the standing risk, which you must keep for the 3.2 cluster:

> There is risk of corruption of secondaries due to mongo 3.2 bug

### 7.6 Enable archivelog / storage-side change

Base: `enable_archive_log_ods1p_2.xlsx`.

`stop Apps/Jobs (EDW team, 15min)` → `set archivelog dest (10min)` → `Enable archivelog (1h)`
→ `start Apps/Jobs (15min)`. Commands are spelled out:

```sql
alter system set log_archive_dest_1='+archgrp';
shu immediate
startup mount
alter database archivelog;
alter database force logging;
alter database open;
```

Rollback: `disable archivelog mode` with the reverse block
(`shu immediate; startup mount; alter system reset log_archive_dest_1; alter database noarchivelog; …`).
Impact: *"There will performance degradation after enabling archive mode"*.

### 7.7 DB-link / connection re-point

Base: `dblink_change_edw_from_post2p_to_sbpost_final.xlsx`.

`cancel MRP, open the standby read-write, restart MRP` → `update <db> dblink from <old> to
<new>` → command is `change tnsnames.ora and sqlnet.ora`. Rollback re-points the link and
returns the standby to mount + MRP. Risk must state the standby exposure — *"Since CBS DR is
getting synced once a day, if sbpost hangs then we don't have a sync standby"*.

### 7.8 Decommission / drop

Base: `drop_nfc_production.xlsx`. `stop Apps/Jobs (App team)` → `bounce and drop of database
(DBA team)`. Impact: *"Users can't connect to database anymore and db will dropped"*.
Test plan: `there is no test plan`. Rollback: `there is no rollback plan` — the safety net is
the backup, and it belongs in the risk cell.

---

## 8. Boilerplate bank — reusable exact text

**Impact Analysis (`C24`)**, use verbatim for any outage-bearing change:

> during the change users/apps can not connect to database

**Service Outage (`J18`) — pgdb / erefill:**

> Bill Payment, Direct topup, Bolton Purchase, Pre2Post, any other purchase from all direct
> channels, P2P, Auto Recharge, wallet cashin, USSD Purchase & Merchants transactions on
> eRefill will fail

**Service Outage (`J18`) — the POST2P blast radius.** POST2P is the BSS core; this is the
text CAB expects to see, and understating it is what gets an RFC bounced:

> Major impacts:
> CLM, CBS, EIA, Provisioning, MNP, OPF, Old flow Bolton, LCMS, UPC, SMSGW will not be accessible.
> HSDP for responding COW, Termination is impacted.
> AAT and CLP loan service are inaccessible during change.
> My business, Mobile ID, SUL / CAS will be affected.
> My Irancell, DPOS, UMS-IVR, 800, USSD, PPMS, AMA, magic, LDMS, Reco (Old flow) and FMS will
> not have any response from above services.
> Auto Debit, P2P, and E-refill for Post-Paid flow and NGPG bill payment will not be
> accessible. Purchasing and subscription flow of RBT will not be available. DMS Call towards
> MW will be locked, so validation process and indexing and un-indexing in DMS cannot be
> performed and subscriber information view also will not be available, thus ECP segmentation
> data will not be updated. Due to unavailability of provisioning, some operation activities
> such as registration, COW, SimSwap, Pre2Post and Dunning (Revoke/Suspension) will be
> executed with delay.
>
> Minor impacts:
> EIA will be down so some procedures via iChat and e-Shop which call EIA service will face
> some fluctuation or disruption.

**Service Outage — CLM switchover:**

> There will be a brief (less than 5 minutes) fluctuation in service due to switchover.
> All the channels which call CLM through MW will face some fluctuations: CLM, DPOS, E-Shop,
> PG, MyIrancell, DMS … online Bolton success rate drop.

**Impact on EDW (`F24`):**

> In case of outage no report will generate to send to BIB/Big Data/EDS

**Generic DB-unavailable outage line (`J18`):**

> DBs are not accessible during change.

---

## 9. Pre-submission checklist

- [ ] `Information!D5` and `D8` say *what* and *why* in one sentence each.
- [ ] `D11` Category matches the legend at `Q7:T7`, not habit — and the window in `J11` fits
      that category (CAT 3 → weekend, CAT 4 → weekday off-peak, CAT 1/2 → agreed window).
- [ ] `J11`/`J12` are ISO, `J12` > `J11`, and the gap equals the Detail Plan total.
- [ ] `J14` Add Support names **every** other team in the Detail Plan's Responsible column.
- [ ] `C19`/`E19` name both sides of a role change.
- [ ] `J18` describes customer-visible impact in business terms, `C24` the technical one,
      `F24` the EDW one, `H24` the residual risk.
- [ ] `K8` carries the Icare id if the change is incident-driven.
- [ ] Detail Plan: every row has a duration and a Responsible; state-changing rows carry the
      real command; the downtime line-range is filled.
- [ ] Rollback Plan: mirror steps with durations, or an explicit "no rollback plan" *plus* a
      recovery path stated in `H24`.
- [ ] Resource management: name + mobile of everyone who must be reachable on the night.
- [ ] `Summary` sheet shows real text, **not `#REF!`**.
- [ ] `N28` Change Reason spelled in full (`Maintenance`, not `Maintenan`).

---

## 10. Standing traps

1. **`Summary` / `Cover Page` are formulas.** Never type over them; verify they resolve. §1.
2. **Date formats are mixed in the archive** and at least two shipped RFCs carry impossible
   dates (`02/30/2020`, an end time before the start). Use ISO and re-read them. §2.2.
3. **`Detail Description` and `Post Implementation Review` are dead sheets** at submission
   time. Filling them is wasted effort; the PIR is filled only after execution, on request.
4. **"Down time" (`J13`) is a yes/no field in practice**, not a duration — the duration lives
   in the Detail Plan totals.
5. **Understating `J18` gets the RFC bounced.** Compare `Restart_post2p.xlsx` (impact cell
   empty) with `Restart_post2p_final.xlsx` (full blast-radius paragraph) — same change, and
   `_not_accepted_post2p_crash_recovery_process.xlsx` is what a thin one looks like when it
   comes back.
6. **The Responsible column is a routing table.** Any team named there must also appear in
   `Information!J14` (Add Support) or they will not be invited to the change.
7. **These workbooks contain internal hostnames and personal mobile numbers.** `RFCs/*.xlsx`
   is git-ignored for that reason — keep it that way; only this runbook is tracked.
