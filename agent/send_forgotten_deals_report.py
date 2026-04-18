#!/usr/bin/env python3
"""
Отправка Андрею подробного объяснения 'забытых сделок' с прямыми ссылками в Битрикс.
Одноразовый скрипт — запустить и удалить.
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

from send_to_bitrix import send_bitrix_message

BITRIX_DOMAIN = "incubird.bitrix24.ru"

# Загружаем данные
with open(os.path.join(BASE_DIR, "data", "forgotten_deals.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

# Фильтруем: сумма >= 50000, давность 5-60 дней
deals = [d for d in data["deals"] if d["amount"] >= 50000 and 5 <= d["days_silent"] <= 60]
deals.sort(key=lambda x: x["amount"], reverse=True)

# Группируем по менеджерам
by_mgr = {}
for d in deals[:30]:
    mgr = d["manager"]
    if mgr not in by_mgr:
        by_mgr[mgr] = []
    by_mgr[mgr].append(d)

# --- Формируем сообщение ---
total_amount = sum(d["amount"] for d in deals)

lines = []
lines.append("Андрей, добрый день! Это Анжелочка")
lines.append("")
lines.append("ЧТО ТАКОЕ 'ЗАБЫТЫЕ СДЕЛКИ'?")
lines.append("")
lines.append("Это НЕ лиды и НЕ задачи.")
lines.append("Это ваши РЕАЛЬНЫЕ СДЕЛКИ в CRM (раздел 'Сделки' в Битриксе),")
lines.append("по которым клиент уже обращался, менеджер создал сделку,")
lines.append("но потом - тишина. Ни звонка, ни письма, ни SMS за 5+ дней.")
lines.append("")
lines.append("Клиент может все ещё ждать ответа или уйти к конкуренту.")
lines.append("Это живые деньги, которые 'спят'.")
lines.append("")
lines.append("ТОП СДЕЛОК С ПРЯМЫМИ ССЫЛКАМИ (от 50 000 руб, давность 5-42 дня):")
lines.append("")

for mgr in ["Эльзара", "Марина Е", "Аня"]:
    if mgr not in by_mgr:
        continue
    mgr_deals = by_mgr[mgr]
    mgr_total = int(sum(d["amount"] for d in mgr_deals))
    lines.append(f"{mgr} ({len(mgr_deals)} сделок на {mgr_total} руб):")
    for d in mgr_deals[:5]:
        link = f"https://{BITRIX_DOMAIN}/crm/deal/details/{d['id']}/"
        amt = int(d["amount"])
        lines.append(f"  #{d['id']} - {amt} руб (молчит {d['days_silent']} дн.) -> {link}")
    if len(mgr_deals) > 5:
        lines.append(f"  ... и ещё {len(mgr_deals)-5} сделок")
    lines.append("")

lines.append(f"ИТОГО: {len(deals)} сделок на {int(total_amount)} руб ждут действий.")
lines.append("")
lines.append("Кликните по любой ссылке - откроется карточка сделки прямо в Битриксе.")
lines.append("Рекомендую начать с крупных - один звонок может вернуть 830 000 руб.")
lines.append("")
lines.append("- Анжелочка")

msg = "\n".join(lines)

print("--- СООБЩЕНИЕ ---")
print(msg)
print(f"\n--- Длина: {len(msg)} символов ---")
print()

# Отправляем
result = send_bitrix_message(msg)
print(f"Результат: {result}")
