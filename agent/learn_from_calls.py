#!/usr/bin/env python3
"""
learn_from_calls.py — Анжела учится из саммари звонков менеджеров.

После каждого скана CRM извлекает из bitrixgpt_summary:
  - Актуальные цены по породам
  - Даты поставок/доставок
  - Доступность пород (есть/нет/когда будет)
  - Клиентские инсайты (жалобы, предпочтения)

Записывает в expert_knowledge.md секцию "📡 ОПЕРАТИВНАЯ СВОДКА"
(перезаписывается ежедневно — всегда актуальная).

Запуск: python3 learn_from_calls.py [--scan path/to/scan.json]
Автозапуск: вызывается из bitrix_scanner.py после каждого скана.

Создано: 07.05.2026
"""

import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIR = os.path.join(BASE_DIR, "data", "bitrix_scans")
KNOWLEDGE_PATH = os.path.join(BASE_DIR, "data", "expert_knowledge.md")
MSK = timezone(timedelta(hours=3))

# Маркер секции в expert_knowledge.md
SECTION_START = "<!-- DAILY_INTELLIGENCE_START -->"
SECTION_END = "<!-- DAILY_INTELLIGENCE_END -->"


def find_latest_scan():
    """Находит последний скан."""
    scans = sorted(glob.glob(os.path.join(SCAN_DIR, "scan_*.json")))
    return scans[-1] if scans else None


def extract_prices(summaries: list[str]) -> dict:
    """Извлекает цены из саммари."""
    prices = defaultdict(list)  # {порода: [цена1, цена2, ...]}
    
    patterns = [
        # "по цене 85 руб./голова" / "85 руб. за единицу"
        r'(?:по цене|цена|по|стоимость)\s+(\d+)\s*(?:руб|₽|р)\w*[./\s]*(?:за\s+)?(?:голов|единиц|шт|штук)',
        # "цена — 400 рублей" / "400 руб./голову"
        r'(\d+)\s*(?:руб|₽|р)\w*[./\s]*(?:за\s+)?(?:голов|единиц|шт|штук)',
        # "по 85 руб."
        r'по\s+(\d+)\s*(?:руб|₽|р)',
    ]
    
    breed_patterns = [
        r'(бройлер\w*)',
        r'(РОСС[\s-]*308)',
        r'(КОББ[\s-]*500)',
        r'(Кобб[\s-]*500)',
        r'(хайсекс\s*(?:браун|коричнев)?)',
        r'(адлерск\w*\s*серебрист\w*)',
        r'(ред\s*бро)',
        r'(рейнджер\w*)',
        r'(мулард\w*|муларт\w*)',
        r'(гус\w*\s*(?:линда|линд)?)',
        r'(ут\w*\s*(?:агидель|черри|голубой\s*фаворит)?)',
        r'(индюш\w*|индюк\w*|индейк\w*)',
        r'(доминант\w*)',
        r'(мастер[\s-]*гр\w*)',
        r'(легор\w*)',
        r'(несуш\w*)',
    ]
    
    for text in summaries:
        text_lower = text.lower()
        for pp in patterns:
            for m in re.finditer(pp, text_lower):
                price = int(m.group(1))
                if price < 5 or price > 5000:
                    continue
                # Ищем ближайшую породу
                context = text_lower[max(0, m.start()-100):m.end()+50]
                for bp in breed_patterns:
                    bm = re.search(bp, context, re.IGNORECASE)
                    if bm:
                        breed = bm.group(1).strip().title()
                        prices[breed].append(price)
                        break
    
    # Усредняем
    result = {}
    for breed, price_list in prices.items():
        avg = sum(price_list) / len(price_list)
        result[breed] = {
            "avg": round(avg),
            "min": min(price_list),
            "max": max(price_list),
            "count": len(price_list),
        }
    return result


