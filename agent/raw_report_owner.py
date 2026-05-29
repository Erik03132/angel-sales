# """
# Raw Report — отправка необработанного дневного отчёта только владельцу (Игорю).
# Запускается скриптом raw_report_owner.py (например, вручную в 20:01 MSK).
# """

import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Load environment variables (same as other agents)
load_dotenv(os.path.join(BASE_DIR, "..", "..", ".env"), override=True)

# Import helpers from daily_report
try:
    from daily_report import build_report_text, get_latest_scan, send_owner_copy
except Exception as e:
    print(f"⚠️ Could not import helpers from daily_report: {e}")
    sys.exit(1)


def run_raw_report_owner_only():
    """Generate and send a raw daily report ONLY to the owner (Igor)."""
    scan = get_latest_scan()
    if not scan:
        print("❌ No scan data available. aborting raw report.")
        return
    report_text = build_report_text(scan)
    if send_owner_copy(report_text):
        print("✅ Raw report sent ONLY to owner (Igor).")
    else:
        print("⚠️ Failed to send raw report to owner.")


if __name__ == "__main__":
    run_raw_report_owner_only()
