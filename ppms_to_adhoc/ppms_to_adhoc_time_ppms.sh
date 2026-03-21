#!/bin/bash
export ORACLE_SID=ppms3p
export ORACLE_HOME=/oracle11/product/11.2.0.3/db_1
PATH=/oracle11/product/11.2.0.3/db_1/bin:/oracle11/product/11.2.0.3/db_1/bin:/sbin:/usr/sbin:/usr/bin:/usr/ccs/bin:/usr/bin/X11:/usr/local
export PATH=$ORACLE_HOME/bin:$PATH
export LD_LIBRARY_PATH=$ORACLE_HOME/lib:/lib
{ while (($(date +%Y%m%d%H%M%S)<$(sqlplus -S / as sysdba @/oracle/admin/dba/sql/ppms_to_adhoc_time.sql))); do sleep 30 ; done ;} && { nohup /oracle/expdp_ppms_to_adhoc.sh ;}
