#!/bin/bash
# =============================================================================
# backup_partition_dwbs_range.sh
#
# Backup daily partitions of dwbs CDR tables (pm_rated_cdrs, pm_tap_cdrs)
# for a given date range. Each partition is dumped to a separate gzipped file.
#
# Usage:
#   ./backup_partition_dwbs_range.sh -s YYYYMMDD -e YYYYMMDD [-p prefix] [-t table1,table2] [-c]
#
# Options:
#   -s  Start date (inclusive) in YYYYMMDD format
#   -e  End date   (inclusive) in YYYYMMDD format
#   -p  Filename prefix (default: empty). Prepended to dump/log filenames.
#   -t  Comma-separated table list (default: pm_rated_cdrs,pm_tap_cdrs)
#   -c  Compress output with gzip (produces .sql.gz instead of .sql)
#   -h  Show this help
#
# Examples:
#   ./backup_partition_dwbs_range.sh -s 20250101 -e 20250131
#   ./backup_partition_dwbs_range.sh -s 20251201 -e 20260201 -p rightel
#   ./backup_partition_dwbs_range.sh -s 20250301 -e 20250315 -t pm_tap_cdrs -c
#   ./backup_partition_dwbs_range.sh -s 20250601 -e 20250630 -p rightel -c
# =============================================================================

export PATH=/data/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin:/data/.local/bin:/data/bin:/usr/bin:/opt/mysql/meb-4.1/bin:/data/soft/mysqlsh8.0.30/bin
set -o pipefail

# --------------- defaults ---------------
LOGIN_PATH="sqlp6"
DATABASE="dwbs"
BASE_OUTPUT_DIR="/dbws_archive_nfs/daily_dump"
DEFAULT_TABLES=("pm_rated_cdrs" "pm_tap_cdrs")
COMPRESS=0
FILE_PREFIX=""
START_DATE=""
END_DATE=""

# --------------- functions ---------------
usage() {
    sed -n '2,/^# =====/p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 1
}

log() {
    local level="INFO"
    [[ -n $2 ]] && level="$2"
    local msg="$(date +%FT%T%:z) [${level}] $1"
    echo "${msg}" | tee -a "${LOGFILE}"
}

validate_date() {
    local d="$1" label="$2"
    if ! date -d "${d}" +%Y%m%d &>/dev/null; then
        echo "ERROR: Invalid ${label} date: ${d}. Use YYYYMMDD format." >&2
        exit 1
    fi
}

dump_partition() {
    local TABLE="$1"
    local CURRENT_DATE="$2"   # YYYYMMDD

    local PARTITION_NAME="P${CURRENT_DATE}"
    local DATE_FMT="${CURRENT_DATE:0:4}-${CURRENT_DATE:4:2}-${CURRENT_DATE:6:2}"
    local NEXT_DATE
    NEXT_DATE=$(date -d "${DATE_FMT} + 1 day" +%Y-%m-%d)

    local OUTPUT_DIR="${BASE_OUTPUT_DIR}/${TABLE}"
    mkdir -p "${OUTPUT_DIR}"

    local NAME_PREFIX=""
    [[ -n "${FILE_PREFIX}" ]] && NAME_PREFIX="${FILE_PREFIX}_"

    LOGFILE="${OUTPUT_DIR}/${NAME_PREFIX}${TABLE}_${CURRENT_DATE}.log"

    # Check if partition exists
    local PART_QUERY="SELECT COUNT(*) FROM information_schema.partitions WHERE table_schema='${DATABASE}' AND table_name='${TABLE}' AND partition_name='${PARTITION_NAME}';"
    local PARTITION_EXISTS
    PARTITION_EXISTS=$(mysql --login-path="${LOGIN_PATH}" -D "${DATABASE}" -NB -e "${PART_QUERY}" 2>>"${LOGFILE}")

    if [[ $? -ne 0 ]]; then
        log "Failed to query partition metadata for ${TABLE} / ${PARTITION_NAME}" "ERROR"
        return 1
    fi

    if [[ "${PARTITION_EXISTS}" -ne 1 ]]; then
        log "Partition ${PARTITION_NAME} does not exist in ${TABLE}. Skipping." "WARN"
        return 0
    fi

    # Determine output filename
    local FILENAME
    if [[ ${COMPRESS} -eq 1 ]]; then
        FILENAME="${OUTPUT_DIR}/${NAME_PREFIX}${TABLE}_${CURRENT_DATE}.sql.gz"
    else
        FILENAME="${OUTPUT_DIR}/${NAME_PREFIX}${TABLE}_${CURRENT_DATE}.sql"
    fi

    # Skip if already dumped
    if [[ -f "${FILENAME}" ]]; then
        local FSIZE
        FSIZE=$(stat -c%s "${FILENAME}" 2>/dev/null || echo 0)
        if [[ ${FSIZE} -gt 0 ]]; then
            log "File ${FILENAME} already exists (${FSIZE} bytes). Skipping." "WARN"
            return 0
        fi
    fi

    log "Dumping ${TABLE} partition ${PARTITION_NAME} (${DATE_FMT}) ..."

    local WHERE_CLAUSE="CALL_DATE >= '${DATE_FMT}' AND CALL_DATE < '${NEXT_DATE}'"
    local RC

    if [[ ${COMPRESS} -eq 1 ]]; then
        mysqldump --login-path="${LOGIN_PATH}" \
            --set-gtid-purged=off \
            --single-transaction \
            --skip-lock-tables \
            --no-create-info \
            --no-create-db \
            --skip-opt \
            --set-charset \
            --quick \
            --extended-insert \
            "${DATABASE}" "${TABLE}" \
            --where="${WHERE_CLAUSE}" 2>>"${LOGFILE}" | gzip > "${FILENAME}"
        RC=${PIPESTATUS[0]}
    else
        mysqldump --login-path="${LOGIN_PATH}" \
            --set-gtid-purged=off \
            --single-transaction \
            --skip-lock-tables \
            --no-create-info \
            --no-create-db \
            --skip-opt \
            --set-charset \
            --quick \
            --extended-insert \
            "${DATABASE}" "${TABLE}" \
            --where="${WHERE_CLAUSE}" > "${FILENAME}" 2>>"${LOGFILE}"
        RC=$?
    fi

    if [[ ${RC} -eq 0 ]]; then
        local FSIZE
        FSIZE=$(stat -c%s "${FILENAME}" 2>/dev/null || echo 0)
        log "Dump OK. File: ${FILENAME} (${FSIZE} bytes)"
    else
        log "Dump FAILED for ${TABLE} / ${PARTITION_NAME}!" "ERROR"
        rm -f "${FILENAME}"   # clean up partial dump
        return 1
    fi
}

