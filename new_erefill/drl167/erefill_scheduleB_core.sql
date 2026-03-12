-- EREFILL Gather Stats - Schedule B (CORE_DATA)
-- PDB: EREFILL_CORE (connected via ORACLE_PDB_SID)
-- Schema: CORE_DATA
-- Runs every 6 hours: 5,11,17,23


WHENEVER SQLERROR EXIT SQL.SQLCODE;
WHENEVER OSERROR EXIT FAILURE;

set time on

set timing on

set echo on
set termout on
set serveroutput on

-- ============================================
-- EREFILL_CORE PDB - CORE_DATA Schema
-- ============================================
PROMPT
PROMPT EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> 'CORE_DATA', TABNAME => 'MFS_ETOPUP_THRESHOLD_CHECK', CASCADE => TRUE, DEGREE => 4);
EXEC DBMS_STATS.GATHER_TABLE_STATS(OWNNAME=> 'CORE_DATA', TABNAME => 'MFS_ETOPUP_THRESHOLD_CHECK', CASCADE => TRUE, DEGREE => 4);
exit SQL.SQLCODE;
