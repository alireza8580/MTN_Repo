#!/bin/bash
#
# run_import.sh - ADHOC Data Pump Import
#
# Runs on the ADHOC server. Waits for export lock to clear, validates dumps,
# drops/creates tables, imports data, cleans PII, creates indexes, sets grants.
#
# Usage: ./run_import.sh
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
# Wait for export lock to be released (skip if --skip-wait)
# ============================================================
if [ "$1" = "--skip-wait" ]; then
    log_info "Lock wait skipped (--skip-wait flag, called from pipeline)."
else
    log_info "Waiting for export to complete (checking lock file)..."

    while check_lock; do
        log_info "Lock file still exists, waiting 3 minutes..."
        sleep 180
    done

    log_info "Lock file cleared. Export appears complete."
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

sqlplus -S / as sysdba <<'EOSQL' >> "${LOG_FILE}" 2>&1
SET ECHO OFF
SET FEEDBACK OFF
SET PAGESIZE 0

-- Drop existing tables
DECLARE
  TYPE t_tables IS TABLE OF VARCHAR2(50);
  v_tables t_tables := t_tables(
    'REPORT.TPS01_CARDS',
    'REPORT.TPS01_LOG_CARDS',
    'REPORT.TPS01_USED_CARDS',
    'REPORT.TPS08_DENOMINATION_TYPES',
    'REPORT.TPS107_DISTRIBUTOR_DETAILS',
    'REPORT.TPS11_OUTLET_CODES',
    'REPORT.TPS30_CARD_BOXES',
    'REPORT.TPS31_CARD_BRICKS',
    'REPORT.TPS73_LOGICAL_ORDERS',
    'REPORT.TPS6073_LOGICAL_ORDERS',
    'REPORT.TPS01_LOG_USED_CARDS',
    'REPORT.TPS09_PPAS_LOG_CARD_PARAMETERS',
    'REPORT.TPS09_PPAS_CARD_PARAMETERS',
    'REPORT.TPS145_STOCK_ORDERS',
    'REPORT.TPS74_LOGICAL_ORDERS_DETAIL'
  );
BEGIN
  FOR i IN 1..v_tables.COUNT LOOP
    BEGIN
      EXECUTE IMMEDIATE 'DROP TABLE ' || v_tables(i) || ' CASCADE CONSTRAINTS';
      DBMS_OUTPUT.PUT_LINE('Dropped: ' || v_tables(i));
    EXCEPTION
      WHEN OTHERS THEN
        IF SQLCODE = -942 THEN
          DBMS_OUTPUT.PUT_LINE('Table not found (OK): ' || v_tables(i));
        ELSE
          RAISE;
        END IF;
    END;
  END LOOP;
END;
/
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

# Set all tables to NOLOGGING for faster import
sqlplus -S / as sysdba <<'EOSQL' >> "${LOG_FILE}" 2>&1
ALTER TABLE REPORT.TPS01_CARDS NOLOGGING;
ALTER TABLE REPORT.TPS01_LOG_CARDS NOLOGGING;
ALTER TABLE REPORT.TPS01_USED_CARDS NOLOGGING;
ALTER TABLE REPORT.TPS08_DENOMINATION_TYPES NOLOGGING;
ALTER TABLE REPORT.TPS107_DISTRIBUTOR_DETAILS NOLOGGING;
ALTER TABLE REPORT.TPS11_OUTLET_CODES NOLOGGING;
ALTER TABLE REPORT.TPS30_CARD_BOXES NOLOGGING;
ALTER TABLE REPORT.TPS31_CARD_BRICKS NOLOGGING;
ALTER TABLE REPORT.TPS73_LOGICAL_ORDERS NOLOGGING;
ALTER TABLE REPORT.TPS6073_LOGICAL_ORDERS NOLOGGING;
ALTER TABLE REPORT.TPS01_LOG_USED_CARDS NOLOGGING;
ALTER TABLE REPORT.TPS09_PPAS_LOG_CARD_PARAMETERS NOLOGGING;
ALTER TABLE REPORT.TPS09_PPAS_CARD_PARAMETERS NOLOGGING;
ALTER TABLE REPORT.TPS145_STOCK_ORDERS NOLOGGING;
ALTER TABLE REPORT.TPS74_LOGICAL_ORDERS_DETAIL NOLOGGING;
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