# --------------- argument parsing ---------------
CUSTOM_TABLES=()

while getopts ":s:e:p:t:ch" opt; do
    case ${opt} in
        s) START_DATE="${OPTARG}" ;;
        e) END_DATE="${OPTARG}" ;;
        p) FILE_PREFIX="${OPTARG}" ;;
        t) IFS=',' read -ra CUSTOM_TABLES <<< "${OPTARG}" ;;
        c) COMPRESS=1 ;;
        h) usage ;;
        \?) echo "Invalid option: -${OPTARG}" >&2; usage ;;
        :)  echo "Option -${OPTARG} requires an argument." >&2; usage ;;
    esac
done

if [[ -z "${START_DATE}" || -z "${END_DATE}" ]]; then
    echo "ERROR: Both -s (start date) and -e (end date) are required." >&2
    usage
fi

validate_date "${START_DATE}" "start"
validate_date "${END_DATE}"   "end"

# Normalise to YYYYMMDD
START_DATE=$(date -d "${START_DATE}" +%Y%m%d)
END_DATE=$(date -d "${END_DATE}" +%Y%m%d)

if [[ "${START_DATE}" -gt "${END_DATE}" ]]; then
    echo "ERROR: Start date (${START_DATE}) is after end date (${END_DATE})." >&2
    exit 1
fi

# Determine table list
if [[ ${#CUSTOM_TABLES[@]} -gt 0 ]]; then
    TABLES=("${CUSTOM_TABLES[@]}")
else
    TABLES=("${DEFAULT_TABLES[@]}")
fi

# --------------- main loop ---------------
TOTAL_OK=0
TOTAL_FAIL=0
TOTAL_SKIP=0

CURRENT="${START_DATE}"
while [[ "${CURRENT}" -le "${END_DATE}" ]]; do
    for TABLE in "${TABLES[@]}"; do
        dump_partition "${TABLE}" "${CURRENT}"
        RC=$?
        if [[ ${RC} -eq 0 ]]; then
            ((TOTAL_OK++))
        else
            ((TOTAL_FAIL++))
        fi
    done
    # advance to next day
    CURRENT=$(date -d "${CURRENT:0:4}-${CURRENT:4:2}-${CURRENT:6:2} + 1 day" +%Y%m%d)
done

echo "========================================="
echo "Backup complete."
echo "  Prefix  : ${FILE_PREFIX:-(none)}"
echo "  Tables  : ${TABLES[*]}"
echo "  Range   : ${START_DATE} -> ${END_DATE}"
echo "  Success : ${TOTAL_OK}"
echo "  Failed  : ${TOTAL_FAIL}"
echo "========================================="

if [[ ${TOTAL_FAIL} -gt 0 ]]; then
    exit 1
fi

exit 0
