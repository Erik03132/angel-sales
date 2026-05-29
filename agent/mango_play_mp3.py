#!/usr/bin/env python3
"""
Mango Office — тест с конвертацией WAV → MP3 и воспроизведением
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
import subprocess
import uuid

import requests

MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

# WAV файлы для теста
WAV_FILES = [
    "/Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.wav",
    "/Users/igorvasin/freelance-2026/ai-eggs/agent/test_tts_output.wav",
    "/Users/igorvasin/freelance-2026/ai-eggs/agent/test_tts_advanced.wav"
]


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


def convert_wav_to_mp3(wav_path: str) -> str:
    """Конвертация WAV → MP3 через ffmpeg"""
    mp3_path = wav_path.replace('.wav', '.mp3')
    
    if os.path.exists(mp3_path):
        print(f"✅ MP3 уже существует: {mp3_path}")
        return mp3_path
    
    # Проверяем ffmpeg
    if not os.path.exists('/opt/homebrew/bin/ffmpeg'):
        print("❌ ffmpeg не найден. Установи: brew install ffmpeg")
        return None
    
    cmd = [
        '/opt/homebrew/bin/ffmpeg',
        '-i', wav_path,
        '-b:a', '128k',
        '-y', mp3_path
    ]
    
    print(f"🎵 Конвертация: {wav_path} → {mp3_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if os.path.exists(mp3_path):
        size = os.path.getsize(mp3_path)
        print(f"✅ Готово! Размер: {size / 1024:.1f} KB")
        return mp3_path
    else:
        print(f"❌ Ошибка конвертации: {result.stderr}")
        return None


def test_call_with_play(to_number: str, mp3_path: str):
    """
    Звонок + воспроизведение MP3
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
    
    result = make_request('commands/callback', json_data)
    print(f"   Результат: {result}")
    
    if result.get('result') != 1000:
        print("❌ Звонок не инициирован")
        return
    
    print("✅ Звонок инициирован. Ожидаем соединения (10 сек)...")
    
    # Даём время на соединение
    import time
    time.sleep(10)
    
    # Шаг 2: Воспроизведение файла (требует call_id из события)
    # Для этого нужен webhook для получения call_id
    print("\n🎵 Шаг 2: Для воспроизведения нужен call_id из webhook")
    print(f"   Файл готов: {mp3_path}")
    print("   Нужно загрузить в Mango и отправить play/start")
    
    return result


def main():
    print("=== Mango Office — WAV → MP3 конвертация ===\n")
    
    # Конвертируем первый WAV файл
    wav_file = WAV_FILES[0]
    print(f"Исходный файл: {wav_file}")
    
    if not os.path.exists(wav_file):
        print(f"❌ Файл не найден: {wav_file}")
        return
    
    mp3_file = convert_wav_to_mp3(wav_file)
    
    if mp3_file:
        print(f"\n✅ MP3 готов: {mp3_file}")
        print(f"   Размер: {os.path.getsize(mp3_file) / 1024:.1f} KB")
        
        # Тест звонка
        print("\n=== Тест звонка ===")
        test_call_with_play('+79859234644', mp3_file)
    else:
        print("\n❌ Конвертация не удалась")
        print("   Установи ffmpeg: brew install ffmpeg")


if __name__ == '__main__':
    main()
