#!/usr/bin/env python3.12
"""
Разведчик 1С-данных в Bitrix24.
Показывает ВСЁ что можно вытащить: кастомные поля, счета, товарные строки, оплаты.

Запуск: python3.12 agent/bitrix_1c_scout.py
"""
import json
import os

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ручной .env
with open(os.path.join(BASE_DIR, '.env')) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        os.environ.setdefault(k.strip(), v.strip().strip('"'))

BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", os.getenv("BITRIX_WEBHOOK_URL", "")).rstrip("/")


def api(method, params=None):
    r = requests.get(f"{BITRIX_URL}/{method}", params=params or {}, timeout=15)
    return r.json() if r.status_code == 200 else {}


print(f"\n{'='*60}")
print("🔍 РАЗВЕДКА 1С-ДАННЫХ В BITRIX24")
print(f"{'='*60}\n")

# ═══════════════════════════════════════
# 1. КАСТОМНЫЕ ПОЛЯ СДЕЛКИ (UF_ = обычно 1С)
# ═══════════════════════════════════════
print("📋 1. КАСТОМНЫЕ ПОЛЯ СДЕЛКИ (UF_)")
fields = api("crm.deal.fields.json").get("result", {})
uf = {k: v for k, v in fields.items() if k.startswith("UF_")}
source = {k: v for k, v in fields.items() if "SOURCE" in k}
print(f"   Всего полей сделки: {len(fields)}")
print(f"   UF_ (кастомные): {len(uf)}")
for name, info in sorted(uf.items()):
    t = info.get("formLabel", info.get("title", name))
    print(f"      {name}: {t} ({info.get('type', '')})")
print(f"   SOURCE поля: {len(source)}")
for name, info in sorted(source.items()):
    t = info.get("formLabel", info.get("title", name))
    print(f"      {name}: {t}")

# ═══════════════════════════════════════
# 2. ТОВАРНЫЕ СТРОКИ (что конкретно купили)
# ═══════════════════════════════════════
print("\n📦 2. ТОВАРНЫЕ СТРОКИ В СДЕЛКАХ")
# Берём последние 5 сделок с суммой > 0
deals = api("crm.deal.list.json", {
    "order[ID]": "DESC", "filter[>OPPORTUNITY]": "0",
    "select[]": ["ID", "TITLE", "OPPORTUNITY"]
}).get("result", [])
for d in deals[:5]:
    did = d["ID"]
    rows = api("crm.deal.productrows.get.json", {"id": did}).get("result", [])
    print(f"   Сделка #{did} ({d.get('OPPORTUNITY', '?')}₽): {len(rows)} товаров")
    for r in rows[:3]:
        print(f"      • {r.get('PRODUCT_NAME', '?')} x{r.get('QUANTITY', '?')} = {r.get('PRICE', '?')}₽")
        # Все поля товарной строки
        if r == rows[0] and d == deals[0]:
            print(f"      [все поля: {list(r.keys())}]")

# ═══════════════════════════════════════
# 3. СЧЕТА (crm.invoice — старый формат)
# ═══════════════════════════════════════
print("\n💳 3. СЧЕТА (crm.invoice)")
invoices = api("crm.invoice.list.json", {
    "order[ID]": "DESC",
    "select[]": ["ID", "STATUS_ID", "DATE_INSERT", "PRICE", "CURRENCY",
                 "PAY_VOUCHER_NUM", "COMMENTS", "RESPONSIBLE_ID"]
}).get("result", [])
print(f"   Найдено: {len(invoices)}")
for inv in invoices[:5]:
    print(f"   #{inv.get('ID')} | {inv.get('PRICE', '?')}₽ | Статус: {inv.get('STATUS_ID')} | {inv.get('DATE_INSERT', '')[:10]}")

# ═══════════════════════════════════════
# 4. SMART-ПРОЦЕССЫ (новые счета в Bitrix)
# ═══════════════════════════════════════
print("\n🔄 4. SMART-ПРОЦЕССЫ")
try:
    types = api("crm.type.list.json").get("result", {}).get("types", [])
    if types:
        for t in types:
            print(f"   Тип: {t.get('title')} (entityTypeId={t.get('entityTypeId')})")
            items = api("crm.item.list.json", {"entityTypeId": t["entityTypeId"]}).get("result", {}).get("items", [])
            print(f"      Записей: {len(items)}")
            if items:
                print(f"      Пример: {json.dumps(items[0], ensure_ascii=False)[:150]}")
    else:
        print("   Нет smart-процессов")
except Exception as e:
    print(f"   Ошибка: {e}")

# ═══════════════════════════════════════
# 5. ПОЛЯ ТОВАРА (есть ли остатки/1С поля)
# ═══════════════════════════════════════
print("\n📦 5. ПОЛЯ ТОВАРА")
pfields = api("crm.product.fields.json").get("result", {})
print(f"   Всего полей: {len(pfields)}")
for name in sorted(pfields.keys()):
    info = pfields[name]
    t = info.get("formLabel", info.get("title", ""))
    interesting = any(x in name.upper() for x in ["QUANTITY", "MEASURE", "SECTION", "XML", "1C", "UF_", "CATALOG", "PROPERTY"])
    if interesting:
        print(f"   ⭐ {name}: {t} ({info.get('type', '')})")

# ═══════════════════════════════════════
# 6. ИСТОЧНИКИ ЛИДОВ/СДЕЛОК
# ═══════════════════════════════════════
print("\n📥 6. ИСТОЧНИКИ ЛИДОВ")
sources = api("crm.lead.source.list.json").get("result", [])
if sources:
    for s in sources:
        print(f"   {s.get('STATUS_ID')}: {s.get('NAME')}")

# ═══════════════════════════════════════
# 7. ПОЛЯ ЛИДА
# ═══════════════════════════════════════
print("\n📥 7. КАСТОМНЫЕ ПОЛЯ ЛИДА")
lfields = api("crm.lead.fields.json").get("result", {})
uf_leads = {k: v for k, v in lfields.items() if k.startswith("UF_")}
print(f"   Всего полей лида: {len(lfields)}")
print(f"   UF_ (кастомные): {len(uf_leads)}")
for name, info in sorted(uf_leads.items()):
    t = info.get("formLabel", info.get("title", name))
    print(f"      {name}: {t}")

# ═══════════════════════════════════════
# 8. Пример реального лида
# ═══════════════════════════════════════
print("\n📥 8. ПОСЛЕДНИЕ 3 ЛИДА")
leads = api("crm.lead.list.json", {
    "order[ID]": "DESC",
    "select[]": ["ID", "TITLE", "NAME", "LAST_NAME", "SOURCE_ID", "STATUS_ID",
                 "OPPORTUNITY", "ASSIGNED_BY_ID", "DATE_CREATE", "COMMENTS"]
}).get("result", [])
for l in leads[:3]:
    name = f"{l.get('NAME', '')} {l.get('LAST_NAME', '')}".strip()
    print(f"   #{l.get('ID')} | {name or l.get('TITLE','?')} | Источник: {l.get('SOURCE_ID')} | Статус: {l.get('STATUS_ID')} | {l.get('OPPORTUNITY','0')}₽")

print(f"\n{'='*60}")
print("✅ Разведка завершена")
print(f"{'='*60}")
