#!/usr/bin/env python3
"""
🕵️ SHADOW MODE — Анжелочка учится у менеджеров.

Тихо сканирует:
- Сессии открытых линий (Telegram, Avito)
- Записи звонков (скачивает аудио, готовит для транскрипции)  
- Лиды и комментарии CRM

НЕ ПИШЕТ НИКОМУ! Только читает и сохраняет паттерны.

v1.0 — 15.04.2026
"""
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")

SHADOW_DIR = os.path.join(BASE_DIR, "data", "shadow_learning")
CALLS_DIR = os.path.join(SHADOW_DIR, "calls")
CHATS_DIR = os.path.join(SHADOW_DIR, "chats")
PATTERNS_DIR = os.path.join(SHADOW_DIR, "patterns")
for d in [SHADOW_DIR, CALLS_DIR, CHATS_DIR, PATTERNS_DIR]:
    os.makedirs(d, exist_ok=True)


def api(method, params=None):
    """Bitrix24 API call."""
    try:
        r = requests.get(f"{BITRIX_URL}/{method}", params=params or {}, timeout=30)
        return r.json()
    except Exception as e:
        print(f"  ❌ API error ({method}): {e}")
        return {"error": str(e)}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ============================================================
# 1. СБОР СЕССИЙ ОТКРЫТЫХ ЛИНИЙ
# ============================================================
def collect_open_line_sessions(days=30):
    """Собирает все сессии открытых линий за N дней."""
    log("📱 Сбор сессий открытых линий...")
    
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    all_sessions = []
    start = 0
    
    while True:
        result = api("crm.activity.list", {
            "order[ID]": "DESC",
            "select[]": ["ID", "SUBJECT", "TYPE_ID", "DESCRIPTION", "PROVIDER_ID", 
                         "RESPONSIBLE_ID", "CREATED", "OWNER_ID", "OWNER_TYPE_ID",
                         "COMMUNICATIONS"],
            "filter[PROVIDER_ID]": "IMOPENLINES_SESSION",
            "filter[>CREATED]": since,
            "start": start
        })
        
        items = result.get("result", [])
        if not items:
            break
            
        all_sessions.extend(items)
        start += 50
        
        if start >= result.get("total", 0):
            break
    
    log(f"  Найдено {len(all_sessions)} сессий")
    
    # Сохраняем
    output = os.path.join(CHATS_DIR, f"open_lines_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(all_sessions, f, ensure_ascii=False, indent=2)
    
    # Анализируем каналы
    channels = {}
    for s in all_sessions:
        subj = s.get("SUBJECT", "")
        if "Telegram" in subj:
            channels["Telegram"] = channels.get("Telegram", 0) + 1
        elif "Avito" in subj or "Авито" in subj:
            channels["Avito"] = channels.get("Avito", 0) + 1
        elif "VK" in subj or "ВК" in subj:
            channels["VK"] = channels.get("VK", 0) + 1
        else:
            channels["Другое"] = channels.get("Другое", 0) + 1
    
    log(f"  Каналы: {json.dumps(channels, ensure_ascii=False)}")
    return all_sessions


# ============================================================
# 2. СБОР ЗАПИСЕЙ ЗВОНКОВ
# ============================================================
def collect_calls(days=14):
    """Собирает записи звонков."""
    log("📞 Сбор записей звонков...")
    
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    result = api("voximplant.statistic.get", {
        "FILTER[>CALL_START_DATE]": since,
        "SORT": "CALL_START_DATE",
        "ORDER": "DESC"
    })
    
    calls = result.get("result", [])
    log(f"  Найдено {len(calls)} звонков")
    
    # Фильтруем значимые (>30 сек)
    meaningful = [c for c in calls if int(c.get("CALL_DURATION", 0)) > 30]
    log(f"  Значимых (>30 сек): {len(meaningful)}")
    
    # Собираем аудиофайлы
    records = []
    for c in meaningful:
        file_id = c.get("RECORD_FILE_ID")
        if file_id:
            records.append({
                "call_id": c.get("ID"),
                "date": c.get("CALL_START_DATE"),
                "duration": c.get("CALL_DURATION"),
                "phone": c.get("PHONE_NUMBER"),
                "manager_id": c.get("PORTAL_USER_ID"),
                "direction": "входящий" if c.get("CALL_TYPE") == "1" else "исходящий",
                "record_file_id": file_id
            })
    
    log(f"  С аудиозаписями: {len(records)}")
    
    # Сохраняем метаданные
    output = os.path.join(CALLS_DIR, f"calls_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    
    return records


# ============================================================
# 3. СБОР ЛИДОВ (с AI-резюме от BitrixGPT)
# ============================================================
def collect_leads(days=30):
    """Собирает лиды с комментариями BitrixGPT."""
    log("📋 Сбор лидов...")
    
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    all_leads = []
    start = 0
    
    while True:
        result = api("crm.lead.list", {
            "order[ID]": "DESC",
            "select[]": ["ID", "TITLE", "NAME", "SOURCE_ID", "COMMENTS", 
                         "STATUS_ID", "ASSIGNED_BY_ID", "DATE_CREATE"],
            "filter[>DATE_CREATE]": since,
            "start": start
        })
        
        items = result.get("result", [])
        if not items:
            break
            
        all_leads.extend(items)
        start += 50
        
        if start >= result.get("total", 0):
            break
    
    log(f"  Найдено {len(all_leads)} лидов")
    
    # Считаем лиды с GPT-резюме
    with_gpt = [l for l in all_leads if l.get("COMMENTS") and "BitrixGPT" in str(l.get("COMMENTS", ""))]
    log(f"  С AI-резюме: {len(with_gpt)}")
    
    # Сохраняем
    output = os.path.join(SHADOW_DIR, f"leads_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(all_leads, f, ensure_ascii=False, indent=2)
    
    return all_leads


# ============================================================
# 4. ИЗВЛЕЧЕНИЕ ПАТТЕРНОВ ПРОДАЖ
# ============================================================
def extract_patterns(sessions, leads):
    """Извлекает паттерны из собранных данных."""
    log("🧠 Анализ паттернов...")
    
    patterns = {
        "generated": datetime.now().isoformat(),
        "total_sessions": len(sessions),
        "total_leads": len(leads),
        "channels": {},
        "popular_products": {},
        "common_questions": [],
        "lead_sources": {},
        "manager_activity": {}
    }
    
    # Анализ каналов
    for s in sessions:
        subj = s.get("SUBJECT", "")
        for ch in ["Telegram", "Avito", "VK", "WhatsApp"]:
            if ch in subj:
                patterns["channels"][ch] = patterns["channels"].get(ch, 0) + 1
    
    # Анализ лидов (продукты)
    product_keywords = {
        "бройлер": 0, "кобб": 0, "росс": 0, "несушка": 0, 
        "индюш": 0, "гус": 0, "ут": 0, "перепел": 0, "мулард": 0
    }
    for l in leads:
        title = (l.get("TITLE", "") + " " + (l.get("COMMENTS") or "")).lower()
        for keyword in product_keywords:
            if keyword in title:
                product_keywords[keyword] += 1
    patterns["popular_products"] = {k: v for k, v in sorted(product_keywords.items(), key=lambda x: -x[1]) if v > 0}
    
    # Источники лидов
    for l in leads:
        src = l.get("SOURCE_ID", "UNKNOWN")
        patterns["lead_sources"][src] = patterns["lead_sources"].get(src, 0) + 1
    
    # Активность менеджеров
    for s in sessions:
        mgr = str(s.get("RESPONSIBLE_ID", "?"))
        patterns["manager_activity"][mgr] = patterns["manager_activity"].get(mgr, 0) + 1
    
    # Сохраняем
    output = os.path.join(PATTERNS_DIR, f"patterns_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)
    
    log(f"  Каналы: {patterns['channels']}")
    log(f"  Популярные продукты: {patterns['popular_products']}")
    log(f"  Источники: {patterns['lead_sources']}")
    
    return patterns


# ============================================================
# MAIN
# ============================================================
def run_shadow_scan():
    """Полный цикл тихого сканирования."""
    log("=" * 50)
    log("🕵️ SHADOW MODE — Анжелочка учится")
    log("   ⚠️ ТОЛЬКО ЧТЕНИЕ! Никаких сообщений!")
    log("=" * 50)
    
    sessions = collect_open_line_sessions(days=30)
    calls = collect_calls(days=14)
    leads = collect_leads(days=30)
    patterns = extract_patterns(sessions, leads)
    
    log("")
    log("📊 ИТОГИ РАЗВЕДКИ:")
    log(f"   📱 Сессий ОЛ: {len(sessions)}")
    log(f"   📞 Звонков: {len(calls)}")
    log(f"   📋 Лидов: {len(leads)}")
    log(f"   🔝 Топ продукт: {list(patterns['popular_products'].keys())[:3]}")
    log(f"   💾 Данные: {SHADOW_DIR}")
    log("")
    log("🎯 NEXT: Транскрибировать аудио → Извлечь скрипты продаж")
    
    return {
        "sessions": len(sessions),
        "calls": len(calls),
        "leads": len(leads),
        "patterns": patterns
    }


if __name__ == "__main__":
    run_shadow_scan()
