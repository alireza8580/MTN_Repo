#!/bin/bash
#
# is_jalali_first.sh - Check if today is the 1st of a Jalali month
#
# Returns 0 (true) if today is the 1st of a Jalali month, 1 otherwise.
# Pure bash, no external dependencies. Works on Solaris 10 bash.
#
# Algorithm: FarsiWeb jalali.c (Roozbeh Pournader, Mohammad Toossi)
# Reference: http://www.farsiweb.info/jalali/jalali.c
#
# Usage:
#   ./is_jalali_first.sh          # exit code 0 = yes, 1 = no
#   ./is_jalali_first.sh 20260321 # check specific date (YYYYMMDD)
#
# For crontab:
#   0 1 * * * /oracle/ppms_to_adhoc/is_jalali_first.sh && /oracle/ppms_to_adhoc/run_export.sh
#

gregorian_to_jalali_day() {
    local gyear=$1 gmonth=$2 gday=$3

    # Days in each Gregorian month
    local g_d_m=(31 28 31 30 31 30 31 31 30 31 30 31)
    # Days in each Jalali month
    local j_d_m=(31 31 31 31 31 31 30 30 30 30 30 29)

    local gy=$(( gyear - 1600 ))
    local gm=$(( gmonth - 1 ))

    # Calculate day number from Gregorian epoch (1600-03-20)
    local j_day_no=$(( 365 * gy + (gy + 3) / 4 - (gy + 99) / 100 + (gy + 399) / 400 + gday - 1 - 79 ))

    # Add days for completed Gregorian months
    local i
    for (( i = 0; i < gm; i++ )); do
        j_day_no=$(( j_day_no + g_d_m[i] ))
    done

    # Gregorian leap year adjustment (after February)
    if (( gm > 1 )); then
        if (( (gy % 4 == 0 && gy % 100 != 0) || gy % 400 == 0 )); then
            j_day_no=$(( j_day_no + 1 ))
        fi
    fi

    # Convert to Jalali
    local j_np=$(( j_day_no / 12053 ))
    j_day_no=$(( j_day_no % 12053 ))

    local jy=$(( 979 + 33 * j_np + 4 * (j_day_no / 1461) ))
    j_day_no=$(( j_day_no % 1461 ))

    if (( j_day_no >= 366 )); then
        j_day_no=$(( j_day_no - 1 ))
        jy=$(( jy + j_day_no / 365 ))
        j_day_no=$(( j_day_no % 365 ))
    fi

    # Find Jalali month and day
    for (( i = 0; i < 11; i++ )); do
        if (( j_day_no < j_d_m[i] )); then
            break
        fi
        j_day_no=$(( j_day_no - j_d_m[i] ))
    done

    local jmonth=$(( i + 1 ))
    local jday=$(( j_day_no + 1 ))

    echo "$jday"
}

# Main
if [[ -n "$1" ]]; then
    check_date="$1"
    g_y="${check_date:0:4}"
    g_m="${check_date:4:2}"
    g_d="${check_date:6:2}"
    # Strip leading zeros for arithmetic
    g_y=$((10#$g_y))
    g_m=$((10#$g_m))
    g_d=$((10#$g_d))
else
    g_y=$(date +%Y)
    g_m=$((10#$(date +%m)))
    g_d=$((10#$(date +%d)))
fi

jalali_day=$(gregorian_to_jalali_day "$g_y" "$g_m" "$g_d")

if [[ "$jalali_day" -eq 1 ]]; then
    echo "Today is the 1st of a Jalali month (Gregorian: ${g_y}-${g_m}-${g_d})"
    exit 0
else
    echo "Jalali day: ${jalali_day} (not 1st)"
    exit 1
fi
