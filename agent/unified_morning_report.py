#!/usr/bin/env python3
"""
unified_morning_report.py — ЕДИНЫЙ утренний отчёт для Игоря.

Объединяет:
1. CRM данные за вчера (сделки, лиды, менеджеры)
2. Транскрибацию звонков (топ пород, крупные заказы, качество)
3. Ночной аудит кода (ruff ошибки)

Запуск: 08:00 MSK ежедневно
Получатель: Игорь (176203333)
"""
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "..", "reports")
SCAN_DIR = os.path.join(DATA_DIR, "bitrix_scans")
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "transcripts")

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OWNER_ID = 176203333  # Игорь
PROXY_URL = os.getenv("TELEGRAM_PROXY")

proxies = {}
if PROXY_URL:
    proxy = PROXY_URL.replace("socks5://", "socks5h://")
    proxies = {"https": proxy, "http": proxy}


def format_rubles(amount):
    """Форматирует рубли с пробелами."""
    try:
        return f"{int(float(amount)):,}".replace(",", " ")
    except:
        return str(amount)


def find_latest_scan():
    """Находит последний скан Битрикс."""
    pattern = os.path.join(SCAN_DIR, "scan_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if files:
        with open(files[0], 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def find_transcripts_for_date(date_str):
    """Находит транскрипты за дату."""
    pattern = os.path.join(TRANSCRIPT_DIR, date_str, "call_*.json")
    files = glob.glob(pattern)
    transcripts = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as file:
                transcripts.append(json.load(file))
        except:
            pass
    return transcripts


def analyze_call_quality(transcripts, deals):
    """Анализирует качество звонков и извлекает топ пород."""
    if not transcripts:
        return None
    
    # Статистика по менеджерам
    mgr_stats = defaultdict(lambda: {
        "total": 0, "success": 0, "pending": 0, "no_contact": 0,
        "named_self": 0, "asked_city": 0, "upsell": 0
    })
    
    # Топ пород
    breed_counts = defaultdict(int)
    
    # Крупные заказы
    large_orders = []
    
    # Проблемы
    problems = defaultdict(int)
    
    for t in transcripts:
        summary = t.get("summary", "")
        transcript = t.get("transcript", "")
        mgr = t.get("manager", "Неизвестно")
        phone = t.get("phone", "")
        
        mgr_stats[mgr]["total"] += 1
        
        # Результативность
        if any(kw in summary.lower() for kw in ["заказ подтвержден", "доставка запланирована", "оформлен"]):
            mgr_stats[mgr]["success"] += 1
        elif any(kw in summary.lower() for kw in ["подумает", "перезвонит", "ожидает"]):
            mgr_stats[mgr]["pending"] += 1
        
        # Контакт не взят
        if "контакт не предоставлен" in summary.lower() or "контактные данные не предоставлены" in summary.lower():
            mgr_stats[mgr]["no_contact"] += 1
        
        # Назвал себя
        if any(kw in transcript.lower() for kw in ["анжелочка", "анжела", "менеджер"]):
            mgr_stats[mgr]["named_self"] += 1
        
        # Уточнял город
        if any(kw in transcript.lower() for kw in ["город", "доставк", "адрес"]):
            mgr_stats[mgr]["asked_city"] += 1
        
        # Апселл
        if any(kw in transcript.lower() for kw in ["корм", "аптечк", "петуш", "брoйлер"]):
            mgr_stats[mgr]["upsell"] += 1
        
        # Извлекаем породы из транскрипта
        breeds = ["бройлер", "мулард", "агидель", "адлер", "ред бро", "индюк", "гус", "утк", "хайсек", "доминант"]
        for b in breeds:
            if b in transcript.lower():
                breed_counts[b.title()] += 1
        
        # Проблемы
        if "отказ" in summary.lower():
            problems["Отказы клиентов"] += 1
        if "не взял контакт" in summary.lower():
            problems["Контакт не взят"] += 1
        if "перезвонит" in summary.lower():
            problems["Клиент обещал перезвонить"] += 1
    
    # Крупные заказы из сделок
    for d in deals.get("items", [])[:50]:
        opp = float(d.get("OPPORTUNITY", 0) or 0)
        if opp > 30000:  # > 30К₽
            large_orders.append({
                "title": d.get("TITLE", "Без названия"),
                "amount": opp,
                "mgr": d.get("ASSIGNED_BY_ID", "?")
            })
    
    return {
        "mgr_stats": dict(mgr_stats),
        "breed_counts": dict(sorted(breed_counts.items(), key=lambda x: -x[1])[:10]),
        "large_orders": sorted(large_orders, key=lambda x: -x["amount"])[:5],
        "problems": dict(sorted(problems.items(), key=lambda x: -x[1])[:5])
    }


def find_latest_audit():
    """Находит последний ночной аудит."""
    pattern = os.path.join(REPORTS_DIR, "night_audit_ai-eggs_*.md")
    files = sorted(glob.glob(pattern), reverse=True)
    if files:
        with open(files[0], 'r', encoding='utf-8') as f:
            content = f.read()
        # Извлекаем ключевые метрики
        metrics = {}
        for line in content.split('\n'):
            if 'ruff ошибок' in line:
                metrics['ruff_errors'] = line.strip()
            if 'Критических' in line:
                metrics['critical'] = line.strip()
        return metrics
    return {}


def build_unified_report():
    """Собирает единый утренний отчёт."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
    date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    lines = [
        f"🌞 <b>УТРЕННИЙ ОТЧЁТ — {now}</b>",
        f"<i>Данные за {yesterday}</i>",
        "",
        "══════════════════════════════════════════",
        ""
    ]
    
    # === 1. CRM ДАННЫЕ ===
    scan = find_latest_scan()
    if scan:
        deals = scan.get("deals", {})
        activities = scan.get("activities", {})
        managers = scan.get("manager_stats", {})
        
        total_amount = float(deals.get("total_amount", 0))
        deals_count = deals.get("count", 0)
        calls_count = activities.get("calls_count", 0)
        
        lines.extend([
            f"💰 <b>CRM ЗА {yesterday.upper()}</b>",
            f"• Сделок: <b>{deals_count}</b> (на {format_rubles(total_amount)}₽)",
            f"• Звонков: <b>{calls_count}</b>",
            ""
        ])
        
        # Топ менеджеров
        if managers:
            lines.append("👥 <b>Менеджеры:</b>")
            for name, stats in sorted(managers.items(), key=lambda x: -x[1].get("amount", 0))[:3]:
                if name not in ("СРМ Б24", "Служебный", "Admin"):
                    d = stats.get("deals", 0)
                    c = stats.get("calls", 0)
                    a = stats.get("amount", 0)
                    lines.append(f"• {name}: {d} сделок, {c} звонков ({format_rubles(a)}₽)")
            lines.append("")
    
    # === 2. ТРАНСКРИБАЦИЯ ЗВОНКОВ ===
    transcripts = find_transcripts_for_date(date_str)
    if transcripts and scan:
        analysis = analyze_call_quality(transcripts, scan.get("deals", {}))
        
        if analysis:
            lines.extend([
                "══════════════════════════════════════════",
                "",
                f"📞 <b>ТРАНСКРИБАЦИЯ ({len(transcripts)} звонков)</b>",
                ""
            ])
            
            # Топ пород
            if analysis["breed_counts"]:
                lines.append("🏆 <b>Топ пород:</b>")
                for breed, count in list(analysis["breed_counts"].items())[:5]:
                    lines.append(f"• {breed}: {count}")
                lines.append("")
            
            # Крупные заказы
            if analysis["large_orders"]:
                lines.append("💰 <b>Крупные заказы:</b>")
                for order in analysis["large_orders"][:3]:
                    lines.append(f"• {order['title'][:40]} — {format_rubles(order['amount'])}₽")
                total_large = sum(o["amount"] for o in analysis["large_orders"])
                lines.append(f"<b>ИТОГО крупных: ~{format_rubles(total_large)}₽+</b>")
                lines.append("")
            
            # Качество менеджеров
            if analysis["mgr_stats"]:
                lines.append("📈 <b>Качество менеджеров:</b>")
                for mgr, stats in analysis["mgr_stats"].items():
                    if stats["total"] > 0:
                        named_pct = int(stats["named_self"] / stats["total"] * 100)
                        city_pct = int(stats["asked_city"] / stats["total"] * 100)
                        upsell_pct = int(stats["upsell"] / stats["total"] * 100)
                        lines.append(f"• {mgr}: назвались {named_pct}%, город {city_pct}%, апселл {upsell_pct}%")
                lines.append("")
            
            # Проблемы
            if analysis["problems"]:
                lines.append("⚠️ <b>Проблемы:</b>")
                for prob, count in list(analysis["problems"].items())[:3]:
                    lines.append(f"• {prob}: {count}")
                lines.append("")
    
    # === 3. НОЧНОЙ АУДИТ ===
    audit = find_latest_audit()
    if audit:
        lines.extend([
            "══════════════════════════════════════════",
            "",
            "🌙 <b>НОЧНОЙ АУДИТ (02:00)</b>",
        ])
        if 'ruff_errors' in audit:
            lines.append(f"• {audit['ruff_errors']}")
        if 'critical' in audit:
            lines.append(f"• {audit['critical']}")
        lines.append("")
    
    # === ПРИЗЫВ К ДЕЙСТВИЮ ===
    lines.extend([
        "══════════════════════════════════════════",
        "",
        "🚀 <b>План на сегодня:</b>",
        "1. Исправить критические ошибки кода",
        "2. Проверить крупные заказы",
        "3. Проконтролировать проблемные звонки",
        "",
        "<i>Отчёт собран unified_morning_report.py</i>",
    ])
    
    return '\n'.join(lines)


def send_telegram(chat_id, text):
    """Отправка в Telegram."""
    if not TELEGRAM_TOKEN:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": part,
                "parse_mode": "HTML"
            }, proxies=proxies, timeout=30)
            if resp.status_code != 200:
                return False
        return True
    except:
        return False


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"🌞 UNIFIED MORNING REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    report = build_unified_report()
    print(report)
    
    # Сохраняем отчёт + lock-файл для cron-страховки
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_file = os.path.join(DATA_DIR, "unified_reports", f"unified_{today_str}.md")
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n💾 Сохранено: {report_file}")
    
    print("\n📤 Отправка Игорю...")
    if send_telegram(OWNER_ID, report):
        print("✅ Отправлено!")
    else:
        print("❌ Ошибка отправки")
