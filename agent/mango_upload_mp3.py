#!/usr/bin/env python3
"""
Mango Office — загрузка MP3 и настройка webhook через API

Автоматическая загрузка аудиофайла в Mango Office и настройка webhook
для сбора DTMF событий.
"""

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

import requests

# === КОНФИГУРАЦИЯ ===
MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

# Файл для загрузки
MP3_FILE = "/Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.mp3"

# Webhook URL (публичный адрес для приёма событий)
# Используем webhook.site для теста или свой сервер
WEBHOOK_URL = "https://webhook.site/unique-id-here"  # ЗАМЕНИТЬ на свой


def generate_signature(json_data: dict) -> str:
    """Генерация подписи"""
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def upload_file_v2(mp3_path: str) -> dict:
    """
    Загрузка файла через API v2.
    
    Mango Office API v2 поддерживает загрузку файлов через multipart/form-data.
    """
    if not os.path.exists(mp3_path):
        print(f"❌ Файл не найден: {mp3_path}")
        return None
    
    # Читаем файл
    with open(mp3_path, 'rb') as f:
        file_data = f.read()
    
    filename = os.path.basename(mp3_path)
    print(f"📁 Файл: {filename} ({len(file_data)} байт)")
    
    # API endpoint для загрузки файлов
    url = f"{MANGO_API_BASE}files/upload"
    
    # Создаём multipart запрос
    boundary = "----MangoAPIBoundary"
    
    # Формируем тело запроса вручную для правильного multipart
    body = b''
    
    # Поле vpbx_api_key
    body += f'--{boundary}\r\n'.encode('utf-8')
    body += b'Content-Disposition: form-data; name="vpbx_api_key"\r\n\r\n'
    body += f'{VPBX_API_KEY}\r\n'.encode('utf-8')
    
    # Поле json
    json_data = {
        "filename": filename,
        "description": "Auto-upload from API"
    }
    body += f'--{boundary}\r\n'.encode('utf-8')
    body += b'Content-Disposition: form-data; name="json"\r\n\r\n'
    body += f'{json.dumps(json_data)}\r\n'.encode('utf-8')
    
    # Поле sign
    sign = generate_signature(json_data)
    body += f'--{boundary}\r\n'.encode('utf-8')
    body += b'Content-Disposition: form-data; name="sign"\r\n\r\n'
    body += f'{sign}\r\n'.encode('utf-8')
    
    # Поле file
    body += f'--{boundary}\r\n'.encode('utf-8')
    body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode('utf-8')
    body += b'Content-Type: audio/mpeg\r\n\r\n'
    body += file_data
    body += b'\r\n'
    
    # Завершающий boundary
    body += f'--{boundary}--\r\n'.encode('utf-8')
    
    headers = {
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body))
    }
    
    print("📤 Загрузка через multipart...")
    print(f"   URL: {url}")
    
    response = requests.post(url, headers=headers, data=body, timeout=60)
    
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:500]}")
    
    try:
        result = response.json()
        return result
    except:
        return {'error': response.text, 'status': response.status_code}


def upload_file_simple(mp3_path: str) -> dict:
    """
    Простая загрузка через requests.files.
    """
    if not os.path.exists(mp3_path):
        print(f"❌ Файл не найден: {mp3_path}")
        return None
    
    with open(mp3_path, 'rb') as f:
        file_data = f.read()
    
    filename = os.path.basename(mp3_path)
    print(f"📁 Файл: {filename} ({len(file_data)} байт)")
    
    url = f"{MANGO_API_BASE}files/upload"
    
    json_data = {
        "filename": filename,
        "description": "Auto-upload from API"
    }
    
    sign = generate_signature(json_data)
    
    # Пробуем через requests.files
    files = {
        'file': (filename, file_data, 'audio/mpeg')
    }
    
    data = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data),
        'sign': sign
    }
    
    print("📤 Загрузка через requests.files...")
    
    response = requests.post(url, files=files, data=data, timeout=60)
    
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:500]}")
    
    try:
        return response.json()
    except:
        return {'error': response.text, 'status': response.status_code}


def configure_webhook(webhook_url: str) -> dict:
    """
    Настройка webhook URL в Mango Office.
    
    Этот метод требует авторизации в ЛК или специальный API endpoint.
    """
    print(f"\n🔔 Настройка webhook: {webhook_url}")
    
    # Mango не имеет публичного API для настройки webhook
    # Это делается через ЛК: Интеграции → API коннектор → URL
    
    # Но можем проверить, работает ли наш webhook
    print("   Проверка webhook...")
    
    # Отправляем тестовый запрос
    test_payload = {
        "test": True,
        "message": "Mango Office webhook test",
        "timestamp": "2026-05-15T22:00:00Z"
    }
    
    try:
        response = requests.post(webhook_url, json=test_payload, timeout=10)
        print(f"   ✅ Webhook ответил: {response.status_code}")
        return {'status': 'ok', 'webhook': webhook_url}
    except Exception as e:
        print(f"   ❌ Webhook не отвечает: {e}")
        return {'error': str(e)}


def main():
    print("=== Mango Office — Загрузка MP3 и настройка webhook ===\n")
    
    # Проверка файла
    if not os.path.exists(MP3_FILE):
        print(f"❌ MP3 файл не найден: {MP3_FILE}")
        print("   Запусти сначала конвертацию: python3 mango_play_mp3.py")
        return
    
    # Загрузка файла (метод 1)
    print("=== Метод 1: requests.files ===")
    result1 = upload_file_simple(MP3_FILE)
    
    if result1 and result1.get('result') == 1000:
        print("\n✅ Файл загружен успешно!")
        print(f"   ID: {result1.get('file_id')}")
        print(f"   Имя: {result1.get('filename')}")
    else:
        print(f"\n❌ Метод 1 не сработал: {result1}")
        
        # Метод 2: multipart вручную
        print("\n=== Метод 2: multipart вручную ===")
        result2 = upload_file_v2(MP3_FILE)
        
        if result2 and result2.get('result') == 1000:
            print("\n✅ Файл загружен успешно!")
        else:
            print(f"\n❌ Метод 2 не сработал: {result2}")
            print("\n⚠️  Загрузите файл вручную через ЛК Mango:")
            print("   1. Зайти в office.mango-office.ru")
            print("   2. Виртуальная АТС → Файлы")
            print("   3. Загрузить: andrej_call_100_gosyat.mp3")
    
    # Настройка webhook
    print("\n=== Настройка webhook ===")
    print("⚠️  Webhook настраивается через ЛК Mango:")
    print("   1. Интеграции → API коннектор")
    print("   2. URL внешней системы: https://webhook.site/your-id")
    print("   3. Сохранить")
    
    # Тест webhook
    # configure_webhook(WEBHOOK_URL)
    
    print("\n=== Готово ===")
    print("\n📞 Для звонка с воспроизведением:")
    print("   python3 mango_auto_caller.py clients.csv")


if __name__ == '__main__':
    main()
