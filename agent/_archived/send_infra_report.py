"""Отправка отчёта по IT-инфраструктуре Андрею и Игорю в TG."""
import os

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY")

ANDREY_ID = 444248782
IGOR_ID = 176203333

# Читаем отчёт
report_path = os.path.join(BASE_DIR, "data", "daily_reports", "report_infra_20260421.txt")
with open(report_path, 'r', encoding='utf-8') as f:
    text = f.read()

def send_tg(chat_id, text, label=""):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        proxy = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": proxy, "http": proxy}
    
    # Telegram лимит 4096 символов
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (продолжение по запросу)"
    
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
        }, proxies=proxies, timeout=15)
        
        if resp.status_code == 200:
            print(f"✅ Отправлено {label} (chat_id={chat_id})")
            return True
        else:
            print(f"⚠️ Ошибка [{label}]: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"⚠️ Ошибка отправки [{label}]: {e}")
        return False

print(f"📄 Отчёт загружен ({len(text)} символов)")
print()

# ⛔ Андрею — НИКАКИХ отчётов в TG! (решение от 12.05.2026)
# Отправляем ТОЛЬКО Игорю
send_tg(IGOR_ID, text, label="Игорь")
