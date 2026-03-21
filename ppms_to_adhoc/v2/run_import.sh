#!/bin/bash
#
# run_import.sh - ADHOC Data Pump Import
#
# Runs on the ADHOC server. Waits for export to finish, validates dumps,
# drops/creates tables, imports data, cleans PII, creates indexes, sets grants.
#
# Wait modes:
#   (default)    Poll NFS signal files on shared storage (no SSH needed)
#   --wait-ssh   Poll SSH lock file on ADHOC (requires firewall whitelist)
#   --skip-wait  Skip waiting entirely (used by run_pipeline.sh via SSH)
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "${SCRIPT_DIR}/ppms_to_adhoc.conf"
. "${SCRIPT_DIR}/common.sh"

# Set Oracle environment for ADHOC
export ORACLE_SID="${ADHOC_SID}"
export ORACLE_HOME="${ADHOC_ORACLE_HOME}"
export PATH="${ORACLE_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${ORACLE_HOME}/lib:/lib"

DATE_TAG=$(date +%Y%m%d)
LOG_FILE="${LOG_DIR_ADHOC}/import_${DATE_TAG}.log"

ensure_dir "${LOG_DIR_ADHOC}"

log_info "=== PPMS to ADHOC Import Starting ==="

# ============================================================
# Wait for export completion
#   (default)    : poll NFS signal files (no SSH required)
#   --wait-ssh   : poll SSH lock file (requires firewall whitelist)
#   --skip-wait  : skip waiting (called from run_pipeline.sh)
# ============================================================
WAIT_MODE="nfs"
if [ "$1" = "--skip-wait" ]; then
    WAIT_MODE="skip"
elif [ "$1" = "--wait-ssh" ]; then
    WAIT_MODE="ssh"
fi

if [ "${WAIT_MODE}" = "skip" ]; then
    log_info "Wait skipped (--skip-wait flag, called from pipeline)."

elif [ "${WAIT_MODE}" = "ssh" ]; then
    log_info "Waiting for export to complete (SSH lock on ${LOCK_HOST})..."
    _wait_start=$(date +%s)
    _max_wait=$((LOCK_MAX_WAIT_HOURS * 3600))
    while check_lock; do
        _elapsed=$(( $(date +%s) - _wait_start ))
        if [ ${_elapsed} -ge ${_max_wait} ]; then
            log_error "Lock file still present after ${LOCK_MAX_WAIT_HOURS}h. Stale lock detected."
            send_mail "PPMS_IMPORT_FAILED" "Import aborted: lock file ${LOCK_FILE} on ${LOCK_HOST} still exists after ${LOCK_MAX_WAIT_HOURS} hours. Possible stale lock."
            exit 1
        fi
        log_info "SSH lock still exists, waiting 3 minutes... (elapsed: $((${_elapsed}/60))m / max: $((${_max_wait}/60))m)"
        sleep 180
    done
    log_info "SSH lock cleared. Export appears complete."

else
    # Default: NFS signal polling
    log_info "Waiting for export to complete (NFS signal on ${NFS_PATH_ADHOC})..."
    _wait_start=$(date +%s)
    _max_wait=$((LOCK_MAX_WAIT_HOURS * 3600))
    while true; do
        if nfs_check_done "${NFS_PATH_ADHOC}" "${DATE_TAG}"; then
            log_info "NFS signal: export completed for today (${DATE_TAG}). Proceeding."
            break
        fi

        _elapsed=$(( $(date +%s) - _wait_start ))
        if [ ${_elapsed} -ge ${_max_wait} ]; then
            log_error "No export done signal after ${LOCK_MAX_WAIT_HOURS}h."
            send_mail "PPMS_IMPORT_FAILED" "Import aborted: NFS export done signal not found after ${LOCK_MAX_WAIT_HOURS} hours.
Signal file expected: ${NFS_PATH_ADHOC}/${NFS_SIGNAL_DONE}
Checked for date: ${DATE_TAG}"
            exit 1
        fi

        if nfs_check_running "${NFS_PATH_ADHOC}"; then
            log_info "Export in progress, waiting 3 min... (elapsed: $((${_elapsed}/60))m)"
        else
            log_info "Export not started yet, waiting 3 min... (elapsed: $((${_elapsed}/60))m)"
        fi
        sleep 180
    done
fi

