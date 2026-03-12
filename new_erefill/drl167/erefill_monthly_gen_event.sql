-- EREFILL Gather Stats - Monthly Generator (EVENT_DATA)
-- PDB: EREFILL_EVENT (connected via ORACLE_PDB_SID)
-- Schema: EVENT_DATA
-- Monthly GLOBAL stats - full table/index structure analysis
-- Runs on 10th of each month
-- Total: 12 tables

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

spool &script_dir./erefill_monthly_list_event

-- EVENT_DATA tables (12) - granularity=>'GLOBAL'
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''RETRY_TABLE'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_CC'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_P2P_TRANSACTION_SUMMARY'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_CDR_01'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_CDR_02'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_EDR_01'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_EDR_02'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_ETOPUP_MERCHANT_IP_EVENTS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_ETOPUP_AUDIT_LOGS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_ETOPUP_PSWD_HISTORY'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_P2P_TRANSACTION_01'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''EVENT_DATA'', TABNAME => ''MFS_P2P_TRANSACTION_02'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

spool off;

-- Restore settings for execution output
set echo on
set feedback on
set timing on

-- Execute the generated commands
@&script_dir./erefill_monthly_list_event.lst

exit SQL.SQLCODE;
