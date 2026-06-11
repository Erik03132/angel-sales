"""
Bitrix24 Scanner — «Тихий Наблюдатель» Анжелочки
Сканирует новые сделки, звонки, задачи и товары.
Запускается каждые 3 часа через cron.
"""
import json
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", os.getenv("BITRIX_WEBHOOK_URL", "")).rstrip("/")
DATA_DIR = os.path.join(BASE_DIR, "data")
SCAN_STATE_FILE = os.path.join(DATA_DIR, "scan_state.json")
SCAN_LOG_DIR = os.path.join(DATA_DIR, "bitrix_scans")
os.makedirs(SCAN_LOG_DIR, exist_ok=True)

# === Фильтр стадий сделок (v2: исправлено 15.04.2026) ===
# Закрытые/терминальные стадии — НЕ считать забытыми
CLOSED_STAGES = frozenset({
    "WON", "LOSE", "7", "APOLOGY", "6", "2", "4", "5", "10", "12", "13"
})
# Активные стадии — заказ в работе, менеджер не забыл
ACTIVE_STAGES = {
    "UC_P1MPTA", "EXECUTING", "9", "3", "11", "UC_FNNB7I", "UC_44FPH8"
}
# Только ЭТИ стадии = действительно забытые (клиент ждёт)
TRULY_FORGOTTEN_STAGES = {"NEW", "8"}

# --- Helpers ---

def get_deal_amount(deal: dict) -> tuple:
    """SSoT: сумма сделки с приоритетом данных 1С.
    
    Правило (SSOT_REPORTS.md, 11.06.2026):
    1. Если есть UF_CRM_1641882450 (факт оплаты из 1С) → берём его
    2. Иначе → OPPORTUNITY (план из Bitrix)
    
    Returns: (amount: float, source: str)
    """
    paid_1c = deal.get("UF_CRM_1641882450", "")
    if paid_1c:
        try:
            val = float(str(paid_1c).replace(" ", "").replace(",", "."))
            if val > 0:
                return val, "1С"
        except (ValueError, TypeError):
            pass
    opp = float(deal.get("OPPORTUNITY", 0) or 0)
    return opp, "Bitrix"

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
    """Новые сделки с момента последнего сканирования.
    
    Включает поля 1С: номер заказа, оплата, организация.
    """
    print("📊 Сканирую сделки...")
    params = {
        "order[ID]": "DESC",
        "select[]": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY", "ASSIGNED_BY_ID", 
                      "DATE_CREATE", "CONTACT_ID", "COMPANY_ID", "COMMENTS", "CLOSED",
                      "SOURCE_ID",
                      # Поля 1С
                      "UF_CRM_3713038619599",  # Номер 1С
                      "UF_CRM_3713038619596",  # Удалён в 1С
                      "UF_CRM_3713038619602",  # Организация
                      "UF_CRM_1641882420",     # Уже оплачено
                      "UF_CRM_1641882450",     # Сумма оплаты
                      "UF_CRM_1773835772534",  # Номер оплаты
                      "UF_CRM_1773923024769",  # Номер Заказа
                      # Доставка
                      "UF_CRM_1557837472437",  # Адрес доставки
                      "UF_CRM_1557837504964",  # Дата доставки
                      ],
    }
    if since:
        params["filter[>=DATE_CREATE]"] = since

    deals = bitrix_list_all("crm.deal.list.json", params, max_items=200)
    print(f"  ✅ Найдено {len(deals)} сделок")
    return deals


def scan_product_rows(deal_ids):
    """Товарные строки для сделок (что конкретно купили).
    
    Использует batch для экономии API-лимитов.
    """
    if not deal_ids:
        return {}
    
    print(f"🐔 Сканирую товарные строки ({len(deal_ids)} сделок)...")
    all_rows = {}  # {deal_id: [rows]}
    
    for i in range(0, len(deal_ids), 50):
        batch = deal_ids[i:i+50]
        batch_cmd = {}
        for did in batch:
            batch_cmd[f"deal_{did}"] = f"crm.deal.productrows.get?id={did}"
        
        data = bitrix_call("batch.json", {
            "halt": 0,
            **{f"cmd[{k}]": v for k, v in batch_cmd.items()}
        })
        
        results = data.get("result", {}).get("result", {})
        for key, rows in results.items():
            if isinstance(rows, list):
                did = key.replace("deal_", "")
                all_rows[did] = rows
        
        if i + 50 < len(deal_ids):
            time.sleep(0.5)
    
    total_rows = sum(len(r) for r in all_rows.values())
    print(f"  ✅ Найдено {total_rows} товарных строк")
    return all_rows


