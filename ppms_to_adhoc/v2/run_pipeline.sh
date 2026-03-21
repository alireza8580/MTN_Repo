#!/bin/bash
#
# run_pipeline.sh - Single-side PPMS to ADHOC pipeline
#
# Runs everything from the PPMS server (dru110a):
#   1. Export locally (expdp)
#   2. SSH to ADHOC (t1u904) and run import (impdp + DDL + indexes)
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
# Phase 1: Export (local on PPMS)
# ============================================================
log_info "Phase 1: Running export on ${PPMS_HOST}..."

${SCRIPT_DIR}/run_export.sh
export_rc=$?

if [ ${export_rc} -ne 0 ]; then
    log_error "Export failed (rc=${export_rc}). Pipeline aborted."
    send_mail "PPMS_PIPELINE_FAILED" "Pipeline aborted: export phase failed on ${PPMS_HOST}."
    exit 1
fi

log_info "Export completed successfully."

# ============================================================
# Phase 2: Import (remote on ADHOC via SSH)
# ============================================================
log_info "Phase 2: Running import on ${ADHOC_HOST} via SSH..."

ssh -q "${REMOTE_USER}@${ADHOC_HOST}" "${REMOTE_INSTALL_DIR}/run_import.sh --skip-wait"
import_rc=$?

if [ ${import_rc} -ne 0 ]; then
    log_error "Import failed on ${ADHOC_HOST} (rc=${import_rc})."
    send_mail "PPMS_PIPELINE_FAILED" "Pipeline failed: import phase failed on ${ADHOC_HOST}."
    exit 1
fi

log_info "Import completed successfully."

# ============================================================
# Done
# ============================================================
log_info "=========================================="
log_info "PPMS to ADHOC Full Pipeline Completed"
log_info "=========================================="

send_mail "PPMS_PIPELINE_COMPLETED" "Full pipeline finished successfully.

Export: ${PPMS_HOST}
Import: ${ADHOC_HOST}
Date: ${DATE_TAG}"

exit 0
