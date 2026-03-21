#!/usr/bin/bash

# ================== ENV ==================
export ORACLE_SID=t3ods1p
export ORACLE_HOME=/oracle/product/12102/db_1
export PATH=$ORACLE_HOME/bin:/usr/sfw/bin:/usr/bin
export LD_LIBRARY_PATH=$ORACLE_HOME/lib:/lib

DBNAME=t3ods1p
ALERT="/diagnostic/diag/rdbms/${DBNAME}/${DBNAME}/trace/alert_${DBNAME}.log"
RECIPIENTS="alireza.aghaja@mtnirancell.ir isdcdba@mtnirancell.ir"

LOCKDIR="/tmp/ora10567_${DBNAME}.lock.d"
LOGFILE="/tmp/ora10567_${DBNAME}.action.log"
RESTORED_FILE="/tmp/ora10567_${DBNAME}.restored"
PROCESSED_FILE="/tmp/ora10567_${DBNAME}.processed"
WATCHER_PIDFILE="/tmp/ora10567_${DBNAME}.watcher.pid"

PRIMARY_SERVICE="ods1p"
COOLDOWN_SECONDS=86400
GAP_THRESHOLD=50        # If gap is higher than this, do NOT open the DB
OPEN_RETRY_COUNT=3      # Number of open attempts after MRP catch-up
OPEN_RETRY_WAIT=1800    # Seconds to wait between open retries (30 minutes)
ASM_FREE_THRESHOLD_GB=1024  # Minimum free space per diskgroup (1 TB)
ASM_DISKGROUPS="DATAGRP ARCHGRP"  # Diskgroups to monitor
ASM_CHECK_INTERVAL=3600 # Check diskgroup space every hour (seconds)
MOUNTED_OPEN_CHECK_INTERVAL=300  # Check gap and try open every 5 minutes when MOUNTED

# ================== FUNCTIONS ==================

send_mail () {
  SUBJECT="$1"
  shift
  (
    echo "$@"
    echo ""
    echo "--------------------------------------------------------------------------------"
    echo "Recent Activity Log (last 30 lines):"
    tail -30 "${LOGFILE}"
    echo "--------------------------------------------------------------------------------"
  ) | /usr/bin/mailx -s "$SUBJECT" ${RECIPIENTS}
}

