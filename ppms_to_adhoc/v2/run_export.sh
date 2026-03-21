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
# Cleanup trap: remove lock file on unexpected exit
# ============================================================
cleanup() {
    log_error "Caught signal — cleaning up before exit"
    nfs_signal_fail "${NFS_PATH_PPMS}"
    if [ "${NO_LOCK}" = "false" ]; then
        remove_lock
    fi
    send_mail "PPMS_EXPORT_ABORTED" "Export script was killed or interrupted."
    exit 130
}
trap cleanup INT TERM HUP

# ============================================================
# Pre-flight checks
# ============================================================
log_info "=== PPMS to ADHOC Export Starting ==="

# Parse flags
NO_LOCK=false
if [ "$1" = "--no-lock" ]; then
    NO_LOCK=true
    log_info "Lock mechanism disabled (--no-lock flag)"
fi

# Check if another export is already running
if [ "${NO_LOCK}" = "false" ]; then
    if check_lock; then
        log_error "Lock file already exists on ${LOCK_HOST}. Another export may be running."
        send_mail "PPMS_EXPORT_BLOCKED" "Export aborted: lock file ${LOCK_FILE} already exists on ${LOCK_HOST}. Check if a previous export is still running."
        exit 1
    fi
fi

# ============================================================
# Archive previous run logs and remove old dumps
# ============================================================
_old_logs=$(ls "${NFS_PATH_PPMS}"/exp_PREPAID*.log "${NFS_PATH_PPMS}"/imp_PREPAID*.log 2>/dev/null)
if [ -n "${_old_logs}" ]; then
    ARCHIVE_DIR="${NFS_PATH_PPMS}/archive/${DATE_TAG}"
    mkdir -p "${ARCHIVE_DIR}"
    log_info "Archiving previous run logs to ${ARCHIVE_DIR}/"
    for _f in ${_old_logs}; do
        mv "${_f}" "${ARCHIVE_DIR}/"
    done
fi

_old_dumps=$(ls "${NFS_PATH_PPMS}"/PREPAID_*.dmp 2>/dev/null)
if [ -n "${_old_dumps}" ]; then
    log_info "Removing old dump files from ${NFS_PATH_PPMS}/"
    rm -f "${NFS_PATH_PPMS}"/PREPAID_*.dmp
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
if [ "${NO_LOCK}" = "false" ]; then
    create_lock
    if [ $? -ne 0 ]; then
        send_mail "PPMS_EXPORT_FAILED" "Failed to create lock file on ${LOCK_HOST}"
        exit 1
    fi
fi

# NFS signal: mark export as running (always, independent of SSH lock)
nfs_signal_start "${NFS_PATH_PPMS}"

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

# Heavy tables first (higher parallelism)
for _t in "${HEAVY_TABLES[@]}"; do
    do_export "${_t}" $(get_exp_parallel "${_t}")
    [ $? -ne 0 ] && export_failed=1
done

# Light tables
for _t in "${LIGHT_TABLES[@]}"; do
    do_export "${_t}" $(get_exp_parallel "${_t}")
    [ $? -ne 0 ] && export_failed=1
done

# ============================================================
# Post-export checks
# ============================================================
log_info "Checking export logs for errors..."
error_logs=$(egrep -il 'ORA-|failed' "${NFS_PATH_PPMS}"/exp_PREPAID*.log 2>/dev/null)

if [ ${export_failed} -ne 0 ] || [ -n "${error_logs}" ]; then
    log_error "Export completed WITH ERRORS"
    _error_detail=$(egrep -h 'ORA-' "${NFS_PATH_PPMS}"/exp_PREPAID*.log 2>/dev/null | sort -u | head -30)
    nfs_signal_fail "${NFS_PATH_PPMS}"
    send_mail "PPMS_EXPORT_FAILED" "Export completed with errors.

Failed log files:
${error_logs:-check return codes}

ORA- errors found:
${_error_detail:-no ORA- errors in logs}

Full logs at: ${NFS_PATH_PPMS}/exp_PREPAID*.log"
    echo "failed expdp" > "${LOG_DIR_PPMS}/failed_expdp_${DATE_TAG}.log"
else
    log_info "Export completed successfully"
    nfs_signal_done "${NFS_PATH_PPMS}"
    send_mail "PPMS_EXPORT_COMPLETED" "Export completed successfully. All tables exported."
fi

# Remove SSH lock when done (if using lock)
if [ "${NO_LOCK}" = "false" ]; then
    remove_lock
fi

log_info "=== PPMS to ADHOC Export Finished ==="
exit ${export_failed}
