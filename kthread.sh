#!/usr/bin/env bash

set -euo pipefail

SCRIPT_NAME=$(basename "$0")
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

TARGET_HOST=${TARGET_HOST:-"30.0.0.232"}
TARGET_PORT=${TARGET_PORT:-"3306"}
TARGET_DB=${TARGET_DB:-"archiver"}
MYSQL_USER=${MYSQL_USER:-"archaiver"}
MYSQL_PASSWORD=${MYSQL_PASSWORD:-""}
PARALLEL_SESSIONS=${PARALLEL_SESSIONS:-60}
INTERVAL_SECONDS=${INTERVAL_SECONDS:-5}
RUN_DURATION_SECONDS=${RUN_DURATION_SECONDS:-1800}
STATE_DIR=${STATE_DIR:-"/var/tmp/kthread"}
PID_FILE="${STATE_DIR}/kthread.pid"
LOG_FILE="${STATE_DIR}/kthread.log"
MYSQL_DEFAULTS_FILE="${STATE_DIR}/mysql-client.cnf"
SANITIZED_SQL_FILE="${STATE_DIR}/queries.sql"
WORKER_LOG_DIR="${STATE_DIR}/workers"

usage() {
    cat <<EOF
Usage: ${SCRIPT_NAME} {start|stop|status|run}

Environment overrides:
  TARGET_HOST        MySQL/ProxySQL target host (default: ${TARGET_HOST})
  TARGET_PORT        MySQL/ProxySQL target port (default: ${TARGET_PORT})
  TARGET_DB          Database name (default: ${TARGET_DB})
    MYSQL_USER         MySQL username (default: ${MYSQL_USER})
    MYSQL_PASSWORD     MySQL password (default: hidden)
  PARALLEL_SESSIONS  Parallel mysql sessions per cycle (default: ${PARALLEL_SESSIONS})
  INTERVAL_SECONDS   Delay between cycles in seconds (default: ${INTERVAL_SECONDS})
    RUN_DURATION_SECONDS  Total runtime limit in seconds (default: ${RUN_DURATION_SECONDS})
  STATE_DIR          Runtime state/log directory (default: ${STATE_DIR})

Examples:
  ${SCRIPT_NAME} start
  ${SCRIPT_NAME} status
  ${SCRIPT_NAME} stop
EOF
}

log() {
    printf '%s %s\n' "$(date '+%F %T')" "$*" >> "${LOG_FILE}"
}

ensure_runtime_dirs() {
    mkdir -p "${STATE_DIR}" "${WORKER_LOG_DIR}"
}

build_mysql_defaults() {
    if [[ -z "${MYSQL_USER}" || -z "${MYSQL_PASSWORD}" ]]; then
        echo "MYSQL_USER and MYSQL_PASSWORD must not be empty" >&2
        exit 1
    fi

    cat > "${MYSQL_DEFAULTS_FILE}" <<EOF
[client]
host=${TARGET_HOST}
port=${TARGET_PORT}
protocol=tcp
user=${MYSQL_USER}
password=${MYSQL_PASSWORD}
database=${TARGET_DB}
connect-timeout=5
EOF
    chmod 600 "${MYSQL_DEFAULTS_FILE}"
}

write_embedded_queries() {
    cat > "${SANITIZED_SQL_FILE}" <<'EOF'
SELECT MAX(guid) AS max_guid FROM (
    SELECT guid
    FROM message FORCE INDEX(idx_message_from_to_guid)
    WHERE topic_type = 1
      AND delete_status <> 1
      AND `from` = '2c7da0e8-752c-456f-9bba-6a94bbc536b8'
      AND `to` = 'ca041ac0-b41b-48a2-9b45-3cca7e8927f3'
    UNION ALL
    SELECT guid
    FROM message FORCE INDEX(idx_message_from_to_guid)
    WHERE topic_type = 1
      AND delete_status <> 1
      AND `from` = 'ca041ac0-b41b-48a2-9b45-3cca7e8927f3'
      AND `to` = '2c7da0e8-752c-456f-9bba-6a94bbc536b8'
) AS t;

SELECT *
FROM message FORCE INDEX(index_message_to_delete_status)
WHERE `to` = '86ec24b3-5279-46fa-9123-18c476779d1d'
  AND delete_status <> 1
ORDER BY guid DESC
LIMIT 1;
EOF
}

