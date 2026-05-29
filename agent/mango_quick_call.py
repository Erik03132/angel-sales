#!/usr/bin/env python3
"""
Mango Office Quick Call Test
Тест метода call/quick для простого звонка
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
import uuid

import requests

# Конфигурация
MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")


def generate_signature(json_data: dict) -> str:
    """Генерация подписи: sign = sha256(vpbx_api_key + json + vpbx_api_salt)"""
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def quick_call(customer: str, source: str, destination: str) -> dict:
    """
    Метод call/quick — простой звонок между двумя номерами.
    
    customer: номер клиента (для определения)
    source: номер, с которого звоним (внутренний или внешний)
    destination: номер, куда звоним
    """
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"
    
    json_data = {
        "command_id": command_id,
        "customer": customer,
        "source": source,
        "destination": destination
    }
    
    url = f"{MANGO_API_BASE}call/quick"
    
    payload = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data, separators=(',', ':'), ensure_ascii=False),
        'sign': generate_signature(json_data)
    }
    
    print(f"POST {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(url, data=payload, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    return response.json()


if __name__ == '__main__':
    print("=== Mango Office Quick Call Test ===\n")
    
    # Тест: звонок с 100 на +79859234644
    result = quick_call(
        customer="+79859234644",  # Номер клиента
        source="100",              # Внутренний номер
        destination="+79859234644" # Куда звоним
    )
    
    print(f"\nРезультат: {result}")
