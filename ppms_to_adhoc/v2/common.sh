#!/bin/bash
#
# common.sh - Shared functions for PPMS to ADHOC pipeline
# Source this after ppms_to_adhoc.conf
#

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

# Check export/import logs for errors
# Usage: check_logs_for_errors "/path/to/logs" "prefix"
# Returns 0 if errors found, 1 if clean
check_logs_for_errors() {
    _log_dir="$1"
    _prefix="$2"
    egrep -il 'ORA-|failed|error' "${_log_dir}/${_prefix}"*.log 2>/dev/null
    return $?
}

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