def extract_deliveries(summaries: list[str]) -> list[dict]:
    """Извлекает даты доставок из саммари."""
    deliveries = []
    
    # Паттерны дат: "доставка 14.05.2026" / "поставка 28 мая"
    date_patterns = [
        r'(?:доставк\w*|поставк\w*|забор\w*|выезд\w*)\s+(?:на\s+|запланирован\w*\s+на\s+)?(\d{1,2}[./]\d{1,2}[./]?\d{0,4})',
        r'(?:доставк\w*|поставк\w*)\s+(?:на\s+)?(\d{1,2})\s+(мая|июня|апреля|марта|июля)',
    ]
    
    for text in summaries:
        for dp in date_patterns:
            for m in re.finditer(dp, text, re.IGNORECASE):
                deliveries.append(m.group(0)[:60])
    
    return list(set(deliveries))[:20]


def extract_availability(summaries: list[str]) -> dict:
    """Что есть / чего нет / когда будет."""
    available = []
    unavailable = []
    
    for text in summaries:
        text_lower = text.lower()
        if any(w in text_lower for w in ['недоступн', 'отсутствуют', 'не поставляются', 'нет в наличии', 'невозможен']):
            # Ищем что именно недоступно
            for bp in [r'(мастер[\s-]*гр\w*)', r'(индюш\w*|индюк\w*)', r'(легор\w*)', r'(московск\w* черн\w*)', 
                       r'(плимутрок\w*)', r'(доминант\w*)', r'(гуси?\w*)', r'(ут\w+)', r'(бройлер\w*)']:
                bm = re.search(bp, text_lower)
                if bm:
                    item = bm.group(1).strip().title()
                    if item not in unavailable:
                        unavailable.append(item)
        
        if any(w in text_lower for w in ['заказ подтвержд', 'заказано', 'есть в наличии', 'доступн']):
            for bp in [r'(бройлер\w*)', r'(хайсекс\w*)', r'(адлерск\w*)', r'(ред\s*бро)', r'(мулард\w*)',
                       r'(гус\w*)', r'(ут\w*\s*агидель)', r'(голубой\s*фаворит)', r'(рейнджер\w*)', r'(редбро\w*)']:
                bm = re.search(bp, text_lower)
                if bm:
                    item = bm.group(1).strip().title()
                    if item not in available:
                        available.append(item)
    
    return {"available": available[:15], "unavailable": unavailable[:10]}


def extract_insights(summaries: list[str]) -> list[str]:
    """Клиентские инсайты — жалобы, нюансы."""
    insights = []
    
    negative_markers = ['недовольн', 'отказал', 'жалоб', 'негативн', 'ошибк', 'не то', 'не тот', 'перепута']
    
    for text in summaries:
        text_lower = text.lower()
        if any(m in text_lower for m in negative_markers):
            # Сокращаем до 150 символов
            short = text[:150].strip()
            if short not in insights:
                insights.append(short)
    
    return insights[:10]


