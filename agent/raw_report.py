# """
# Raw Report — отправка необработанного дневного отчёта в Telegram.
# Запускается скриптом raw_report.py (примерно в 20:01 MSK) после обычного daily_report.
# Он берёт последний скан CRM и формирует простой текстовый отчёт без AI‑аналитики.
# """

import os
import sys

from dotenv import load_dotenv

# Ensure we can import sibling modules (daily_report.py) from the same package
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Load environment variables (same as other agents)
load_dotenv(os.path.join(BASE_DIR, "..", "..", ".env"), override=True)

# Import helpers from daily_report
try:
    from daily_report import (
        build_report_text,
        get_latest_scan,
        send_telegram_message,
    )
except Exception as e:
    print(f"⚠️ Could not import helpers from daily_report: {e}")
    sys.exit(1)


def run_raw_report():
    """Generate and send a raw daily report without AI insights.
    The function:
    1. Retrieves the latest Bitrix24 scan.
    2. Builds a plain‑text report using the same formatter as the AI report.
    3. Sends the report to the main admin (Andrey) and a copy to the owner (Igor).
    """
    scan = get_latest_scan()
    if not scan:
        print("❌ No scan data available. aborting raw report.")
        return
    report_text = build_report_text(scan)
    # ⛔ Андрею — НИКАКИХ отчётов в TG! (решение от 12.05.2026)
    # send_telegram_message уже шлёт ТОЛЬКО Игорю
    if send_telegram_message(report_text):
        print("✅ Raw report sent to Igor.")
    else:
        print("⚠️ Failed to send raw report.")


if __name__ == "__main__":
    run_raw_report()
