#!/usr/bin/env python3
"""
Mango Office - проверить статус звонка
"""


import os
from pathlib import Path

from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

import hashlib
import json
import time

import requests

MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")


def generate_signature(json_data: dict) -> str:
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def make_request(endpoint: str, json_data: dict):
    url = f"{MANGO_API_BASE}{endpoint}"
    payload = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data, separators=(',', ':'), ensure_ascii=False),
        'sign': generate_signature(json_data)
    }
    
    response = requests.post(url, data=payload, timeout=30)
    return response.json()


# Сначала инициируем звонок
print("=== Инициация звонка ===\n")

command_id = "test_call_status_001"

json_data = {
    "command_id": command_id,
    "from": {
        "extension": "22",
        "number": "79181805577"
    },
    "to_number": "+79859234644"
}

result = make_request('commands/callback', json_data)
print(f"Результат: {result}")

if result.get('result') == 1000:
    print("\n✅ Звонок инициирован. Ожидаю 5 сек...")
    time.sleep(5)
    
    # Пробуем получить статус (если есть call_id)
    # Для этого нужно получить call_id из события
    print("\nДля проверки статуса нужно получить call_id из события notification")
    print("События приходят на URL внешней системы (настроен в ЛК Mango)")
