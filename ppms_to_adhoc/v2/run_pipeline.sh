#!/bin/bash
#
# run_pipeline.sh - Single-side PPMS to ADHOC pipeline
#
# Runs from the PPMS server (dru110a). Probes SSH to t1u904:
#   - SSH works:  export (with SSH lock) + SSH import  → full pipeline
#   - SSH fails:  export (NFS signals only, --no-lock) → defers import to t1u904 cron
#
# Usage: ./run_pipeline.sh
#

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
. "${SCRIPT_DIR}/ppms_to_adhoc.conf"
. "${SCRIPT_DIR}/common.sh"

DATE_TAG=$(date +%Y%m%d)
LOG_FILE="${LOG_DIR_PPMS}/pipeline_${DATE_TAG}.log"

ensure_dir "${LOG_DIR_PPMS}"

log_info "=========================================="
log_info "PPMS to ADHOC Full Pipeline Starting"
log_info "  PPMS: ${PPMS_HOST} (SID ${PPMS_SID})"
log_info "  ADHOC: ${ADHOC_HOST} (SID ${ADHOC_SID})"
log_info "=========================================="

# ============================================================
# Probe SSH connectivity to ADHOC server
# ============================================================
SSH_AVAILABLE=false
ssh -q -o ConnectTimeout=10 -o BatchMode=yes "${REMOTE_USER}@${ADHOC_HOST}" 'echo ok' >/dev/null 2>&1
if [ $? -eq 0 ]; then
    SSH_AVAILABLE=true
    log_info "SSH to ${ADHOC_HOST} — available. Running full pipeline."
else
    log_info "SSH to ${ADHOC_HOST} — unavailable. Export only; import deferred to ${ADHOC_HOST} cron."
fi

# ============================================================
# Phase 1: Export (local on PPMS)
# ============================================================
log_info "Phase 1: Running export on ${PPMS_HOST}..."

if [ "${SSH_AVAILABLE}" = "true" ]; then
    ${SCRIPT_DIR}/run_export.sh
else
    ${SCRIPT_DIR}/run_export.sh --no-lock
fi
export_rc=$?

if [ ${export_rc} -ne 0 ]; then
    log_error "Export failed (rc=${export_rc}). Pipeline aborted."
    send_mail "PPMS_PIPELINE_FAILED" "Pipeline aborted: export phase failed on ${PPMS_HOST}."
    exit 1
fi

log_info "Export completed successfully."

# ============================================================
# Phase 2: Import (remote on ADHOC via SSH, or deferred)
# ============================================================
if [ "${SSH_AVAILABLE}" = "true" ]; then
    log_info "Phase 2: Running import on ${ADHOC_HOST} via SSH..."
    ssh -q "${REMOTE_USER}@${ADHOC_HOST}" "${REMOTE_INSTALL_DIR}/run_import.sh --skip-wait"
    import_rc=$?

    if [ ${import_rc} -ne 0 ]; then
        log_error "Import failed on ${ADHOC_HOST} (rc=${import_rc})."
        send_mail "PPMS_PIPELINE_FAILED" "Pipeline failed: import phase failed on ${ADHOC_HOST}."
        exit 1
    fi

    log_info "Import completed successfully."
    log_info "=========================================="
    log_info "PPMS to ADHOC Full Pipeline Completed"
    log_info "=========================================="

    send_mail "PPMS_PIPELINE_COMPLETED" "Full pipeline finished successfully.

Export: ${PPMS_HOST}
Import: ${ADHOC_HOST}
Date: ${DATE_TAG}"
else
    log_info "Phase 2: SKIPPED — SSH unavailable."
    log_info "Import will be handled by cron on ${ADHOC_HOST} (polls NFS signal)."
    log_info "=========================================="
    log_info "PPMS Export Completed (import deferred)"
    log_info "=========================================="

    send_mail "PPMS_EXPORT_DONE_IMPORT_DEFERRED" "Export completed successfully on ${PPMS_HOST}.

SSH to ${ADHOC_HOST} is unavailable — import deferred to scheduled cron on ${ADHOC_HOST}.
NFS signal file created: ${NFS_PATH_PPMS}/${NFS_SIGNAL_DONE}
Date: ${DATE_TAG}"
fi

exit 0
