#!/usr/bin/env python3
"""
recon_timeline.py — Ищем BitrixGPT-резюме звонков в timeline лида/сделки.
"""

import os
import json
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
print(f"🔗 Production URL: {BITRIX_URL[:50]}...\n")

# ──────────────────────────────────────────────────────────
# 1. Берём лид из скрина — ID 182384 (incubird.bitrix24.ru/crm/lead/details/182384/)
# ──────────────────────────────────────────────────────────
LEAD_ID = 182384

# ──────────────────────────────────────────────────────────
# 2. Смотрим timeline этого лида
# ──────────────────────────────────────────────────────────
print(f"📋 Запрашиваем timeline лида #{LEAD_ID}...\n")

resp = requests.post(
    f"{BITRIX_URL}/crm.timeline.comment.list.json",
    json={
        "filter": {
            "ENTITY_ID": LEAD_ID,
            "ENTITY_TYPE": "lead",
        },
        "select": ["*"],
        "order": {"ID": "DESC"},
    },
    timeout=20,
)
data = resp.json()
print(f"crm.timeline.comment.list → {json.dumps(data, ensure_ascii=False)[:500]}\n")

# ──────────────────────────────────────────────────────────
# 3. Пробуем crm.activity.list для конкретного лида
# ──────────────────────────────────────────────────────────
print(f"📞 Activity звонки для лида #{LEAD_ID}...\n")
resp2 = requests.post(
    f"{BITRIX_URL}/crm.activity.list.json",
    json={
        "filter": {
            "OWNER_ID": LEAD_ID,
            "OWNER_TYPE_ID": 1,   # 1 = Lead
            "TYPE_ID": 2,
        },
        "select": ["*"],
        "order": {"ID": "DESC"},
    },
    timeout=20,
)
data2 = resp2.json()
activities = data2.get("result", [])
print(f"Найдено активностей: {len(activities)}")
for act in activities[:3]:
    print(f"\n  ID={act.get('ID')} SUBJECT={act.get('SUBJECT')!r}")
    print(f"  DESCRIPTION={act.get('DESCRIPTION', '')[:500]!r}")
    print(f"  RESULT_STATUS={act.get('RESULT_STATUS')}")
    print(f"  RESULT_STREAM={act.get('RESULT_STREAM')}")

# ──────────────────────────────────────────────────────────
# 4. Смотрим crm.lead.productrows + все поля лида
# ──────────────────────────────────────────────────────────
print(f"\n📋 Поля лида #{LEAD_ID}...\n")
resp3 = requests.post(
    f"{BITRIX_URL}/crm.lead.get.json",
    json={"id": LEAD_ID},
    timeout=20,
)
lead = resp3.json().get("result", {})
print("COMMENTS поле лида:")
print(repr(lead.get("COMMENTS", "")[:600]))

# ──────────────────────────────────────────────────────────
# 5. Пробуем получить все timeline-записи лида (новый метод)
# ──────────────────────────────────────────────────────────
print(f"\n🕐 crm.timeline.note.list для лида #{LEAD_ID}...\n")
resp4 = requests.post(
    f"{BITRIX_URL}/crm.timeline.note.list.json",
    json={
        "entityTypeId": 1,   # 1 = lead
        "entityId": LEAD_ID,
    },
    timeout=20,
)
data4 = resp4.json()
print(json.dumps(data4, ensure_ascii=False)[:800])

# ──────────────────────────────────────────────────────────
# 6. Пробуем log записи (история изменений)
# ──────────────────────────────────────────────────────────
print(f"\n📝 crm.lead.log.list для лида #{LEAD_ID}...\n")
resp5 = requests.post(
    f"{BITRIX_URL}/crm.lead.log.list.json",
    json={
        "order": {"ID": "DESC"},
        "filter": {"ENTITY_ID": LEAD_ID},
        "select": ["*"],
    },
    timeout=20,
)
data5 = resp5.json()
log_items = data5.get("result", [])
print(f"Log записей: {len(log_items)}")
for item in log_items[:5]:
    print(f"  {item}")

print("\n✅ Готово!")
