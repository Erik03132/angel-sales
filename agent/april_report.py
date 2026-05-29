#!/usr/bin/env python3
"""
Месячный отчёт Заботкиной за АПРЕЛЬ 2026.
Сбор данных напрямую из Битрикс24 API + отправка в Telegram.
Без requests — только stdlib (urllib).
"""
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
from collections import defaultdict


# .env парсинг без dotenv
def load_env(path):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_env(os.path.join(BASE_DIR, ".env"))

BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
TG_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OWNER_ID = 176203333

SINCE = "2026-04-01T00:00:00"
UNTIL = "2026-05-01T00:00:00"

# SSL context (skip verify for simplicity)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def http_post(url, data):
    """HTTP POST с JSON."""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ HTTP error: {e}")
        return {}

def bx(method, params=None):
    """Bitrix24 API с пагинацией."""
    url = f"{BITRIX_URL}/{method}"
    all_items = []
    start = 0
    while True:
        p = dict(params or {})
        p["start"] = start
        data = http_post(url, p)
        items = data.get("result", [])
        if isinstance(items, dict):
            return items
        all_items.extend(items)
        nxt = data.get("next")
        if nxt:
            start = nxt
            time.sleep(0.5)
        else:
            break
    return all_items

def send_tg(text, chat_id=OWNER_ID):
    """Отправить в Telegram."""
    if not TG_TOKEN:
        print("❌ TG_TOKEN не найден")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    chunks = []
    while text:
        if len(text) <= 4000:
            chunks.append(text)
            break
        cut = text[:4000].rfind("\n")
        if cut < 100:
            cut = 4000
        chunks.append(text[:cut])
        text = text[cut:]
    for chunk in chunks:
        http_post(url, {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"})
        time.sleep(0.5)

def main():
    print("📊 Собираю отчёт Заботкиной за АПРЕЛЬ 2026...")
    print(f"   Bitrix: {BITRIX_URL[:50]}...")
    
    # 1. Пользователи
    print("👥 Менеджеры...")
    raw_users = bx("user.get", {"ACTIVE": True})
    users = {str(u["ID"]): f"{u.get('NAME','')} {u.get('LAST_NAME','')}".strip() for u in raw_users}
    print(f"   Найдено: {len(users)}")
    
    # 2. Сделки
    print("💰 Сделки за апрель...")
    deals = bx("crm.deal.list", {
        "filter": {">=DATE_CREATE": SINCE, "<DATE_CREATE": UNTIL},
        "select": ["ID","TITLE","OPPORTUNITY","STAGE_ID","ASSIGNED_BY_ID",
                    "CONTACT_ID","COMPANY_ID","DATE_CREATE",
                    "UF_CRM_1641882420","UF_CRM_1641882450"]
    })
    print(f"   Найдено: {len(deals)}")
    
    if not deals:
        msg = "❌ Нет данных по сделкам за апрель 2026."
        print(msg)
        send_tg(msg)
        return
    
    # 3. Контакты
    print("📇 Имена покупателей...")
    contact_ids = list(set(d.get("CONTACT_ID") for d in deals if d.get("CONTACT_ID")))
    contacts = {}
    for cid in contact_ids[:50]:
        try:
            c = http_post(f"{BITRIX_URL}/crm.contact.get", {"ID": cid}).get("result", {})
            name = f"{c.get('NAME','')} {c.get('LAST_NAME','')}".strip()
            contacts[str(cid)] = name or f"#{cid}"
            time.sleep(0.3)
        except:
            contacts[str(cid)] = f"#{cid}"
    print(f"   Разрезолвлено: {len(contacts)}")
    
    # 4. Звонки
    print("📞 Звонки...")
    activities = bx("crm.activity.list", {
        "filter": {">=CREATED": SINCE, "<CREATED": UNTIL, "TYPE_ID": 2},
        "select": ["ID","DIRECTION","COMPLETED","RESPONSIBLE_ID"]
    })
    print(f"   Найдено: {len(activities)}")
    
    # 5. Товарные строки
    print("🐔 Товарные строки...")
    product_rows = []
    for did in [str(d["ID"]) for d in deals[:80]]:
        try:
            rows = http_post(f"{BITRIX_URL}/crm.deal.productrows.get", {"id": did}).get("result", [])
            product_rows.extend(rows)
            time.sleep(0.3)
        except:
            pass
    print(f"   Найдено: {len(product_rows)}")
    
    # === АГРЕГАЦИЯ ===
    total_deals = len(deals)
    total_sum = sum(float(d.get("OPPORTUNITY",0) or 0) for d in deals)
    total_calls = len(activities)
    missed = sum(1 for a in activities if a.get("DIRECTION")=="1" and a.get("COMPLETED")=="N")
    
    # Менеджеры
    mgr = defaultdict(lambda: {"deals":0,"sum":0,"calls":0,"missed":0})
    for d in deals:
        m = str(d.get("ASSIGNED_BY_ID","?"))
        mgr[m]["deals"] += 1
        mgr[m]["sum"] += float(d.get("OPPORTUNITY",0) or 0)
    for a in activities:
        m = str(a.get("RESPONSIBLE_ID","?"))
        mgr[m]["calls"] += 1
        if a.get("DIRECTION")=="1" and a.get("COMPLETED")=="N":
            mgr[m]["missed"] += 1
    
    # ТОП сделки
    top5 = sorted(deals, key=lambda d: float(d.get("OPPORTUNITY",0) or 0), reverse=True)[:5]
    
    # Породы
    breeds = defaultdict(lambda: {"qty":0,"rev":0,"cnt":0})
    for r in product_rows:
        nm = r.get("PRODUCT_NAME","?")
        q = float(r.get("QUANTITY",0) or 0)
        p = float(r.get("PRICE",0) or 0)
        breeds[nm]["qty"] += q
        breeds[nm]["rev"] += q*p
        breeds[nm]["cnt"] += 1
    
    # Оплаты
    paid_sum, paid_cnt, unpaid_cnt = 0, 0, 0
    for d in deals:
        if d.get("UF_CRM_1641882420") in ("1","true","True","Y"):
            paid_sum += float(d.get("UF_CRM_1641882450",0) or d.get("OPPORTUNITY",0) or 0)
            paid_cnt += 1
        else:
            unpaid_cnt += 1
    
    # Воронка
    stages = defaultdict(lambda: {"cnt":0,"sum":0})
    for d in deals:
        s = d.get("STAGE_ID","?")
        stages[s]["cnt"] += 1
        stages[s]["sum"] += float(d.get("OPPORTUNITY",0) or 0)
    
    # === ФОРМИРОВАНИЕ ===
    R = []
    R.append("📋 <b>ОТЧЁТ ЗАБОТКИНОЙ — АПРЕЛЬ 2026</b>")
    R.append("📅 01.04.2026 → 30.04.2026\n")
    
    R.append("━━━━━━━━━━━━━━━━━━")
    R.append("📊 <b>CRM СВОДКА</b>")
    R.append(f"  🆕 Сделки: <b>{total_deals}</b>")
    R.append(f"  💰 Сумма:  <b>{total_sum:,.0f}₽</b>")
    R.append(f"  📞 Звонки: <b>{total_calls}</b>")
    R.append(f"  ⚠️ Пропущ: <b>{missed}</b>\n")
    
    R.append("━━━━━━━━━━━━━━━━━━")
    R.append("👩‍💼 <b>МЕНЕДЖЕРЫ</b>")
    for mid, s in sorted(mgr.items(), key=lambda x: x[1]["deals"], reverse=True)[:10]:
        nm = users.get(mid, f"ID:{mid}")
        ms = f" ⚠️{s['missed']}пропущ" if s["missed"] else ""
        R.append(f"  • <b>{nm}</b>: {s['deals']}сд / {s['calls']}зв / {s['sum']:,.0f}₽{ms}")
    R.append("")
    
    R.append("━━━━━━━━━━━━━━━━━━")
    R.append("💰 <b>ТОП-5 СДЕЛОК</b>")
    for i, d in enumerate(top5, 1):
        cid = str(d.get("CONTACT_ID",""))
        buyer = contacts.get(cid, f"#{cid}" if cid else "—")
        m = users.get(str(d.get("ASSIGNED_BY_ID","")), "?")
        amt = float(d.get("OPPORTUNITY",0) or 0)
        R.append(f"  {i}. <b>{amt:,.0f}₽</b> — {buyer} ({m})")
    R.append("")
    
    R.append("━━━━━━━━━━━━━━━━━━")
    R.append("📊 <b>ВОРОНКА</b>")
    for st, s in sorted(stages.items(), key=lambda x: x[1]["cnt"], reverse=True)[:6]:
        R.append(f"  • {st}: {s['cnt']}шт ({s['sum']:,.0f}₽)")
    R.append("")
    
    if breeds:
        R.append("━━━━━━━━━━━━━━━━━━")
        R.append("🐔 <b>ТОП ПОРОД</b>")
        for nm, s in sorted(breeds.items(), key=lambda x: x[1]["rev"], reverse=True)[:10]:
            R.append(f"  • <b>{nm}</b>: {s['qty']:.0f}шт, {s['rev']:,.0f}₽ ({s['cnt']}сд)")
        R.append("")
    
    R.append("━━━━━━━━━━━━━━━━━━")
    R.append("💳 <b>ОПЛАТЫ (1С)</b>")
    R.append(f"  ✅ Оплачено: <b>{paid_sum:,.0f}₽</b> ({paid_cnt}сд)")
    R.append(f"  ❌ Не оплачено: {unpaid_cnt}сд")
    R.append("")
    
    R.append("\n🐥 <i>Анжела Заботкина • Апрель 2026</i>")
    
    full = "\n".join(R)
    
    # Сохраняем
    out = os.path.join(BASE_DIR, "agent", "data", "report_april_2026.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(full)
    print(f"\n💾 Сохранён: {out}")
    
    # ТГ
    print(f"📱 Отправляю в TG ({OWNER_ID})...")
    send_tg(full)
    print("✅ Готово!")
    
    # Консоль
    import re
    print(f"\n{'='*50}")
    print(re.sub(r'<[^>]+>', '', full))

if __name__ == "__main__":
    main()
