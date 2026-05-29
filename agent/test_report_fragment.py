#!/usr/bin/env python3
"""
test_report_fragment.py – выводит небольшой фрагмент отчёта за вчера (2026‑04‑28)
для быстрой проверки.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .. (freelance-2026)
DATA_DIR = PROJECT_ROOT / "ai-eggs" / "data"
EXTRACTED_JSON = DATA_DIR / "extracted_wisdom_clean.json"
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)
BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL")
BITRIX_TOKEN = os.getenv("BITRIX24_TOKEN")

def get_manager_names() -> dict:
    """Возвращает словарь manager_id → "Имя Фамилия" через Bitrix API."""
    if not BITRIX_URL:
        raise RuntimeError("BITRIX_WEBHOOK_URL не задан в .env")
    resp = requests.get(f"{BITRIX_URL}user.get.json", params={"auth": BITRIX_TOKEN}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Bitrix error {data['error_description']}")
    mapping = {}
    for u in data.get("result", []):
        uid = str(u["ID"])
        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        mapping[uid] = name if name else f"ID_{uid}"
    return mapping

# Читаем все звонки
with open(EXTRACTED_JSON, "r", encoding="utf-8") as f:
    calls = json.load(f)

# Вчерашняя дата (по Москве)
TZ = timezone(timedelta(hours=3))
today = datetime.now(TZ).date()
yesterday = today - timedelta(days=1)

# Фильтруем за вчера
y_calls = [c for c in calls if datetime.fromisoformat(c["date"]).date() == yesterday]

# Получаем имена менеджеров
manager_names = get_manager_names()

# Выводим первые 3 звонка с резюме в виде markdown‑фрагмента
print(f"# Фрагмент отчёта за {yesterday}\n")
count = 0
for call in y_calls:
    tr = call.get("transcript", "")
    m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\\n\\n|$)", tr, re.DOTALL)
    if not m:
        continue  # пропускаем без резюме
    summary = re.sub(r"\s+", " ", m.group(1).strip())
    manager_id = str(call.get("manager_id", ""))
    manager = manager_names.get(manager_id, f"ID_{manager_id}")
    count += 1
    print(f"## Звонок {count} (ID {call.get('call_id', '-')}) – менеджер {manager}\n- **Дата**: {call.get('date')}\n- **Длительность**: {call.get('duration')} сек\n- **Кратко**: {summary}\n")
    if count >= 3:
        break
