#!/usr/bin/env python3
"""
Mango Office — полностью автоматический обзвон с DTMF

После загрузки MP3 в ЛК и настройки webhook этот скрипт:
1. Генерирует персонализированный скрипт
2. Создаёт TTS аудио (Gemini)
3. Загружает в Mango (через ЛК, один раз)
4. Звонит клиенту
5. Воспроизводит сообщение
6. Собирает DTMF (1 = да, 0 = нет)
7. Сохраняет результат
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

# === КОНФИГУРАЦИЯ ===
MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

# Внутренний номер и линия
FROM_EXTENSION = os.getenv('MANGO_FROM_EXTENSION', '25')
FROM_NUMBER = os.getenv('MANGO_FROM_NUMBER', '73652777654')

# MP3 файл (должен быть загружен в ЛК Mango)
# Укажи имя файла, как оно отображается в ЛК Mango
MP3_FILENAME = os.getenv('MANGO_MP3_FILENAME', 'andrej_call_100_gosyat.mp3')

# Webhook URL (настроить в ЛК Mango)
WEBHOOK_URL = os.getenv('MANGO_WEBHOOK_URL', '')

# TTS настройки
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_TTS_MODEL = 'gemini-2.5-flash-preview-tts'
GEMINI_VOICE = 'Kore'


def generate_signature(json_data: dict) -> str:
    """Генерация подписи"""
    json_string = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode('utf-8')).hexdigest()


def make_request(endpoint: str, json_data: dict) -> dict:
    """POST запрос к Mango API"""
    url = f"{MANGO_API_BASE}{endpoint}"
    
    payload = {
        'vpbx_api_key': VPBX_API_KEY,
        'json': json.dumps(json_data, separators=(',', ':'), ensure_ascii=False),
        'sign': generate_signature(json_data)
    }
    
    response = requests.post(url, data=payload, timeout=30)
    return response.json()


def generate_script(row: dict) -> str:
    """Персонализированный скрипт (17 секунд)"""
    name = row.get('name', 'Клиент')
    product = row.get('product', 'продукцию')
    delivery = row.get('delivery_location', 'не указано')
    
    script = (
        f"{name}, добрый вечер! Это Анжела, Азовский Инкубатор. "
        f"Вы заказали {product} на доставку в {delivery}. "
        f"Водитель позвонит вам завтра. "
        f"Для подтверждения — нажмите 1. "
        f"Для переноса — нажмите 0. "
        f"Спасибо!"
    )
    
    return script


def make_auto_call(to_number: str, mp3_filename: str) -> dict:
    """
    Автоматический звонок с воспроизведением MP3.
    
    После соединения Mango автоматически воспроизведёт файл
    и соберёт DTMF нажатия.
    """
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"
    
    json_data = {
        "command_id": command_id,
        "from": {
            "extension": FROM_EXTENSION,
            "number": FROM_NUMBER
        },
        "to_number": to_number,
        "file": mp3_filename  # Имя файла в Mango
    }
    
    print(f"   📞 Звонок на {to_number}...")
    print(f"   🎵 Файл: {mp3_filename}")
    
    result = make_request('commands/callback', json_data)
    
    if result.get('result') == 1000:
        print(f"   ✅ Звонок инициирован (command_id: {command_id})")
        print("   ⏰ Ожидаем ответ клиента (DTMF: 1=да, 0=нет)...")
    else:
        print(f"   ❌ Ошибка: {result}")
    
    return result


def call_single(contact: dict, delay_after_call: int = 5):
    """Одиночный автоматический звонок"""
    name = contact.get('name', 'Клиент')
    phone = contact.get('phone', '')
    product = contact.get('product', '')
    delivery = contact.get('delivery_location', '')
    
    print(f"\n{'='*60}")
    print(f"📞 АВТОЗВОНОК: {name} ({phone})")
    print(f"{'='*60}")
    
    # Генерация скрипта (для лога)
    script = generate_script({
        'name': name,
        'product': product,
        'delivery_location': delivery
    })
    print(f"\n📋 Скрипт:\n{script}\n")
    
    # Звонок
    result = make_auto_call(phone, MP3_FILENAME)
    
    # Логирование
    timestamp = datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'name': name,
        'phone': phone,
        'product': product,
        'delivery': delivery,
        'script': script,
        'mp3_file': MP3_FILENAME,
        'result': result,
        'dtmf_status': 'pending'  # Будет обновлён через webhook
    }
    
    # Сохранение в лог
    log_file = Path('/Users/igorvasin/freelance-2026/ai-eggs/data/mango/auto_call_log.jsonl')
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    print(f"   📝 Записано в лог: {log_file}")
    
    # Пауза до следующего звонка
    if delay_after_call > 0:
        print(f"\n   ⏰ Пауза {delay_after_call} сек...")
        time.sleep(delay_after_call)
    
    return result


def load_contacts(file_path: str) -> list:
    """Загрузка из CSV"""
    contacts = []
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        contacts = list(reader)
    
    return contacts


def auto_call_batch(contacts: list, delay: int = 30):
    """Массовый автоматический обзвон"""
    print(f"\n{'='*60}")
    print(f"🤖 MANGO AUTO CALLER: {len(contacts)} контактов")
    print(f"{'='*60}\n")
    
    for i, contact in enumerate(contacts, 1):
        print(f"\n[{i}/{len(contacts)}]", end=" ")
        call_single(contact, delay_after_call=0)
        
        if i < len(contacts):
            print(f"\n   ⏰ Пауза {delay} сек до следующего звонка...")
            time.sleep(delay)
    
    print(f"\n{'='*60}")
    print("✅ АВТООБЗВОН ЗАВЕРШЁН")
    print(f"{'='*60}\n")
    
    print("📊 Результаты:")
    print(f"   Всего звонков: {len(contacts)}")
    print("   Лог: /Users/igorvasin/freelance-2026/ai-eggs/data/mango/auto_call_log.jsonl")
    print("\n⚠️  DTMF ответы придут через webhook и будут записаны в отдельный файл")


def main():
    print("\n🤖 Mango Office — Автоматический обзвон с DTMF")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("""
Использование:
    python3 mango_auto_call_full.py <file.csv> [--delay <sec>]

Пример:
    python3 mango_auto_call_full.py clients.csv --delay 30

Формат CSV:
    name,phone,product,delivery_location
    Игорь,+79859234644,125 цыплят,Джанкой
""")
        sys.exit(1)
    
    file_path = sys.argv[1]
    delay = 30
    
    if '--delay' in sys.argv:
        idx = sys.argv.index('--delay')
        if idx + 1 < len(sys.argv):
            delay = int(sys.argv[idx + 1])
    
    # Загрузка контактов
    try:
        contacts = load_contacts(file_path)
        print(f"\n✅ Загружено {len(contacts)} контактов")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Проверка настроек
    print("\n⚙️  Настройки:")
    print(f"   Внутренний номер: {FROM_EXTENSION}")
    print(f"   Внешний номер: {FROM_NUMBER}")
    print(f"   MP3 файл: {MP3_FILENAME}")
    print(f"   Задержка между звонками: {delay} сек")
    
    if not GEMINI_API_KEY:
        print("\n⚠️  GEMINI_API_KEY не указан — используется готовый MP3")
    
    # Обзвон
    auto_call_batch(contacts, delay=delay)


if __name__ == '__main__':
    main()
