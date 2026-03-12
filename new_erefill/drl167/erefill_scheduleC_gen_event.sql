-- EREFILL Gather Stats - Schedule C Generator (EVENT_DATA)
-- PDB: EREFILL_EVENT (connected via ORACLE_PDB_SID)
-- Schema: EVENT_DATA
-- Generates dynamic partition-based gather stats commands
-- Partitioned tables: RETRY_TABLE, MFS_CC, MFS_ETOPUP_TRANSACTIONS, MFS_P2P_TRANSACTION_SUMMARY, MFS_ETOPUP_MERCHANT_IP_EVENTS

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

spool &script_dir./erefill_scheduleC_list_event

-- RETRY_TABLE (EVENT_DATA) - Daily partitions
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> '''||table_owner||''', TABNAME => '''||table_name||''' , partname => '''
||PARTITION_NAME|| ''' ,granularity => ''PARTITION'' ,CASCADE => TRUE, DEGREE => 4);'
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER='EVENT_DATA'
AND TABLE_NAME='RETRY_TABLE'
AND partition_name IN ('DAY'||(SELECT to_number(to_char(sysdate,'DD')) FROM dual),'DAY'||(SELECT to_number(to_char(sysdate-1,'DD')) FROM dual));

-- MFS_CC (EVENT_DATA) - Monthly partitions
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> '''||table_owner||''', TABNAME => '''||table_name||''' , partname => '''
||PARTITION_NAME|| ''' ,granularity => ''PARTITION'' ,CASCADE => TRUE, DEGREE => 4);'
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER='EVENT_DATA'
AND TABLE_NAME='MFS_CC'
AND partition_name IN ('MONTH'||(SELECT to_number(to_char(sysdate,'MM')) FROM dual),'MONTH'||(SELECT to_number(to_char(sysdate-30,'MM')) FROM dual));

-- MFS_P2P_TRANSACTION_SUMMARY (EVENT_DATA) - Jalali Monthly partitions
-- Uses NLS_CALENDAR=PERSIAN for Jalali month (e.g., Jan 2026 = Month 10 Dey/دی 1404)
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> '''||table_owner||''', TABNAME => '''||table_name||''' , partname => '''
||PARTITION_NAME|| ''' ,granularity => ''PARTITION'' ,CASCADE => TRUE, DEGREE => 4);'
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER='EVENT_DATA'
AND TABLE_NAME='MFS_P2P_TRANSACTION_SUMMARY'
AND partition_name IN ('MONTH'||(SELECT to_number(to_char(sysdate,'MM','nls_calendar=persian')) FROM dual),'MONTH'||(SELECT to_number(to_char(sysdate-30,'MM','nls_calendar=persian')) FROM dual));

-- MFS_ETOPUP_MERCHANT_IP_EVENTS (EVENT_DATA) - Monthly partitions
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> '''||table_owner||''', TABNAME => '''||table_name||''' , partname => '''
||PARTITION_NAME|| ''' ,granularity => ''PARTITION'' ,CASCADE => TRUE, DEGREE => 4);'
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER='EVENT_DATA'
AND TABLE_NAME='MFS_ETOPUP_MERCHANT_IP_EVENTS'
AND partition_name IN ('MONTH'||(SELECT to_number(to_char(sysdate,'MM')) FROM dual),'MONTH'||(SELECT to_number(to_char(sysdate-30,'MM')) FROM dual));

spool off;

-- Restore settings for execution output
set echo on
set feedback on
set timing on

-- Execute the generated commands
@&script_dir./erefill_scheduleC_list_event.lst

exit SQL.SQLCODE;