# ============================================================
# Validate dump files
# ============================================================
cnt_dumps=$(find "${NFS_PATH_ADHOC}" -name "PREPAID_*.dmp" -mtime -${DUMP_MAX_AGE_DAYS} 2>/dev/null | wc -l)
cnt_dumps=$(echo "${cnt_dumps}" | tr -d ' ')

if [ "${cnt_dumps}" -lt "${EXPECTED_DUMP_COUNT}" ]; then
    log_error "Dump file count ${cnt_dumps} is less than expected ${EXPECTED_DUMP_COUNT}"
    send_mail "PPMS_IMPORT_FAILED" "Import aborted: dump file count is ${cnt_dumps}, expected >= ${EXPECTED_DUMP_COUNT}"
    exit 1
fi

log_info "Dump file count: ${cnt_dumps} (expected >= ${EXPECTED_DUMP_COUNT}) - OK"

# ============================================================
# Phase 1: Drop and recreate tables
# ============================================================
log_info "Phase 1: Dropping and recreating REPORT tables..."
send_mail "PPMS_IMPORT_STARTED" "Import pipeline started. Dump count: ${cnt_dumps}"

# Build dynamic DROP list from HEAVY + LIGHT (excluding SPECIAL) + extras
drop_sql=""
for _table in "${HEAVY_TABLES[@]}" "${LIGHT_TABLES[@]}"; do
    [ "${_table}" = "${SPECIAL_IMPORT_TABLE}" ] && continue
    _rtable=$(to_report_table "${_table}")
    drop_sql="${drop_sql}
BEGIN EXECUTE IMMEDIATE 'DROP TABLE ${_rtable} CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN IF SQLCODE = -942 THEN NULL; ELSE RAISE; END IF; END;
/"
done
for _table in "${DROP_EXTRA_TABLES[@]}"; do
    drop_sql="${drop_sql}
BEGIN EXECUTE IMMEDIATE 'DROP TABLE ${_table} CASCADE CONSTRAINTS'; EXCEPTION WHEN OTHERS THEN IF SQLCODE = -942 THEN NULL; ELSE RAISE; END IF; END;
/"
done

sqlplus -S / as sysdba <<EOSQL >> "${LOG_FILE}" 2>&1
SET ECHO OFF
SET FEEDBACK OFF
SET PAGESIZE 0
${drop_sql}
EXIT;
EOSQL

if [ $? -ne 0 ]; then
    log_error "Failed to drop tables"
    send_mail "PPMS_IMPORT_FAILED" "Failed during table drop phase"
    exit 1
fi

log_info "Tables dropped. Running DDL creation..."

# Run the table creation SQL (this is the big DDL file)
sqlplus -S / as sysdba @"${SQL_DIR}/create_tables.sql" >> "${LOG_FILE}" 2>&1

if [ $? -ne 0 ]; then
    log_error "Failed to create tables"
    send_mail "PPMS_IMPORT_FAILED" "Failed during table creation DDL"
    exit 1
fi

# Set all tables to NOLOGGING for faster import (skip SPECIAL - uses REPLACE)
nolog_sql=""
for _table in "${HEAVY_TABLES[@]}" "${LIGHT_TABLES[@]}"; do
    [ "${_table}" = "${SPECIAL_IMPORT_TABLE}" ] && continue
    _rtable=$(to_report_table "${_table}")
    nolog_sql="${nolog_sql}
ALTER TABLE ${_rtable} NOLOGGING;"
done

sqlplus -S / as sysdba <<EOSQL >> "${LOG_FILE}" 2>&1
${nolog_sql}
EXIT;
EOSQL

log_info "Phase 1 complete: Tables recreated with NOLOGGING"

# ============================================================
# Phase 2: Import data (parallel streams)
# ============================================================
log_info "Phase 2: Importing data..."
send_mail "PPMS_IMPORT_DATA_LOADING" "Data import phase started"

