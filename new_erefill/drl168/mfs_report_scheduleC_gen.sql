-- MFS_REPORT Gather Stats - Schedule C Generator
-- Server: Drl168
-- PDB: MFS_REPORT (connected via ORACLE_PDB_SID)
-- Schema: APP_USER
-- Generates dynamic partition-based gather stats commands
-- Partitioned tables: MFS_EDR_DAILY

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

spool &script_dir./mfs_report_scheduleC_list

-- MFS_EDR_DAILY (APP_USER) - Day of year partitions (PDAY)
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> '''||table_owner||''', TABNAME => '''||table_name||''' , partname => '''
||PARTITION_NAME|| ''' ,granularity => ''PARTITION'' ,CASCADE => TRUE, DEGREE => 4);'
FROM DBA_TAB_PARTITIONS
WHERE TABLE_OWNER='APP_USER'
AND TABLE_NAME='MFS_EDR_DAILY'
AND partition_name IN ('PDAY'||(SELECT to_number(to_char(sysdate,'DDD')) FROM dual),'PDAY'||(SELECT to_number(to_char(sysdate-1,'DDD')) FROM dual));

spool off;

-- Restore settings for execution output
set echo on
set feedback on
set timing on

-- Execute the generated commands
@&script_dir./mfs_report_scheduleC_list.lst

exit SQL.SQLCODE;
