#!/usr/bin/env python3
"""
📞 Mango Office — Тестовый звонок с проверкой webhook

ВАЖНО: Прежде чем запускать, убедись что:
1. Webhook URL в ЛК Mango указывает на рабочий сервер (НЕ httpbin.org!)
2. Webhook сервер запущен и принимает POST-запросы

Что делает скрипт:
1. Проверяет баланс
2. Инициирует callback (Mango звонит extension → потом to_number)
3. Показывает что должно произойти

Использование:
    python3 mango_test_call.py --to +79859234644 --from-ext 25
    python3 mango_test_call.py --to +79859234644 --from-ext 25 --dry
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# Mango API — только прямой доступ (без SOCKS)
for _p in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_p, None)

VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/")


def sign(json_data: dict) -> str:
    j = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((VPBX_API_KEY + j + VPBX_API_SALT).encode()).hexdigest()


def api_call(endpoint: str, json_data: dict) -> dict:
    url = f"{API_BASE.rstrip('/')}/{endpoint}"
    payload = {
        "vpbx_api_key": VPBX_API_KEY,
        "json": json.dumps(json_data, separators=(",", ":"), ensure_ascii=False),
        "sign": sign(json_data),
    }
    r = requests.post(url, data=payload, timeout=15)
    return r.json()


def check_balance():
    """Проверить баланс."""
    result = api_call("account/balance", {})
    balance = result.get("balance", "?")
    print(f"💰 Баланс: {balance} ₽")
    return float(balance) if isinstance(balance, (int, float)) else 0


def make_callback(to_number: str, from_extension: str = "25", command_id: str = None):
    """
    Инициировать callback-звонок.
    
    ВАЖНО — как работает callback:
    1. Mango СНАЧАЛА звонит на from_extension (оператор)
    2. Когда оператор ПОДНИМАЕТ трубку, Mango звонит на to_number (клиент)
    3. Оба соединяются
    
    Для нашей задачи (играть MP3 клиенту) нужен другой подход — см. IVR.
    """
    if command_id is None:
        command_id = f"test_{int(time.time())}"

    json_data = {
        "command_id": command_id,
        "from": {"extension": from_extension},
        "to_number": to_number,
    }

    print("\n📞 Отправляю callback:")
    print(f"   command_id: {command_id}")
    print(f"   from.extension: {from_extension} (оператор — ему звонят ПЕРВОМУ)")
    print(f"   to_number: {to_number} (клиент — ему звонят ВТОРЫМ)")
    print()
    print("   ⏱️  Ожидаемая последовательность:")
    print(f"   1️⃣  Mango звонит на extension {from_extension}")
    print(f"      (телефон сотрудника {from_extension} ЗВОНИТ)")
    print(f"   2️⃣  Сотрудник {from_extension} поднимает трубку")
    print(f"   3️⃣  Mango звонит на {to_number}")
    print(f"   4️⃣  Клиент {to_number} поднимает трубку")
    print("   5️⃣  Оба соединены — разговор")
    print()

    result = api_call("commands/callback", json_data)

    code = result.get("result")
    if code == 1000:
        print("   ✅ Callback инициирован! (result: 1000)")
    else:
        print(f"   ❌ Ошибка: {result}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Mango Office — тестовый звонок")
    parser.add_argument("--to", required=True, help="Номер для звонка (клиент)")
    parser.add_argument("--from-ext", default="25", help="Extension оператора (по умолчанию 25)")
    parser.add_argument("--dry", action="store_true", help="Только показать что произойдёт")
    args = parser.parse_args()

    print("=" * 60)
    print("📞 MANGO OFFICE — Тестовый звонок")
    print("=" * 60)

    # Проверка баланса
    balance = check_balance()
    if balance < 10:
        print("⚠️  Баланс слишком мал!")
        sys.exit(1)

    # Информация о потоке
    print("\n📋 СХЕМА CALLBACK:")
    print(f"""
    ┌─────────────┐        ┌──────────────┐        ┌──────────────┐
    │   Mango     │──1──►  │  Оператор    │        │   Клиент     │
    │   Office    │        │  ext:{args.from_ext:>3}     │        │ {args.to:>14}│
    │   ВАТС      │──3──►  │              │◄──5──► │              │
    └─────────────┘        └──────────────┘        └──────────────┘
    
    1. Mango звонит оператору (ext {args.from_ext})
    2. Оператор отвечает
    3. Mango звонит клиенту ({args.to})
    4. Клиент отвечает
    5. Соединение установлено
    """)

    if args.dry:
        print("🧪 DRY-RUN — звонок НЕ выполняется")
        print()
        print("🔜 Для play/start (проигрывание MP3 клиенту) нужно:")
        print("   1. Настроить webhook URL в ЛК (сейчас httpbin.org)")
        print("   2. Запустить webhook-сервер на VPS (72.56.38.19:8080)")
        print("   3. Настроить IVR-схему переадресации")
        print("   4. Использовать play/start через API")
        print()
        print("   Файл Angel (id=1000296138) уже в Mango — можно тестить!")
        return

    # Подтверждение
    print("⚡ Сейчас будет РЕАЛЬНЫЙ звонок!")
    print(f"   Extension {args.from_ext} зазвонит ПЕРВЫМ")
    print(f"   Потом зазвонит {args.to}")
    print()
    confirm = input("   Продолжить? (y/N): ").strip().lower()
    if confirm != "y":
        print("   Отменено.")
        return

    make_callback(args.to, args.from_ext)


if __name__ == "__main__":
    main()
