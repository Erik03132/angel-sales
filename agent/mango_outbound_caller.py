#!/usr/bin/env python3
"""
Mango Office Outbound Caller

Обзвон по CSV/Excel с персонализированным скриптом.
Использует Mango Office API для инициации звонков.

Формат CSV:
    name,phone,product,delivery_location

Пример:
    Андрей,+79859234644,Бетон М300,Москва, ул. Ленина 1
    Иван,+79991234567,Арматура 12мм,Подольск, склад №5
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
from pathlib import Path

import requests

# === КОНФИГУРАЦИЯ MANGO OFFICE ===
MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")

# Внутренний номер сотрудника, от имени которого звоним
# ЗАМЕНИТЬ на реальный номер из вашей ВАТС (например, 101, 200, etc.)
DEFAULT_FROM_EXTENSION = os.getenv('MANGO_FROM_EXTENSION', '25')

# Внешний номер сотрудника (телефон, с которого идёт звонок)
# Если указан, звонок пойдёт через этот номер (используется как from.number)
DEFAULT_FROM_NUMBER = os.getenv('MANGO_FROM_NUMBER', None)  # Попробуем без номера

# SIP URI сотрудника (альтернатива номеру)
DEFAULT_SIP_URI = os.getenv('MANGO_SIP_URI', 'user4@vpbx400161137.mangosip.ru')

# Входящая линия ВАТС (обязательно для некоторых конфигураций)
# Укажи номер линии из ЛК Mango (например, +74951234567)
DEFAULT_LINE_NUMBER = os.getenv('MANGO_LINE_NUMBER', None)  # Попробуем без линии

# Режим звонка: 'callback' (стандарт) или 'quick' (упрощённый)
CALL_MODE = os.getenv('MANGO_CALL_MODE', 'callback')

# Путь к WAV файлу для теста (опционально)
TEST_WAV_FILE = "/Users/igorvasin/freelance-2026/ai-eggs/agent/andrej_call_100_gosyat.wav"


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
    response.raise_for_status()
    
    return response.json()


def generate_script(row: dict) -> str:
    """
    Генерация персонализированного скрипта звонка.
    
    row: {name, phone, product, delivery_location}
    """
    name = row.get('name', 'Клиент')
    product = row.get('product', 'продукцию')
    delivery = row.get('delivery_location', 'не указано')
    
    script = f"""
