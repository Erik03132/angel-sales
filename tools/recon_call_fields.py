#!/usr/bin/env python3
"""
recon_call_fields.py — Разведка: смотрим реальную структуру звонков в Bitrix24.
Ищем где BitrixGPT пишет резюме звонка.
"""

import os
import json
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# Пробуем production URL (incubird.bitrix24.ru — это Заботкина)
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
print(f"🔗 URL: {BITRIX_URL[:50]}...")

# ──────────────────────────────────────────────────────────
# 1. Берём последние 5 завершённых звонков
# ──────────────────────────────────────────────────────────
print("\n📞 Запрашиваем последние звонки (TYPE_ID=2)...\n")

resp = requests.post(
    f"{BITRIX_URL}/crm.activity.list.json",
    json={
        "filter": {
            "TYPE_ID": 2,           # 2 = звонок
            "COMPLETED": "Y",
        },
        "select": ["*"],            # ВСЕ поля
        "order": {"ID": "DESC"},
        "start": 0,
    },
    timeout=20,
)

data = resp.json()
calls = data.get("result", [])
print(f"✅ Получено звонков: {len(calls)}")

if not calls:
    print("❌ Звонков нет. Проверь webhook URL.")
    exit(1)

# ──────────────────────────────────────────────────────────
# 2. Выводим ВСЕ поля первого звонка
# ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("📋 ВСЕ ПОЛЯ ПЕРВОГО ЗВОНКА:")
print("="*60)
first = calls[0]
for key, val in sorted(first.items()):
    val_str = str(val)
    if len(val_str) > 200:
        val_str = val_str[:200] + "..."
    print(f"  {key:35s} = {val_str}")

# ──────────────────────────────────────────────────────────
# 3. Ищем поля где упоминается BitrixGPT или резюме
# ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("🔍 ПОЛЯ С BitrixGPT / резюме (все 5 звонков):")
print("="*60)

keywords = ["BitrixGPT", "bitrixgpt", "резюм", "сводк", "итог", "Звонок носил", "скрипт"]

for i, call in enumerate(calls[:5], 1):
    call_id = call.get("ID", "?")
    found_fields = {}
    for key, val in call.items():
        val_str = str(val)
        if any(kw.lower() in val_str.lower() for kw in keywords):
            found_fields[key] = val_str[:300]

    print(f"\n--- Звонок #{call_id} ---")
    if found_fields:
        for k, v in found_fields.items():
            print(f"  ✅ НАЙДЕНО в поле [{k}]:")
            print(f"     {v}")
    else:
        print(f"  ⚠️  BitrixGPT-резюме не найдено в стандартных полях")
        # Покажем DESCRIPTION и SUBJECT
        print(f"  DESCRIPTION = {str(call.get('DESCRIPTION', ''))[:200]!r}")
        print(f"  SUBJECT     = {str(call.get('SUBJECT', ''))[:200]!r}")

# ──────────────────────────────────────────────────────────
# 4. Проверяем UF_* кастомные поля
# ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("🔎 КАСТОМНЫЕ ПОЛЯ (UF_*) первого звонка:")
print("="*60)
uf_fields = {k: v for k, v in first.items() if k.startswith("UF_")}
if uf_fields:
    for k, v in uf_fields.items():
        print(f"  {k} = {str(v)[:300]}")
else:
    print("  Кастомных UF_* полей нет")

# ──────────────────────────────────────────────────────────
# 5. Сохраняем сырые данные для детального анализа
# ──────────────────────────────────────────────────────────
out_file = os.path.join(BASE_DIR, "data", "recon_calls.json")
os.makedirs(os.path.dirname(out_file), exist_ok=True)
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(calls[:5], f, ensure_ascii=False, indent=2)

print(f"\n💾 Сырые данные сохранены: {out_file}")
print("\n✅ Разведка завершена!")
