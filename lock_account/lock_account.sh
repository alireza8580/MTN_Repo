#!/bin/bash

# Bash best practices
set -euo pipefail
IFS=$'\n\t'

# ======================
# CONFIGURATION
# ======================
readonly ORACLE_HOME="/oracle/product/19.13/db_1"
readonly SCRIPT_HOME="/oracle/alireza/script/lock_account_dir"
readonly LOG_DIR="$SCRIPT_HOME/logs"
readonly ERROR_FILE="$LOG_DIR/errors"
readonly LIST_HOME="/oracle/alireza/script/dblist"
readonly PROD_LIST="$LIST_HOME/PRODUCTIONLIST"
readonly UAT_LIST="$LIST_HOME/UATLIST"
readonly IAT_LIST="$LIST_HOME/IATLIST"
readonly USERNAME="monitoruser"
readonly PASSWORD="${ORACLE_PASSWORD:-}"
readonly TIMEOUT="2"

# Export Oracle environment variables
export ORACLE_HOME
export PATH="$ORACLE_HOME/bin:$PATH"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ======================
# FUNCTIONS
# ======================

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Generate logfile name with timestamp and username
current_time=$(date +"%Y-%m-%d_%H-%M-%S")
ldap_username="$1"
oracle_username=$(echo "$ldap_username" | tr '[:lower:]' '[:upper:]' | tr '.' '_')
logfile="$LOG_DIR/${current_time}_${oracle_username}.log"

# Start logging (tee will output to both screen and file)
exec > >(tee -i "$logfile")
exec 2>&1

# Log initial header
echo "=================================================================="
echo "Script started at: $(date)"
echo "User being checked: $oracle_username"
echo "=================================================================="

function usage() {
    echo "Usage: $0 <username>"
    echo "Example: $0 alireza.aghaja"
    exit 1
}

function get_db_list() {
    local env="$1"
    case "$env" in
        1) echo "$PROD_LIST" ;;
        2) echo "$UAT_LIST" ;;
        3) echo "$IAT_LIST" ;;
        *) echo "Invalid environment selected." ; exit 2 ;;
    esac
}

function check_service() {
    local servicename="$1"

    if timeout ${TIMEOUT} tnsping "$servicename" &>/dev/null; then
        return 0
    else
        echo -e "${YELLOW}⚠️  $servicename - Network/Access issue (timeout or error)${NC}" >> "$ERROR_FILE"
        return 1
    fi
}

function query_user_status() {
    local servicename="$1"
    local username="$2"

    $ORACLE_HOME/bin/sqlplus -S "${USERNAME}/${PASSWORD}@${servicename}" <<EOF
SET PAGESIZE 0 FEEDBACK OFF VERIFY OFF HEADING OFF ECHO OFF
SELECT USERNAME || '|' || ACCOUNT_STATUS || '|' || PROFILE FROM DBA_USERS WHERE USERNAME = '${username}';
EXIT;
EOF
}

function lock_user() {
    local servicename="$1"
    local username="$2"

    echo "Locking user $username on $servicename..."
    $ORACLE_HOME/bin/sqlplus -S "${USERNAME}/${PASSWORD}@${servicename}" <<EOF
ALTER USER ${username} ACCOUNT LOCK profile invalid_prof;
EXIT;
EOF
}

function process_service() {
    local servicename="$1"
    local oracle_username="$2"

    if check_service "$servicename"; then
        local result
        result=$(query_user_status "$servicename" "$oracle_username" | tr -d ' ' || true)

        # Handle SQL errors
        if echo "$result" | grep -qE "ORA-|SP2-"; then
            echo -e "${YELLOW}⚠️  $servicename - SQL Error occurred.${NC}" >> "$ERROR_FILE"
            return
        fi

        if [ -n "$result" ]; then
            echo "======================================================================================================================"
            echo "                                            Start of result for $servicename                                           "
            echo "**********-------------------------------------------------------------------------------------------------***********"

            local username_db
            local account_status
            local profile
            username_db=$(echo "$result" | cut -d'|' -f1)
            account_status=$(echo "$result" | cut -d'|' -f2)
            profile=$(echo "$result" | cut -d'|' -f3)

            echo "User: $username_db"
            echo "Status: $account_status"
            echo "Profile: $profile"

            if [[ "$account_status" == *"LOCKED"* ]]; then
                echo -e "${GREEN}=> Already locked: NO ACTION NEEDED${NC}"
            else
                echo -e "${RED}=> NOT locked: NEED TO LOCK!${NC}"
                # ➡️ NEW: Add service needing locking to list
                services_to_lock+=("$servicename")
            fi

            echo "**********-------------------------------------------------------------------------------------------------***********"
            echo "                                            End of result for $servicename                                           "
            echo "======================================================================================================================"
            echo ""
        fi
    else
        echo -e "${RED}❗ $servicename - Connection issue${NC}" >> "$ERROR_FILE"
    fi
}

# ======================
# MAIN
# ======================

# ➡️ NEW: Temporary array to track databases needing locking
declare -a services_to_lock=()

# Clear error file
> "$ERROR_FILE"
clear

if [ $# -ne 1 ]; then
    usage
fi

if [[ -z "${PASSWORD}" ]]; then
    echo "ORACLE_PASSWORD must be set in the environment" >&2
    exit 4
fi

ldap_username="$1"
oracle_username=$(echo "$ldap_username" | tr '[:lower:]' '[:upper:]' | tr '.' '_')

echo "Checking user: $oracle_username"
echo ""

echo "Please select environment number:"
echo "1) PRODUCTION ENV"
echo "2) UAT ENV"
echo "3) IAT ENV"
read -r env

db_list_file=$(get_db_list "$env")

if [ ! -f "$db_list_file" ]; then
    echo "Database list file not found: $db_list_file"
    exit 3
fi

while IFS= read -r servicename || [ -n "$servicename" ]; do
    # Clean spaces
    servicename="${servicename// /}"

    # Skip empty lines and commented lines
    if [[ -z "$servicename" || "$servicename" == \#* ]]; then
        continue
    fi

    # Process valid service
    process_service "$servicename" "$oracle_username"
done < "$db_list_file"

# ➡️ NEW: BULK LOCKING PROMPT AFTER SCANNING
if [ "${#services_to_lock[@]}" -gt 0 ]; then
    echo ""
    echo -e "${RED}\e[1m======================================================================================================================"
    echo -e "User '${oracle_username}' is NOT locked in the following databases:"
    printf '%s\n' "${services_to_lock[@]}"
    echo -e "======================================================================================================================${NC}"
    read -rp "🔒 Do you want to lock user '${oracle_username}' in ALL these databases? (yes/no): " bulk_answer
    if [[ "$bulk_answer" == "yes" ]]; then
        for svc in "${services_to_lock[@]}"; do
            lock_user "$svc" "$oracle_username"
            echo -e "${GREEN}✅ User $oracle_username locked successfully in $svc.${NC}"
        done
    else
        echo "❌ Skipped locking in all databases."
    fi
fi

echo "======================================================================================================================"
echo "                    Services with connection problems:"
echo "======================================================================================================================"
if [ -s "$ERROR_FILE" ]; then
    cat "$ERROR_FILE"
else
    echo "None 🎉"
fi
echo "======================================================================================================================"
