#!/usr/bin/env python3
"""
CEO Report — Расширенный отчёт руководителю из Битрикс24.
Использует bitrix_scanner.py как ЕДИНСТВЕННЫЙ источник данных.

🔴 ЖЕЛЕЗНОЕ ПРАВИЛО:
Никогда не дёргать Bitrix API напрямую! Использовать только scan из bitrix_scanner.py.
Это гарантирует:
  • UF_CRM поля (оплаты 1С, номера заказов)
  • Товарные строки (породы, количество)
  • Забытые сделки (DATE_MODIFY > 3 дней)
  • Лиды с источниками (SOURCE_ID)
  • Консистентность с daily_report.py

Отправляется Игорю (176203333) ежедневно в 20:00 MSK.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

# Загрузка .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OWNER_ID = 176203333  # Игорь
PROXY_URL = os.getenv("TELEGRAM_PROXY")

# Прокси для Telegram
proxies = {}
if PROXY_URL:
    proxy = PROXY_URL.replace("socks5://", "socks5h://")
    proxies = {"https": proxy, "http": proxy}


def run_bitrix_scanner():
    """
    🔴 ЖЕЛЕЗНОЕ ПРАВИЛО: Запускаем bitrix_scanner.py для получения ПОЛНЫХ данных.
    Никогда не дёргать API напрямую!
    """
    scanner_path = os.path.join(BASE_DIR, "agent", "bitrix_scanner.py")
    scan_log_dir = os.path.join(BASE_DIR, "data", "bitrix_scans")
    
    # Запускаем сканер (он сам сохранит в scan_YYYYMMDD_HHMM.json)
    venv_python = os.path.join(BASE_DIR, "venv", "bin", "python3")
    if not os.path.exists(venv_python):
        venv_python = sys.executable
    
    try:
        result = subprocess.run(
            [venv_python, scanner_path],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(scanner_path)
        )
        
        if result.returncode != 0:
            print(f"⚠️ Scanner error: {result.stderr[:200]}")
            return None
        
        # Находим последний файл скана
        import glob
        scan_files = sorted(glob.glob(os.path.join(scan_log_dir, "scan_*.json")))
        if not scan_files:
            print("⚠️ Scanner не создал файл скана")
            return None
        
        latest_scan = scan_files[-1]
        print(f"✅ Скан завершен: {latest_scan}")
        
        # Читаем результат
        with open(latest_scan, 'r', encoding='utf-8') as f:
            scan = json.load(f)
        
        return scan
    
    except subprocess.TimeoutExpired:
        print("⚠️ Scanner timeout (120s)")
        return None
    except Exception as e:
        print(f"⚠️ Scanner exception: {e}")
        return None


def format_rubles(amount):
    """Форматирует рубли с пробелами."""
    try:
        return f"{int(float(amount)):,}".replace(",", " ")
    except:
        return str(amount)


def get_manager_name(mgr_id):
    """Имя менеджера по ID."""
    users = {
        "1": "Андрей", "22": "Олег Мосин", "124": "Татьяна",
        "1528": "Аня", "1586": "Менеджер", "4388": "Эльзара",
        "40318": "Марина Е", "40994": "Ольга М.", "41624": "Анжелочка",
        "31200": "Марина Е",  # Из CRM
        "37728": "ID:37728"
    }
    return users.get(str(mgr_id), f"ID:{mgr_id}")


def get_forgotten_deals(deal_items, days=3):
    """
    🔴 ЖЕЛЕЗНОЕ ПРАВИЛО: Забытые сделки = ACTIVE_STAGES + DATE_MODIFY > 3 дней.
    """
    # Активные стадии (клиент ждёт, менеджер не закрыл)
    active_stages = {"NEW", "8", "UC_P1MPTA", "EXECUTING", "9", "3", "11"}
    
    forgotten = []
    now = datetime.now()
    
    for d in deal_items:
        stage = d.get("STAGE_ID", "")
        modified = d.get("DATE_MODIFY", "")
        
        # Только активные стадии
        if stage not in active_stages:
            continue
        
        # Проверяем давность
        if modified:
            try:
                mod_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                age = (now - mod_dt).days
                if age > days:
                    forgotten.append(d)
            except:
                pass
    
    return sorted(forgotten, key=lambda x: x.get("DATE_MODIFY", ""))[:5]


def get_product_stats(deal_items):
    """
    🔴 ЖЕЛЕЗНОЕ ПРАВИЛО: Товарные строки из 1С = реальные породы.
    """
    product_stats = {}
    
    for d in deal_items:
        products = d.get("PRODUCTS", [])
        if not products:
            # Пробуем из товарных строк
            product_rows = d.get("PRODUCT_ROWS", [])
            if product_rows:
                for pr in product_rows:
                    name = pr.get("NAME", "Неизвестно")
                    qty = int(pr.get("QUANTITY", 1) or 1)
                    price = float(pr.get("PRICE", 0) or 0)
                    
                    if name not in product_stats:
                        product_stats[name] = {"count": 0, "amount": 0, "deals": 0}
                    product_stats[name]["count"] += qty
                    product_stats[name]["amount"] += qty * price
                    product_stats[name]["deals"] += 1
    
    return product_stats


def build_ceo_report(scan):
    """Собирает расширенный отчёт из данных скана."""
    now = datetime.now()
    today = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    
    # Данные из скана
    deals = scan.get("deals", {})
    activities = scan.get("activities", {})
    leads = scan.get("leads", {})
    payments = scan.get("payments", {})
    managers = scan.get("manager_stats", {})
    
    deal_items = deals.get("items", [])
    lead_items = leads.get("items", [])
    
    print(f"\n{'='*60}")
    print(f"📊 CEO REPORT — {today} {time_str}")
    print(f"{'='*60}\n")
    
    # 1. Пропущенные звонки
    missed_calls = activities.get("missed_calls", 0)
    print(f"📞 Пропущенные звонки: {missed_calls}")
    
    # 2. Сделки по менеджерам
    total_amount = float(deals.get("total_amount", 0))
    print(f"💰 Сделки: {deals.get('count', 0)} (на {format_rubles(total_amount)}₽)")
    
    # 3. Лиды и конверсия
    leads_count = leads.get("count", 0)
    deals_count = deals.get("count", 0)
    conversion = f"{(deals_count / max(leads_count, 1) * 100):.0f}%"
    print(f"📥 Лиды: {leads_count}, Конверсия: {conversion}")
    
    # 4. Счета
    paid_count = payments.get("paid_count", 0)
    paid_amount = payments.get("paid_amount", 0)
    unpaid_count = payments.get("unpaid_count", 0)
    unpaid_amount = payments.get("unpaid_amount", 0)
    print(f"🧾 Счета: оплачено {paid_count} ({format_rubles(paid_amount)}₽)")
    
    # 5. Забытые сделки
    forgotten = get_forgotten_deals(deal_items)
    print(f"⏰ Забытые сделки: {len(forgotten)}")
    
    # 6. Товары/породы
    product_stats = get_product_stats(deal_items)
    print(f"🐔 Продано пород: {len(product_stats)}")
    
    # Формируем текст отчёта
    lines = [
        "══════════════════════════════════════════",
        f"📊 ОТЧЁТ РУКОВОДИТЕЛЮ — {today}",
        f"⏰ Сформирован: {time_str} MSK",
        "══════════════════════════════════════════",
        "",
        "🔴 КРИТИЧЕСКОЕ",
        f"   • Пропущенных звонков: {missed_calls}" + (" ⚠️" if missed_calls > 0 else ""),
        f"   • Забытых сделок: {len(forgotten)}" + (" ⚠️" if len(forgotten) > 0 else ""),
        "",
        "💰 CRM",
        f"   • Лидов: {leads_count}",
        f"   • Сделок: {deals_count} (на {format_rubles(total_amount)}₽)",
        f"   • Конверсия: {conversion}",
        "",
        "📞 ТЕЛЕФОНИЯ",
        f"   • Всего звонков: {activities.get('calls_count', 0)}",
        f"   • Отвеченных: {activities.get('answered_calls', 0)}",
        f"   • Пропущенных: {missed_calls}",
        "",
        "👥 МЕНЕДЖЕРЫ",
    ]
    
    # Топ менеджеров
    for name, stats in sorted(managers.items(), key=lambda x: -x[1].get("amount", 0)):
        if name in ("СРМ Б24", "Служебный", "Admin"):
            continue
        deals_m = stats.get("deals", 0)
        calls_m = stats.get("calls", 0)
        amount_m = stats.get("amount", 0)
        lines.append(f"   • {name}: {deals_m} сделок, {calls_m} звонков ({format_rubles(amount_m)}₽)")
    
    # Воронка по стадиям
    stage_stats = {}
    for d in deal_items:
        stage = d.get("STAGE_ID", "UNKNOWN")
        stage_name = d.get("STAGE_NAME", stage)
        opp = float(d.get("OPPORTUNITY", 0) or 0)
        
        if stage_name not in stage_stats:
            stage_stats[stage_name] = {"count": 0, "amount": 0}
        stage_stats[stage_name]["count"] += 1
        stage_stats[stage_name]["amount"] += opp
    
    if stage_stats:
        lines.extend([
            "",
            "📊 ВОРОНКА ПО СТАДИЯМ",
        ])
        stage_icons = {
            "NEW": "🆕", "PREPAYMENT": "⏳", "INVOICE": "📝",
            "WON": "✅", "LOSE": "❌", "EXECUTING": "🚧"
        }
        for stage_name, stats in sorted(stage_stats.items(), key=lambda x: -x[1]["amount"]):
            icon = stage_icons.get(stage_name.split(":")[0].strip(), "📋")
            lines.append(f"   {icon} {stage_name}: {stats['count']} шт. ({format_rubles(stats['amount'])}₽)")
    
    # Забытые сделки
    if forgotten:
        lines.extend([
            "",
            "⏰ ЗАБЫТЫЕ СДЕЛКИ (>3 дней без движения)",
        ])
        for fd in forgotten:
            title = fd.get("TITLE", "Без названия")
            modified = fd.get("DATE_MODIFY", "")[:10]
            opp = format_rubles(fd.get("OPPORTUNITY", 0))
            mgr_id = fd.get("ASSIGNED_BY_ID", "?")
            mgr_name = get_manager_name(mgr_id)
            lines.append(f"   • {title} ({modified}) — {opp}₽ ({mgr_name})")
    
    # Товары/породы
    if product_stats:
        lines.extend([
            "",
            "🐔 ТОП ПРОДАЖ (породы)",
        ])
        for prod_name, stats in sorted(product_stats.items(), key=lambda x: -x[1]["amount"])[:5]:
            lines.append(f"   • {prod_name}: {stats['count']} шт. ({format_rubles(stats['amount'])}₽)")
    
    # Счета
    lines.extend([
        "",
        "🧾 СЧЕТА (1С)",
        f"   • ✅ Оплачено: {paid_count} ({format_rubles(paid_amount)}₽)",
        f"   • ⏳ Не оплачено: {unpaid_count} ({format_rubles(unpaid_amount)}₽)",
    ])
    
    # Лиды по источникам
    lead_sources = {}
    for l in lead_items[:100]:
        src = l.get("SOURCE_ID", "UNKNOWN")
        lead_sources[src] = lead_sources.get(src, 0) + 1
    
    if lead_sources:
        lines.extend([
            "",
            "📥 ЛИДЫ ПО ИСТОЧНИКАМ",
        ])
        src_labels = {
            "CALL": "📞 Звонки", "OPENLINE": "💬 Чаты", "EMAIL": "📧 Email",
            "VK": "📱 VK", "WEBFORM": "🌐 Сайт", "FACEBOOK": "FB"
        }
        for src, cnt in sorted(lead_sources.items(), key=lambda x: -x[1]):
            label = src_labels.get(src, src)
            lines.append(f"   • {label}: {cnt}")
    
    # Сотрудники
    lines.extend([
        "",
        "👥 СОТРУДНИКИ",
        f"   • Активных: {len(managers)}",
    ])
    
    lines.extend([
        "",
        "══════════════════════════════════════════",
        "🤖 Отчёт собран Анжелочкой (CEO Report v3 — bitrix_scanner)",
    ])
    
    report_text = "\n".join(lines)
    print(f"\n{report_text}")
    
    return report_text


def send_telegram(chat_id, text):
    """Отправка в Telegram."""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не задан")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }, proxies=proxies, timeout=15)
        
        if resp.status_code == 200:
            print(f"✅ Отправлено chat_id={chat_id}")
            return True
        else:
            print(f"⚠️ Telegram error: {resp.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ Send error: {e}")
        return False


if __name__ == "__main__":
    # 🔴 ЖЕЛЕЗНОЕ ПРАВИЛО: Запускаем bitrix_scanner.py
    print("🔴 Запуск bitrix_scanner.py для получения ПОЛНЫХ данных...")
    scan = run_bitrix_scanner()
    
    if not scan:
        print("❌ Не удалось получить данные скана!")
        sys.exit(1)
    
    # Генерация отчёта
    report = build_ceo_report(scan)
    
    # Отправка Игорю
    print("\n📤 Отправка в Telegram...")
    
    import requests
    send_telegram(OWNER_ID, report)
    
    print("\n✅ Готово!")
