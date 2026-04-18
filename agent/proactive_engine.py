#!/usr/bin/env python3
"""
📡 PROACTIVE ENGINE — Движок проактивных действий.

Google AI Trend #3: «Danfoss: automated 80% of transactional decisions,
reduced response time from 42 hours to near real-time»

Задачи:
1. Находит забытые сделки в CRM
2. Находит «уснувших» клиентов (из памяти)
3. Генерирует рекомендации для менеджеров
4. Отправляет алерты Андрею через Битрикс

Запуск: python3 proactive_engine.py
Cron: каждые 6 часов

v1.0 — 15.04.2026
"""
import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

REPORT_DIR = os.path.join(BASE_DIR, "data", "proactive")
os.makedirs(REPORT_DIR, exist_ok=True)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def bitrix_call(method, params=None):
    try:
        resp = requests.get(f"{BITRIX_URL}/{method}", params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"  API error: {e}")
    return {}


def send_bitrix_message(text, dialog_id=1):
    """Отправляем сообщение в Битрикс."""
    try:
        resp = requests.post(f"{BITRIX_URL}/im.message.add.json", json={
            "DIALOG_ID": dialog_id,
            "MESSAGE": text[:4000]
        }, timeout=15)
        return resp.json().get("result")
    except Exception as e:
        log(f"  Send error: {e}")
    return None


# ============================================================
# ТРИГГЕР 1: Забытые сделки в CRM
# ============================================================
def check_forgotten_deals(days_threshold=7):
    """Сканирует CRM на сделки, зависшие в активных стадиях."""
    log("🔍 Проверяю забытые сделки...")
    
    forgotten = []
    threshold = datetime.now() - timedelta(days=days_threshold)
    
    # Получаем активные сделки
    data = bitrix_call("crm.deal.list", {
        "filter[>DATE_CREATE]": "2026-01-01",
        "filter[CLOSED]": "N",
        "select[]": ["ID", "TITLE", "DATE_MODIFY", "STAGE_ID", "OPPORTUNITY", "CONTACT_ID"],
        "order[DATE_MODIFY]": "ASC"
    })
    
    deals = data.get("result", [])
    
    for deal in deals:
        modified = deal.get("DATE_MODIFY", "")
        if modified:
            try:
                mod_dt = datetime.fromisoformat(modified.replace("T", " ").split("+")[0])
                if mod_dt < threshold:
                    days_idle = (datetime.now() - mod_dt).days
                    forgotten.append({
                        "id": deal["ID"],
                        "title": deal.get("TITLE", "?"),
                        "stage": deal.get("STAGE_ID", "?"),
                        "amount": deal.get("OPPORTUNITY", 0),
                        "days_idle": days_idle,
                        "contact_id": deal.get("CONTACT_ID")
                    })
            except Exception:
                pass
    
    log(f"  Найдено забытых сделок: {len(forgotten)}")
    return forgotten


# ============================================================
# ТРИГГЕР 2: Уснувшие клиенты (из памяти)
# ============================================================
def check_dormant_clients(days_threshold=30):
    """Находит клиентов, которые давно не обращались."""
    log("🔍 Проверяю уснувших клиентов...")
    
    try:
        from client_memory import memory
        dormant = memory.get_dormant_clients(days=days_threshold)
        log(f"  Уснувших клиентов: {len(dormant)}")
        return dormant
    except Exception as e:
        log(f"  Ошибка загрузки памяти: {e}")
        return []


# ============================================================
# ТРИГГЕР 3: Сезонные возможности
# ============================================================
def check_seasonal_opportunities():
    """Анализирует сезонный спрос и предлагает действия."""
    log("🔍 Проверяю сезонные возможности...")
    
    month = datetime.now().month
    
    opportunities = []
    
    if month in [3, 4]:  # Март-Апрель: ПИК сезона
        opportunities.append({
            "type": "season_peak",
            "message": "🔥 ПИК СЕЗОНА! Бройлер КОББ-500 и РОСС-308 в максимальном спросе. Рекомендация: поднять все объявления бройлеров на Авито, добавить пометку 'Бронирование открыто!'",
            "priority": 1
        })
    elif month in [5, 6]:  # Май-Июнь: Индюки и утки
        opportunities.append({
            "type": "season_turkey",
            "message": "🦃 Сезон индюков и уток! Спрос на БИГ-6 и Мулард растёт. Рекомендация: активировать продвижение индюков x5 на Авито.",
            "priority": 2
        })
    elif month in [7, 8]:  # Июль-Август: Второй вывод
        opportunities.append({
            "type": "season_second",
            "message": "🐣 Второй вывод бройлеров! Рекомендация: написать клиентам из весеннего сезона — предложить повторный заказ со скидкой.",
            "priority": 2
        })
    elif month in [9, 10]:  # Сентябрь-Октябрь: Несушки
        opportunities.append({
            "type": "season_layers",
            "message": "🥚 Сезон несушек на зиму! Ломан Браун и Доминант в спросе. Рекомендация: акцент на Авито на несушек.",
            "priority": 3
        })
    
    log(f"  Сезонных рекомендаций: {len(opportunities)}")
    return opportunities


