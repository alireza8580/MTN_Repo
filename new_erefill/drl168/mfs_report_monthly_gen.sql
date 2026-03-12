-- MFS_REPORT Gather Stats - Monthly Generator
-- Server: Drl168
-- PDB: MFS_REPORT (connected via ORACLE_PDB_SID)
-- Schema: APP_USER
-- Monthly GLOBAL stats - full table/index structure analysis
-- Runs on 10th of each month

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

spool &script_dir./mfs_report_monthly_list

-- APP_USER tables - granularity=>'GLOBAL' for full structure stats
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''APP_USER'', TABNAME => ''MFS_EDR_DAILY'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''APP_USER'', TABNAME => ''MFS_RPT_FACT'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''APP_USER'', TABNAME => ''MFS_RPT_SERVICE_FACT'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''APP_USER'', TABNAME => ''MFS_RPT_RECON_FACT'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''APP_USER'', TABNAME => ''MFS_RPT_HOURLY_FACT'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

spool off;

-- Restore settings for execution output
set echo on
set feedback on
set timing on

-- Execute the generated commands
@&script_dir./mfs_report_monthly_list.lst

exit SQL.SQLCODE;