is_running() {
    [[ -f "${PID_FILE}" ]] || return 1

    local pid
    pid=$(cat "${PID_FILE}")
    [[ -n "${pid}" ]] || return 1

    kill -0 "${pid}" 2>/dev/null
}

run_cycle() {
    local cycle=$1
    local session
    local pids=()

    log "cycle=${cycle} launching ${PARALLEL_SESSIONS} sessions against ${TARGET_HOST}:${TARGET_PORT}/${TARGET_DB}"

    for ((session = 1; session <= PARALLEL_SESSIONS; session++)); do
        mysql --defaults-extra-file="${MYSQL_DEFAULTS_FILE}" --batch --raw --skip-column-names --force \
            < "${SANITIZED_SQL_FILE}" \
            >> "${WORKER_LOG_DIR}/worker_${session}.log" 2>&1 &
        pids+=("$!")
    done

    for pid in "${pids[@]}"; do
        wait "${pid}" || true
    done

    log "cycle=${cycle} completed"
}

daemon_loop() {
    local cycle=0
    local start_ts
    local now_ts
    local elapsed

    ensure_runtime_dirs
    build_mysql_defaults
    write_embedded_queries
    echo "$$" > "${PID_FILE}"
    start_ts=$(date +%s)

    trap 'rm -f "${PID_FILE}"' EXIT
    trap 'log "received stop signal"; exit 0' INT TERM

    log "started pid=$$ db=${TARGET_DB} user=${MYSQL_USER} sessions=${PARALLEL_SESSIONS} interval=${INTERVAL_SECONDS}s duration=${RUN_DURATION_SECONDS}s"

    while true; do
        now_ts=$(date +%s)
        elapsed=$((now_ts - start_ts))
        if (( elapsed >= RUN_DURATION_SECONDS )); then
            log "duration limit reached after ${elapsed}s, stopping"
            break
        fi

        cycle=$((cycle + 1))
        run_cycle "${cycle}"

        now_ts=$(date +%s)
        elapsed=$((now_ts - start_ts))
        if (( elapsed >= RUN_DURATION_SECONDS )); then
            log "duration limit reached after ${elapsed}s, stopping"
            break
        fi

        sleep "${INTERVAL_SECONDS}"
    done
}

start() {
    ensure_runtime_dirs

    if is_running; then
        echo "${SCRIPT_NAME} is already running with pid $(cat "${PID_FILE}")"
        exit 0
    fi

    nohup "$0" run >> "${LOG_FILE}" 2>&1 < /dev/null &
    disown || true

    sleep 1

    if is_running; then
        echo "started ${SCRIPT_NAME} with pid $(cat "${PID_FILE}")"
        echo "log: ${LOG_FILE}"
        exit 0
    fi

    echo "failed to start ${SCRIPT_NAME}, check ${LOG_FILE}" >&2
    exit 1
}

stop() {
    if ! is_running; then
        echo "${SCRIPT_NAME} is not running"
        rm -f "${PID_FILE}"
        exit 0
    fi

    local pid
    pid=$(cat "${PID_FILE}")
    kill "${pid}"

    local wait_count=0
    while kill -0 "${pid}" 2>/dev/null; do
        wait_count=$((wait_count + 1))
        if (( wait_count >= 10 )); then
            kill -9 "${pid}" 2>/dev/null || true
            break
        fi
        sleep 1
    done

    rm -f "${PID_FILE}"
    echo "stopped ${SCRIPT_NAME} pid=${pid}"
}

status() {
    if is_running; then
        echo "${SCRIPT_NAME} is running with pid $(cat "${PID_FILE}")"
        echo "log: ${LOG_FILE}"
        exit 0
    fi

    echo "${SCRIPT_NAME} is not running"
    exit 1
}

main() {
    local command=${1:-}

    case "${command}" in
        start)
            start
            ;;
        stop)
            stop
            ;;
        status)
            status
            ;;
        run)
            daemon_loop
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"