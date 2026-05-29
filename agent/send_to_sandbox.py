#!/usr/bin/env python3
"""
Отправка сообщений Андрею в песочницу Битрикс24.
Песочница: b24-mjxvhq.bitrix24.ru
Андрей = Иван Иванов = ID=16
"""
import sys

import requests

SANDBOX_URL = "https://b24-mjxvhq.bitrix24.ru/rest/1/3crdltc04zo7fp8l"
ANDREY_ID = 16  # Иван Иванов = Андрей в песочнице


def send_sandbox_message(text, dialog_id=ANDREY_ID):
    """Отправляет сообщение в песочницу Битрикс24."""
    resp = requests.post(f"{SANDBOX_URL}/im.message.add.json", json={
        "DIALOG_ID": dialog_id,
        "MESSAGE": text[:4000]
    }, timeout=15)
    if resp.status_code == 200 and resp.json().get("result"):
        msg_id = resp.json()["result"]
        print(f"  ✅ Отправлено Андрею (msg #{msg_id})")
        return msg_id
    else:
        print(f"  ⚠️ Ошибка: {resp.status_code} — {resp.text[:300]}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 send_to_sandbox.py 'message'")
        print("       python3 send_to_sandbox.py --file path.txt")
        sys.exit(1)

    if sys.argv[1] == "--file":
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            text = f.read()
    else:
        text = " ".join(sys.argv[1:])

    send_sandbox_message(text)
