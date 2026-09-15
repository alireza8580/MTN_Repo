# RCA Runbook — how to write an MTN Irancell root cause analysis

Operator-facing runbook, reverse-engineered from the RCA documents archived in this
directory (2024 → 2026-08) and from the mail threads that carried them. Everything below is
what accepted RCAs actually contain, not what the blank template suggests.

An **RCA** at MTNI is a Word document (`.docx`) attached to the incident mail thread and to
the Post Incident Review that ITS Incident Management runs for every major incident. It is
**not** an Icare artifact and **not** an RFC: the Icare ticket (`MTNI-XXXXXXX`) is the
incident it explains, and any change made during recovery is referenced by its own
`MTNI-XXXXXXX` change number inside the RCA.

Two related artifacts show up in the same threads and are not the same thing:

- **RCA** — ours, technical, one document per incident, owned by the team that owns the CI.
- **Post Incident Review (PIR)** — Incident Management's meeting and tracker over one or
  more major incidents, e.g. "Post Incident Review for Major incidents MTNI-1538021,
  MTNI-1536412". The PIR consumes the RCA; it does not replace it.
- **RCA Action Tracker** — the follow-up system that chases the actions the RCA commits to.
  Actions written into the RCA come back as tickets, so do not write an action the team
  cannot deliver.

---

## 0. Never start from a blank page

Every archived RCA was made by copying the previous one. Do the same:

