-- EREFILL Gather Stats - Monthly Generator (CORE_DATA + CORE_CONFIG)
-- PDB: EREFILL_CORE (connected via ORACLE_PDB_SID)
-- Schema: CORE_DATA (9 tables), CORE_CONFIG (7 tables)
-- Monthly GLOBAL stats - full table/index structure analysis
-- Runs on 15th of each month (separate from EVENT to reduce load)
-- Total: 16 tables

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

spool &script_dir./erefill_monthly_list_core

-- CORE_DATA tables (9) - granularity=>'GLOBAL'
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_ETOPUP_TRANSACTIONS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_ETOPUP_ACCOUNT_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_ETOPUP_HINT_ANSWER_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_ETOPUP_THRESHOLD_CHECK'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_ETOPUP_P2P_USER_DETAILS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_NICKNAME_MDN_MAPPING'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_P2PBLOCK_MSIDN_DETAILS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_P2PREQUESTED_PIN_DETAILS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_DATA'', TABNAME => ''MFS_ETOPUP_LOGIN_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

-- CORE_CONFIG tables (7) - granularity=>'GLOBAL'
SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_USER_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_ADDRESS_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_CONFIG_PARAMETERS'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_ERROR_CODES'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_LEVEL_ROLE_MENU_MAP'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_LEVEL_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

SELECT chr(10)||'EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> ''CORE_CONFIG'', TABNAME => ''MFS_ETOPUP_ROLE_MASTER'', granularity => ''GLOBAL'', CASCADE => TRUE, DEGREE => 8);'
FROM dual;

spool off;

-- Restore settings for execution output
set echo on
set feedback on
set timing on

-- Execute the generated commands
@&script_dir./erefill_monthly_list_core.lst

exit SQL.SQLCODE;