# Import function
do_import() {
    _table="$1"
    _parallel="$2"
    _tname=$(table_short_name "${_table}")
    _schema=$(table_schema "${_table}")

    _dumpfile="${_schema}_${_tname}"
    _logfile="imp_${_schema}_${_tname}.log"

    if [ "${_parallel}" -gt 1 ]; then
        _dumpfile="${_dumpfile}_%u"
    fi

    log_info "Importing ${_table} (parallel=${_parallel})"

    cd "${NFS_PATH_ADHOC}"

    ${ORACLE_HOME}/bin/impdp \'/ as sysdba\' \
        directory=${ORA_DIR_IMPORT} \
        DUMPFILE="${_dumpfile}.dmp" \
        TABLES="${_table}" \
        logfile="${_logfile}" \
        REMAP_SCHEMA=${_schema}:REPORT \
        CONTENT=DATA_ONLY \
        PARALLEL=${_parallel}

    _rc=$?
    if [ ${_rc} -ne 0 ]; then
        log_error "impdp failed for ${_table} (rc=${_rc})"
        return 1
    fi
    log_info "Import completed for ${_table}"
    return 0
}

# Special import for TPS6074 (TABLE_EXISTS_ACTION=REPLACE, no DATA_ONLY)
do_import_special() {
    _table="$1"
    _tname=$(table_short_name "${_table}")
    _schema=$(table_schema "${_table}")

    log_info "Importing ${_table} (special REPLACE mode)"

    cd "${NFS_PATH_ADHOC}"

    ${ORACLE_HOME}/bin/impdp \'/ as sysdba\' \
        directory=${ORA_DIR_IMPORT} \
        DUMPFILE="${_schema}_${_tname}.dmp" \
        TABLES="${_table}" \
        logfile="imp_${_schema}_${_tname}_${DATE_TAG}.log" \
        REMAP_SCHEMA=${_schema}:REPORT \
        TABLE_EXISTS_ACTION=REPLACE \
        EXCLUDE=GRANT

    _rc=$?
    if [ ${_rc} -ne 0 ]; then
        log_error "impdp (special) failed for ${_table} (rc=${_rc})"
        return 1
    fi
    log_info "Import completed for ${_table} (special)"
    return 0
}

# Stream 1: Heavy tables (background)
(
    _stream_failed=0
    for _table in "${HEAVY_TABLES[@]}"; do
        do_import "${_table}" $(get_imp_parallel "${_table}")
        [ $? -ne 0 ] && _stream_failed=1
    done
    exit ${_stream_failed}
) &
pid_heavy=$!

# Stream 2: Light tables (background)
(
    _stream_failed=0
    for _table in "${LIGHT_TABLES[@]}"; do
        if [ "${_table}" = "${SPECIAL_IMPORT_TABLE}" ]; then
            do_import_special "${_table}"
        else
            do_import "${_table}" $(get_imp_parallel "${_table}")
        fi
        [ $? -ne 0 ] && _stream_failed=1
    done
    exit ${_stream_failed}
) &
pid_light=$!

# Wait for both streams
wait ${pid_heavy}
rc_heavy=$?
wait ${pid_light}
rc_light=$?

if [ ${rc_heavy} -ne 0 ] || [ ${rc_light} -ne 0 ]; then
    log_error "Import failed (heavy=${rc_heavy}, light=${rc_light}). ABORTING pipeline."
    # Extract actual ORA- errors from import logs for the email
    _error_detail=$(egrep -h 'ORA-' "${NFS_PATH_ADHOC}"/imp_PREPAID*.log 2>/dev/null | sort -u | head -30)
    _failed_files=$(egrep -il 'ORA-|failed' "${NFS_PATH_ADHOC}"/imp_PREPAID*.log 2>/dev/null)
    send_mail "PPMS_IMPORT_FAILED" "Import data phase failed (heavy=${rc_heavy}, light=${rc_light}).
Pipeline ABORTED before index creation to avoid wasting time on broken data.

Files with errors:
${_failed_files:-none detected}

ORA- errors found:
${_error_detail:-no ORA- errors in logs (check return codes)}

Full logs at: ${NFS_PATH_ADHOC}/imp_PREPAID*.log"
    exit 1
fi

log_info "Phase 2 complete: Data import finished"

# ============================================================
# Phase 2b: Row count validation (catch partial imports)
# ============================================================
log_info "Phase 2b: Validating row counts..."

rowcount_sql=""
for _table in "${HEAVY_TABLES[@]}" "${LIGHT_TABLES[@]}"; do
    _rtable=$(to_report_table "${_table}")
    rowcount_sql="${rowcount_sql}
SELECT '${_rtable}' || '=' || COUNT(*) FROM ${_rtable};"
done