1. Pick the closest incident from [§6 Pattern library](#6-pattern-library).
2. Copy that `.docx`, keep the section order, replace the content.
3. Keep the section headings **exactly** as they are. Incident Management reads them in
   that order and a renamed heading gets the document sent back.

Archived source documents in this directory:

| File | Incident | Subject |
|---|---|---|
| `RCA_New_Template-NGPG.docx` | MTNI-1412967 | the blank house template, filled thinly for NGPG/OID |
| `RCA_ichat.docx` | MTNI-1540502 | iChat, MySQL InnoDB Cluster lost its writable primary |
| `RCA_Erefill_MTNI-1538021_v1.docx` | MTNI-1538021 | Erefill, Oracle unresponsive under memory pressure, first version |
| `RCA_Erefill_DBA_Reviewed__1_.docx` | MTNI-1538021 | the same incident after DBA review, the strongest example of the evidence-first voice |
| `RCA_ICHAT.docx`, `RCA_ICHAT_-MTNI-969618.docx`, `RCA_MTNI-923117.docx` | older | short-form RCAs from the earlier years |

---

## 1. Section order — the canonical form

The template (`RCA New Template`) has these sections, in this order. Fill every one; write
"Not applicable" rather than deleting a heading.

1. **Business Impact** — what the customer or the business lost. Include **Details of
   Impact** and **Impacted CIs** (hostnames, one per line).
2. **Root Cause Type (Layer 1 / Layer 2 / Layer 3)** — see §2.
3. **Outage Duration (Minutes)** — a number. If the start is not provable, say so and give
   the bound, e.g. "At least 23 minutes", with the reason the start is uncertain.
4. **First Occurrence** — is this the first time? If not, name the earlier dates and the
   earlier ticket.
5. **Permanent fix plan** — the fix that removes the cause, not the recovery action. If it
   belongs to another team, say which team owns it.
6. **Detection Source** — how it was found: `Automated monitoring` (name the tool, e.g.
   Zabbix), `User Reports`, `Customer feedback channels`. Being honest that monitoring did
   not catch it is a finding in itself.
7. **Management Summary** — 3 to 6 sentences, no log lines, readable by a non-DBA manager.
8. **Chronological Report of Events** — the table, see §3.
9. **Symptoms and Error Messages (Business and Technical Side)** — the business-visible
   symptom next to the exact error strings.
10. **Technical Root Cause**, with these sub-headings:
    - Technical Root Cause Summary — 2 to 3 sentences.
    - Supporting Technical Data — affected systems, key log entries, configuration values.
    - Root Cause Details — triggering event, underlying cause, contributing factors.
    - Root Cause Validation — what was done to prove it, and what remains unproven.
    - Impacted Services — every service or process affected.
    - Resolution Path — the steps that restored service.
11. **Workaround** — what to do if it recurs before the permanent fix lands.
12. **Major Incident Accountability Group** — which team owns the incident. See §5.
13. **Preventive Actions** — table: Action | Owner | Priority | Target Date | Status.
14. **RCA Actions** (or "RCA Actions / Closure Criteria") — what must be true to close.

A header block above section 1 is used in the longer RCAs and is worth keeping:

```
ROOT CAUSE ANALYSIS
<one-line incident title>

Incident ID | MTNI-XXXXXXX      | Affected Service | <service>
Affected Server | <hosts>       | Incident Date    | DD-Mon-YYYY
Related Change | MTNI-XXXXXXX   | Recovery Change  | MTNI-XXXXXXX
RCA Status | <Confirmed | Technical cause not conclusively proven> | Prepared By | DBA Team
```

---

## 2. Root Cause Type — the three layers

Two filling styles are both accepted, so pick by how much you can prove:

- **Taxonomy style** (used in the iChat RCA) — three increasingly specific labels:
  `Layer 1: Infrastructure` / `Layer 2: Storage Performance` /
  `Layer 3: Database node unresponsiveness due to local I/O stall (underlying storage latency)`.
  Layer 1 is the domain (Infrastructure, Database, Application, Network, Change), Layer 2 is
  the component class, Layer 3 is the specific mechanism.
- **Narrative style** (used in the Erefill RCA) — one paragraph per layer, each naming what
  was observed at that depth, ending with what is still only suspected.

Whichever style, **Layer 3 must name a mechanism, not a symptom**. "Database was down" is a
symptom. "Every member that transitioned to PRIMARY aborted on a server invariant in the
awaitable-hello code path" is a mechanism.

---

## 3. The chronological table

Five columns, always: **Time Stamp | Event Description | Action Taken | Actor Involved |
Decision Points**.

- One row per real event, not per mail. Start before the first customer symptom and end at
  service restoration plus the post-incident review row.
- `Actor Involved` names teams (`DBA Team`, `UNIX`, `Application`, `Monitoring`,
  `Incident Management`), not people.
- `Decision Points` is where the escalation logic goes: "Escalate as service-impacting
  incident", "Reduce workload and protect service recovery", "Keep final cause conditional
  pending logs".
- If a timestamp is unknown write `time not recorded` rather than inventing one. The
  archived RCAs do exactly this and it is accepted.
- Use one timezone for the whole table and say which. Mixed-timezone hosts are the trap
  that makes a chronology wrong (Esfahan hosts run +04:30 while Tehran runs +03:30).

---

## 4. Voice — evidence first, boundary second

The DBA-reviewed Erefill RCA is the model. Rules it follows:

- **Separate confirmed from suspected, explicitly.** Use the headings the archive uses:
  "Confirmed failure mode:", "Not confirmed as root cause:", "Most defensible current RCA
  statement:".
- **Quote the evidence inline.** Exact log lines with their message ids, exact configured
  values, exact counts. A claim with no artifact behind it does not go in.
- **Say what would prove it.** When the cause is not isolated, list the specific evidence
  that would settle it (alert log entries, OOM records, HugePages counters, ASH/AWR window).
  This is what turns "we do not know" into a defensible position.
- **Refuse a cause you cannot prove, and say why.** When another team's RCA blamed the
  Oracle user limits, the DBA review answered with the vendor guideline values next to the
  configured values in a table, and concluded the limits met the guideline. Do that instead
  of arguing in prose.
- **Name the control gap, not a person.** "The available record does not show a documented
  joint pre-cutover validation" is the house phrasing. Never name an individual, and never
  write who typed a command.
- **State the DBA boundary where it is real**: "the DBA team does not support OID as a
  service", "DBA has no control over network", "storage team should comment on this". A
  section owned by another team is left for that team to fill, marked as such.
- **Recovery is not proof.** When several actions were taken together, write that the
  successful recovery does not isolate which action worked. The archive says this in as
  many words and it is the single most reused sentence in a DBA-reviewed RCA.
- No em-dash, no marketing English, no apology. Short declarative sentences.

---

## 5. Accountability group

`Major Incident Accountability Group` is the field that decides whose bucket the incident
sits in, so it is the field to get right.

- If the cause is genuinely ours, name the DBA team and do not hedge.
- If the cause is another team's, name that team (the NGPG RCA names the NGPG team, the
  iChat RCA points the permanent fix at the storage team).
