#!/usr/bin/env python3
"""
Mango Office — загрузка MP3 через API с сессионной авторизацией
"""

import hashlib
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# Конфигурация
MANGO_LK_URL = 'https://office.mango-office.ru'
MANGO_API_BASE = os.getenv('MANGO_API_BASE', 'https://app.mango-office.ru/vpbx/')

VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

MANGO_LOGIN = os.getenv("MANGO_LOGIN", "")
MANGO_PASSWORD = os.getenv("MANGO_PASSWORD", "")

MP3_FILE = '/Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.mp3'


def generate_signature(json_data: dict) -> str:
    """Генерация подписи"""
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def login_to_lk() -> requests.Session:
    """Логин в ЛК Mango для получения сессионной cookies"""
    print("🔐 Логин в ЛК Mango...")
    
    session = requests.Session()
    
    # Шаг 1: Получаем форму логина
    login_url = f'{MANGO_LK_URL}/auth/login'
    response = session.get(login_url)
    
    # Шаг 2: Отправляем логин/пароль
    payload = {
        'login': MANGO_LOGIN,
        'password': MANGO_PASSWORD
    }
    
    response = session.post(login_url, data=payload, allow_redirects=False)
    
    if response.status_code in [200, 302]:
        print("   ✅ Успешный вход")
        return session
    else:
        print(f"   ❌ Ошибка входа: {response.status_code}")
        return None


def upload_via_api(session: requests.Session):
    """Загрузка через API с сессионной cookies"""
    print("\n📤 Загрузка MP3 через API...")
    
    if not os.path.exists(MP3_FILE):
        print(f"❌ Файл не найден: {MP3_FILE}")
        return None
    
    with open(MP3_FILE, 'rb') as f:
        file_data = f.read()
    
    filename = os.path.basename(MP3_FILE)
    
    # API endpoint
    url = f'{MANGO_API_BASE}files/upload'
    
    json_data = {
        'filename': filename,
        'description': 'Auto-upload via API'
    }
    
    sign = generate_signature(json_data)
    
    # Пробуем с сессионной cookies
    files = {
        'file': (filename, file_data, 'audio/mpeg')
    }
    
    data = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data),
        'sign': sign
    }
    
    response = session.post(url, files=files, data=data, timeout=60)
    
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:500]}")
    
    try:
        result = response.json()
        if result.get('result') == 1000:
            print(f"   ✅ Файл загружен: {filename}")
            return filename
        else:
            print(f"   ❌ Ошибка: {result}")
            return None
    except:
        return None


def configure_webhook_api(session: requests.Session, webhook_url: str):
    """Настройка webhook через API"""
    print(f"\n🔔 Настройка Webhook: {webhook_url}")
    
    url = f'{MANGO_API_BASE}settings/webhook'
    
    json_data = {
        'webhook_url': webhook_url
    }
    
    sign = generate_signature(json_data)
    
    data = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data),
        'sign': sign
    }
    
    response = session.post(url, data=data, timeout=30)
    
    print(f"   Status: {response.status_code}")
    
    try:
        result = response.json()
        if result.get('result') == 1000:
            print("   ✅ Webhook настроен")
            return True
        else:
            print(f"   ❌ Ошибка: {result}")
            return False
    except:
        return False


def main():
    print("=== Mango Office — Автоматическая загрузка MP3 ===\n")
    
    # Логин
    session = login_to_lk()
    
    if not session:
        print("\n❌ Не удалось войти в ЛК")
        return
    
    # Загрузка файла
    filename = upload_via_api(session)
    
    if filename:
        print(f"\n✅ MP3 загружен: {filename}")
        
        # Настройка webhook
        # webhook_url = 'https://webhook.site/unique-id'
        # configure_webhook_api(session, webhook_url)
        
        print("\n=== Готово ===")
        print("\n📞 Для звонка:")
        print("   python3 ai-eggs/agent/mango_auto_call_full.py ai-eggs/data/mango/clients.csv")
        print("\n⚙️  Параметры:")
        print(f"   MP3 файл: {filename}")
    else:
        print("\n❌ Не удалось загрузить MP3")


if __name__ == '__main__':
    main()
