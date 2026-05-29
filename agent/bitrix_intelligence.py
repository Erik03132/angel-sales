#!/usr/bin/env python3
"""
🕵️ Заботкина — Разведывательный модуль Битрикс24.
Собирает данные из ВСЕХ разделов CRM и формирует полную картину.

Запуск: каждые 2 часа через chat_listener или отдельно через PM2.
v1.0 — 05.05.2026
"""
import json
import os
import sys
from datetime import datetime

import requests

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(AGENT_DIR)
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

sys.path.insert(0, AGENT_DIR)
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
INTEL_PATH = os.path.join(DATA_DIR, 'intelligence_digest.json')
INTEL_MD_PATH = os.path.join(DATA_DIR, 'intelligence_digest.md')
KNOWLEDGE_PATH = os.path.join(DATA_DIR, 'expert_knowledge.md')

# Карта менеджеров (ID → имя)
MANAGERS = {}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def bx_post(method, params=None):
    """POST-запрос к Bitrix24 REST API."""
    try:
        resp = requests.post(f"{BITRIX_URL}/{method}", json=params or {}, timeout=20)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"  API error ({method}): {e}")
    return {}


def bx_get_all(method, params=None, key="result", limit=200):
    """Получить все записи с пагинацией (до limit)."""
    params = params or {}
    params["start"] = 0
    all_items = []
    max_iterations = 50  # защита от бесконечного цикла при сбое API
    for _ in range(max_iterations):
        data = bx_post(method, params)
        items = data.get(key, [])
        if isinstance(items, dict):
            items = items.get("tasks", items.get("items", []))
        all_items.extend(items)
        next_page = data.get("next")
        if len(all_items) >= limit or not next_page:
            break
        params["start"] = next_page
    return all_items[:limit]


# === СБОР ДАННЫХ ===

def load_managers():
    """Загружает карту сотрудников."""
    global MANAGERS
    users = bx_post("user.get", {"ACTIVE": True}).get("result", [])
    for u in users:
        uid = str(u.get("ID", ""))
        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        pos = u.get("WORK_POSITION", "")
        MANAGERS[uid] = {"name": name, "position": pos}
    log(f"👥 Сотрудников: {len(MANAGERS)}")
    return MANAGERS


def get_manager_name(uid):
    return MANAGERS.get(str(uid), {}).get("name", f"ID:{uid}")


