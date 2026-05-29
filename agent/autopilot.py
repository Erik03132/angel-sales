"""
Автопилот Анжелочки v3.1 — Только утренний пинг.
═══════════════════════════════════════════════════
Расписание (MSK):
  09:00 — Утренний чек (пинг владельцу)
═══════════════════════════════════════════════════
"""
import os
import time
from datetime import datetime

import requests
import schedule
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'), override=True)

BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY")
OWNER_ID = 176203333  # Игорь

def send_to_owner(text, parse_mode="HTML"):
    """Отправить сообщение владельцу (Игорь)."""
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN не задан, пропускаю отправку")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        p = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": p, "http": p}
    
    try:
        requests.post(url, json={
            "chat_id": OWNER_ID, 
            "text": text, 
            "parse_mode": parse_mode
        }, proxies=proxies, timeout=15)
    except Exception as e:
        print(f"⚠️ TG send error ({OWNER_ID}): {e}")

def morning_job(is_startup=False):
    """Утренний пинг — система жива."""
    status = "запущена" if is_startup else "по расписанию"
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"🌅 Утренний чек ({status}) — {now}")
    
    msg = f"🐣 {'Система запущена!' if is_startup else 'Доброе утро, команда!'}\n"
    msg += f"📅 {now}\n"
    msg += "✅ Автопилот v3.1 работает. Только утренний пинг."
    send_to_owner(msg)



# ═══════════════════════════════════════════════
# РАСПИСАНИЕ (время сервера = MSK)
# ═══════════════════════════════════════════════
schedule.every().day.at("09:00").do(morning_job)

if __name__ == "__main__":
    print("═" * 50)
    print("🚀 АВТОПИЛОТ v3.1 — Только утренний пинг")
    print("═" * 50)
    print("   09:00 — Пинг владельцу в TG")
    print(f"   Время сервера: {datetime.now().strftime('%H:%M %Z')}")
    print("═" * 50)
    
    # Утренний пинг при запуске
    morning_job(is_startup=True)
    
    while True:
        schedule.run_pending()
        time.sleep(60)
