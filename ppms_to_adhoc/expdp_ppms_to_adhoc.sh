#!/bin/bash
export ORACLE_SID=ppms3p
export ORACLE_HOME=/oracle11/product/11.2.0.3/db_1
export PATH=/sbin:/usr/sbin:/usr/bin:/usr/ccs/bin:/usr/bin/X11:/usr/local
export PATH=$ORACLE_HOME/bin:$PATH
rem_space=$(df -h /net/dru112c/dba_data | awk '{print $4,$5}')
pid=$$
#ssh -q alireza.aghaja@t1u904 "ls /tmp/exp.lock"
ssh -q oracle@t1u904 "ls /tmp/exp.lock"
#ssh -q alireza.aghaja@t1u904 "chmod 777 /tmp/exp.lock"
[[ $? -eq 0 ]] && ( mailx -s "Expdp is already running" isdcdba@mtnirancell.ir <<<$'\n expdp wont run because exp.lock file already exists at t1u904 tmp directory please check if expdp is running \n' ) && exit 1
ssh -q oracle@t1u904 'touch /tmp/exp.lock'
#mailx -s "PPMS to ADHOC EXPDP has been started" isdcdba@mtnirancell.ir <<<$'expdp started'
mailx -s "PPMS to ADHOC EXPDP has been started" isdcdba@mtnirancell.ir <<EOF
expdp started

remaining space of /net/dru112c/dba_data:
$rem_space
EOF
/net/dru112c/dba_data/RAMIN/PPMS3P/ram_exp
egrep -i 'failed|error' /net/dru112c/dba_data/RAMIN/PPMS3P/exp_PREPAID*.log &> /dev/null
#test $? -eq 0 && ( mailx -s "PPMS to ADHOC EXPDP at $(date +%Y%m%d_%H) has been completed sucsessfully" isdcdba@mtnirancell.ir <<<$'\n EXPDP COMPLETED \n' && ssh alireza.aghaja@t1u904 'rm -rf /tmp/exp.lock' ) || ( mailx -s "PPMS to ADHOC EXP DP at $(date +%Y%m%d_%H) has been failed" isdcdba@mtnirancell.ir <<<$'\n EXPDP FAILED \n' && echo "failed expdp" > /oracle/failed_expdp_$(date +%Y%m%d).log )
if [[ ! $? -eq 0 ]]; then
mailx -s "PPMS to ADHOC EXPDP at $(date +%Y%m%d_%H) has been completed sucsessfully" isdcdba@mtnirancell.ir <<<$'\n EXPDP COMPLETED \n'
ssh -q oracle@t1u904 'rm  /tmp/exp.lock'
#ssh -q alireza.aghaja@t1u904 'rm  /tmp/exp.lock'
else
mailx -s "PPMS to ADHOC EXPDP at $(date +%Y%m%d_%H) has been faiilled" isdcdba@mtnirancell.ir <<<$'\n EXPDP FAIILLED \n'
ssh -q oracle@t1u904 'rm  /tmp/exp.lock'
#ssh -q alireza.aghaja@t1u904 'rm  /tmp/exp.lock'
echo "failed expdp" > /oracle/failed_expdp_$(date +%Y%m%d).log
fi

#to check above command
#test $? -eq 0 && echo true && mailx -s "PPMS to ADHOC EXPDP at $(date +%Y%m%d_%H) has been completed sucsessfully" alireza.aghaja@mtnirancell.ir <<<$'\n EXPDP COMPLETED \n' || mailx -s "PPMS to ADHOC EXPDP at $(date +%Y%m%d_%H) has been failed" alireza.aghaja@mtnirancell.ir <<<$'\n EXPDP FAILED \n' && echo "failed expdp" > /oracle/failed_expdp_$(date +%Y%m%d)_test
You have new mail in /var/mail/oracle