def build_intelligence_section(scan_path: str) -> str:
    """Формирует секцию оперативной сводки."""
    with open(scan_path, 'r') as f:
        data = json.load(f)
    
    calls = data.get("activities", {}).get("calls", [])
    summaries = [c.get("bitrixgpt_summary", "") for c in calls if c.get("bitrixgpt_summary")]
    
    if not summaries:
        return ""
    
    now = datetime.now(MSK)
    prices = extract_prices(summaries)
    availability = extract_availability(summaries)
    deliveries = extract_deliveries(summaries)
    insights = extract_insights(summaries)
    
    # Статистика по менеджерам
    users = data.get("users", {})
    mgr_stats = defaultdict(lambda: {"in": 0, "out": 0})
    for c in calls:
        rid = str(c.get("RESPONSIBLE_ID", ""))
        u = users.get(rid, {})
        name = f"{u.get('NAME','')} {u.get('LAST_NAME','')}".strip() if isinstance(u, dict) else str(u)
        if c.get("DIRECTION") == "1":
            mgr_stats[name]["in"] += 1
        else:
            mgr_stats[name]["out"] += 1
    
    lines = []
    lines.append(f"\n{SECTION_START}")
    lines.append(f"## 📡 ОПЕРАТИВНАЯ СВОДКА (обновлено {now.strftime('%d.%m.%Y %H:%M')})")
    lines.append(f"Источник: {len(summaries)} саммари из {len(calls)} звонков за день\n")
    
    # Менеджеры
    lines.append("### 👩 Менеджеры сегодня")
    for name, stats in sorted(mgr_stats.items(), key=lambda x: -(x[1]["in"]+x[1]["out"])):
        total = stats["in"] + stats["out"]
        lines.append(f"- {name}: {total} звонков (📥{stats['in']} 📤{stats['out']})")
    lines.append("")
    
    # Цены
    if prices:
        lines.append("### 💰 Актуальные цены (из звонков)")
        for breed, info in sorted(prices.items(), key=lambda x: -x[1]["count"]):
            if info["min"] == info["max"]:
                lines.append(f"- {breed}: {info['avg']}₽/шт ({info['count']} упомин.)")
            else:
                lines.append(f"- {breed}: {info['min']}–{info['max']}₽/шт, ср. {info['avg']}₽ ({info['count']} упомин.)")
        lines.append("")
    
    # Доступность
    if availability["available"]:
        lines.append("### ✅ Сейчас в наличии / заказывают")
        lines.append(", ".join(availability["available"]))
        lines.append("")
    
    if availability["unavailable"]:
        lines.append("### ❌ Нет в наличии / не поставляются")
        lines.append(", ".join(availability["unavailable"]))
        lines.append("")
    
    # Ближайшие поставки
    if deliveries:
        lines.append("### 🚚 Ближайшие поставки (из разговоров)")
        for d in deliveries[:15]:
            lines.append(f"- {d}")
        lines.append("")
    
    # Инсайты
    if insights:
        lines.append("### ⚠️ Клиентские инсайты")
        for ins in insights:
            lines.append(f"- {ins}")
        lines.append("")
    
    lines.append(SECTION_END)
    
    return "\n".join(lines)


def update_knowledge(intelligence: str):
    """Обновляет expert_knowledge.md — заменяет секцию DAILY_INTELLIGENCE."""
    if not intelligence:
        print("⚠️ Нет данных для обучения")
        return
    
    if not os.path.exists(KNOWLEDGE_PATH):
        print(f"❌ {KNOWLEDGE_PATH} не найден")
        return
    
    with open(KNOWLEDGE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Убираем старую секцию
    if SECTION_START in content:
        start = content.index(SECTION_START)
        end = content.index(SECTION_END) + len(SECTION_END) if SECTION_END in content else len(content)
        content = content[:start].rstrip() + content[end:].lstrip()
    
    # Убираем старые блоки "--- Разведка ..." 
    content = re.sub(r'\n--- Разведка [\d\-\s:]+ ---\n.*?(?=\n---|$)', '', content, flags=re.DOTALL)
    content = content.rstrip()
    
    # Добавляем новую секцию
    content = content + "\n\n" + intelligence + "\n"
    
    with open(KNOWLEDGE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ expert_knowledge.md обновлён — оперативная сводка из саммари звонков")


def main():
    scan_path = None
    
    # Аргумент --scan
    if "--scan" in sys.argv:
        idx = sys.argv.index("--scan") + 1
        if idx < len(sys.argv):
            scan_path = sys.argv[idx]
    
    if not scan_path:
        scan_path = find_latest_scan()
    
    if not scan_path or not os.path.exists(scan_path):
        print("❌ Скан не найден")
        sys.exit(1)
    
    print(f"📚 Учусь из саммари: {os.path.basename(scan_path)}")
    
    intelligence = build_intelligence_section(scan_path)
    
    if intelligence:
        update_knowledge(intelligence)
        # Показываем что узнали
        print(intelligence[:500] + "...")
    else:
        print("⚠️ В скане нет саммари — нечему учиться")


if __name__ == "__main__":
    main()
