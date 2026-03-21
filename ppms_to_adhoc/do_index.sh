#!/bin/bash
export PATH=/oracle/product/11.2.0.4/db_1/bin:/oracle/product/11.2.0.4/db_1/bin:/sbin:/usr/sbin:/usr/bin:/usr/ccs/bin:/usr/bin/X11:/usr/local:/bin:/oracle/admin/dba/sql
/oracle/impdp_ppms_to_adhoc_mail.sh "Index_creation_started" "Index creation started"
sqlplus / as sysdba @/oracle/admin/dba/sql/ramram2.sql &
sqlplus / as sysdba @/oracle/admin/dba/sql/ramram3.sql &
wait
/oracle/impdp_ppms_to_adhoc_mail.sh "Index_creation_finished" "Index creation finished"