- If the incident crossed layers, list every team as the Erefill RCA does (Application,
  DBA, UNIX/Infrastructure, Monitoring, Incident/Change Management) and explain in one line
  why ownership is shared.

---

## 6. Pattern library

**Cluster lost its writable primary (iChat, MTNI-1540502).** Impact section names the
routing layer that could not find a primary. Layer 2/3 point at the storage latency under
the node, not at the cluster software. Outage duration is bounded and the reason the start
is unprovable (incomplete router logs) is stated. `First Occurrence` says explicitly that
it recurred over several nights. Permanent fix is handed to the storage team.

**Database unresponsive under memory pressure (Erefill, MTNI-1538021).** Two versions
exist: the original assigning the cause to a configuration item, and the DBA review that
rejects it with a guideline-vs-configured table. When another team's RCA lands on us, the
review version is the pattern to copy.

**Application blames a service we do not own (NGPG, MTNI-1412967).** Short RCA. Management
Summary carries the boundary, the accountability group is the application team, and the
permanent fix is that the application stops using the unsupported path. Chronology may be
one line if we have no logs, and the RCA says why: "As we don't have any issue in LDAP
service we can't share any log".

**Resource exhaustion after an infrastructure event (MTNI-923117).** `ORA-00020: maximum
number of processes exceeded` quoted verbatim, the I/O abnormality that preceded it named,
and the honest closing that the hardware layer has to comment before prevention can be
promised.

---

## 7. Pre-submission checklist

1. Every heading from §1 present, in order, nothing renamed.
2. Incident ID, affected service, affected servers, incident date filled in the header.
3. Outage duration is a number or an explicit bound with the reason.
4. Every technical claim has an artifact: a log line, a configured value, a count.
5. Confirmed and unproven are separated, and the unproven part lists what would prove it.
6. Chronology in one timezone, `time not recorded` where unknown, teams not people.
7. Preventive actions have an owner and a target date, and we can actually deliver ours.
8. The accountability group is stated, and any section owned by another team is marked.
9. No credentials, no personal mobile numbers, no individual named as a cause.
10. Grep the document for the em-dash and remove every one.

---

## 8. Standing traps

- **The RCA is quoted onward.** It reaches Incident Management, the service owner and
  sometimes the vendor, so every sentence is a position the team has to defend later.
- **Actions become tickets.** The RCA Action Tracker turns each preventive action into a
  chased item with a due date. Do not write an action another team has not agreed to.
- **Do not let the recovery narrative become the root cause.** "We restarted it and it came
  back" explains the resolution path and nothing else.
- **Mixed timezones break the chronology.** Convert everything to one zone and name it.
- **Version the file.** `RCA_<Service>_<MTNI-ticket>_v1.docx`, and when we review someone
  else's, `RCA_<Service>_DBA_Reviewed.docx`. Both naming forms are in the archive.
- **These documents carry internal hostnames.** `RCAs/*.docx` and `RCAs/*.pdf` are
  git-ignored for the same reason the RFC workbooks are; only this runbook is tracked.