def scan_deals():
    """Сканирует сделки: новые за сегодня, по стадиям, по менеджерам."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Новые сделки за сегодня
    new_deals = bx_post("crm.deal.list", {
        "filter": {">DATE_CREATE": f"{today}T00:00:00"},
        "select": ["ID", "TITLE", "STAGE_ID", "ASSIGNED_BY_ID", "OPPORTUNITY"],
        "order": {"ID": "DESC"}
    })
    new_list = new_deals.get("result", []) if new_deals else []
    new_total = new_deals.get("total", 0) if new_deals else 0
    
    # Сводка по менеджерам (последние 50 сделок)
    recent_data = bx_post("crm.deal.list", {
        "select": ["ID", "STAGE_ID", "ASSIGNED_BY_ID", "OPPORTUNITY"],
        "order": {"ID": "DESC"},
        "start": 0
    })
    recent = recent_data.get("result", []) if recent_data else []
    
    by_manager = {}
    for d in recent:
        mid = str(d.get("ASSIGNED_BY_ID", "?"))
        name = get_manager_name(mid)
        if name not in by_manager:
            by_manager[name] = {"count": 0, "sum": 0, "stages": {}}
        by_manager[name]["count"] += 1
        try:
            by_manager[name]["sum"] += float(d.get("OPPORTUNITY", 0) or 0)
        except (ValueError, TypeError):
            pass
        stage = d.get("STAGE_ID", "?")
        by_manager[name]["stages"][stage] = by_manager[name]["stages"].get(stage, 0) + 1
    
    return {
        "new_today": new_total,
        "new_deals": [{"id": d["ID"], "title": d.get("TITLE", ""), "sum": d.get("OPPORTUNITY", "0"),
                       "manager": get_manager_name(d.get("ASSIGNED_BY_ID", ""))} for d in new_list[:10]],
        "by_manager": by_manager
    }


def scan_calls():
    """Статистика звонков за сегодня."""
    today = datetime.now().strftime("%Y-%m-%d")
    data = bx_post("voximplant.statistic.get", {
        "FILTER": {">CALL_START_DATE": f"{today}T00:00:00"},
        "ORDER": {"ID": "DESC"}
    })
    calls = data.get("result", [])
    total = data.get("total", 0)
    
    by_user = {}
    total_duration = 0
    for c in calls:
        uid = str(c.get("PORTAL_USER_ID", "?"))
        name = get_manager_name(uid)
        dur = int(c.get("CALL_DURATION", 0) or 0)
        total_duration += dur
        if name not in by_user:
            by_user[name] = {"calls": 0, "duration": 0, "answered": 0}
        by_user[name]["calls"] += 1
        by_user[name]["duration"] += dur
        if dur > 0:
            by_user[name]["answered"] += 1
    
    return {"total": total, "total_duration": total_duration, "by_manager": by_user}


def scan_tasks():
    """Задачи: просроченные и активные."""
    data = bx_post("tasks.task.list", {
        "select": ["ID", "TITLE", "STATUS", "RESPONSIBLE_ID", "DEADLINE", "CREATED_DATE"],
        "order": {"ID": "desc"}
    })
    tasks = data.get("result", {}).get("tasks", [])
    
    overdue = []
    active = []
    now = datetime.now()
    for t in tasks:
        status = int(t.get("status", 0))
        if status in (4, 5):  # завершена/отложена
            continue
        deadline = t.get("deadline", "")
        resp = get_manager_name(t.get("responsibleId", ""))
        task_info = {"id": t["id"], "title": t.get("title", "")[:60], "responsible": resp, "deadline": deadline}
        if deadline and deadline < now.isoformat():
            overdue.append(task_info)
        else:
            active.append(task_info)
    
    return {"overdue": overdue, "active": active[:10], "total": len(tasks)}


def scan_timeman():
    """Кто сейчас на работе."""
    online = []
    for uid, info in MANAGERS.items():
        if uid == "41624":  # Пропускаем саму Анжелочку
            continue
        try:
            data = bx_post("timeman.status", {"USER_ID": uid})
            status = data.get("result", {}).get("STATUS", "CLOSED")
            if status == "OPENED":
                online.append(info["name"])
        except Exception:
            pass
    return {"online": online, "total_staff": len(MANAGERS) - 1}


def scan_new_contacts():
    """Новые контакты за сегодня."""
    today = datetime.now().strftime("%Y-%m-%d")
    data = bx_post("crm.contact.list", {
        "filter": {">DATE_CREATE": f"{today}T00:00:00"},
        "select": ["ID", "NAME", "LAST_NAME", "SOURCE_ID"],
        "order": {"ID": "DESC"}
    })
    contacts = data.get("result", [])
    total_new = data.get("total", 0)
    return {
        "new_today": total_new,
        "contacts": [{"id": c["ID"], "name": f"{c.get('NAME','')} {c.get('LAST_NAME','')}".strip(),
                      "source": c.get("SOURCE_ID", "?")} for c in contacts[:10]]
    }


def scan_activities():
    """Последние активности (звонки, письма, встречи)."""
    data = bx_post("crm.activity.list", {
        "select": ["ID", "SUBJECT", "TYPE_ID", "COMPLETED", "RESPONSIBLE_ID", "CREATED"],
        "order": {"ID": "DESC"},
        "filter": {">ID": 0}
    })
    acts = data.get("result", [])
    total = data.get("total", 0)
    
    type_names = {"1": "📧 Письмо", "2": "📞 Звонок", "3": "📅 Встреча", "6": "💬 Чат"}
    
    return {
        "total": total,
        "recent": [{"id": a["ID"], "type": type_names.get(str(a.get("TYPE_ID", "")), f"тип:{a.get('TYPE_ID', '?')}"),
                    "subject": a.get("SUBJECT", "")[:50], "done": a.get("COMPLETED", "N"),
                    "who": get_manager_name(a.get("RESPONSIBLE_ID", ""))} for a in acts[:10]]
    }


# === ГЕНЕРАЦИЯ ДАЙДЖЕСТА ===

def build_digest():
    """Собирает полный разведывательный дайджест."""
    log("🕵️ НАЧИНАЮ РАЗВЕДКУ БИТРИКС24...")
    
    load_managers()
    
    digest = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    
    log("  📊 Сканирую сделки...")
    digest["deals"] = scan_deals()
    
    log("  📞 Сканирую звонки...")
    digest["calls"] = scan_calls()
    
    log("  📋 Сканирую задачи...")
    digest["tasks"] = scan_tasks()
    
    log("  👥 Проверяю рабочее время...")
    digest["timeman"] = scan_timeman()
    
    log("  🆕 Новые контакты...")
    digest["contacts"] = scan_new_contacts()
    
    log("  📌 Последние активности...")
    digest["activities"] = scan_activities()
    
    return digest


def digest_to_markdown(d):
    """Конвертирует дайджест в читаемый Markdown."""
    lines = [f"# 🕵️ Разведка Битрикс24 — {d['date']}\n"]
    
    # Сделки
    deals = d.get("deals", {})
    lines.append("## 📊 Сделки")
    lines.append(f"Новых сегодня: **{deals.get('new_today', 0)}**\n")
    if deals.get("by_manager"):
        lines.append("| Менеджер | Сделок | Сумма |")
        lines.append("|----------|--------|-------|")
        for name, info in deals["by_manager"].items():
            lines.append(f"| {name} | {info['count']} | {info['sum']:.0f}₽ |")
    lines.append("")
    
    # Звонки
    calls = d.get("calls", {})
    lines.append(f"## 📞 Звонки сегодня: {calls.get('total', 0)}")
    if calls.get("by_manager"):
        lines.append("| Менеджер | Звонков | Ответивших | Пропущенных | Время |")
        lines.append("|----------|----------|------------|-------------|------|")
        for name, info in calls["by_manager"].items():
            mins = info["duration"] // 60
            lines.append(f"| {name} | {info['calls']} | {info.get('answered', 0)} | {info.get('missed', 0)} | {mins} мин |")
    lines.append("")
    
    # Задачи
    tasks = d.get("tasks", {})
    overdue = tasks.get("overdue", [])
    lines.append(f"## 📋 Задачи (всего: {tasks.get('total', 0)})")
    if overdue:
        lines.append(f"### ⚠️ Просроченных: {len(overdue)}")
        for t in overdue[:5]:
            lines.append(f"- **{t['title']}** → {t['responsible']} (дедлайн: {t.get('deadline', '?')[:10]})")
    lines.append("")
    
    # Рабочее время
    tm = d.get("timeman", {})
    online = tm.get("online", [])
    lines.append(f"## 👥 На работе: {len(online)}/{tm.get('total_staff', '?')}")
    if online:
        lines.append(f"Сейчас: {', '.join(online)}")
    else:
        lines.append("Никого нет на месте")
    lines.append("")
    
    # Контакты
    contacts = d.get("contacts", {})
    lines.append(f"## 🆕 Новые контакты сегодня: {contacts.get('new_today', 0)}")
    lines.append("")
    
    # Активности
    acts = d.get("activities", {})
    lines.append(f"## 📌 Активности (всего: {acts.get('total', 0)})")
    for a in acts.get("recent", [])[:5]:
        done = "✅" if a.get("done") == "Y" else "⏳"
        lines.append(f"- {done} {a['type']} {a.get('subject', '')} — {a.get('who', '?')}")
    
    return "\n".join(lines)


def save_digest(digest):
    """Сохраняет дайджест в JSON и MD."""
    with open(INTEL_PATH, 'w', encoding='utf-8') as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)
    
    md = digest_to_markdown(digest)
    with open(INTEL_MD_PATH, 'w', encoding='utf-8') as f:
        f.write(md)
    
    # Дописываем ключевые факты в expert_knowledge
    try:
        deals = digest.get("deals", {})
        calls = digest.get("calls", {})
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(KNOWLEDGE_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n\n--- Разведка {ts} ---")
            f.write(f"\n- [разведка] Новых сделок сегодня: {deals.get('new_today', 0)}")
            f.write(f"\n- [разведка] Звонков сегодня: {calls.get('total', 0)}")
            overdue = digest.get("tasks", {}).get("overdue", [])
            if overdue:
                f.write(f"\n- [разведка] Просроченных задач: {len(overdue)}")
            online = digest.get("timeman", {}).get("online", [])
            if online:
                f.write(f"\n- [разведка] На работе: {', '.join(online)}")
    except Exception as e:
        log(f"  ⚠️ Ошибка записи в knowledge: {e}")
    
    log(f"💾 Дайджест сохранён: {INTEL_MD_PATH}")


def run_intelligence():
    """Главная функция — запуск полной разведки."""
    if not BITRIX_URL:
        print("❌ PRODUCTION_BITRIX_WEBHOOK_URL не задан!")
        return None
    
    digest = build_digest()
    save_digest(digest)
    
    log("✅ РАЗВЕДКА ЗАВЕРШЕНА")
    
    # Краткая сводка
    d = digest.get("deals", {})
    c = digest.get("calls", {})
    t = digest.get("tasks", {})
    log(f"   Сделок новых: {d.get('new_today', 0)} | Звонков: {c.get('total', 0)} | "
        f"Задач просроч.: {len(t.get('overdue', []))}")
    
    return digest


if __name__ == "__main__":
    run_intelligence()
