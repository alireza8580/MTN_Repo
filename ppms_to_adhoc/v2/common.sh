#!/bin/bash
#
# common.sh - Shared functions for PPMS to ADHOC pipeline
# Source this after ppms_to_adhoc.conf
#

# Epoch seconds (Solaris 10 date doesn't support %s)
epoch() {
    nawk 'BEGIN { srand(); print srand() }'
}

# Timestamp for log messages
ts() {
    date "+%Y-%m-%d %H:%M:%S"
}

# Log to stdout and logfile
log_msg() {
    _msg="$(ts) [$$] $1"
    echo "${_msg}"
    if [ -n "${LOG_FILE}" ]; then
        echo "${_msg}" >> "${LOG_FILE}"
    fi
}

log_error() {
    log_msg "ERROR: $1"
}

log_info() {
    log_msg "INFO: $1"
}

# Send email notification
# Usage: send_mail "subject" "body"
send_mail() {
    _subject="$1 at $(date +%Y%m%d_%H%M)"
    _body="$2"
    mailx -s "${_subject}" "${MAIL_DBA}" <<EOF
${_body}
EOF
}

# Send email to specific recipient
# Usage: send_mail_to "recipient" "subject" "body"
send_mail_to() {
    _to="$1"
    _subject="$2 at $(date +%Y%m%d_%H%M)"
    _body="$3"
    mailx -s "${_subject}" "${_to}" <<EOF
${_body}
EOF
}

# ============================================================
# SSH-based lock functions (requires SSH between servers)
# ============================================================

# Check if lock file exists on remote host
# Returns 0 if lock exists, 1 if not
check_lock() {
    ssh -q "${LOCK_USER}@${LOCK_HOST}" "ls ${LOCK_FILE}" 2>/dev/null
    return $?
}

# Create lock file on remote host
create_lock() {
    ssh -q "${LOCK_USER}@${LOCK_HOST}" "touch ${LOCK_FILE}"
    if [ $? -ne 0 ]; then
        log_error "Failed to create lock file on ${LOCK_HOST}"
        return 1
    fi
    log_info "Lock file created on ${LOCK_HOST}:${LOCK_FILE}"
    return 0
}

# Remove lock file from remote host
remove_lock() {
    ssh -q "${LOCK_USER}@${LOCK_HOST}" "rm -f ${LOCK_FILE}"
    if [ $? -ne 0 ]; then
        log_error "Failed to remove lock file on ${LOCK_HOST}"
        return 1
    fi
    log_info "Lock file removed from ${LOCK_HOST}:${LOCK_FILE}"
    return 0
}

# ============================================================
# NFS-based signal functions (no SSH required)
# ============================================================
# Signal files live on the shared NFS directory visible to both servers.
# Each script uses its own NFS_PATH_* variable as the base directory.

# Mark export as started (removes any previous done/failed signals)
nfs_signal_start() {
    local _dir="$1"
    rm -f "${_dir}/${NFS_SIGNAL_DONE}" "${_dir}/${NFS_SIGNAL_FAILED}"
    echo "$(date +%Y%m%d) started pid=$$ at $(date +%H:%M:%S)" > "${_dir}/${NFS_SIGNAL_RUNNING}"
    chmod 644 "${_dir}/${NFS_SIGNAL_RUNNING}" 2>/dev/null
    log_info "NFS signal: export running (${_dir}/${NFS_SIGNAL_RUNNING})"
}

# Mark export as completed successfully, include manifest of exported tables
nfs_signal_done() {
    local _dir="$1"
    rm -f "${_dir}/${NFS_SIGNAL_RUNNING}"
    {
        echo "$(date +%Y%m%d) completed pid=$$ at $(date +%H:%M:%S)"
        echo "TABLES_EXPORTED:"
        ls -1 "${_dir}"/PREPAID_*.dmp 2>/dev/null | sed 's|.*/||' | sort
        echo "DUMP_COUNT=$(ls -1 "${_dir}"/PREPAID_*.dmp 2>/dev/null | wc -l | tr -d ' ')"
    } > "${_dir}/${NFS_SIGNAL_DONE}"
    chmod 644 "${_dir}/${NFS_SIGNAL_DONE}" 2>/dev/null
    log_info "NFS signal: export done (${_dir}/${NFS_SIGNAL_DONE})"
}

