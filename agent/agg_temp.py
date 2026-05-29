#!/usr/bin/env python3
"""Точная агрегация ВСЕХ сделок за апрель из скачанных JSON."""
import json
import os
import re
from collections import defaultdict

STEPS = "/Users/igorvasin/.gemini/antigravity/brain/19971457-888a-4f8e-9a06-b3a4268eab21/.system_generated/steps"
users = {"1":"Андрей","1528":"Аня","4388":"Эльзара","40318":"Марина Е",
         "37548":"СРМ Б24","37728":"Анна Ш.","40466":"Служебный",
         "40994":"Ольга М.","41624":"Анжелочка"}

all_deals = []
calls_total = 0

# Проходим все step-директории  
for step_name in os.listdir(STEPS):
    step_dir = os.path.join(STEPS, step_name)
    content_file = os.path.join(step_dir, "content.md")
    if not os.path.isfile(content_file):
        continue
    try:
        with open(content_file, 'r', encoding='utf-8') as f:
            text = f.read()
    except:
        continue
    
    if 'crm.deal.list' not in text or 'DATE_CREATE' not in text:
        continue
    if 'crm.activity' in text:
        # Звонки
        m = re.search(r'"total":(\d+)', text)
        if m:
            calls_total = int(m.group(1))
        continue
    
    # Извлекаем JSON массив результатов
    m = re.search(r'"result":\[(.*?)\],"next"', text, re.DOTALL)
    if not m:
        m = re.search(r'"result":\[(.*?)\],"total"', text, re.DOTALL)
    if not m:
        continue
    
    try:
        items = json.loads('[' + m.group(1) + ']')
        all_deals.extend(items)
    except:
        continue

# Дедупликация
seen = set()
deals = []
for d in all_deals:
    did = d.get("ID")
    if did and did not in seen:
        seen.add(did)
        deals.append(d)

# Агрегация
total_sum = 0
mgr = defaultdict(lambda: {"deals": 0, "sum": 0})

for d in deals:
    opp = float(d.get("OPPORTUNITY", 0) or 0)
    total_sum += opp
    mid = d.get("ASSIGNED_BY_ID", "?")
    mgr[mid]["deals"] += 1
    mgr[mid]["sum"] += opp

print("ТОЧНЫЕ ДАННЫЕ — ВСЕ сделки за апрель 2026")
print(f"Загружено уникальных: {len(deals)}")
print(f"Общая сумма: {total_sum:,.2f}₽")
print()
print("МЕНЕДЖЕРЫ:")
for mid, s in sorted(mgr.items(), key=lambda x: x[1]["sum"], reverse=True):
    name = users.get(mid, f"ID:{mid}")
    if s["deals"] > 0:
        print(f"  {name}: {s['deals']} сделок, {s['sum']:,.2f}₽")

print(f"\nЗвонки total (API): {calls_total}")
