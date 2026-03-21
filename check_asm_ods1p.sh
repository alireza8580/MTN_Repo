#!/usr/bin/bash

# =============================================================================
# check_asm_ods1p.sh - Query ARCHGRP free space on ods1p and email result
# =============================================================================

export ORACLE_SID=t2oid
export ORACLE_HOME=/oracle/product/19.13/db_1
export PATH=$ORACLE_HOME/bin:/usr/bin:/usr/sfw/bin

CONNECT_STRING="zabbix/L_52#ZaBb1xXf_4mon12@ods1p"
RECIPIENTS="isdcdba@mtnirancell.ir,alireza.aghaja@mtnirancell.ir,#ITSPerformanceCapacityMgmt@mtnirancell.ir"
RECIPIENTS="isdcdba@mtnirancell.ir,alireza.aghaja@mtnirancell.ir"
SUBJECT="ods1p archgrp query check and execution time"

QUERY="SELECT free_mb * 1024 * 1024 FROM v\$asm_diskgroup_stat WHERE name='ARCHGRP';"
QUERY="SELECT 1 from dual;"

# Execute query and capture timing
START_EPOCH=$(date +%s%N)

RAW_RESULT=$(sqlplus -S "${CONNECT_STRING}" <<EOF
set heading off feedback off pagesize 0 linesize 200 trimspool on
${QUERY}
exit
EOF
)
RC=$?
RESULT=$(echo "${RAW_RESULT}" | sed '/^$/d' | sed 's/^[[:space:]]*//')

END_EPOCH=$(date +%s%N)
ELAPSED_MS=$(( (END_EPOCH - START_EPOCH) / 1000000 ))
ELAPSED_SEC=$(awk "BEGIN {printf \"%.3f\", ${ELAPSED_MS}/1000}")

# Build email body
BODY="Host: $(hostname)
Date: $(date '+%Y-%m-%d %H:%M:%S')
Oracle SID: ${ORACLE_SID}
Connect: zabbix@ods1p

Query:
${QUERY}

Result:
${RESULT}

SQLPlus Exit Code: ${RC}
Total Execution Time: ${ELAPSED_SEC} seconds
"

echo "${BODY}" | /usr/bin/mailx -s "${SUBJECT}" "${RECIPIENTS}"
