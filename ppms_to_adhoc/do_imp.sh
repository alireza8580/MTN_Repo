#!/bin/bash
date_imp=$(date +%Y%m%d)
/oracle/impdp_ppms_to_adhoc_mail.sh "IMPDP_started" "IMPDP is going to get started"
/net/dru112c/dba_data/RAMIN/PPMS3P/ram_imp1a &
/net/dru112c/dba_data/RAMIN/PPMS3P/ram_imp2a &
wait
