#!/usr/bin/env python3
"""
Mango Office — проверка сотрудников и линий
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
    
    print(f"POST {url}")
    print(f"JSON: {json.dumps(json_data)}")
    print(f"Sign: {generate_signature(json_data)[:32]}...")
    
    response = requests.post(url, data=payload, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}\n")
    
    return response.json()


print("=== Mango Office — Проверка сотрудников ===\n")

# Пробуем получить список сотрудников
# Метод 1: users/request с разными параметрами
print("1. users/request (show_users=1)...")
result = make_request('users/request', {"show_users": 1})

print("2. users/request (пустой запрос)...")
result = make_request('users/request', {})

print("3. account/balance...")
result = make_request('account/balance', {})

print("4. commands/callback (проверка подписи)...")
result = make_request('commands/callback', {
    "command_id": "test_signature",
    "from": {"extension": "25", "number": "73652777654"},
    "to_number": "+79859234644"
})
