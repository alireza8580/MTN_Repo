#!/usr/bin/env python3
import subprocess
import time
import argparse

def get_failing_gtid(host):
    # Query the performance_schema to find the exact GTID that caused the SQL thread to stop
    query = "SELECT APPLYING_TRANSACTION FROM performance_schema.replication_applier_status_by_worker WHERE LAST_ERROR_NUMBER > 0 AND APPLYING_TRANSACTION IS NOT NULL AND APPLYING_TRANSACTION != '';"
    cmd = f"ssh {host} \"mysql --login-path=sqlp -N -B -e '{query}'\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0 and result.stdout.strip():
        # In case of multi-threaded replication, there might be multiple rows, we take the first one
        return result.stdout.strip().split('\n')[0]
    return None

def skip_gtid(host, gtid):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Skipping GTID {gtid} on {host}...")
    cmds = [
        "STOP REPLICA;",
        f"SET GTID_NEXT = '{gtid}';",
        "BEGIN;",
        "COMMIT;",
        "SET GTID_NEXT = 'AUTOMATIC';",
        "START REPLICA;"
    ]
    full_cmd = "".join(cmds)
    cmd = f"ssh {host} \"mysql --login-path=sqlp -e \\\"{full_cmd}\\\"\""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Failed to skip GTID on {host}: {result.stderr}")
    else:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Successfully skipped GTID {gtid} on {host}.")

def main():
    parser = argparse.ArgumentParser(description="Auto skip replication errors by injecting empty transactions for failing GTIDs.")
    parser.add_argument("hosts", nargs='+', help="Hosts to monitor (e.g. dr-prod-db2 dr-prod-db3)")
    parser.add_argument("--interval", type=int, default=1, help="Check interval in seconds")
    args = parser.parse_args()

    print(f"Monitoring hosts: {', '.join(args.hosts)} every {args.interval} seconds...")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            for host in args.hosts:
                gtid = get_failing_gtid(host)
                if gtid:
                    skip_gtid(host, gtid)
            
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    main()
