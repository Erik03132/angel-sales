#!/usr/bin/env python3
"""
Mango Office — загрузка MP3 и звонок с воспроизведением
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
import time
import uuid

import requests

MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

# MP3 файл для воспроизведения
MP3_FILE = "/Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.mp3"


def generate_signature(json_data: dict) -> str:
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def upload_file(mp3_path: str) -> dict:
    """
    Загрузка MP3 файла в Mango Office через API.
    """
    url = f"{MANGO_API_BASE}files/upload"
    
    if not os.path.exists(mp3_path):
        print(f"❌ Файл не найден: {mp3_path}")
        return None
    
    # Читаем файл
    with open(mp3_path, 'rb') as f:
        file_data = f.read()
    
    filename = os.path.basename(mp3_path)
    
    # Для загрузки файлов используется multipart/form-data
    # Но Mango API требует подпись
    # Пробуем через POST с файлом
    
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"
    
    json_data = {
        "command_id": command_id,
        "filename": filename
    }
    
    payload = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data, separators=(',', ':'), ensure_ascii=False),
        'sign': generate_signature(json_data),
        'file': (filename, file_data, 'audio/mpeg')
    }
    
    print(f"📤 Загрузка файла: {filename} ({len(file_data)} байт)")
    
    # Используем Session для правильного multipart
    session = requests.Session()
    # Отключаем автоматическую кодировку для file
    encoder = requests.packages.urllib3.fields.RequestField
    response = session.post(url, files={'file': (filename, file_data, 'audio/mpeg')}, 
                           data={'vpbx_api_key': VPBX_API_KEY, 
                                 'json': json.dumps(json_data),
                                 'sign': generate_signature(json_data)})
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    return response.json()


def make_call_with_play(to_number: str, filename: str):
    """
    Звонок с воспроизведением MP3 файла.
    """
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"
    
    # Шаг 1: Инициируем звонок
    print(f"\n📞 Шаг 1: Инициация звонка на {to_number}...")
    
    json_data = {
        "command_id": command_id,
        "from": {
            "extension": "25",
            "number": "73652777654"
        },
        "to_number": to_number
    }
    
    result = requests.post(
        f"{MANGO_API_BASE}commands/callback",
        data={
            'vpbx_api_key': VPBX_API_KEY,
            'json': json.dumps(json_data, separators=(',', ':'), ensure_ascii=False),
            'sign': generate_signature(json_data)
        }
    ).json()
    
    print(f"   Результат: {result}")
    
    if result.get('result') != 1000:
        print("❌ Звонок не инициирован")
        return None
    
    print("✅ Звонок инициирован. Ожидаем соединения (15 сек)...")
    time.sleep(15)
    
    # Шаг 2: Воспроизведение файла
    # Для этого нужен call_id из события webhook
    # Но попробуем отправить play/start с предположением, что call_id ещё активен
    
    print(f"\n🎵 Шаг 2: Воспроизведение {filename}...")
    print("   ⚠️ Для play/start нужен call_id из webhook события")
    print("   Без webhook невозможно получить call_id активного звонка")
    
    return result


def main():
    print("=== Mango Office — Звонок с MP3 ===\n")
    
    if not os.path.exists(MP3_FILE):
        print(f"❌ MP3 файл не найден: {MP3_FILE}")
        print("   Запусти сначала конвертацию: python3 mango_play_mp3.py")
        return
    
    print(f"📁 Файл: {MP3_FILE}")
    print(f"   Размер: {os.path.getsize(MP3_FILE) / 1024:.1f} KB")
    
    # Пробуем загрузить файл
    print("\n=== Загрузка файла в Mango ===")
    upload_result = upload_file(MP3_FILE)
    
    if upload_result and upload_result.get('result') == 1000:
        filename = os.path.basename(MP3_FILE)
        print(f"\n✅ Файл загружен: {filename}")
        
        # Звонок с воспроизведением
        print("\n=== Тест звонка с воспроизведением ===")
        make_call_with_play('+79859234644', filename)
    else:
        print(f"\n❌ Загрузка не удалась: {upload_result}")
        print("\n=== Тест звонка (без воспроизведения) ===")
        make_call_with_play('+79859234644', None)


if __name__ == '__main__':
    main()
