#!/usr/bin/env python3
"""Отправляем Андрею скорректированный список забытых сделок."""
import os, sys, json
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "agent"))
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)
from send_to_bitrix import send_bitrix_message

BITRIX_DOMAIN = "incubird.bitrix24.ru"

with open(os.path.join(BASE_DIR, "data", "forgotten_deals.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

deals = data["deals"]
total = int(data["total_amount"])

by_mgr = {}
for d in deals:
    mgr = d["manager"]
    if mgr not in by_mgr:
        by_mgr[mgr] = []
    by_mgr[mgr].append(d)

lines = []
lines.append("Андрей, вот СКОРРЕКТИРОВАННЫЙ список.")
lines.append("Убраны дубли, отказы и подтвержденные заказы.")
lines.append("Остались ТОЛЬКО сделки, по которым клиент ждет звонка:")
lines.append("")
lines.append(f"Итого: {len(deals)} сделок на {total} руб")
lines.append("")

for mgr in ["Эльзара", "Марина Е", "Аня"]:
    if mgr not in by_mgr:
        continue
    mgr_deals = by_mgr[mgr]
    mgr_total = int(sum(d["amount"] for d in mgr_deals))
    lines.append(f"{mgr} ({len(mgr_deals)} сделок, {mgr_total} руб):")
    for d in mgr_deals[:7]:
        link = f"https://{BITRIX_DOMAIN}/crm/deal/details/{d['id']}/"
        amt = int(d["amount"])
        stage = d.get("stage", "?")
        stage_name = "Новый заказ" if stage == "NEW" else "Ожид. предоплаты" if stage == "8" else stage
        lines.append(f"  #{d['id']} - {amt} руб ({stage_name}, молчит {d['days_silent']} дн.) -> {link}")
    if len(mgr_deals) > 7:
        lines.append(f"  ... и ещё {len(mgr_deals)-7}")
    lines.append("")

lines.append("Стадии 'Новый заказ' = клиент оставил заявку, никто не перезвонил.")
lines.append("Стадия 'Ожид. предоплаты' = нужно напомнить клиенту об оплате.")
lines.append("")
lines.append("- Анжелочка")

msg = "\n".join(lines)
print(msg)
print(f"\n--- {len(msg)} символов ---\n")
result = send_bitrix_message(msg)
print(f"Результат: msg #{result}")
