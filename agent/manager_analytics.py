"""
Аналитика менеджеров за последний месяц.
Собирает звонки, сделки, конверсию.
"""
import os, json, requests, time
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'), override=True)
BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")

def bitrix_batch(method, params, max_items=2000):
    all_items = []
    start = 0
    while len(all_items) < max_items:
        params["start"] = start
        r = requests.get(f"{BITRIX_URL}/{method}", params=params, timeout=30)
        if r.status_code != 200: break
        d = r.json()
        items = d.get("result", [])
        if isinstance(items, dict) and "tasks" in items: items = items["tasks"]
        all_items.extend(items)
        if d.get("next") is None: break
        start = d["next"]
        time.sleep(0.4)
    return all_items

# Период: последний месяц
since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
print(f"📅 Период: {since[:10]} → {datetime.now().strftime('%Y-%m-%d')}")

# 1. Сотрудники
print("👥 Загружаю сотрудников...")
users_raw = requests.get(f"{BITRIX_URL}/user.get.json", params={"ACTIVE": "true"}, timeout=15).json().get("result", [])
users = {}
for u in users_raw:
    uid = str(u["ID"])
    name = f"{u.get('NAME','')} {u.get('LAST_NAME','')}".strip()
    if name in ("Иван Иванов", "СРМ Б24", "Служебный"): continue
    users[uid] = name or f"User#{uid}"
print(f"  ✅ {len(users)} менеджеров")

# 2. Звонки за месяц
print("📞 Загружаю звонки...")
calls = bitrix_batch("crm.activity.list.json", {
    "order[ID]": "DESC",
    "filter[TYPE_ID]": 2,
    "filter[>=CREATED]": since,
    "select[]": ["ID","SUBJECT","DESCRIPTION","RESPONSIBLE_ID","CREATED","DIRECTION","END_TIME","START_TIME"]
}, max_items=5000)
print(f"  ✅ {len(calls)} звонков")

# 3. Сделки за месяц
print("📊 Загружаю сделки...")
deals = bitrix_batch("crm.deal.list.json", {
    "order[ID]": "DESC",
    "filter[>=DATE_CREATE]": since,
    "select[]": ["ID","TITLE","STAGE_ID","OPPORTUNITY","ASSIGNED_BY_ID","DATE_CREATE","CLOSEDATE"]
}, max_items=3000)
print(f"  ✅ {len(deals)} сделок")

# Анализ
stats = defaultdict(lambda: {
    "calls_in": 0, "calls_out": 0, "calls_total": 0,
    "call_duration_sec": 0, "calls_short": 0, "calls_long": 0,
    "deals_new": 0, "deals_won": 0, "deals_lost": 0,
    "revenue": 0, "avg_deal": 0
})

# Звонки
for c in calls:
    mgr_id = str(c.get("RESPONSIBLE_ID", ""))
    if mgr_id not in users: continue
    s = stats[mgr_id]
    s["calls_total"] += 1
    direction = str(c.get("DIRECTION", ""))
    if direction == "1": s["calls_in"] += 1
    elif direction == "2": s["calls_out"] += 1
    
    # Длительность
    desc = c.get("DESCRIPTION", "") or ""
    import re
    dur_match = re.search(r'(\d+)\s*сек', desc)
    if dur_match:
        dur = int(dur_match.group(1))
        s["call_duration_sec"] += dur
        if dur < 15: s["calls_short"] += 1
        elif dur > 120: s["calls_long"] += 1

# Сделки
WON_STAGES = {"WON", "C6:WON", "FINAL_INVOICE", "EXECUTING"}
LOST_STAGES = {"LOSE", "C6:LOSE", "APOLOGY"}
for d in deals:
    mgr_id = str(d.get("ASSIGNED_BY_ID", ""))
    if mgr_id not in users: continue
    s = stats[mgr_id]
    s["deals_new"] += 1
    stage = d.get("STAGE_ID", "")
    amount = float(d.get("OPPORTUNITY", 0) or 0)
    s["revenue"] += amount
    if stage in WON_STAGES: s["deals_won"] += 1
    elif stage in LOST_STAGES: s["deals_lost"] += 1

# Отчёт
print(f"\n{'='*70}")
print(f"📊 АНАЛИТИКА МЕНЕДЖЕРОВ — последние 30 дней")
print(f"{'='*70}\n")

sorted_mgrs = sorted(stats.items(), key=lambda x: x[1]["calls_total"], reverse=True)
for mgr_id, s in sorted_mgrs:
    name = users.get(mgr_id, f"#{mgr_id}")
    avg_dur = s["call_duration_sec"] / max(s["calls_total"], 1)
    avg_deal = s["revenue"] / max(s["deals_new"], 1)
    conv = (s["deals_won"] / max(s["deals_new"], 1) * 100) if s["deals_new"] else 0
    
    print(f"👩‍💼 {name}")
    print(f"   📞 Звонки: {s['calls_total']} (↙ вход: {s['calls_in']}, ↗ исход: {s['calls_out']})")
    print(f"   ⏱  Ср. длительность: {avg_dur:.0f} сек | Коротких (<15с): {s['calls_short']} | Длинных (>2мин): {s['calls_long']}")
    print(f"   📊 Сделки: {s['deals_new']} новых | ✅ {s['deals_won']} выиграно | ❌ {s['deals_lost']} проиграно")
    print(f"   💰 Выручка: {s['revenue']:,.0f}₽ | Ср. чек: {avg_deal:,.0f}₽ | Конверсия: {conv:.0f}%".replace(",", " "))
    print()

# Рейтинг
print(f"{'='*70}")
print(f"🏆 РЕЙТИНГ:")
by_calls = sorted(sorted_mgrs, key=lambda x: x[1]["calls_total"], reverse=True)
by_revenue = sorted(sorted_mgrs, key=lambda x: x[1]["revenue"], reverse=True)
by_deals = sorted(sorted_mgrs, key=lambda x: x[1]["deals_new"], reverse=True)

if by_calls: print(f"   📞 Больше всех звонков: {users[by_calls[0][0]]} ({by_calls[0][1]['calls_total']})")
if by_revenue: print(f"   💰 Максимальная выручка: {users[by_revenue[0][0]]} ({by_revenue[0][1]['revenue']:,.0f}₽)".replace(",", " "))
if by_deals: print(f"   📊 Больше всех сделок: {users[by_deals[0][0]]} ({by_deals[0][1]['deals_new']})")

# Сохраняем
report_data = {}
for mgr_id, s in sorted_mgrs:
    report_data[users.get(mgr_id, mgr_id)] = s
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "manager_analytics.json"), "w", encoding="utf-8") as f:
    json.dump({"period": f"{since[:10]} - {datetime.now().strftime('%Y-%m-%d')}", "managers": report_data}, f, ensure_ascii=False, indent=2)
print(f"\n💾 Сохранено: data/manager_analytics.json")
