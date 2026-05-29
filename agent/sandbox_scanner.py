#!/usr/bin/env python3
"""
Sandbox Scanner — «Наблюдатель» Анжелы Птенчиковой.
Сканирует задачи и события в Песочнице.
"""
import json
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# ПЕСОЧНИЦА
BITRIX_URL = os.getenv("SANDBOX_BITRIX_WEBHOOK_URL", "").rstrip("/")
DATA_DIR = os.path.join(BASE_DIR, "data")
SCAN_LOG_DIR = os.path.join(DATA_DIR, "sandbox_scans")
os.makedirs(SCAN_LOG_DIR, exist_ok=True)

def bitrix_call(method, params=None):
    url = f"{BITRIX_URL}/{method}"
    try:
        resp = requests.get(url, params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return {}
    except Exception as e:
        print(f"Error: {e}")
        return {}

def scan_sandbox():
    print(f"🕵️ SANDBOX SCANNER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. Сканируем участников (кто есть в песочнице)
    users_data = bitrix_call("user.get.json")
    users = {str(u['ID']): f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip() for u in users_data.get("result", [])}
    
    # 2. Сканируем задачи (самое важное для Птенчиковой)
    tasks_data = bitrix_call("tasks.task.list.json", {
        "select[]": ["ID", "TITLE", "STATUS", "CREATED_DATE", "DEADLINE", "RESPONSIBLE_ID", "DESCRIPTION"],
        "order[ID]": "DESC"
    })
    tasks = tasks_data.get("result", {}).get("tasks", [])
    
    # НОВОЕ: Сканируем чек-листы для каждой задачи
    for task in tasks:
        task_id = task.get("id") or task.get("ID")
        if task_id:
            checklist_data = bitrix_call("task.checklistitem.getlist.json", {"taskId": task_id})
            task["checklist"] = checklist_data.get("result", [])
    
    # 3. Сканируем ленту новостей
    feed_data = bitrix_call("log.blogpost.get.json")
    posts = feed_data.get("result", [])
    
    scan_result = {
        "scan_time": datetime.now().isoformat(),
        "users": users,
        "tasks_summary": {
            "count": len(tasks),
            "items": tasks[:20] # Последние 20 задач
        },
        "feed_summary": {
            "count": len(posts),
            "items": posts[:5] # Последние 5 постов
        },
        "persona": "Анжела Птенчикова",
        "context": "Песочница Bitrix24 (для планов и задач)"
    }
    
    # Сохраняем
    scan_file = os.path.join(SCAN_LOG_DIR, f"sandbox_scan_{datetime.now().strftime('%Y%p%m%d_%H%M')}.json")
    with open(scan_file, 'w', encoding='utf-8') as f:
        json.dump(scan_result, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Сканирование песочницы завершено. Найдено {len(tasks)} задач.")
    return scan_result

if __name__ == "__main__":
    scan_sandbox()
