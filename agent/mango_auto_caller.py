#!/usr/bin/env python3
"""
Mango Office Auto Caller с TTS и DTMF

Автоматический обзвон по CSV с персонализированным голосовым сообщением.
Клиент нажимает 1 (подтвердить) или 0 (перенести).

Использование:
    python3 mango_auto_caller.py contacts.csv --test +79859234644
    python3 mango_auto_caller.py contacts.csv --delay 30
"""

import csv
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
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

# === КОНФИГУРАЦИЯ MANGO OFFICE ===
MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

# Внутренний номер и линия
DEFAULT_FROM_EXTENSION = os.getenv('MANGO_FROM_EXTENSION', '25')
DEFAULT_FROM_NUMBER = os.getenv('MANGO_FROM_NUMBER', '73652777654')

# TTS настройки (Gemini)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_TTS_MODEL = 'gemini-2.5-flash-preview-tts'
GEMINI_VOICE = 'Kore'  # или Puck

# Webhook URL для DTMF событий (настроить в ЛК Mango)
WEBHOOK_URL = os.getenv('MANGO_WEBHOOK_URL', '')

# Путь к MP3 файлам
MP3_DIR = Path('/Users/igorvasin/freelance-2026/ai-eggs/agent')


def generate_signature(json_data: dict) -> str:
    """Генерация подписи: sign = sha256(vpbx_api_key + json + vpbx_api_salt)"""
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def make_request(endpoint: str, json_data: dict) -> dict:
    """Выполнение POST запроса к Mango Office API"""
    url = f"{MANGO_API_BASE}{endpoint}"
    
    payload = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data, separators=(',', ':'), ensure_ascii=False),
        'sign': generate_signature(json_data)
    }
    
    response = requests.post(url, data=payload, timeout=30)
    return response.json()


def generate_tts_script(row: dict) -> str:
    """
    Генерация персонализированного скрипта для TTS.
    
    row: {name, phone, product, delivery_location}
    """
    name = row.get('name', 'Клиент')
    product = row.get('product', 'продукцию')
    delivery = row.get('delivery_location', 'не указано')
    
    # Скрипт из вчерашней сессии (17 секунд)
    script = (
        f"{name}, добрый вечер! Это Анжела, Азовский Инкубатор. "
        f"Вы заказали {product} на доставку в {delivery}. "
        f"Водитель позвонит вам завтра. "
        f"Для подтверждения — нажмите 1. "
        f"Для переноса — нажмите 0. "
        f"Спасибо!"
    )
    
    return script


def generate_tts_audio(text: str, output_path: str = None) -> str:
    """
    Генерация MP3 через Gemini TTS API.
    
    Возвращает путь к MP3 файлу.
    """
    if not GEMINI_API_KEY:
        print("   ⚠️  GEMINI_API_KEY не указан — используем тестовый MP3")
        return str(MP3_DIR / 'andrej_call_100_gosyat.mp3')
    
    if output_path is None:
        filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        output_path = str(MP3_DIR / filename)
    
    # Gemini TTS API запрос
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent"
    
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': GEMINI_API_KEY
    }
    
    # Параметры TTS из вчерашней сессии
    tts_config = {
        "voiceConfig": {
            "prebuiltVoiceConfig": {
                "voiceName": GEMINI_VOICE
            }
        },
        "responseModalities": ["AUDIO"]
    }
    
    payload = {
        "contents": [{
            "parts": [{
                "text": text
            }]
        }],
        "generationConfig": tts_config
    }
    
    print(f"   🎤 Генерация TTS через Gemini ({GEMINI_VOICE})...")
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    
    if response.status_code != 200:
        print(f"   ❌ Ошибка TTS: {response.status_code} — {response.text}")
        return str(MP3_DIR / 'andrej_call_100_gosyat.mp3')
    
    result = response.json()
    
    # Извлекаем аудио (base64)
    try:
        audio_data = result['candidates'][0]['content']['parts'][0]['inlineData']['data']
        
        # Декодируем и сохраняем MP3
        import base64
        audio_bytes = base64.b64decode(audio_data)
        
        with open(output_path, 'wb') as f:
            f.write(audio_bytes)
        
        size = os.path.getsize(output_path)
        print(f"   ✅ MP3 сохранён: {output_path} ({size / 1024:.1f} KB)")
        
        return output_path
        
    except (KeyError, IndexError) as e:
        print(f"   ❌ Ошибка парсинга TTS ответа: {e}")
        print(f"   Response: {json.dumps(result, indent=2)}")
        return str(MP3_DIR / 'andrej_call_100_gosyat.mp3')


def upload_mp3_to_mango(mp3_path: str) -> dict:
    """
    Загрузка MP3 файла в Mango Office через API.
    
    Возвращает ID файла в Mango.
    """
    if not os.path.exists(mp3_path):
        print(f"   ❌ Файл не найден: {mp3_path}")
        return None
    
    # Mango API для загрузки файлов требует OAuth или特殊ную авторизацию
    # Для простоты возвращаем путь — файл нужно загрузить через ЛК вручную
    
    filename = os.path.basename(mp3_path)
    print(f"   📁 Файл: {filename}")
    print("   ⚠️  Загрузите этот файл в ЛК Mango: Виртуальная АТС → Файлы")
    
    return {'filename': filename, 'path': mp3_path}


