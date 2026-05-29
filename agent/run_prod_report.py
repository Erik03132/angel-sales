import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Force the production URL
prod_url = "https://incubird.bitrix24.ru/rest/41624/6qs4929lpgqrei9s/"
os.environ["BITRIX_WEBHOOK_URL"] = prod_url

import asyncio

import bitrix_scanner


async def main():
    print(f"Forcing BITRIX_URL = {prod_url}")
    # Run the scanner
    bitrix_scanner.BITRIX_URL = prod_url
    bitrix_scanner.run_scan()
    
    # Run daily report logic locally, overriding URL
    import daily_report
    daily_report.BITRIX_URL = prod_url
    
    # Disable AI and TG sends for this manual run
    def dummy_ai(prompt): return "\n".join(["AI отключен для ручного запуска."])
    daily_report._generate_ai_insight = dummy_ai
    
    def dummy_send(text): 
        print("\n\n==== ГОТОВЫЙ ОТЧЕТ ====\n")
        print(text)
        print("\n=======================\n")
    
    daily_report.send_telegram_message = dummy_send
    daily_report.send_owner_copy = dummy_send
    
    daily_report.run_daily_report()

if __name__ == "__main__":
    asyncio.run(main())