def scan_activities(since):
    """Активности: звонки, SMS, чаты, формы. Классификация по TYPE_ID + PROVIDER_ID."""
    print("📞 Сканирую активности...")
    params = {
        "order[ID]": "DESC",
        "select[]": ["ID", "TYPE_ID", "PROVIDER_ID", "PROVIDER_TYPE_ID", "SUBJECT", 
                      "DESCRIPTION", "RESPONSIBLE_ID", "CREATED", "DIRECTION", 
                      "OWNER_ID", "OWNER_TYPE_ID", "DURATION", "RESULT_STATUS"],
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


def resolve_contacts(contact_ids):
    """Резолвит CONTACT_ID → ФИО покупателя через crm.contact.get.
    
    Использует batch-запросы (до 50 за раз) для экономии API-лимитов.
    """
    if not contact_ids:
        return {}
    
    unique_ids = list(set(str(cid) for cid in contact_ids if cid))
    print(f"👤 Резолвлю имена контактов ({len(unique_ids)} уник.)...")
    
    contacts = {}  # {contact_id: "Имя Фамилия"}
    
    # Батчим по 50 (лимит Bitrix batch)
    for i in range(0, len(unique_ids), 50):
        batch = unique_ids[i:i+50]
        # Формируем batch-запрос
        batch_cmd = {}
        for cid in batch:
            batch_cmd[f"contact_{cid}"] = f"crm.contact.get?ID={cid}"
        
        data = bitrix_call("batch.json", {
            "halt": 0,
            **{f"cmd[{k}]": v for k, v in batch_cmd.items()}
        })
        
        results = data.get("result", {}).get("result", {})
        for key, contact in results.items():
            if isinstance(contact, dict):
                cid = str(contact.get("ID", ""))
                name = contact.get("NAME", "")
                last = contact.get("LAST_NAME", "")
                full_name = f"{name} {last}".strip()
                if full_name:
                    contacts[cid] = full_name
        
        if i + 50 < len(unique_ids):
            time.sleep(0.5)  # Rate limit
    
    print(f"  ✅ Резолвлено {len(contacts)}/{len(unique_ids)} контактов")
    return contacts


def scan_leads(since):
    """Лиды за период (crm.lead.list)."""
    print("📥 Сканирую лиды...")
    params = {
        "order[ID]": "DESC",
        "select[]": ["ID", "TITLE", "NAME", "LAST_NAME", "PHONE",
                      "SOURCE_ID", "STATUS_ID", "ASSIGNED_BY_ID",
                      "DATE_CREATE", "OPPORTUNITY", "COMMENTS"],
    }
    if since:
        params["filter[>=DATE_CREATE]"] = since
    
    leads = bitrix_list_all("crm.lead.list.json", params, max_items=200)
    print(f"  ✅ Найдено {len(leads)} лидов")
    return leads


def parse_bitrixgpt_comment(comments_text: str) -> dict:
    """Разбирает поле COMMENTS на части BitrixGPT.
    
    Формат BitrixGPT:
      BitrixGPT\n<резюме звонка>
    
    Возвращает dict:
      summary  — краткое резюме
      score    — % соответствия скрипту (если найден, иначе None)
      raw      — исходный текст
    """
    if not comments_text or "BitrixGPT" not in comments_text:
        return {"summary": "", "score": None, "raw": ""}
    
    import re
    raw = comments_text.strip()
    
    # Убираем префикс BitrixGPT\n
    text = re.sub(r'^\s*BitrixGPT\s*\n?', '', raw, flags=re.MULTILINE).strip()
    
    # Ищем % соответствия скрипту (формат: "20%", "Соответствие: 20%" и т.п.)
    score = None
    score_match = re.search(r'(?:соответстви[еяи]\s*(?:скрипту)?\s*[:\-]?\s*)?(\d{1,3})\s*%', text, re.IGNORECASE)
    if score_match:
        try:
            score = int(score_match.group(1))
        except (ValueError, AttributeError):
            score = None
    
    return {"summary": text, "score": score, "raw": raw}


def enrich_calls_with_bitrixgpt(calls: list, users: dict) -> list:
    """Обогащает каждый звонок данными BitrixGPT из COMMENTS родительской сущности.
    
    Для каждого звонка:
    - OWNER_TYPE_ID=1 → crm.lead.get     (поле COMMENTS)
    - OWNER_TYPE_ID=2 → crm.deal.get     (поле COMMENTS)
    - OWNER_TYPE_ID=3 → crm.contact.get  (поле COMMENTS)
    - OWNER_TYPE_ID=14 → crm.item.get    (смарт-процесс, поле comments)
    
    Использует batch-запросы (до 50 за раз) для экономии rate limit.
    Добавляет в объект звонка поля:
      bitrixgpt_summary  — текст резюме от BitrixGPT
      bitrixgpt_score    — % соответствия скрипту (int или None)
      manager_name       — имя менеджера (из users map)
    """
    if not calls:
        return calls
    
    print(f"🤖 Обогащаю {len(calls)} звонков данными BitrixGPT...")
    
    # Группируем по типу владельца
    lead_call_ids = {}      # {lead_id: [call_idx, ...]}
    deal_call_ids = {}      # {deal_id: [call_idx, ...]}
    contact_call_ids = {}   # {contact_id: [call_idx, ...]}
    smart_call_ids = {}     # {item_id: [call_idx, ...]}
    
    enriched = list(calls)  # копируем список
    
    for idx, call in enumerate(enriched):
        owner_id = str(call.get("OWNER_ID", ""))
        owner_type = str(call.get("OWNER_TYPE_ID", ""))
        # Добавляем имя менеджера сразу
        mgr_id = str(call.get("RESPONSIBLE_ID", ""))
        enriched[idx]["manager_name"] = users.get(mgr_id, f"ID_{mgr_id}")
        enriched[idx]["bitrixgpt_summary"] = ""
        enriched[idx]["bitrixgpt_score"] = None
        
        if owner_id and owner_id != "0":
            if owner_type == "1":    # Lead
                lead_call_ids.setdefault(owner_id, []).append(idx)
            elif owner_type == "2":  # Deal
                deal_call_ids.setdefault(owner_id, []).append(idx)
            elif owner_type == "3":  # Contact
                contact_call_ids.setdefault(owner_id, []).append(idx)
            elif owner_type == "14": # Smart process
                smart_call_ids.setdefault(owner_id, []).append(idx)
    
    skipped = len(calls) - len(lead_call_ids) - len(deal_call_ids) - len(contact_call_ids) - len(smart_call_ids)
    print(f"  📊 Лиды: {len(lead_call_ids)}, Сделки: {len(deal_call_ids)}, "
          f"Контакты: {len(contact_call_ids)}, Смарт: {len(smart_call_ids)}")
    
    def _batch_enrich(entity_ids: dict, api_method: str, prefix: str, comments_field: str = "COMMENTS"):
        """Универсальный батч-обогатитель для любого типа сущности."""
        ids_list = list(entity_ids.keys())
        found = 0
        for i in range(0, len(ids_list), 50):
            batch = ids_list[i:i+50]
            batch_cmd = {
                f"{prefix}_{eid}": f"{api_method}?id={eid}&select[]={comments_field}"
                for eid in batch
            }
            data = bitrix_call("batch.json", {
                "halt": 0,
                **{f"cmd[{k}]": v for k, v in batch_cmd.items()}
            })
            results = data.get("result", {}).get("result", {})
            for key, entity in results.items():
                if not isinstance(entity, dict):
                    continue
                eid = key.replace(f"{prefix}_", "")
                comments = entity.get(comments_field, "") or entity.get("COMMENTS", "")
                parsed = parse_bitrixgpt_comment(comments)
                if parsed["summary"]:
                    found += 1
                for idx in entity_ids.get(eid, []):
                    enriched[idx]["bitrixgpt_summary"] = parsed["summary"]
                    enriched[idx]["bitrixgpt_score"] = parsed["score"]
            if i + 50 < len(ids_list):
                time.sleep(0.4)
        return found
    
    # --- Батчим лиды ---
    found_leads = _batch_enrich(lead_call_ids, "crm.lead.get", "lead")
    
    # --- Батчим сделки ---
    found_deals = _batch_enrich(deal_call_ids, "crm.deal.get", "deal")
    
    # --- Батчим контакты ---
    found_contacts = _batch_enrich(contact_call_ids, "crm.contact.get", "contact")
    
    # --- Батчим смарт-процессы ---
    # OWNER_TYPE_ID в Bitrix = entityTypeId для CRM Universal API
    # Типичные значения: 128, 130, 132... (динамические), но OWNER_TYPE_ID=14 — тоже встречается
    if smart_call_ids:
        smart_ids_list = list(smart_call_ids.keys())
        found_smart = 0
        for i in range(0, len(smart_ids_list), 50):
            batch = smart_ids_list[i:i+50]
            # Пробуем entityTypeId = OWNER_TYPE_ID (14)
            batch_cmd = {
                f"smart_{sid}": f"crm.item.get?entityTypeId=14&id={sid}"
                for sid in batch
            }
            try:
                data = bitrix_call("batch.json", {
                    "halt": 0,
                    **{f"cmd[{k}]": v for k, v in batch_cmd.items()}
                })
                results = data.get("result", {}).get("result", {})
                if isinstance(results, list):
                    # Иногда batch возвращает list — пропускаем
                    pass
                elif isinstance(results, dict):
                    for key, item_data in results.items():
                        if not isinstance(item_data, dict):
                            continue
                        sid = key.replace("smart_", "")
                        # Смарт-процессы: ответ может быть {item: {...}} или напрямую {...}
                        item = item_data.get("item", item_data)
                        if isinstance(item, list) and item:
                            item = item[0]
                        if not isinstance(item, dict):
                            continue
                        comments = item.get("comments", "") or item.get("COMMENTS", "")
                        parsed = parse_bitrixgpt_comment(comments)
                        if parsed["summary"]:
                            found_smart += 1
                        for idx in smart_call_ids.get(sid, []):
                            enriched[idx]["bitrixgpt_summary"] = parsed["summary"]
                            enriched[idx]["bitrixgpt_score"] = parsed["score"]
            except Exception as e:
                print(f"  ⚠️ Смарт-процессы: {e}")
            if i + 50 < len(smart_ids_list):
                time.sleep(0.4)
    else:
        found_smart = 0
    
    with_summary = sum(1 for c in enriched if c.get("bitrixgpt_summary"))
    with_score = sum(1 for c in enriched if c.get("bitrixgpt_score") is not None)
    print(f"  ✅ Обогащено: {with_summary}/{len(enriched)} с резюме, {with_score} с оценкой скрипта")
    print(f"     (лиды: {found_leads}, сделки: {found_deals}, контакты: {found_contacts}, смарт: {found_smart})")
    return enriched


# --- Main scan ---

def run_scan():
    """Основной метод сканирования.
    
    КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ (2026-05-01):
    Фильтр ВСЕГДА = "сегодня с 00:00 MSK", а НЕ от last_scan.
    Старый баг: если сканер не запускался 4 дня, last_scan накапливал
    данные за несколько дней, и отчёт показывал 200 сделок вместо 20.
    """
    print(f"\n{'='*50}")
    print(f"🕵️ BITRIX SCANNER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    if not BITRIX_URL:
        print("❌ BITRIX_WEBHOOK_URL не настроен!")
        return None

    # === КРИТИЧНО: Всегда сканируем ТОЛЬКО ЗА СЕГОДНЯ ===
    # Не используем last_scan — он может быть устаревшим на дни/недели
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = today_start.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"📅 Сканирую данные ЗА СЕГОДНЯ с: {since}")

    # Сканируем
    users = scan_users()
    deals = scan_deals(since)
    activities = scan_activities(since)
    tasks = scan_tasks(since)
    products = scan_products()
    leads = scan_leads(since)
    
    # Обогащаем звонки данными BitrixGPT (резюме + оценка скрипта)
    enriched_calls = enrich_calls_with_bitrixgpt(activities["calls"], users)
    activities["calls"] = enriched_calls  # Обновляем в месте

    # Резолвим имена покупателей из сделок
    contact_ids = [d.get("CONTACT_ID") for d in deals if d.get("CONTACT_ID")]
    contacts = resolve_contacts(contact_ids)

    # Товарные строки (что конкретно купили) — для топ-50 сделок
    deal_ids = [str(d.get("ID")) for d in deals[:50] if d.get("ID")]
    product_rows = scan_product_rows(deal_ids)

    # Агрегация: что продаётся (по породам)
    breed_stats = {}  # {название: {quantity: N, revenue: N, deals: N}}
    for did, rows in product_rows.items():
        for row in rows:
            name = row.get("PRODUCT_NAME", "?")
            qty = float(row.get("QUANTITY", 0) or 0)
            price = float(row.get("PRICE", 0) or 0)
            revenue = qty * price
            if name not in breed_stats:
                breed_stats[name] = {"quantity": 0, "revenue": 0, "deals": 0}
            breed_stats[name]["quantity"] += qty
            breed_stats[name]["revenue"] += revenue
            breed_stats[name]["deals"] += 1

    # Собираем результат
    scan_result = {
        "scan_time": datetime.now().isoformat(),
        "since": since,
        "users": users,
        "contacts": contacts,  # {contact_id: "Имя Фамилия"}
        "deals": {
            "count": len(deals),
            "items": deals[:50],  # Не храним больше 50 за раз
            "total_amount": sum(get_deal_amount(d)[0] for d in deals)
        },
        "activities": {
            "total": len(activities["all"]),
            "calls_count": len(activities["calls"]),
            "chats_ol_count": len(activities.get("chats_ol", [])),
            "sms_count": len(activities["sms"]),
            "emails_count": len(activities["emails"]),
            "webforms_count": len(activities.get("webforms", [])),
            "other_count": len(activities["other"]),
            "calls": activities["calls"],  # Обогащённые звонки (+ bitrixgpt_summary, bitrixgpt_score)
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
        },
        "leads": {
            "count": len(leads),
            "items": leads[:50],
        },
        "breed_stats": breed_stats,  # {название: {quantity, revenue, deals}}
    }

    # Статус оплат (из полей 1С)
    paid_count = 0
    paid_amount = 0
    for d in deals:
        paid_val = d.get("UF_CRM_1641882420", "")  # "Уже оплачено"
        paid_sum = d.get("UF_CRM_1641882450", "")  # "Сумма оплаты"
        if paid_val and str(paid_val).strip().lower() not in ("", "0", "нет", "false"):
            paid_count += 1
            try:
                paid_amount += float(str(paid_sum).replace(" ", "").replace(",", "."))
            except (ValueError, TypeError):
                pass
    # Расхождения план (Bitrix) vs факт (1С)
    mismatches = []
    for d in deals:
        amt_1c, src = get_deal_amount(d)
        amt_bx = float(d.get("OPPORTUNITY", 0) or 0)
        if src == "1С" and abs(amt_1c - amt_bx) > 1.0:
            mismatches.append({
                "deal_id": d.get("ID"),
                "title": d.get("TITLE", "")[:50],
                "bitrix_sum": amt_bx,
                "1c_sum": amt_1c,
                "diff": amt_bx - amt_1c,
            })
    
    scan_result["payment_summary"] = {
        "paid_count": paid_count,
        "paid_amount": paid_amount,
        "total_count": len(deals),
        "total_amount": scan_result["deals"]["total_amount"],
        "mismatches": mismatches,  # Расхождения Bitrix vs 1С
        "mismatch_count": len(mismatches),
    }

    # Статистика по менеджерам
    manager_stats = {}
    for deal in deals:
        mgr_id = str(deal.get("ASSIGNED_BY_ID", "?"))
        mgr_name = users.get(mgr_id, f"User #{mgr_id}")
        if mgr_name not in manager_stats:
            manager_stats[mgr_name] = {"deals": 0, "amount": 0}
        manager_stats[mgr_name]["deals"] += 1
        manager_stats[mgr_name]["amount"] += get_deal_amount(deal)[0]

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

    # Сводка
    print("\n📊 СВОДКА:")
    print(f"  Новых сделок: {scan_result['deals']['count']} (на {scan_result['deals']['total_amount']:.0f}₽)")
    print(f"  📞 Звонков: {scan_result['activities']['calls_count']}")
    print(f"  💬 Чатов ОЛ: {scan_result['activities']['chats_ol_count']}")
    print(f"  📱 SMS: {scan_result['activities']['sms_count']}")
    print(f"  📋 Веб-форм: {scan_result['activities']['webforms_count']}")
    print(f"  ✅ Задач: {scan_result['tasks']['open']} открытых, {scan_result['tasks']['closed']} закрытых")
    print(f"  📦 Товаров: {scan_result['products']['count']}")
    print(f"  📥 Лидов: {scan_result['leads']['count']}")
    print(f"  👤 Контактов резолвлено: {len(contacts)}")
    if scan_result['products']['low_stock']:
        print(f"  ⚠️ Мало на складе: {len(scan_result['products']['low_stock'])} позиций")

    return scan_result


if __name__ == "__main__":
    result = run_scan()
    if result:
        print("\n✅ Сканирование завершено успешно.")