# Stream 1: Heavy tables (background)
(
    do_import "PREPAID.TPS01_CARDS" ${IMP_PARALLEL_CARDS}
    do_import "PREPAID.TPS01_LOG_CARDS" ${IMP_PARALLEL_LARGE}
) &
pid_heavy=$!

# Stream 2: Light tables (background)
(
    do_import "PREPAID.TPS107_DISTRIBUTOR_DETAILS" 1
    do_import "PREPAID.TPS73_LOGICAL_ORDERS" 1
    do_import "PREPAID.TPS11_OUTLET_CODES" 1
    do_import "PREPAID.TPS30_CARD_BOXES" ${IMP_PARALLEL_MEDIUM}
    do_import "PREPAID.TPS31_CARD_BRICKS" ${IMP_PARALLEL_LARGE}
    do_import "PREPAID.TPS08_DENOMINATION_TYPES" 1
    do_import "PREPAID.TPS6073_LOGICAL_ORDERS" 1
    do_import "PREPAID.TPS01_LOG_USED_CARDS" ${IMP_PARALLEL_LARGE}
    do_import "PREPAID.TPS09_PPAS_LOG_CARD_PARAMETERS" 1
    do_import "PREPAID.TPS09_PPAS_CARD_PARAMETERS" 1
    do_import "PREPAID.TPS145_STOCK_ORDERS" 1
    do_import "PREPAID.TPS74_LOGICAL_ORDERS_DETAIL" 1
    # This one uses TABLE_EXISTS_ACTION=REPLACE
    cd "${NFS_PATH_ADHOC}"
    ${ORACLE_HOME}/bin/impdp \'/ as sysdba\' \
        directory=${ORA_DIR_IMPORT} \
        DUMPFILE=PREPAID_TPS6074_LOGICAL_ORDERS_DETAIL.dmp \
        TABLES=PREPAID.TPS6074_LOGICAL_ORDERS_DETAIL \
        logfile=imp_PREPAID_TPS6074_LOGICAL_ORDERS_DETAIL_${DATE_TAG}.log \
        REMAP_SCHEMA=PREPAID:REPORT \
        TABLE_EXISTS_ACTION=REPLACE \
        EXCLUDE=GRANT
) &
pid_light=$!

# Wait for both streams
wait ${pid_heavy}
rc_heavy=$?
wait ${pid_light}
rc_light=$?

if [ ${rc_heavy} -ne 0 ] || [ ${rc_light} -ne 0 ]; then
    log_error "Some imports failed (heavy=${rc_heavy}, light=${rc_light})"
fi

log_info "Phase 2 complete: Data import finished"

# ============================================================
# Phase 3: PII cleanup
# ============================================================
log_info "Phase 3: Removing PII columns..."

sqlplus -S / as sysdba <<'EOSQL' >> "${LOG_FILE}" 2>&1
ALTER TABLE REPORT.TPS01_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
ALTER TABLE REPORT.TPS01_LOG_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
ALTER TABLE REPORT.TPS01_LOG_USED_CARDS SET UNUSED (CPS01_PIN_NUMBER, CPS01_ACCESS_CODE);
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
    send_mail "PPMS_IMPORT_FAILED" "Import completed with errors.

Failed log files:
${error_logs}

Check logs at: ${NFS_PATH_ADHOC}/imp_PREPAID*.log"
    echo "FAILED IMPORT at $(date +%Y/%m/%d_%H:%M:%S)" >> "${LOG_FILE}"
    exit 1
else
    log_info "Import pipeline completed successfully"
    send_mail_to "${MAIL_ALIREZA}" "PPMS_IMPORT_COMPLETED" "Import pipeline completed successfully."
    send_mail "PPMS_IMPORT_COMPLETED" "Full pipeline completed successfully."
    echo "Finished IMPORT at $(date +%Y/%m/%d_%H:%M:%S)" >> "${LOG_FILE}"
fi

log_info "=== PPMS to ADHOC Import Finished ==="
exit 0