get_log_gap () {
  # Returns the numeric gap, or -1 if query fails/returns garbage
  local gap=$(sqlplus -S / as sysdba <<EOF 2>/dev/null | grep -v "LOG_GAP" | grep -v "^-" | tr -d '[:space:]'
set heading on feedback off pagesize 0
select LOG_ARCHIVED-LOG_APPLIED "LOG_GAP" from
(SELECT MAX(SEQUENCE#) LOG_ARCHIVED FROM V\$ARCHIVED_LOG WHERE DEST_ID=1 AND ARCHIVED='YES'),
(SELECT MAX(SEQUENCE#) LOG_APPLIED FROM V\$ARCHIVED_LOG WHERE DEST_ID=2 AND APPLIED='YES');
exit
EOF
)
  # Return -1 on any parse failure (NOT 0 — 0 means "caught up")
  [[ "${gap}" =~ ^[0-9]+$ ]] && echo "${gap}" || echo "-1"
}

ensure_single_instance () {
  # Use mkdir for atomic lock acquisition
  local lockdir="${WATCHER_PIDFILE}.d"
  if ! mkdir "${lockdir}" 2>/dev/null; then
    local oldpid=$(cat "${WATCHER_PIDFILE}" 2>/dev/null)
    if [[ -n "${oldpid}" ]] && kill -0 "${oldpid}" 2>/dev/null; then
      echo "$(date) ORA-10567 watcher already running (PID=${oldpid}) - exiting" >> ${LOGFILE}
      exit 0
    fi
    # Stale lock - reclaim
    rm -rf "${lockdir}"
    mkdir "${lockdir}" 2>/dev/null || { echo "$(date) Failed to acquire lock" >> ${LOGFILE}; exit 1; }
  fi
  echo $$ > "${WATCHER_PIDFILE}"
}

get_line_signature () {
  echo "$1" | sed -n 's/.*\(file# [0-9]*.*block# [0-9]*.*offset is [0-9]*\).*/\1/p'
}

is_already_processed () {
  [[ -f "${PROCESSED_FILE}" ]] && /usr/sfw/bin/ggrep -qF "$1" "${PROCESSED_FILE}"
}

mark_processed () {
  echo "$1" >> "${PROCESSED_FILE}"
  tail -100 "${PROCESSED_FILE}" > "${PROCESSED_FILE}.tmp" 2>/dev/null && mv "${PROCESSED_FILE}.tmp" "${PROCESSED_FILE}"
}

is_recently_restored () {
  local NOW=$(date +%s)
  [[ ! -f "${RESTORED_FILE}" ]] && return 1
  while IFS='|' read -r df_num timestamp; do
    if [[ "${df_num}" == "$1" ]]; then
      (( NOW - timestamp < COOLDOWN_SECONDS )) && return 0
    fi
  done < "${RESTORED_FILE}"
  return 1
}

mark_restored () {
  local NOW=$(date +%s)
  [[ -f "${RESTORED_FILE}" ]] && /usr/sfw/bin/ggrep -v "^$1|" "${RESTORED_FILE}" > "${RESTORED_FILE}.tmp"
  echo "$1|${NOW}" >> "${RESTORED_FILE}.tmp"
  mv "${RESTORED_FILE}.tmp" "${RESTORED_FILE}"
}

acquire_lock () {
  # Atomic lock using mkdir + PID file for stale detection.
  if mkdir "${LOCKDIR}" 2>/dev/null; then
    echo $$ > "${LOCKDIR}/pid"
    return 0
  fi
  # Lock exists — check if holder is still alive
  local lock_pid=$(cat "${LOCKDIR}/pid" 2>/dev/null)
  if [[ -n "${lock_pid}" ]] && kill -0 "${lock_pid}" 2>/dev/null; then
    return 1  # Lock held by a live process
  fi
  # Stale lock — reclaim
  echo "$(date) ... Stale lockfile found (PID=${lock_pid}), reclaiming" >> ${LOGFILE}
  rm -rf "${LOCKDIR}"
  if mkdir "${LOCKDIR}" 2>/dev/null; then
    echo $$ > "${LOCKDIR}/pid"
    return 0
  fi
  return 1  # Another process beat us to it
}

release_lock () {
  rm -rf "${LOCKDIR}"
}

try_open_db () {
  # Attempts ALTER DATABASE OPEN. Returns 0 on success, 1 on failure.
  echo "$(date) ... Attempting ALTER DATABASE OPEN" >> ${LOGFILE}
  local open_output
  open_output=$(sqlplus -S / as sysdba <<EOF 2>&1
whenever sqlerror exit failure
whenever oserror exit failure
alter database open;
exit
EOF
)
  local rc=$?
  echo "${open_output}" >> ${LOGFILE}
  return ${rc}
}

start_mrp () {
  echo "$(date) ... Starting MRP (recover managed standby database disconnect)" >> ${LOGFILE}
  sqlplus -S / as sysdba <<EOF >> ${LOGFILE} 2>&1
whenever sqlerror continue
recover managed standby database disconnect;
exit
EOF
}

cancel_mrp () {
  echo "$(date) ... Cancelling MRP" >> ${LOGFILE}
  sqlplus -S / as sysdba <<EOF >> ${LOGFILE} 2>&1
whenever sqlerror continue
recover managed standby database cancel;
exit
EOF
}

get_db_status () {
  # Returns: OPEN, MOUNTED, STARTED, or UNKNOWN
  # Use V$INSTANCE.STATUS for basic state (STARTED, MOUNTED, OPEN)
  local status=$(sqlplus -S / as sysdba <<EOF 2>/dev/null | tr -d '[:space:]'
set heading off feedback off pagesize 0
select status from v\$instance;
exit
EOF
)
  echo "${status:-UNKNOWN}"
}

get_db_open_mode () {
  # Returns: MOUNTED, READ ONLY, READ ONLY WITH APPLY, READ WRITE, or UNKNOWN
  # More accurate than V$INSTANCE for standby databases
  local mode=$(sqlplus -S / as sysdba <<EOF 2>/dev/null | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
set heading off feedback off pagesize 0
select open_mode from v\$database;
exit
EOF
)
  echo "${mode:-UNKNOWN}"
}

is_mrp_running () {
  # Returns 0 if MRP process is active, 1 otherwise
  local mrp_count=$(sqlplus -S / as sysdba <<EOF 2>/dev/null | tr -d '[:space:]'
set heading off feedback off pagesize 0
select count(*) from v\$managed_standby where process like 'MRP%';
exit
EOF
)
  [[ "${mrp_count}" =~ ^[0-9]+$ ]] && [[ "${mrp_count}" -gt 0 ]] && return 0
  return 1
}

check_asm_diskgroups () {
  # Check ASM diskgroup free space, send warning email if below threshold
  # Skip if recovery is in progress (SQL would fail during shutdown/mount)
  [[ -d "${LOCKDIR}" ]] && return
  # NOTE: v$asm_diskgroup is only queryable when DB is OPEN (not MOUNTED)
  local db_mode=$(get_db_open_mode)
  if [[ "${db_mode}" == "MOUNTED" ]] || [[ "${db_mode}" == "UNKNOWN" ]]; then
    echo "$(date) ... Skipping ASM check - DB open_mode is ${db_mode}" >> ${LOGFILE}
    return
  fi
  for dg in ${ASM_DISKGROUPS}; do
    local free_gb=$(sqlplus -S / as sysdba <<EOF 2>/dev/null | tr -d '[:space:]'
set heading off feedback off pagesize 0
select round(free_mb/1024) from v\$asm_diskgroup where name='${dg}';
exit
EOF
)
    if ! [[ "${free_gb}" =~ ^[0-9]+$ ]]; then
      echo "$(date) ... WARNING: Could not query free space for diskgroup ${dg}" >> ${LOGFILE}
      continue
    fi
    if [[ "${free_gb}" -lt "${ASM_FREE_THRESHOLD_GB}" ]]; then
      echo "$(date) ... WARNING: Diskgroup ${dg} has only ${free_gb}GB free (threshold: ${ASM_FREE_THRESHOLD_GB}GB)" >> ${LOGFILE}
      send_mail "[WARNING] ${DBNAME} - ASM Diskgroup ${dg} Low Space" \
        "Diskgroup ${dg} free space is ${free_gb}GB which is below the ${ASM_FREE_THRESHOLD_GB}GB threshold.

Please investigate and free up space or extend the diskgroup.

This is a warning only - the watcher script continues to operate."
    else
      echo "$(date) ... Diskgroup ${dg}: ${free_gb}GB free (OK)" >> ${LOGFILE}
    fi
  done
}

startup_health_check () {
  # On startup, check DB state and fix if needed:
  # - If MOUNTED and MRP not running, start MRP and try to open
  # - Also check ASM diskgroup space
  echo "$(date) === Startup health check ===" >> ${LOGFILE}

  local db_status=$(get_db_status)
  echo "$(date) ... Database status: ${db_status}" >> ${LOGFILE}

  if [[ "${db_status}" == "OPEN" ]]; then
    # DB is open - just ensure MRP is running
    if ! is_mrp_running; then
      echo "$(date) ... DB is OPEN but MRP is not running. Starting MRP." >> ${LOGFILE}
      start_mrp
      send_mail "[NOTICE] ${DBNAME} - MRP Started on Startup" \
        "Database was OPEN but MRP was not running. MRP has been started."
    else
      echo "$(date) ... DB is OPEN and MRP is running. All good." >> ${LOGFILE}
    fi
  elif [[ "${db_status}" == "MOUNTED" ]]; then
    echo "$(date) ... DB is MOUNTED. Checking MRP and attempting recovery." >> ${LOGFILE}

    if ! is_mrp_running; then
      echo "$(date) ... MRP is not running. Starting MRP first." >> ${LOGFILE}
      start_mrp
    fi

    # Check gap before attempting to open
    CURRENT_GAP=$(get_log_gap)
    echo "$(date) ... Current Log Gap: ${CURRENT_GAP}" >> ${LOGFILE}

    if [[ "${CURRENT_GAP}" -lt 0 ]] || [[ "${CURRENT_GAP}" -gt "${GAP_THRESHOLD}" ]]; then
      echo "$(date) ... Gap is too large or unknown (${CURRENT_GAP}). MRP is running. Will NOT attempt to open." >> ${LOGFILE}
      send_mail "[NOTICE] ${DBNAME} - Startup: DB MOUNTED, Lagging" \
        "Database is in MOUNTED state with log gap of ${CURRENT_GAP} (threshold: ${GAP_THRESHOLD}).
MRP has been started. DBA should open the database once lag is reduced."
    else
      # Gap is acceptable, let MRP apply some redo before attempting open
      sleep 30
      cancel_mrp
      sleep 5
      if try_open_db; then
        echo "$(date) ... Database opened successfully on startup." >> ${LOGFILE}
        start_mrp
        send_mail "[RESOLVED] ${DBNAME} - Startup: Database Opened" \
          "Database was in MOUNTED state. Opened successfully and MRP is running."
      else
        echo "$(date) ... Open failed on startup. Starting MRP to continue applying redo." >> ${LOGFILE}
        start_mrp
        send_mail "[ACTION REQUIRED] ${DBNAME} - Startup: Open Failed" \
          "Database is in MOUNTED state. ALTER DATABASE OPEN failed (gap: ${CURRENT_GAP}).
MRP has been started. DBA should open the database manually once recovery catches up."
      fi
    fi
  elif [[ "${db_status}" == "STARTED" ]]; then
    echo "$(date) ... DB is in STARTED (NOMOUNT) state. Cannot auto-fix. DBA intervention needed." >> ${LOGFILE}
    send_mail "[ACTION REQUIRED] ${DBNAME} - Startup: DB in NOMOUNT" \
      "Database is in STARTED (NOMOUNT) state. Manual intervention required."
  else
    echo "$(date) ... DB status is ${db_status}. Cannot determine state." >> ${LOGFILE}
  fi

  # Check ASM diskgroup space
  check_asm_diskgroups

  echo "$(date) === Startup health check complete ===" >> ${LOGFILE}
}

ensure_mrp_running () {
  # Ensure MRP is running whenever DB is OPEN or MOUNTED.
  # Skip if a recovery operation holds the lock (fix_standby is working).
  [[ -d "${LOCKDIR}" ]] && return
  local db_status=$(get_db_status)
  if [[ "${db_status}" == "OPEN" ]] || [[ "${db_status}" == "MOUNTED" ]]; then
    if ! is_mrp_running; then
      echo "$(date) ... MRP check: DB is ${db_status} but MRP is not running. Restarting." >> ${LOGFILE}
      start_mrp
    fi
  fi
}

try_periodic_open () {
  # Called periodically when DB is stuck in MOUNTED state with MRP running.
  # If gap has dropped below threshold, cancel MRP, try open, restart MRP.
  local db_status=$(get_db_status)
  [[ "${db_status}" != "MOUNTED" ]] && return 0  # Already open or other state, skip

  # Acquire lockfile to prevent racing with fix_standby
  acquire_lock || return 1

  local gap=$(get_log_gap)
  if [[ "${gap}" -lt 0 ]] || [[ "${gap}" -gt "${GAP_THRESHOLD}" ]]; then
    echo "$(date) ... Periodic check: DB MOUNTED, gap=${gap} (above ${GAP_THRESHOLD} or unknown). MRP continues." >> ${LOGFILE}
    # Ensure MRP is running
    if ! is_mrp_running; then
      echo "$(date) ... Periodic check: MRP not running, restarting." >> ${LOGFILE}
      start_mrp
    fi
    release_lock
    return 1
  fi

  echo "$(date) ... Periodic check: Gap=${gap} is below threshold (${GAP_THRESHOLD}). Attempting to open DB." >> ${LOGFILE}
  cancel_mrp
  sleep 5

  if try_open_db; then
    echo "$(date) ... Periodic check: Database opened successfully!" >> ${LOGFILE}
    start_mrp
    send_mail "[RESOLVED] ${DBNAME} - Periodic Check: Database Opened" \
      "Database was in MOUNTED state with MRP running.
Gap reduced to ${gap} (threshold: ${GAP_THRESHOLD}).
ALTER DATABASE OPEN succeeded. MRP has been restarted."
    release_lock
    return 0
  else
    echo "$(date) ... Periodic check: Open failed despite gap=${gap}. Restarting MRP." >> ${LOGFILE}
    start_mrp
    release_lock
    return 1
  fi
}

fix_standby () {
  local DATAFILE="$1"

  echo "$(date) === Starting recovery for datafile ${DATAFILE} ===" >> ${LOGFILE}

  # 1. Shutdown and Mount
  # NOTE: Skip cancel_mrp here - if standby is hung on the corrupted datafile,
  # the cancel command can block indefinitely. shutdown abort handles it.
  echo "$(date) ... Stopping instance (abort) and Restarting (mount)" >> ${LOGFILE}
  sqlplus -S / as sysdba <<EOF >> ${LOGFILE} 2>&1
whenever sqlerror continue
shutdown abort;
EOF

  # Wait for PMON to disappear (up to 120s) instead of fixed sleep
  local wait_elapsed=0
  while [[ ${wait_elapsed} -lt 120 ]]; do
    ps -ef | grep "ora_pmon_${DBNAME}" | grep -v grep > /dev/null 2>&1 || break
    sleep 5
    wait_elapsed=$((wait_elapsed + 5))
  done
  [[ ${wait_elapsed} -ge 120 ]] && echo "$(date) ... WARNING: PMON still present after 120s" >> ${LOGFILE}

  sqlplus -S / as sysdba <<EOF >> ${LOGFILE} 2>&1
whenever sqlerror exit failure
whenever oserror exit failure
startup mount;
exit
EOF
  [[ $? -ne 0 ]] && return 1 # Status 1: Mount Failed

  # 2. Validate datafile exists
  local df_valid=$(sqlplus -S / as sysdba <<EOF 2>/dev/null | tr -d '[:space:]'
set heading off feedback off pagesize 0
select count(*) from v\$datafile where file#=${DATAFILE};
exit
EOF
)
  if [[ "${df_valid}" != "1" ]]; then
    echo "$(date) ... ERROR: Datafile# ${DATAFILE} not found in V\$DATAFILE (count=${df_valid})" >> ${LOGFILE}
    return 1
  fi

  # 3. RMAN Restore
  echo "$(date) ... Restoring datafile from ${PRIMARY_SERVICE}" >> ${LOGFILE}
  rman target / <<EOF >> ${LOGFILE} 2>&1
restore datafile ${DATAFILE} from service ${PRIMARY_SERVICE} section size 64G;
exit
EOF
  [[ $? -ne 0 ]] && return 1 # Status 1: Restore Failed

  # 4. Check Gap - if too large, start MRP and skip open entirely
  CURRENT_GAP=$(get_log_gap)
  echo "$(date) ... Current Log Gap: ${CURRENT_GAP}" >> ${LOGFILE}

  if [[ "${CURRENT_GAP}" -lt 0 ]] || [[ "${CURRENT_GAP}" -gt "${GAP_THRESHOLD}" ]]; then
    echo "$(date) ... Gap is too large or unknown (${CURRENT_GAP}). Starting MRP but NOT opening DB." >> ${LOGFILE}
    start_mrp
    return 2 # Status 2: Restored but stayed in MOUNT due to lag
  fi

  # 5. Try to open the database
  if try_open_db; then
    echo "$(date) ... Database opened successfully." >> ${LOGFILE}
    start_mrp
    return 0 # Status 0: Full Success
  fi

  # 6. Open failed - start MRP to apply redo, then retry open up to OPEN_RETRY_COUNT times
  echo "$(date) ... ALTER DATABASE OPEN failed. Will start MRP and retry." >> ${LOGFILE}

  local attempt=1
  while [[ ${attempt} -le ${OPEN_RETRY_COUNT} ]]; do
    echo "$(date) ... Retry ${attempt}/${OPEN_RETRY_COUNT}: Starting MRP for ${OPEN_RETRY_WAIT}s catch-up" >> ${LOGFILE}
    start_mrp
    sleep ${OPEN_RETRY_WAIT}
    cancel_mrp
    sleep 5

    CURRENT_GAP=$(get_log_gap)
    echo "$(date) ... Retry ${attempt}/${OPEN_RETRY_COUNT}: Log Gap is ${CURRENT_GAP}" >> ${LOGFILE}

    if try_open_db; then
      echo "$(date) ... Database opened successfully on retry ${attempt}." >> ${LOGFILE}
      start_mrp
      return 0 # Status 0: Full Success (after retries)
    fi

    echo "$(date) ... Retry ${attempt}/${OPEN_RETRY_COUNT}: Open still failed." >> ${LOGFILE}
    attempt=$((attempt + 1))
  done

  # 7. All retries exhausted - start MRP and leave it running for DBA
  echo "$(date) ... All ${OPEN_RETRY_COUNT} open retries exhausted (total wait: $((OPEN_RETRY_COUNT * OPEN_RETRY_WAIT / 60)) minutes). Starting MRP and leaving for DBA." >> ${LOGFILE}
  start_mrp
  return 3 # Status 3: Restored, open failed after retries, MRP running
}

# Global variable used by fix_standby and referenced in email notifications
CURRENT_GAP=0

# ================== MAIN ==================
umask 077
touch "${LOGFILE}"
ensure_single_instance

CHECKER_PID=""
FIFO="/tmp/ora10567_${DBNAME}.fifo"

cleanup () {
  # Kill the checker subshell and all its children (tail, sleep)
  if [[ -n "${CHECKER_PID}" ]]; then
    pkill -P "${CHECKER_PID}" 2>/dev/null
    kill "${CHECKER_PID}" 2>/dev/null
  fi
  rm -f "${WATCHER_PIDFILE}" "${FIFO}"
  rm -rf "${WATCHER_PIDFILE}.d" "${LOCKDIR}"
}
trap cleanup EXIT

# Rotate log if it exceeds 100MB
LOG_MAX_BYTES=104857600
if [[ -f "${LOGFILE}" ]]; then
  log_size=$(stat -c%s "${LOGFILE}" 2>/dev/null || stat -f%z "${LOGFILE}" 2>/dev/null || echo 0)
  if [[ ${log_size} -ge ${LOG_MAX_BYTES} ]]; then
    mv "${LOGFILE}" "${LOGFILE}.1"
    touch "${LOGFILE}"
  fi
fi

echo "$(date) ORA-10567 watcher started (PID=$$)" >> ${LOGFILE}

# Run startup health check (fix MOUNTED state, check ASM space)
startup_health_check

echo "$(date) Entering monitoring mode - watching alert log for ORA-10567" >> ${LOGFILE}
send_mail "[INFO] ${DBNAME} - ORA-10567 Watcher Active" \
  "ORA-10567 watcher has started and completed startup health checks.
Now monitoring alert log for ORA-10567 errors.

PID: $$
Host: $(hostname)
Alert Log: ${ALERT}
Database Status: $(get_db_status)
MRP Running: $(is_mrp_running && echo 'YES' || echo 'NO')
Log Gap: $(get_log_gap)"

# Use a FIFO to decouple tail from the reader loop.
# A background subprocess manages tail and restarts it on alert log rotation.
rm -f "${FIFO}"
mkfifo -m 600 "${FIFO}"

start_checker () {
  # Background: feed alert log into FIFO, restart tail on inode change (rotation)
  # Also periodically checks ASM diskgroup space and tries to open MOUNTED DB
  (
    last_asm_check=0
    last_open_check=0
    while true; do
      [[ ! -f "${ALERT}" ]] && { sleep 10; continue; }
      local_inode=$(ls -i "${ALERT}" 2>/dev/null | awk '{print $1}')
      tail -0lf "${ALERT}" > "${FIFO}" &
      local_tail=$!
      while kill -0 "${local_tail}" 2>/dev/null; do
        sleep 60
        # Check alert log rotation
        new_inode=$(ls -i "${ALERT}" 2>/dev/null | awk '{print $1}')
        if [[ "${new_inode}" != "${local_inode}" ]]; then
          echo "$(date) Alert log rotated (inode ${local_inode} -> ${new_inode}). Restarting tail." >> ${LOGFILE}
          kill "${local_tail}" 2>/dev/null
          wait "${local_tail}" 2>/dev/null
          break
        fi
        # Periodic ASM diskgroup space check
        now_epoch=$(date +%s)
        if [[ $((now_epoch - last_asm_check)) -ge ${ASM_CHECK_INTERVAL} ]]; then
          check_asm_diskgroups
          last_asm_check=${now_epoch}
        fi
        # Periodic check: try to open DB if stuck in MOUNTED state
        if [[ $((now_epoch - last_open_check)) -ge ${MOUNTED_OPEN_CHECK_INTERVAL} ]]; then
          ensure_mrp_running
          try_periodic_open
          last_open_check=${now_epoch}
        fi
      done
      sleep 2
    done
  ) &
  CHECKER_PID=$!
}

start_checker

# Main loop: read from FIFO, restart checker if it dies (EOF on FIFO)
while true; do
  while IFS= read -r line; do
  echo "$line" | /usr/sfw/bin/ggrep -q "ORA-10567" || continue
  SIGNATURE=$(get_line_signature "$line")
  [[ -z "${SIGNATURE}" ]] && continue
  is_already_processed "${SIGNATURE}" && continue

  DATAFILE=$(echo "$line" | sed -n 's/.*file# \([0-9][0-9]*\).*/\1/p')
  [[ -z "${DATAFILE}" ]] && continue
  is_recently_restored "${DATAFILE}" && continue
  # Retry lock acquisition (e.g. try_periodic_open holds it briefly)
  lock_attempts=0
  while ! acquire_lock; do
    lock_attempts=$((lock_attempts + 1))
    [[ ${lock_attempts} -ge 12 ]] && { echo "$(date) Could not acquire lock after 60s, skipping datafile ${DATAFILE}" >> ${LOGFILE}; continue 2; }
    sleep 5
  done

  mark_processed "${SIGNATURE}"

  send_mail "[CRITICAL] ${DBNAME} - ORA-10567 Recovery Initiated" "Detected ORA-10567 for File ${DATAFILE}. Starting recovery."

  fix_standby "${DATAFILE}"
  RESULT=$?

  if [[ $RESULT -eq 0 ]]; then
    mark_restored "${DATAFILE}"
    send_mail "[RESOLVED] ${DBNAME} - Recovery Complete" \
      "Datafile ${DATAFILE} restored. Database is OPEN and MRP is running."
  elif [[ $RESULT -eq 2 ]]; then
    mark_restored "${DATAFILE}"
    send_mail "[NOTICE] ${DBNAME} - Restored but Lagging" \
      "Datafile ${DATAFILE} restored.
NOTE: Database was NOT opened because log gap is ${CURRENT_GAP} (Threshold: ${GAP_THRESHOLD}).
MRP has been started. Please open manually once lag is reduced."
  elif [[ $RESULT -eq 3 ]]; then
    mark_restored "${DATAFILE}"
    send_mail "[ACTION REQUIRED] ${DBNAME} - Open Failed After Retries" \
      "Datafile ${DATAFILE} was restored successfully via RMAN.
However, ALTER DATABASE OPEN failed on all ${OPEN_RETRY_COUNT} attempts over $((OPEN_RETRY_COUNT * OPEN_RETRY_WAIT / 60)) minutes.
The file still needs more recovery to be consistent.

MRP is currently running to continue applying redo logs.
DBA must check and open the database manually once recovery catches up.

Review log: ${LOGFILE}"
  else
    send_mail "[FAILED] ${DBNAME} - Recovery Failed" \
      "RECOVERY FAILED:
  Datafile#   : ${DATAFILE}
  Status      : Automatic recovery encountered errors (mount or restore failed).

ACTION REQUIRED:
  1. SSH to server
  2. Check status: sqlplus / as sysdba
  3. Review log: ${LOGFILE}"
  fi

  release_lock
  done < "${FIFO}"

  # If we get here, the FIFO writer (checker subprocess) died — restart it
  echo "$(date) WARNING: FIFO reader got EOF - checker subprocess died. Restarting." >> ${LOGFILE}
  # Clean up dead checker
  if [[ -n "${CHECKER_PID}" ]]; then
    pkill -P "${CHECKER_PID}" 2>/dev/null
    kill "${CHECKER_PID}" 2>/dev/null
    wait "${CHECKER_PID}" 2>/dev/null
  fi
  rm -f "${FIFO}"
  mkfifo -m 600 "${FIFO}"
  start_checker
  sleep 2
done
