#!/usr/bin/env python3
"""
🔍 Mango Office API — Разведка доступных возможностей

Тестирует ВСЕ эндпоинты из документации v16.02.2026:
- Баланс (account/balance)
- Список мелодий/аудиофайлов (audiofiles) — для play/start
- Список сотрудников (config/users/request)
- Список номеров ВАТС (config/lines/request)
- Список кампаний ИО (v2/campaign/list) — если есть КЦ
- Список схем переадресации (config/schemas/request)

Использование:
    python3 mango_recon.py
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

for _p in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_p, None)

VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/")

if not VPBX_API_KEY or not VPBX_API_SALT:
    print("❌ MANGO_VPBX_API_KEY и MANGO_VPBX_API_SALT не заданы в .env!")
    sys.exit(1)


def sign(json_data: dict) -> str:
    """Подпись: sha256(api_key + json + api_salt)"""
    j = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((VPBX_API_KEY + j + VPBX_API_SALT).encode()).hexdigest()


def api_call(endpoint: str, json_data: dict = None, timeout: int = 15) -> dict:
    """Универсальный вызов Mango API."""
    if json_data is None:
        json_data = {}

    url = f"{API_BASE.rstrip('/')}/{endpoint}"
    payload = {
        "vpbx_api_key": VPBX_API_KEY,
        "json": json.dumps(json_data, separators=(",", ":"), ensure_ascii=False),
        "sign": sign(json_data),
    }

    try:
        r = requests.post(url, data=payload, timeout=timeout)
        return {
            "status": r.status_code,
            "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500],
        }
    except requests.exceptions.Timeout:
        return {"status": "TIMEOUT", "body": None}
    except Exception as e:
        return {"status": "ERROR", "body": str(e)}


def test_endpoint(name: str, endpoint: str, json_data: dict = None, extract_fn=None):
    """Тест одного эндпоинта с красивым выводом."""
    print(f"\n{'─'*60}")
    print(f"🔬 {name}")
    print(f"   POST /{endpoint}")

    result = api_call(endpoint, json_data or {})
    status = result["status"]
    body = result["body"]

    if status == 200:
        # Проверяем result code внутри JSON
        if isinstance(body, dict):
            code = body.get("result")
            if code == 1000 or code is None:
                print(f"   ✅ HTTP 200 | result: {code}")
                if extract_fn:
                    extract_fn(body)
                else:
                    # Показать структуру ответа
                    preview = json.dumps(body, ensure_ascii=False, indent=2)
                    if len(preview) > 500:
                        preview = preview[:500] + "\n   ... (truncated)"
                    print(f"   📦 Ответ:\n{preview}")
            else:
                print(f"   ⚠️  HTTP 200, но result: {code}")
                if isinstance(body, dict) and "message" in body:
                    print(f"   📝 {body['message']}")
                else:
                    print(f"   📦 {json.dumps(body, ensure_ascii=False)[:300]}")
        else:
            print("   ✅ HTTP 200")
            print(f"   📦 {str(body)[:300]}")
    elif status == 401:
        print("   ❌ HTTP 401 — Unauthorized (неверная подпись или нет доступа)")
    elif status == 403:
        print("   ❌ HTTP 403 — Forbidden")
    elif status == 404:
        print("   ❌ HTTP 404 — Endpoint не существует")
    elif status == "TIMEOUT":
        print("   ⏳ Таймаут (15 сек)")
    elif status == "ERROR":
        print(f"   ❌ Ошибка: {body}")
    else:
        print(f"   ⚠️  HTTP {status}")
        if body:
            print(f"   📦 {str(body)[:300]}")

    return result


def extract_balance(body):
    """Извлечь баланс."""
    balance = body.get("balance")
    if balance is not None:
        print(f"   💰 Баланс: {balance} ₽")


def extract_audiofiles(body):
    """Извлечь список аудиофайлов."""
    files = body.get("audiofiles", body.get("files", []))
    if isinstance(body, list):
        files = body
    
    # Попробуем разные форматы ответа
    if isinstance(files, list):
        print(f"   🎵 Аудиофайлов: {len(files)}")
        for f in files[:10]:
            if isinstance(f, dict):
                name = f.get("name", f.get("title", "?"))
                iid = f.get("internal_id", f.get("id", "?"))
                print(f"      • [{iid}] {name}")
    else:
        preview = json.dumps(body, ensure_ascii=False, indent=2)[:500]
        print(f"   📦 {preview}")


def extract_users(body):
    """Извлечь список сотрудников."""
    users = body.get("users", [])
    if isinstance(users, list):
        print(f"   👥 Сотрудников: {len(users)}")
        for u in users[:10]:
            if isinstance(u, dict):
                ext = u.get("extension", u.get("telephony", {}).get("extension", "?"))
                name = u.get("general", {}).get("name", u.get("name", "?"))
                print(f"      • [{ext}] {name}")
    else:
        preview = json.dumps(body, ensure_ascii=False, indent=2)[:500]
        print(f"   📦 {preview}")


def extract_campaigns(body):
    """Извлечь список кампаний ИО."""
    campaigns = body.get("campaigns", body.get("data", []))
    if isinstance(campaigns, list):
        print(f"   📞 Кампаний ИО: {len(campaigns)}")
        for c in campaigns[:5]:
            if isinstance(c, dict):
                cid = c.get("campaign_id", c.get("id", "?"))
                name = c.get("name", c.get("title", "?"))
                status = c.get("status", "?")
                print(f"      • [{cid}] {name} — {status}")
    else:
        preview = json.dumps(body, ensure_ascii=False, indent=2)[:500]
        print(f"   📦 {preview}")


def extract_lines(body):
    """Извлечь номера ВАТС."""
    lines = body.get("lines", body.get("numbers", []))
    if isinstance(lines, list):
        print(f"   📱 Номеров ВАТС: {len(lines)}")
        for ln in lines[:10]:
            if isinstance(ln, dict):
                num = ln.get("number", ln.get("line_number", "?"))
                print(f"      • {num}")
            else:
                print(f"      • {ln}")
    else:
        preview = json.dumps(body, ensure_ascii=False, indent=2)[:500]
        print(f"   📦 {preview}")


def main():
    print("=" * 60)
    print("🔍 MANGO OFFICE API — Разведка")
    print(f"   API Key: {VPBX_API_KEY[:8]}...{VPBX_API_KEY[-4:]}")
    print(f"   API Base: {API_BASE}")
    print("=" * 60)

    # 1. Баланс (гарантированно работает)
    test_endpoint(
        "Баланс (account/balance)",
        "account/balance",
        extract_fn=extract_balance,
    )

    # 2. Список аудиофайлов — КЛЮЧЕВОЙ для play/start
    test_endpoint(
        "Аудиофайлы/Мелодии (audiofiles) — нужен internal_id!",
        "audiofiles",
        extract_fn=extract_audiofiles,
    )

    # 3. Список сотрудников
    test_endpoint(
        "Сотрудники (config/users/request)",
        "config/users/request",
        extract_fn=extract_users,
    )

    # 4. Номера ВАТС
    test_endpoint(
        "Номера ВАТС (config/lines/request)",
        "config/lines/request",
        extract_fn=extract_lines,
    )

    # 5. Схемы переадресации
    test_endpoint(
        "Схемы переадресации (config/schemas/request)",
        "config/schemas/request",
    )

    # 6. Кампании ИО (Контакт-центр)
    test_endpoint(
        "Кампании ИО — v2/campaign/list (требует КЦ!)",
        "v2/campaign/list",
        json_data={"limit": 10, "cursor": None},
        extract_fn=extract_campaigns,
    )

    # 7. Проверим ещё v2/campaign/tasks (задачи кампаний)
    # Нужен campaign_id, поэтому пустой запрос
    test_endpoint(
        "Задачи кампаний — v2/campaign/tasks",
        "v2/campaign/tasks",
        json_data={"fields": ["alias_all"], "limit": 5, "cursor": None},
    )

    # Итоги
    print(f"\n{'='*60}")
    print("📊 ИТОГИ РАЗВЕДКИ")
    print("=" * 60)
    print("""
Что нужно для автодозвона:
  1. ✅ audiofiles → internal_id файлов → для play/start
  2. ✅ webhook настроен → получаем call_id и DTMF
  3. ❓ Кампании ИО → зависит от тарифа КЦ
  
Следующий шаг:
  → Загрузить тестовый MP3 в ЛК Mango вручную
  → Повторить audiofiles → получить internal_id
  → Протестировать play/start в IVR-цепочке
""")


if __name__ == "__main__":
    main()
