#!/bin/bash
export ORACLE_SID=adhoc1p
export ORACLE_HOME=/oracle/product/11.2.0.4/db_1
export PATH=$ORACLE_HOME/bin:$PATH
LOG_FILE=/oracle/impdp_ppms_to_adhoc_dir/impdp_ppms_to_adhoc_$(date +%Y%m%d).log
start_hour="0700"
while [[ -f /tmp/exp.lock ]]
#&& (($(date +%H%M)>$start_hour))
do
sleep 180
done
cnt_dumps=$(find /net/dru112c/dba_data/RAMIN/PPMS3P -name "PREPAID_*.dmp" -mtime -3 | wc -l )
[[ ${cnt_dumps} -lt 58 ]] && { /oracle/impdp_ppms_to_adhoc_mail.sh "IMPDP_Failleed" "IMPDP job Failed. dump file count should be 58 which is ${cnt_dumps}" && exit 1; }
echo "Started impdp at $(date +%Y/%m/%d_%H:%M:%S)" >>${LOG_FILE}
#sqlplus -S / as sysdba @/oracle/test_al.sql >>${LOG_FILE}
#impdp email in sql file
sqlplus -S / as sysdba @/oracle/admin/dba/sql/ramram1.sql >>${LOG_FILE}
egrep -i 'failed|error' /net/dru112c/dba_data/RAMIN/PPMS3P/imp_PREPAID*.log &> /dev/null
exit_status=$?
[[ ! ${exit_status} -eq 0 ]] && ( mailx -s "PPMS to ADHOC IMPDP at $(date +%Y%m%d_%H) has been completed sucsessfully" alireza.aghaja@mtnirancell.ir <<<$'\n IMPDP COMPLETED \n' && echo "Finished IMPDP at $(date +%Y/%m/%d_%H:%M:%S)" >>${LOG_FILE} ) || ( mailx -s "PPMS to ADHOC IMPDP at $(date +%Y%m%d_%H) has been failleed" isdcdba@mtnirancell.ir <<<$'\n IMPDP FAILED \n' && echo "FAILED IMPDP at $(date +%Y/%m/%d_%H:%M:%S)" >> ${LOG_FILE} )
#[[ ! ${exit_status} -eq 0 ]] && rm -rf /net/dru112c/dba_data/RAMIN/PPMS3P/PREPAID_*.dmp && mkdir /net/dru112c/dba_data/RAMIN/PPMS3P/adhoc_to_ppms_$(date +%Y%m%d_%H%M)_logs && mv /net/dru112c/dba_data/RAMIN/PPMS3P/*PREPAID*.log $_
echo "" >>${LOG_FILE}
