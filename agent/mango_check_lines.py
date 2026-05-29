#!/usr/bin/env python3
"""
Mango Office - получить список линий
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
    
    response = requests.post(url, data=payload, timeout=30)
    return response.json()


# Пробуем разные методы для получения информации о линиях
print("=== Проверка доступных линий ===\n")

# Метод 1: users/request с параметрами
print("1. users/request...")
result = make_request('users/request', {"show_users": 1, "show_groups": 1})
print(f"   {result}\n")

# Метод 2: account/balance (проверка что API работает)
print("2. account/balance...")
result = make_request('account/balance', {})
print(f"   {result}\n")
