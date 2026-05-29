#!/usr/bin/env python3
"""
 daily_summary_top5_clean.py – выводит общее количество звонков за вчера
 и пять самых значимых звонков (по длительности и ключевым признакам).
 Требования: только стандартная библиотека Python; при наличии `requests` и `.env`
 будет попытка подстановки имён менеджеров, иначе используется ID.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Попытка импортировать необязательные пакеты
try:
    import requests  # noqa: F401
except ImportError:
    requests = None
    print("⚠️  requests не установлен – имена менеджеров не будут определены.")

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # .env может отсутствовать – продолжаем без него
    pass

# ------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .. (freelance-2026)
DATA_DIR = PROJECT_ROOT / "ai-eggs" / "data"
EXTRACTED_JSON = DATA_DIR / "extracted_wisdom_clean.json"
BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL")
BITRIX_TOKEN = os.getenv("BITRIX24_TOKEN")

def get_manager_names() -> dict:
    """Получить словарь manager_id → "Имя Фамилия" через Bitrix API.
    Если запрос не удался, вернуть пустой словарь.
    """
    if not requests or not BITRIX_URL:
        return {}
    try:
        resp = requests.get(f"{BITRIX_URL}user.get.json", params={"auth": BITRIX_TOKEN}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return {}
    except Exception:
        return {}
    mapping = {}
    for u in data.get("result", []):
        uid = str(u.get("ID"))
        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        mapping[uid] = name if name else f"ID_{uid}"
    return mapping

def is_significant(call: dict) -> bool:
    """Определяет, является ли звонок значимым.
    - Длительность > 120 сек
    - В резюме есть ключевые слова
    """
    duration = int(call.get("duration", "0"))
    if duration > 120:
        return True
    transcript = call.get("transcript", "")
    m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\\n\\n|$)", transcript, re.DOTALL)
    if not m:
        return False
    summary = m.group(1).lower()
    keywords = ["груб", "негатив", "проблем", "требуется уточн"]
    return any(kw in summary for kw in keywords)

def extract_summary(transcript: str) -> str:
    """Вернуть текст блока РЕЗЮМЕ (одной строкой) или пустую строку, если нет.
    """
    m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\\n\\n|$)", transcript, re.DOTALL)
    if not m:
        return ""
    return re.sub(r"\\s+", " ", m.group(1).strip())

# -------------------- Основная логика --------------------
# Вчерашняя дата (по Москве)
TZ = timezone(timedelta(hours=3))
today = datetime.now(TZ).date()
yesterday = today - timedelta(days=1)

# Загрузка звонков
with open(EXTRACTED_JSON, "r", encoding="utf-8") as f:
    calls = json.load(f)

# Фильтрация по дате
calls_yesterday = [c for c in calls if datetime.fromisoformat(c["date"]).date() == yesterday]

total_calls = len(calls_yesterday)

# Выбираем значимые (с резюме)
significant = [c for c in calls_yesterday if is_significant(c)]
# Сортируем по длительности по убыванию
significant.sort(key=lambda x: int(x.get("duration", "0")), reverse=True)

# Оставляем только те, у которых есть резюме (extract_summary != "")
top5_candidates = []
for c in significant:
    if extract_summary(c.get("transcript", "")):
        top5_candidates.append(c)
    if len(top5_candidates) >= 5:
        break

manager_names = get_manager_names()

# -------------------- Вывод --------------------
print(f"# Сводка за {yesterday}\n")
print(f"**Всего звонков:** {total_calls}\n")
if top5_candidates:
    print("## Топ‑5 значимых звонков\n")
    for idx, call in enumerate(top5_candidates, 1):
        manager_id = str(call.get("manager_id", ""))
        manager = manager_names.get(manager_id, f"ID_{manager_id}")
        summary = extract_summary(call.get("transcript", ""))
        print(
            f"### {idx}. Звонок {call.get('call_id', '-')} – менеджер {manager}\n"
            f"- **Дата:** {call.get('date')}\n"
            f"- **Длительность:** {call.get('duration')} сек\n"
            f"- **Кратко:** {summary}\n"
        )
else:
    print("Нет значимых звонков с резюме за вчера.")
