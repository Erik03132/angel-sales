#!/usr/bin/env python3
"""
generate_daily_report_with_summary.py
Автоматически формирует отчёт за вчера (2026‑04‑28) со
словесным резюме ярких звонков и SMS‑сообщений.

Требования:
    pip install python-dotenv tqdm requests

Файлы:
    data/extracted_wisdom_clean.json   – список звонков (получен ранее)
    data/shadow_learning/calls/*.json   – оригинальные транскрипты (опционально)
    .env                               – BITRIX_WEBHOOK_URL, BITRIX24_TOKEN

Вывод:
    reports/report_2026-04-28.md
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from tqdm import tqdm

# ------------------------------------------------------------
# Конфигурация
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .. (freelance-2026)
DATA_DIR = PROJECT_ROOT / "ai-eggs" / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

EXTRACTED_JSON = DATA_DIR / "extracted_wisdom_clean.json"
TIMEZONE_OFFSET = timedelta(hours=3)          # +03:00 (Москва)

# ------------------------------------------------------------
# Утилиты
# ------------------------------------------------------------
def load_env():
    """Загружает .env из корня проекта."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path)
    else:
        print("⚠️  .env не найден – понадобится BITRIX_WEBHOOK_URL/Token")
    return os.getenv("BITRIX_WEBHOOK_URL"), os.getenv("BITRIX24_TOKEN")

def bitrix_api(method: str, params: dict = None):
    """Обёртка для Bitrix‑24 REST API."""
    url, token = load_env()
    if not url:
        raise RuntimeError("BITRIX_WEBHOOK_URL не задан в .env")
    params = params or {}
    params["auth"] = token
    resp = requests.get(f"{url}{method}.json", params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Bitrix error {data['error_description']}")
    return data["result"]

def iso_to_dt(iso_str: str) -> datetime:
    """Конвертирует ISO‑строку в datetime с учётом +03:00."""
    return datetime.fromisoformat(iso_str).replace(tzinfo=timezone.utc).astimezone(
        timezone(TIMEZONE_OFFSET)
    )

def load_calls() -> list:
    """Читает список звонков из extracted_wisdom_clean.json."""
    with open(EXTRACTED_JSON, "r", encoding="utf-8") as f:
        return json.load(f)

def get_manager_names() -> dict:
    """Возвращает словарь manager_id → «Имя Фамилия»."""
    users = bitrix_api("user.get")
    mapping = {}
    for u in users:
        uid = str(u["ID"])
        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        mapping[uid] = name if name else f"ID_{uid}"
    return mapping

def extract_summary(transcript: str) -> str:
    """Находит блок «РЕЗЮМЕ:» в транскрипте и возвращает его (без лишних переносов)."""
    match = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\\n\\n|$)", transcript, re.DOTALL)
    if not match:
        return "Нет резюме"
    raw = match.group(1).strip()
    return re.sub(r"\s+", " ", raw)

def is_bright(call: dict) -> bool:
    """Определяет, считается ли звонок «ярким»."""
    duration = int(call.get("duration", "0"))
    if duration > 120:
        return True
    summary = call.get("_summary", "").lower()
    bad_keywords = ["груб", "такт", "негатив", "проблем", "требуется уточн"]
    return any(kw in summary for kw in bad_keywords)

def format_call_entry(call: dict, manager_name: str) -> str:
    """Возвращает markdown‑строку для одного яркого звонка."""
    call_id = call.get("call_id", "—")
    summary = call.get("_summary", "Нет резюме")
    return f"- **ID:** {call_id} — {manager_name}\n  - **Кратко:** {summary}"

def main():
    # 1️⃣ Дата «вчера»
    today = datetime.now(timezone(TIMEZONE_OFFSET)).date()
    yesterday = today - timedelta(days=1)
    date_str = yesterday.isoformat()

    # 2️⃣ Загрузка данных
    calls = load_calls()
    manager_names = get_manager_names()

    # 3️⃣ Фильтрация звонков за вчера
    calls_yesterday = [c for c in calls if iso_to_dt(c["date"]).date() == yesterday]

    # 4️⃣ Сбор статистики
    mgr_stats = defaultdict(lambda: {"calls": [], "sms": []})
    for call in calls_yesterday:
        mgr_id = str(call.get("manager_id", "0"))
        call["_summary"] = extract_summary(call.get("transcript", ""))
        mgr_stats[mgr_id]["calls"].append(call)

    # -----------------------------------------------------------------
    # Если хотите добавить SMS‑активности, раскомментируйте блок ниже
    # -----------------------------------------------------------------
    # try:
    #     sms_activities = bitrix_api(
    #         "crm.activity.list",
    #         {
    #             "filter[TYPE_ID]": "SMS",
    #             "filter[>=CREATED_TIME]": f"{date_str} 00:00:00",
    #             "filter[<CREATED_TIME]": f"{date_str} 23:59:59",
    #         },
    #     )
    #     for sms in sms_activities.get("result", []):
    #         mgr_id = str(sms.get("ASSIGNED_BY_ID", "0"))
    #         mgr_stats[mgr_id]["sms"].append({
    #             "from": sms.get("FROM", ""),
    #             "text": sms.get("DESCRIPTION", ""),
    #         })
    # except Exception as e:
    #     print(f"⚠️ Не удалось загрузить SMS: {e}")

    # 5️⃣ Формируем markdown‑отчёт
    lines = [
        f"# Ежедневный отчёт за {date_str}",
        "",
        "## Общие показатели",
        f"- Звонков: **{len(calls_yesterday)}**",
        f"- SMS‑сообщений: **{sum(len(v['sms']) for v in mgr_stats.values())}**",
        "",
        "## Менеджеры",
        "",
    ]

    for mgr_id, data in mgr_stats.items():
        name = manager_names.get(mgr_id, f"ID_{mgr_id}")
        num_calls = len(data["calls"])
        num_sms = len(data["sms"])
        lines.append(f"### {name} (ID {mgr_id})")
        lines.append(f"- Звонков: {num_calls}")
        lines.append(f"- SMS: {num_sms}")
        bright = [c for c in data["calls"] if is_bright(c)]
        if bright:
            lines.append("- **Яркие звонки**")
            for c in bright:
                lines.append(format_call_entry(c, name))
        else:
            lines.append("- Нет ярких звонков")
        if data["sms"]:
            lines.append("- **SMS‑сообщения**")
            for sms in data["sms"]:
                sender = sms["from"] or "Неизвестный"
                txt = sms["text"] or ""
                lines.append(f"  - **От:** {sender} → **Текст:** {txt}")
        lines.append("")

    report_path = REPORTS_DIR / f"report_{date_str}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ Отчёт записан в {report_path}")

if __name__ == "__main__":
    with tqdm(total=0, desc="Генерация отчёта", leave=False):
        main()
