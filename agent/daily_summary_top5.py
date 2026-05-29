#!/usr/bin/env python3
"""
 daily_summary_top5.py – выводит общее количество звонков за вчерашний день
 и пять самых значимых звонков (по длительности и ключевым признакам).
 Требования: pip install python-dotenv requests
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Optional import – если библиотека requests не установлена, будем работать без запросов к Bitrix
try:
    import requests
except ImportError:  # pragma: no cover
    requests = None
    print("⚠️  requests не установлен – в отчёте будут только ID менеджеров")

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
    """Возвращает словарь manager_id → "Имя Фамилия" через Bitrix API.
    Если запрос невозможен (нет requests или неверные переменные), возвращаем пустой словарь.
    """
    if not requests:
        return {}
    if not BITRIX_URL:
        print("⚠️  BITRIX_WEBHOOK_URL не задан в .env – будут использованы только ID")
        return {}
    try:
        resp = requests.get(
            f"{BITRIX_URL}user.get.json", params={"auth": BITRIX_TOKEN}, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            print(f"⚠️  Bitrix error: {data['error_description']}")
            return {}
    except Exception as e:
        print(f"⚠️  Ошибка при запросе к Bitrix: {e}")
        return {}
    mapping = {}
    for u in data.get("result", []):
        uid = str(u["ID"])
        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        mapping[uid] = name if name else f"ID_{uid}"
    return mapping

def is_significant(call: dict) -> bool:
    """Определяем значимый звонок.
    - Длительность > 120 сек
    - В резюме присутствуют ключевые слова (груб, негатив, проблема, требуется уточн)
    """
    duration = int(call.get("duration", "0"))
    if duration > 120:
        return True
    tr = call.get("transcript", "")
    m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\\n\\n|$)", tr, re.DOTALL)
    if not m:
        return False
    summary = m.group(1).lower()
    keywords = ["груб", "негатив", "проблем", "требуется уточн"]
    return any(kw in summary for kw in keywords)

def extract_summary(transcript: str) -> str:
    """Извлекает блок РЕЗЮМЕ из транскрипта, если есть."""
    m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\\n\\n|$)", transcript, re.DOTALL)
    if not m:
        return "(без резюме)"
    return re.sub(r"\s+", " ", m.group(1).strip())

# -------------------- Основная логика --------------------
# Вчерашняя дата (по Москве)
TZ = timezone(timedelta(hours=3))
today = datetime.now(TZ).date()
yesterday = today - timedelta(days=1)

# Читаем звонки
with open(EXTRACTED_JSON, "r", encoding="utf-8") as f:
    calls = json.load(f)

# Фильтрация по дате
calls_yesterday = [c for c in calls if datetime.fromisoformat(c["date"]).date() == yesterday]

total_calls = len(calls_yesterday)

# Выбираем значимые
significant = [c for c in calls_yesterday if is_significant(c)]
# Сортируем по длительности (по убыванию)
significant.sort(key=lambda x: int(x.get("duration", "0")), reverse=True)

top5 = significant[:5]

# Получаем имена менеджеров
manager_names = get_manager_names()

# Формируем вывод
print(f"# Сводка за {yesterday}\n")
print(f"**Всего звонков:** {total_calls}\n")
if top5:
    print("## Топ‑5 значимых звонков\n")
    for i, call in enumerate(top5, 1):
        manager_id = str(call.get("manager_id", ""))
        manager = manager_names.get(manager_id, f"ID_{manager_id}")
        summary = extract_summary(call.get("transcript", ""))
        print(
            f"### {i}. Звонок {call.get('call_id', '-')} – менеджер {manager}\n"
            f"- **Дата:** {call.get('date')}\n"
            f"- **Длительность:** {call.get('duration')} сек\n"
            f"- **Кратко:** {summary}\n"
        )
else:
    print("Нет значимых звонков за вчера.")
