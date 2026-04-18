#!/usr/bin/env python3
"""
Отправка сообщений Андрею в Битрикс24 через внутренний мессенджер.
Использование:
  python3 send_to_bitrix.py "Текст сообщения"
  python3 send_to_bitrix.py --file report.txt
"""
import os
import sys
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")
ANDREY_ID = 1  # Андрей — первый пользователь в Bitrix


def send_bitrix_message(text, dialog_id=ANDREY_ID):
    """Отправляет сообщение в Битрикс24 мессенджер."""
    resp = requests.post(f"{BITRIX_URL}/im.message.add.json", json={
        "DIALOG_ID": dialog_id,
        "MESSAGE": text[:4000]
    }, timeout=15)
    if resp.status_code == 200 and resp.json().get("result"):
        msg_id = resp.json()["result"]
        print(f"✅ Отправлено в Битрикс (msg #{msg_id})")
        return msg_id
    else:
        print(f"⚠️ Ошибка Битрикс: {resp.text[:200]}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 send_to_bitrix.py 'message' | --file path")
        sys.exit(1)
    
    if sys.argv[1] == "--file":
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        text = " ".join(sys.argv[1:])
    
    send_bitrix_message(text)