# Remove running signal on failure and write reason for early import abort
nfs_signal_fail() {
    local _dir="$1"
    local _reason="${2:-unknown failure}"
    rm -f "${_dir}/${NFS_SIGNAL_RUNNING}"
    {
        echo "$(date +%Y%m%d) failed pid=$$ at $(date +%H:%M:%S)"
        echo "REASON: ${_reason}"
    } > "${_dir}/${NFS_SIGNAL_FAILED}"
    chmod 644 "${_dir}/${NFS_SIGNAL_FAILED}" 2>/dev/null
    log_info "NFS signal: export failed — ${_reason}"
}

# Check if export failed today. Returns 0 if failed, 1 if not.
# Sets NFS_FAIL_REASON variable with the failure reason.
nfs_check_failed() {
    local _dir="$1"
    local _today="$2"  # YYYYMMDD
    if [ -f "${_dir}/${NFS_SIGNAL_FAILED}" ]; then
        if [ ! -r "${_dir}/${NFS_SIGNAL_FAILED}" ]; then
            log_error "NFS failed signal exists but is not readable: ${_dir}/${NFS_SIGNAL_FAILED}"
            return 1
        fi
        local _sig_date=$(awk 'NR==1{print $1; exit}' "${_dir}/${NFS_SIGNAL_FAILED}" 2>/dev/null)
        if [ "${_sig_date}" = "${_today}" ]; then
            NFS_FAIL_REASON=$(grep '^REASON:' "${_dir}/${NFS_SIGNAL_FAILED}" 2>/dev/null | sed 's/^REASON: //')
            return 0
        fi
    fi
    return 1
}

# Check if export completed today. Returns 0 if done, 1 if not.
nfs_check_done() {
    local _dir="$1"
    local _today="$2"  # YYYYMMDD
    if [ -f "${_dir}/${NFS_SIGNAL_DONE}" ]; then
        if [ ! -r "${_dir}/${NFS_SIGNAL_DONE}" ]; then
            log_error "NFS done signal exists but is not readable: ${_dir}/${NFS_SIGNAL_DONE}"
            return 1
        fi
        local _sig_date=$(awk 'NR==1{print $1; exit}' "${_dir}/${NFS_SIGNAL_DONE}" 2>/dev/null)
        if [ "${_sig_date}" = "${_today}" ]; then
            return 0
        fi
    fi
    return 1
}

# Check if export is currently running. Returns 0 if running, 1 if not.
nfs_check_running() {
    local _dir="$1"
    [ -f "${_dir}/${NFS_SIGNAL_RUNNING}" ]
}

# check_logs_for_errors() removed — was unused; inline egrep used instead

# Ensure directory exists
ensure_dir() {
    if [ ! -d "$1" ]; then
        mkdir -p "$1"
        if [ $? -ne 0 ]; then
            log_error "Failed to create directory: $1"
            return 1
        fi
    fi
    return 0
}

# Extract table short name from SCHEMA.TABLE format
table_short_name() {
    echo "$1" | sed 's/.*\.//'
}

# Extract schema name from SCHEMA.TABLE format
table_schema() {
    echo "$1" | sed 's/\..*//'
}

# Convert PREPAID.TABLE to REPORT.TABLE
to_report_table() {
    echo "$1" | sed 's/^PREPAID\./REPORT./'
}

# Get export parallelism for a table (uses EXP_PARALLEL_* from conf)
get_exp_parallel() {
    case "$1" in
        *TPS01_CARDS)                                                    echo "${EXP_PARALLEL_CARDS:-20}" ;;
        *TPS01_LOG_CARDS|*TPS01_LOG_USED_CARDS|*TPS31_CARD_BRICKS)      echo "${EXP_PARALLEL_LARGE:-8}" ;;
        *TPS30_CARD_BOXES)                                               echo "${EXP_PARALLEL_MEDIUM:-4}" ;;
        *)                                                               echo 1 ;;
    esac
}

# Get import parallelism for a table (uses IMP_PARALLEL_* from conf)
get_imp_parallel() {
    case "$1" in
        *TPS01_CARDS)                                                    echo "${IMP_PARALLEL_CARDS:-20}" ;;
        *TPS01_LOG_CARDS|*TPS01_LOG_USED_CARDS|*TPS31_CARD_BRICKS)      echo "${IMP_PARALLEL_LARGE:-8}" ;;
        *TPS30_CARD_BOXES)                                               echo "${IMP_PARALLEL_MEDIUM:-4}" ;;
        *)                                                               echo 1 ;;
    esac
}