_rowcount_out=$(sqlplus -S / as sysdba <<EOSQL
SET ECHO OFF
SET FEEDBACK OFF
SET PAGESIZE 0
SET HEADING OFF
${rowcount_sql}
EXIT;
EOSQL
)

_empty_tables=""
while IFS='=' read -r _tbl _cnt; do
    [ -z "${_tbl}" ] && continue
    _cnt=$(echo "${_cnt}" | tr -d ' ')
    if [ "${_cnt}" = "0" ] || [ -z "${_cnt}" ]; then
        _empty_tables="${_empty_tables}  ${_tbl} (0 rows)
"
    fi
    log_info "Row count: ${_tbl} = ${_cnt}"
done <<< "${_rowcount_out}"

if [ -n "${_empty_tables}" ]; then
    log_error "Empty tables detected after import (possible partial import):"
    log_error "${_empty_tables}"
    send_mail "PPMS_IMPORT_WARNING" "Row count validation found EMPTY tables after import:
${_empty_tables}
Pipeline continues but data may be incomplete."
fi

# ============================================================
# Phase 3: PII cleanup
# ============================================================
log_info "Phase 3: Removing PII columns..."

pii_sql=""
for _table in "${PII_TABLES[@]}"; do
    pii_sql="${pii_sql}
ALTER TABLE ${_table} SET UNUSED (${PII_COLUMNS});"
done

sqlplus -S / as sysdba <<EOSQL >> "${LOG_FILE}" 2>&1
${pii_sql}
EXIT;
EOSQL

log_info "Phase 3 complete: PII columns set to UNUSED"

# ============================================================
# Phase 4: Create indexes (parallel streams)
# ============================================================
log_info "Phase 4: Creating indexes..."
send_mail "PPMS_INDEX_CREATION_STARTED" "Index creation phase started"

sqlplus / as sysdba @"${SQL_DIR}/create_indexes_1.sql" &
pid_idx1=$!

sqlplus / as sysdba @"${SQL_DIR}/create_indexes_2.sql" &
pid_idx2=$!

wait ${pid_idx1}
rc_idx1=$?
wait ${pid_idx2}
rc_idx2=$?

if [ ${rc_idx1} -ne 0 ] || [ ${rc_idx2} -ne 0 ]; then
    log_error "Some index creation failed (stream1=${rc_idx1}, stream2=${rc_idx2})"
fi

send_mail "PPMS_INDEX_CREATION_FINISHED" "Index creation completed"
log_info "Phase 4 complete: Indexes created"

# ============================================================
# Phase 5: Post-processing
# ============================================================
log_info "Phase 5: Setting index parallelism and grants..."

sqlplus -S / as sysdba @"${SQL_DIR}/post_import.sql" >> "${LOG_FILE}" 2>&1

log_info "Phase 5 complete"

# ============================================================
# Final status
# ============================================================
# Check import logs for errors
error_logs=$(egrep -il 'ORA-|failed' "${NFS_PATH_ADHOC}"/imp_PREPAID*.log 2>/dev/null)

if [ -n "${error_logs}" ]; then
    log_error "Import pipeline completed WITH ERRORS"
    _error_detail=$(egrep -h 'ORA-' ${error_logs} 2>/dev/null | sort -u | head -30)
    send_mail "PPMS_IMPORT_FAILED" "Import completed with errors.

Failed log files:
${error_logs}

ORA- errors found:
${_error_detail:-check logs manually}

Full logs at: ${NFS_PATH_ADHOC}/imp_PREPAID*.log"
    echo "FAILED IMPORT at $(date +%Y/%m/%d_%H:%M:%S)" >> "${LOG_FILE}"
    exit 1
else
    log_info "Import pipeline completed successfully"

    # Clean up dump files after successful import
    log_info "Removing dump files from ${NFS_PATH_ADHOC}/"
    rm -f "${NFS_PATH_ADHOC}"/PREPAID_*.dmp

    send_mail_to "${MAIL_ALIREZA}" "PPMS_IMPORT_COMPLETED" "Import pipeline completed successfully."
    send_mail "PPMS_IMPORT_COMPLETED" "Full pipeline completed successfully."
    echo "Finished IMPORT at $(date +%Y/%m/%d_%H:%M:%S)" >> "${LOG_FILE}"
fi

log_info "=== PPMS to ADHOC Import Finished ==="
exit 0