def make_call_with_dtmf(to_number: str, mp3_filename: str, from_extension: str = DEFAULT_FROM_EXTENSION, 
                        from_number: str = DEFAULT_FROM_NUMBER) -> dict:
    """
    Исходящий звонок с воспроизведением MP3 и сбором DTMF.
    
    to_number: номер клиента
    mp3_filename: имя файла в Mango (загрузить через ЛК)
    from_extension: внутренний номер
    from_number: внешний номер
    """
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"
    
    # Шаг 1: Инициируем звонок
    json_data = {
        "command_id": command_id,
        "from": {
            "extension": from_extension,
            "number": from_number
        },
        "to_number": to_number
    }
    
    print(f"   📞 Инициация звонка на {to_number}...")
    result = make_request('commands/callback', json_data)
    
    if result.get('result') != 1000:
        print(f"   ❌ Ошибка: {result}")
        return result
    
    print(f"   ✅ Звонок инициирован (command_id: {command_id})")
    
    # Шаг 2: Воспроизведение MP3 (нужен call_id из webhook)
    # Для этого нужно ждать событие от Mango с call_id
    
    print(f"   🎵 Ожидаем соединения для воспроизведения {mp3_filename}...")
    print("   ⚠️  Для play/start нужен webhook URL в настройках Mango")
    
    return result


def call_single(contact: dict, test_mode: bool = False):
    """
    Одиночный звонок с генерацией TTS и DTMF.
    """
    name = contact.get('name', 'Клиент')
    phone = contact.get('phone', contact.get('Phone', ''))
    product = contact.get('product', contact.get('Product', ''))
    delivery = contact.get('delivery_location', contact.get('Delivery', ''))
    
    row_data = {
        'name': name,
        'phone': phone,
        'product': product,
        'delivery_location': delivery
    }
    
    print(f"\n{'='*60}")
    print(f"📞 ОБЗВОН: {name} ({phone})")
    print(f"{'='*60}")
    
    # Генерация скрипта
    script = generate_tts_script(row_data)
    print(f"\n📋 Скрипт:\n{script}\n")
    
    if test_mode:
        print("🧪 ТЕСТОВЫЙ РЕЖИМ\n")
        return {'status': 'test', 'phone': phone}
    
    # Генерация TTS аудио
    mp3_file = generate_tts_audio(script)
    
    # Загрузка в Mango (или инструкция)
    file_info = upload_mp3_to_mango(mp3_file)
    
    # Звонок
    result = make_call_with_dtmf(phone, file_info['filename'])
    
    # Логирование результата
    timestamp = datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'name': name,
        'phone': phone,
        'product': product,
        'delivery': delivery,
        'mp3_file': file_info['filename'],
        'result': result
    }
    
    log_file = Path('/Users/igorvasin/freelance-2026/ai-eggs/data/mango/call_log.jsonl')
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    print(f"   📝 Записано в лог: {log_file}")
    
    return result


def load_contacts(file_path: str) -> list:
    """Загрузка контактов из CSV"""
    contacts = []
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        contacts = list(reader)
    
    return contacts


def call_batch(contacts: list, delay: int = 30, test_mode: bool = False):
    """Массовый обзвон по списку"""
    print(f"\n{'='*60}")
    print(f"🤖 MANGO AUTO CALLER: {len(contacts)} контактов")
    print(f"{'='*60}\n")
    
    for i, contact in enumerate(contacts, 1):
        print(f"\n[{i}/{len(contacts)}]", end=" ")
        call_single(contact, test_mode)
        
        if i < len(contacts) and not test_mode:
            print(f"\n   ⏰ Пауза {delay} сек до следующего звонка...")
            time.sleep(delay)
    
    print(f"\n{'='*60}")
    print("✅ ОБЗВОН ЗАВЕРШЁН")
    print(f"{'='*60}\n")


def main():
    """Главная функция"""
    print("\n🤖 Mango Office Auto Caller с TTS + DTMF")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("""
Использование:
    python3 mango_auto_caller.py <file.csv> [--test <phone>] [--delay <sec>]

Примеры:
    python3 mango_auto_caller.py contacts.csv --test +79859234644
    python3 mango_auto_caller.py contacts.csv --delay 30

Формат CSV:
    name,phone,product,delivery_location
    Андрей,+79859234644,100 гусят,"Джанкой"
""")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # Парсинг аргументов
    test_mode = False
    test_phone = None
    delay = 30
    
    if '--test' in sys.argv:
        idx = sys.argv.index('--test')
        if idx + 1 < len(sys.argv):
            test_phone = sys.argv[idx + 1]
            test_mode = True
    
    if '--delay' in sys.argv:
        idx = sys.argv.index('--delay')
        if idx + 1 < len(sys.argv):
            delay = int(sys.argv[idx + 1])
    
    # Тестовый звонок
    if test_phone:
        test_contact = {
            'name': 'Игорь (тест)',
            'phone': test_phone,
            'product': 'Тестовая продукция',
            'delivery_location': 'Тестовая доставка'
        }
        call_single(test_contact, test_mode=True)
        return
    
    # Загрузка контактов
    try:
        contacts = load_contacts(file_path)
        print(f"\n✅ Загружено {len(contacts)} контактов из {file_path}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Обзвон
    call_batch(contacts, delay=delay, test_mode=False)


if __name__ == '__main__':
    main()