# ============================================================
# ГЕНЕРАЦИЯ ОТЧЁТА
# ============================================================
def generate_proactive_report(forgotten_deals, dormant_clients, seasonal):
    """Формирует отчёт и отправляет Андрею."""
    
    report_lines = []
    report_lines.append("📡 ПРОАКТИВНЫЙ ОТЧЁТ АНЖЕЛОЧКИ\n")
    report_lines.append(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
    
    has_actions = False
    
    # Забытые сделки
    if forgotten_deals:
        has_actions = True
        total_amount = sum(int(float(d.get("amount", 0))) for d in forgotten_deals)
        report_lines.append(f"🔴 ЗАБЫТЫЕ СДЕЛКИ: {len(forgotten_deals)} (на сумму {total_amount:,}₽)")
        for d in forgotten_deals[:10]:
            amt = int(float(d.get('amount', 0)))
            report_lines.append(f"  • [{d['id']}] {d['title']} — {d['days_idle']} дн. без движения ({amt:,}₽)")
        report_lines.append("")
    
    # Уснувшие клиенты
    if dormant_clients:
        has_actions = True
        total_ltv = sum(c.get("ltv", 0) for c in dormant_clients)
        report_lines.append(f"🟡 УСНУВШИЕ КЛИЕНТЫ: {len(dormant_clients)} (LTV: {total_ltv:,.0f}₽)")
        for c in dormant_clients[:5]:
            prefs = ", ".join(c.get("preferences", [])[:3])
            report_lines.append(f"  • {c['name']} — {c['days_silent']} дн. молчания | LTV: {c['ltv']}₽ | Любит: {prefs}")
        report_lines.append("  💡 Рекомендация: отправить персональное предложение")
        report_lines.append("")
    
    # Сезонные
    if seasonal:
        has_actions = True
        for s in seasonal:
            report_lines.append(f"📅 {s['message']}")
        report_lines.append("")
    
    if not has_actions:
        report_lines.append("✅ Всё чисто! Нет забытых сделок и уснувших клиентов.")
    
    report = "\n".join(report_lines)
    
    # Сохраняем
    report_path = os.path.join(REPORT_DIR, f"proactive_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    log(f"📝 Отчёт сохранён: {report_path}")
    
    return report, has_actions


# ============================================================
# MAIN
# ============================================================
def run_proactive_cycle():
    """Полный цикл проактивных проверок."""
    log("=" * 50)
    log("📡 PROACTIVE ENGINE v1.0 — Цикл запущен")
    log("=" * 50)
    
    # 1. Забытые сделки
    forgotten = check_forgotten_deals(days_threshold=7)
    
    # 2. Уснувшие клиенты
    dormant = check_dormant_clients(days_threshold=30)
    
    # 3. Сезонные
    seasonal = check_seasonal_opportunities()
    
    # 4. Генерация отчёта
    report, has_actions = generate_proactive_report(forgotten, dormant, seasonal)
    
    # 5. Публикуем инсайты в A2A шину
    try:
        from a2a_protocol import report_insight, notify
        
        if forgotten:
            report_insight("proactive", f"Найдено {len(forgotten)} забытых сделок в CRM", {
                "count": len(forgotten),
                "total_amount": sum(int(float(d.get("amount", 0))) for d in forgotten),
                "top_deals": forgotten[:5]
            })
        
        if dormant:
            report_insight("proactive", f"Найдено {len(dormant)} уснувших клиентов", {
                "count": len(dormant),
                "clients": dormant[:5]
            })
        
        if seasonal:
            for s in seasonal:
                notify("proactive", "angelochka", s["message"], 
                       {"type": s["type"]}, priority=s["priority"])
        
        log("🔗 A2A: инсайты опубликованы в шину")
    except Exception as e:
        log(f"⚠️ A2A publish skipped: {e}")
    
    # 6. Отправляем Андрею если есть что показать
    if has_actions:
        log("📤 Отправляю отчёт Андрею...")
        send_bitrix_message(f"— Анжелочка\n\n{report}")
        log("✅ Отправлено!")
    else:
        log("✅ Всё чисто — не беспокоим Андрея.")
    
    log("")
    log("📡 Цикл завершён.")
    return report


if __name__ == "__main__":
    run_proactive_cycle()
