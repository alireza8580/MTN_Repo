-- EREFILL Gather Stats - Schedule C Generator (CORE_DATA)
-- PDB: EREFILL_CORE (connected via ORACLE_PDB_SID)
-- Schema: CORE_DATA
-- Generates dynamic partition-based gather stats commands
-- Partitioned tables: MFS_ETOPUP_TRANSACTIONS

-- Script directory passed as parameter
define script_dir = &1

WHENEVER SQLERROR EXIT SQL.SQLCODE;
WHENEVER OSERROR EXIT FAILURE;

-- Settings for clean list file (no extra output)
set lin 300

set pages 0

set head off

set echo off

set feedback off
set timing off
set verify off
set trimspool on

spool &script_dir./erefill_scheduleC_list_core

-- MFS_ETOPUP_TRANSACTIONS (CORE_DATA) - Day of Year partitions
-- Uses DDD format for day of year (1-365/366) instead of DD (day of month 1-31)
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> '''||table_owner||''', TABNAME => '''||table_name||''' , partname => '''
||PARTITION_NAME|| ''' ,granularity => ''PARTITION'' ,CASCADE => TRUE, DEGREE => 4);'
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER='CORE_DATA'
AND TABLE_NAME='MFS_ETOPUP_TRANSACTIONS'
AND partition_name IN ('DAY'||(SELECT to_number(to_char(sysdate,'DDD')) FROM dual),'DAY'||(SELECT to_number(to_char(sysdate-1,'DDD')) FROM dual));

spool off;

-- Restore settings for execution output
set echo on
set feedback on
set timing on

-- Execute the generated commands
@&script_dir./erefill_scheduleC_list_core.lst

exit SQL.SQLCODE;