📞 Скрипт звонка для: {name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Добрый день, {name}! 

Вас беспокоит компания "Везём Цип". 

✅ По вашему заказу:
   • Продукция: {product}
   • Место доставки: {delivery}

📋 Подтвердите, пожалуйста:
   1. Готовы принять заказ?
   2. Адрес доставки верный?
   3. Удобное время для доставки?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return script


def make_call(to_number: str, from_extension: str = DEFAULT_FROM_EXTENSION,
              line_number: str = None, from_number: str = None, sip_uri: str = None) -> dict:
    """
    Инициировать исходящий вызов через Mango Office.

    to_number: номер клиента
    from_extension: внутренний номер сотрудника
    line_number: входящая линия
    from_number: внешний номер сотрудника
    sip_uri: SIP URI сотрудника (альтернатива номеру)
    """
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"

    # Для commands/callback нужны оба: extension И number
    json_data = {
        "command_id": command_id,
        "from": {
            "extension": from_extension
        },
        "to_number": to_number
    }

    # Добавляем номер сотрудника или SIP URI
    if sip_uri:
        json_data["from"]["sip"] = sip_uri
    elif from_number:
        json_data["from"]["number"] = from_number

    # line_number для маршрутизации
    if line_number:
        json_data["line_number"] = line_number

    return make_request('commands/callback', json_data)


def load_contacts(file_path: str) -> list:
    """Загрузка контактов из CSV или Excel файла"""
    contacts = []
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    if path.suffix.lower() == '.csv':
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            contacts = list(reader)
    elif path.suffix.lower() in ['.xlsx', '.xls']:
        try:
            import pandas as pd
            df = pd.read_excel(path)
            contacts = df.to_dict('records')
        except ImportError:
            print("❌ Для Excel файлов нужен pandas: pip install pandas openpyxl")
            sys.exit(1)
    else:
        print(f"❌ Не поддерживаемый формат: {path.suffix}")
        print("   Используйте .csv или .xlsx")
        sys.exit(1)
    
    return contacts


def call_single(contact: dict, test_mode: bool = False, from_extension: str = DEFAULT_FROM_EXTENSION) -> dict:
    """
    Одиночный звонок с персонализированным скриптом.
    
    contact: {name, phone, product, delivery_location}
    test_mode: если True, только вывод скрипта без звонка
    from_extension: внутренний номер сотрудника
    """
    name = contact.get('name', 'Клиент')
    phone = contact.get('phone', contact.get('Phone', ''))
    product = contact.get('product', contact.get('Product', ''))
    delivery = contact.get('delivery_location', contact.get('Delivery', contact.get('delivery_address', '')))
    
    row_data = {
        'name': name,
        'phone': phone,
        'product': product,
        'delivery_location': delivery
    }
    
    # Генерируем скрипт
    script = generate_script(row_data)
    print(script)
    
    if test_mode:
        print("🧪 ТЕСТОВЫЙ РЕЖИМ — звонок не выполняется\n")
        return {'status': 'test', 'phone': phone}
    
    # Выполняем звонок
    print(f"📞 Звоним на {phone}...")
    print(f"   От сотрудника: {from_extension}")
    if DEFAULT_FROM_NUMBER:
        print(f"   Номер сотрудника: {DEFAULT_FROM_NUMBER}")
    if DEFAULT_LINE_NUMBER:
        print(f"   Линия: {DEFAULT_LINE_NUMBER}")
    
    result = make_call(
        to_number=phone,
        from_extension=from_extension,
        from_number=DEFAULT_FROM_NUMBER,
        sip_uri=DEFAULT_SIP_URI,
        line_number=DEFAULT_LINE_NUMBER
    )
    
    print(f"   API Response: {result}")
    
    if result.get('result') == 1000:
        print("✅ Звонок инициирован успешно!\n")
    else:
        print(f"❌ Ошибка: {result}\n")
    
    return result


def call_batch(contacts: list, delay: int = 5, test_mode: bool = False):
    """
    Массовый обзвон по списку контактов.
    
    contacts: список контактов
    delay: пауза между звонками (сек)
    test_mode: если True, только вывод скриптов
    """
    print(f"\n{'='*60}")
    print(f"📞 ОБЗВОН: {len(contacts)} контактов")
    print(f"{'='*60}\n")
    
    for i, contact in enumerate(contacts, 1):
        print(f"\n[{i}/{len(contacts)}]", end=" ")
        call_single(contact, test_mode)
        
        if i < len(contacts) and not test_mode:
            time.sleep(delay)


def test_call(my_phone: str):
    """
    Тестовый звонок на указанный номер.
    
    my_phone: номер для теста (например, +79859234644)
    """
    print("\n" + "="*60)
    print(f"🧪 ТЕСТОВЫЙ ЗВОНОК НА {my_phone}")
    print("="*60 + "\n")
    
    # Тестовый контакт
    test_contact = {
        'name': 'Игорь (тест)',
        'phone': my_phone,
        'product': 'Тестовая продукция',
        'delivery_location': 'Тестовая доставка'
    }
    
    result = call_single(test_contact, test_mode=False)
    
    # Информация о WAV файле
    if os.path.exists(TEST_WAV_FILE):
        size = os.path.getsize(TEST_WAV_FILE)
        print(f"\n🎤 Тестовый WAV файл: {TEST_WAV_FILE}")
        print(f"   Размер: {size / 1024:.1f} KB")
    else:
        print(f"\n⚠️  WAV файл не найден: {TEST_WAV_FILE}")
    
    return result


def main():
    """Главная функция"""
    print("\n🤖 Mango Office Outbound Caller")
    print("="*60)
    
    if len(sys.argv) < 2:
        print("""
Использование:
    python3 mango_outbound_caller.py <file.csv> [--test <phone>]
    
Примеры:
    python3 mango_outbound_caller.py contacts.csv --test +79859234644
    python3 mango_outbound_caller.py contacts.csv --delay 10
    python3 mango_outbound_caller.py contacts.xlsx

Формат CSV:
    name,phone,product,delivery_location
    Андрей,+79859234644,Бетон М300,"Москва, ул. Ленина 1"
""")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    # Проверка флагов
    test_mode = False
    test_phone = None
    delay = 5
    
    if '--test' in sys.argv:
        test_idx = sys.argv.index('--test')
        if test_idx + 1 < len(sys.argv):
            test_phone = sys.argv[test_idx + 1]
    
    if '--delay' in sys.argv:
        delay_idx = sys.argv.index('--delay')
        if delay_idx + 1 < len(sys.argv):
            delay = int(sys.argv[delay_idx + 1])
    
    # Тестовый звонок
    if test_phone:
        test_call(test_phone)
        return
    
    # Загрузка контактов
    try:
        contacts = load_contacts(file_path)
        print(f"\n✅ Загружено {len(contacts)} контактов из {file_path}")
    except FileNotFoundError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # Обзвон
    call_batch(contacts, delay=delay)
    
    print("\n" + "="*60)
    print("✅ ОБЗВОН ЗАВЕРШЁН")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()
