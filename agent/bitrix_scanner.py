"""
Bitrix24 Scanner — «Тихий Наблюдатель» Анжелочки
Сканирует новые сделки, звонки, задачи и товары.
Запускается каждые 3 часа через cron.
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")
DATA_DIR = os.path.join(BASE_DIR, "data")
SCAN_STATE_FILE = os.path.join(DATA_DIR, "scan_state.json")
SCAN_LOG_DIR = os.path.join(DATA_DIR, "bitrix_scans")
os.makedirs(SCAN_LOG_DIR, exist_ok=True)

# === Фильтр стадий сделок (v2: исправлено 15.04.2026) ===
# Закрытые/терминальные стадии — НЕ считать забытыми
CLOSED_STAGES = {
    "WON", "LOSE", "7", "APOLOGY", "6", "2", "4", "5", "10", "12", "13"
}
# Активные стадии — заказ в работе, менеджер не забыл
ACTIVE_STAGES = {
    "UC_P1MPTA", "EXECUTING", "9", "3", "11", "UC_FNNB7I", "UC_44FPH8"
}
# Только ЭТИ стадии = действительно забытые (клиент ждёт)
TRULY_FORGOTTEN_STAGES = {"NEW", "8"}

# --- Helpers ---

def bitrix_call(method, params=None):
    """Вызов Bitrix24 REST API."""
    url = f"{BITRIX_URL}/{method}"
    try:
        resp = requests.get(url, params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"  ⚠️ Bitrix {method}: HTTP {resp.status_code}")
            return {}
    except Exception as e:
        print(f"  ⚠️ Bitrix {method} error: {e}")
        return {}


def bitrix_list_all(method, params=None, max_items=500):
    """Пагинация Bitrix (по 50 записей за раз)."""
    params = params or {}
    all_items = []
    start = 0
    while True:
        params["start"] = start
        data = bitrix_call(method, params)
        items = data.get("result", [])
        # Для tasks.task.list результат вложен
        if isinstance(items, dict) and "tasks" in items:
            items = items["tasks"]
        all_items.extend(items)
        if len(all_items) >= max_items or data.get("next") is None:
            break
        start = data["next"]
        time.sleep(0.3)  # Не превышаем rate limit
    return all_items


def load_scan_state():
    if os.path.exists(SCAN_STATE_FILE):
        with open(SCAN_STATE_FILE, 'r') as f:
            return json.load(f)
    return {"last_scan": None}


def save_scan_state(state):
    with open(SCAN_STATE_FILE, 'w') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# --- Scanners ---

def scan_deals(since):
    """Новые сделки с момента последнего сканирования."""
    print("📊 Сканирую сделки...")
    params = {
        "order[ID]": "DESC",
        "select[]": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "ASSIGNED_BY_ID", 
                      "DATE_CREATE", "CONTACT_ID", "COMPANY_ID", "COMMENTS", "CLOSED"],
    }
    if since:
        params["filter[>=DATE_CREATE]"] = since

    deals = bitrix_list_all("crm.deal.list.json", params, max_items=200)
    print(f"  ✅ Найдено {len(deals)} сделок")
    return deals


def scan_activities(since):
    """Активности: звонки, SMS, чаты, формы. Классификация по TYPE_ID + PROVIDER_ID."""
    print("📞 Сканирую активности...")
    params = {
        "order[ID]": "DESC",
        "select[]": ["ID", "TYPE_ID", "PROVIDER_ID", "PROVIDER_TYPE_ID", "SUBJECT", 
                      "DESCRIPTION", "RESPONSIBLE_ID", "CREATED", "DIRECTION", 
                      "OWNER_ID", "OWNER_TYPE_ID"],
    }
    if since:
        params["filter[>=CREATED]"] = since

    activities = bitrix_list_all("crm.activity.list.json", params, max_items=500)
    
    # Классифицируем по TYPE_ID (основной) + PROVIDER_ID (уточняющий)
    calls = [a for a in activities if str(a.get("TYPE_ID")) == "2"]  # TYPE_ID=2 = звонок
    sms_raw = [a for a in activities if str(a.get("TYPE_ID")) == "6"]  # TYPE_ID=6 = SMS/чат
    emails = [a for a in activities if str(a.get("TYPE_ID")) == "1"]  # TYPE_ID=1 = email
    tasks = [a for a in activities if str(a.get("TYPE_ID")) == "4"]   # TYPE_ID=4 = задача
    
    # Разделяем TYPE_ID=6 на РЕАЛЬНЫЕ SMS и ЧАТЫ Открытых Линий
    chats_ol = [a for a in sms_raw if str(a.get("PROVIDER_ID")) == "IMOPENLINES_SESSION"]
    sms_real = [a for a in sms_raw if str(a.get("PROVIDER_ID")) == "CRM_SMS"]
    webforms = [a for a in activities if str(a.get("PROVIDER_ID")) == "CRM_WEBFORM"]
    other = [a for a in activities if str(a.get("TYPE_ID")) not in ("1", "2", "4", "6")]
    
    print(f"  ✅ Итого активностей: {len(activities)}")
    print(f"     📞 Звонков (TYPE_ID=2/VoxImplant): {len(calls)}")
    print(f"     💬 Чатов Открытых Линий: {len(chats_ol)}")
    print(f"     📱 SMS (настоящих): {len(sms_real)}")
    print(f"     📧 Email: {len(emails)}")
    print(f"     📋 Веб-формы: {len(webforms)}")
    print(f"     📄 Прочих: {len(other)}")
    
    return {
        "all": activities,
        "calls": calls,
        "chats_ol": chats_ol,
        "sms": sms_real,
        "emails": emails,
        "webforms": webforms,
        "other": other
    }


def scan_tasks(since):
    """Задачи менеджеров."""
    print("✅ Сканирую задачи...")
    params = {
        "order[ID]": "DESC",
        "select[]": ["ID", "TITLE", "STATUS", "RESPONSIBLE_ID", "CREATED_DATE", "CLOSED_DATE"],
    }
    if since:
        params["filter[>=CREATED_DATE]"] = since

    tasks = bitrix_list_all("tasks.task.list.json", params, max_items=100)
    
    open_tasks = [t for t in tasks if str(t.get("status")) in ("1", "2", "3")]
    closed_tasks = [t for t in tasks if str(t.get("status")) in ("4", "5")]
    
    print(f"  ✅ Найдено: {len(open_tasks)} открытых, {len(closed_tasks)} закрытых")
    return {"all": tasks, "open": open_tasks, "closed": closed_tasks}


def scan_products():
    """Товары и остатки (полный список)."""
    print("📦 Сканирую товары...")
    products = bitrix_list_all("crm.product.list.json", {
        "select[]": ["ID", "NAME", "PRICE", "CURRENCY_ID", "ACTIVE", "QUANTITY"]
    }, max_items=200)
    print(f"  ✅ Найдено {len(products)} товаров")
    return products


def scan_users():
    """Сотрудники."""
    print("👥 Сканирую сотрудников...")
    data = bitrix_call("user.get.json", {"ACTIVE": "true"})
    users = data.get("result", [])
    user_map = {}
    for u in users:
        uid = str(u.get("ID"))
        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
        user_map[uid] = name or f"User #{uid}"
    print(f"  ✅ Найдено {len(user_map)} сотрудников")
    return user_map


# --- Main scan ---

def run_scan():
    """Основной метод сканирования."""
    print(f"\n{'='*50}")
    print(f"🕵️ BITRIX SCANNER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    if not BITRIX_URL:
        print("❌ BITRIX_WEBHOOK_URL не настроен!")
        return None

    state = load_scan_state()
    since = state.get("last_scan")
    
    if since:
        print(f"📅 Сканирую изменения с: {since}")
    else:
        # Первый запуск — берём за последние 24 часа
        since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
        print(f"📅 Первый запуск — сканирую за последние 24ч с: {since}")

    # Сканируем
    users = scan_users()
    deals = scan_deals(since)
    activities = scan_activities(since)
    tasks = scan_tasks(since)
    products = scan_products()

    # Собираем результат
    scan_result = {
        "scan_time": datetime.now().isoformat(),
        "since": since,
        "users": users,
        "deals": {
            "count": len(deals),
            "items": deals[:50],  # Не храним больше 50 за раз
            "total_amount": sum(float(d.get("OPPORTUNITY", 0) or 0) for d in deals)
        },
        "activities": {
            "total": len(activities["all"]),
            "calls_count": len(activities["calls"]),
            "chats_ol_count": len(activities.get("chats_ol", [])),
            "sms_count": len(activities["sms"]),
            "emails_count": len(activities["emails"]),
            "webforms_count": len(activities.get("webforms", [])),
            "other_count": len(activities["other"]),
            "calls": activities["calls"][:30],
        },
        "tasks": {
            "open": len(tasks["open"]),
            "closed": len(tasks["closed"]),
            "items": tasks["all"][:20]
        },
        "products": {
            "count": len(products),
            "items": products,
            "low_stock": [p for p in products if p.get("QUANTITY") is not None and float(p.get("QUANTITY", 999)) < 10]
        }
    }

    # Статистика по менеджерам
    manager_stats = {}
    for deal in deals:
        mgr_id = str(deal.get("ASSIGNED_BY_ID", "?"))
        mgr_name = users.get(mgr_id, f"User #{mgr_id}")
        if mgr_name not in manager_stats:
            manager_stats[mgr_name] = {"deals": 0, "amount": 0}
        manager_stats[mgr_name]["deals"] += 1
        manager_stats[mgr_name]["amount"] += float(deal.get("OPPORTUNITY", 0) or 0)

    for act in activities["calls"]:
        mgr_id = str(act.get("RESPONSIBLE_ID", "?"))
        mgr_name = users.get(mgr_id, f"User #{mgr_id}")
        if mgr_name not in manager_stats:
            manager_stats[mgr_name] = {"deals": 0, "amount": 0}
        manager_stats[mgr_name]["calls"] = manager_stats[mgr_name].get("calls", 0) + 1

    scan_result["manager_stats"] = manager_stats

    # Забытые сделки (v2: только реально забытые стадии)
    forgotten = []
    for deal in deals:
        stage = deal.get("STAGE_ID", "")
        closed = deal.get("CLOSED", "N")
        if stage not in TRULY_FORGOTTEN_STAGES or closed == "Y":
            continue
        # Считаем дни тишины от DATE_CREATE (последняя известная дата)
        try:
            created = deal.get("DATE_CREATE", "")[:10]
            days = (datetime.now() - datetime.strptime(created, "%Y-%m-%d")).days
        except Exception:
            days = 0
        if days >= 3:
            mgr_id = str(deal.get("ASSIGNED_BY_ID", "?"))
            forgotten.append({
                "id": deal.get("ID"),
                "title": deal.get("TITLE", f"Сделка #{deal.get('ID')}"),
                "manager": users.get(mgr_id, f"User #{mgr_id}"),
                "amount": float(deal.get("OPPORTUNITY", 0) or 0),
                "days_silent": days,
                "stage": stage,
            })
    forgotten.sort(key=lambda x: x["amount"], reverse=True)
    scan_result["forgotten_deals"] = {
        "count": len(forgotten),
        "total_amount": sum(d["amount"] for d in forgotten),
        "deals": forgotten[:50]
    }
    if forgotten:
        print(f"  ⚠️ Забытых сделок (NEW/Ожид.предоплаты): {len(forgotten)} на {sum(d['amount'] for d in forgotten):,.0f}₽".replace(",", " "))

    # Сохраняем
    scan_file = os.path.join(SCAN_LOG_DIR, f"scan_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    with open(scan_file, 'w', encoding='utf-8') as f:
        json.dump(scan_result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n💾 Результат сохранён: {scan_file}")

    # Обновляем состояние
    state["last_scan"] = datetime.now().isoformat()
    save_scan_state(state)

    # Сводка
    print(f"\n📊 СВОДКА:")
    print(f"  Новых сделок: {scan_result['deals']['count']} (на {scan_result['deals']['total_amount']:.0f}₽)")
    print(f"  📞 Звонков: {scan_result['activities']['calls_count']}")
    print(f"  💬 Чатов ОЛ: {scan_result['activities']['chats_ol_count']}")
    print(f"  📱 SMS: {scan_result['activities']['sms_count']}")
    print(f"  📋 Веб-форм: {scan_result['activities']['webforms_count']}")
    print(f"  ✅ Задач: {scan_result['tasks']['open']} открытых, {scan_result['tasks']['closed']} закрытых")
    print(f"  📦 Товаров: {scan_result['products']['count']}")
    if scan_result['products']['low_stock']:
        print(f"  ⚠️ Мало на складе: {len(scan_result['products']['low_stock'])} позиций")

    return scan_result


if __name__ == "__main__":
    result = run_scan()
    if result:
        print(f"\n✅ Сканирование завершено успешно.")
