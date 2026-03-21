#!/bin/bash
export PATH=/oracle/product/11.2.0.4/db_1/bin:/oracle/product/11.2.0.4/db_1/bin:/sbin:/usr/sbin:/usr/bin:/usr/ccs/bin:/usr/bin/X11:/usr/local:/bin:/oracle/admin/dba/sql
subject=$1
body=$2
mailx -s "${subject} at $(date +%Y%m%d)" isdcdba@mtnirancell.ir <<<$"${body}"
