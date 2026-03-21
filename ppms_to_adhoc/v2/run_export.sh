#!/bin/bash
#
# run_export.sh - PPMS Data Pump Export
#
# Runs on the PPMS server. Exports all PREPAID tables to NFS via expdp.
# Manages lock file, email notifications, and error checking.
#
# Usage: ./run_export.sh
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "${SCRIPT_DIR}/ppms_to_adhoc.conf"
. "${SCRIPT_DIR}/common.sh"

# Set Oracle environment for PPMS
export ORACLE_SID="${PPMS_SID}"
export ORACLE_HOME="${PPMS_ORACLE_HOME}"
export PATH="${ORACLE_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${ORACLE_HOME}/lib:/lib"

DATE_TAG=$(date +%Y%m%d)
LOG_FILE="${LOG_DIR_PPMS}/export_${DATE_TAG}.log"

ensure_dir "${LOG_DIR_PPMS}"

# ============================================================
# Pre-flight checks
# ============================================================
log_info "=== PPMS to ADHOC Export Starting ==="

# Check if another export is already running
if check_lock; then
    log_error "Lock file already exists on ${LOCK_HOST}. Another export may be running."
    send_mail "PPMS_EXPORT_BLOCKED" "Export aborted: lock file ${LOCK_FILE} already exists on ${LOCK_HOST}. Check if a previous export is still running."
    exit 1
fi

# Check NFS space
rem_space=$(df -h "${NFS_PATH_PPMS}" 2>/dev/null | awk 'NR==2{print $4,$5}')
if [ -z "${rem_space}" ]; then
    log_error "Cannot check NFS space at ${NFS_PATH_PPMS}"
    send_mail "PPMS_EXPORT_FAILED" "Cannot access NFS path ${NFS_PATH_PPMS}"
    exit 1
fi
log_info "NFS remaining space: ${rem_space}"

# ============================================================
# Create lock and notify
# ============================================================
create_lock
if [ $? -ne 0 ]; then
    send_mail "PPMS_EXPORT_FAILED" "Failed to create lock file on ${LOCK_HOST}"
    exit 1
fi

send_mail "PPMS_EXPORT_STARTED" "Export started.

Remaining space on NFS (${NFS_PATH_PPMS}):
${rem_space}
"

# ============================================================
# Export function
# ============================================================
do_export() {
    _table="$1"
    _parallel="$2"
    _tname=$(table_short_name "${_table}")
    _schema=$(table_schema "${_table}")

    _dumpfile="${_schema}_${_tname}"
    _logfile="exp_${_schema}_${_tname}.log"

    if [ "${_parallel}" -gt 1 ]; then
        _dumpfile="${_dumpfile}_%u"
    fi

    log_info "Exporting ${_table} (parallel=${_parallel})"

    cd "${NFS_PATH_PPMS}"

    ${ORACLE_HOME}/bin/expdp \'/ as sysdba\' \
        directory=${ORA_DIR_EXPORT} \
        DUMPFILE="${_dumpfile}.dmp" \
        TABLES="${_table}" \
        logfile="${_logfile}" \
        PARALLEL=${_parallel} \
        EXCLUDE=STATISTICS

    _rc=$?
    if [ ${_rc} -ne 0 ]; then
        log_error "expdp failed for ${_table} (rc=${_rc})"
        return 1
    fi
    log_info "Export completed for ${_table}"
    return 0
}

# ============================================================
# Run exports
# ============================================================
export_failed=0

# Heavy tables (high parallelism)
do_export "PREPAID.TPS01_CARDS" ${EXP_PARALLEL_CARDS}
[ $? -ne 0 ] && export_failed=1

do_export "PREPAID.TPS01_LOG_CARDS" ${EXP_PARALLEL_LARGE}
[ $? -ne 0 ] && export_failed=1

do_export "PREPAID.TPS01_LOG_USED_CARDS" ${EXP_PARALLEL_LARGE}
[ $? -ne 0 ] && export_failed=1

do_export "PREPAID.TPS31_CARD_BRICKS" ${EXP_PARALLEL_LARGE}
[ $? -ne 0 ] && export_failed=1

do_export "PREPAID.TPS30_CARD_BOXES" ${EXP_PARALLEL_MEDIUM}
[ $? -ne 0 ] && export_failed=1

# Light tables (single-threaded)
for _t in \
    PREPAID.TPS11_OUTLET_CODES \
    PREPAID.TPS107_DISTRIBUTOR_DETAILS \
    PREPAID.TPS73_LOGICAL_ORDERS \
    PREPAID.TPS08_DENOMINATION_TYPES \
    PREPAID.TPS6073_LOGICAL_ORDERS \
    PREPAID.TPS09_PPAS_LOG_CARD_PARAMETERS \
    PREPAID.TPS09_PPAS_CARD_PARAMETERS \
    PREPAID.TPS145_STOCK_ORDERS \
    PREPAID.TPS74_LOGICAL_ORDERS_DETAIL \
    PREPAID.TPS6074_LOGICAL_ORDERS_DETAIL
do
    do_export "${_t}" 1
    [ $? -ne 0 ] && export_failed=1
done

# ============================================================
# Post-export checks
# ============================================================
log_info "Checking export logs for errors..."
error_logs=$(egrep -il 'ORA-|failed' "${NFS_PATH_PPMS}"/exp_PREPAID*.log 2>/dev/null)

if [ ${export_failed} -ne 0 ] || [ -n "${error_logs}" ]; then
    log_error "Export completed WITH ERRORS"
    send_mail "PPMS_EXPORT_FAILED" "Export completed with errors.

Failed log files:
${error_logs}

Check logs at: ${NFS_PATH_PPMS}/exp_PREPAID*.log"
    echo "failed expdp" > "${LOG_DIR_PPMS}/failed_expdp_${DATE_TAG}.log"
else
    log_info "Export completed successfully"
    send_mail "PPMS_EXPORT_COMPLETED" "Export completed successfully. All tables exported."
fi

# Always remove lock when done
remove_lock

log_info "=== PPMS to ADHOC Export Finished ==="
exit ${export_failed}
