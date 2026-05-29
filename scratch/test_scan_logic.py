
import os
import sys
from datetime import datetime

# Adjust path to find the agent scripts
sys.path.append('/Users/igorvasin/freelance-2026/ai-eggs/agent')

from daily_report import get_latest_scan, build_report_text

scan = get_latest_scan()
if scan:
    print(f"Latest scan found!")
    # Check if scan has a time
    print(f"Scan data keys: {scan.keys()}")
    if 'scan_time' in scan:
        print(f"Scan time in file: {scan['scan_time']}")
    
    report = build_report_text(scan)
    print("\n--- REPORT OUTPUT ---")
    print(report)
else:
    print("No scan found!")
