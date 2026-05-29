#!/usr/bin/env python3
"""
call_alert.py — Немедленные алерты по звонкам Заботкиной.

Запускается после каждого сканирования (добавить в cron после bitrix_scanner.py).
Читает обогащённые звонки из последнего scan_*.json и шлёт алерт Андрею
если сработал один из 3 триггеров:

  1. КРУПНАЯ СДЕЛКА  — сумма >20 000₽ + клиент не закрыт
  2. ЖАЛОБА / УГРОЗА — падёж, компенсация, суд, возврат
  3. ГРУБОСТЬ        — менеджер нагрубил клиенту

Использует dedupe-файл чтобы не слать дубли при повторном запуске.
"""

import glob
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
ADMIN_ID  = 444248782   # Андрей (Заботкина)
OWNER_ID  = 176203333   # Игорь (контроль)
PROXY_URL = os.getenv("TELEGRAM_PROXY", "")

SCAN_DIR   = os.path.join(BASE_DIR, "data", "bitrix_scans")
DEDUPE_FILE = os.path.join(BASE_DIR, "data", "alerts_sent.json")

MSK = timezone(timedelta(hours=3))

# ──────────────────────────────────────────────────────────
# Порог крупной сделки
# ──────────────────────────────────────────────────────────
BIG_DEAL_THRESHOLD = 20_000  # руб.

# ──────────────────────────────────────────────────────────
# Ключевые слова по категориям
# ──────────────────────────────────────────────────────────
COMPLAINT_WORDS = [
    "погибл", "пад[её]ж", "сдохл", "издохл", "мертв",
    "компенсац", "возврат денег", "верн[иу] деньги",
    "суд", "прокурат", "роспотреб", "жалоб",
    "обман", "мошенни",
]

RUDENESS_WORDS = [
    "груб", "хамст", "нагрубил", "оскорбил", "неуважительн",
    "кричал на клиент", "повысил голос", "грубо ответил",
]

# Слова которые говорят что клиент ГОТОВ, но сделка не закрыта
OPEN_DEAL_WORDS = [
    "не оформлен", "перезвонит", "перезвоним", "ожидается обратный звонок",
    "подтвердит позже", "уточнит", "свяжется",
]


# ──────────────────────────────────────────────────────────
# Dedupe — не слать одно и то же дважды
# ──────────────────────────────────────────────────────────
def load_sent() -> set:
    if os.path.exists(DEDUPE_FILE):
        try:
            with open(DEDUPE_FILE) as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_sent(sent: set):
    with open(DEDUPE_FILE, 'w') as f:
        json.dump(list(sent), f)


def alert_id(call_id: str, trigger: str) -> str:
    return hashlib.md5(f"{call_id}:{trigger}".encode()).hexdigest()[:12]


# ──────────────────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────────────────
def send_tg(chat_id: int, text: str) -> bool:
    if not TELEGRAM_TOKEN:
        print("❌ ANGELOCHKA_BOT_TOKEN не задан")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        proxy = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": proxy, "http": proxy}
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text},
                             proxies=proxies, timeout=15)
        return resp.status_code == 200
    except Exception as e:
        print(f"⚠️ TG error: {e}")
        return False


# ──────────────────────────────────────────────────────────
# Проверка триггеров
# ──────────────────────────────────────────────────────────
def match_words(text: str, patterns: list) -> str:
    """Возвращает первое найденное ключевое слово или пустую строку."""
    text_lower = text.lower()
    for pat in patterns:
        if re.search(pat, text_lower):
            # Возвращаем читабельное слово (без regex-спецсимволов)
            return re.sub(r'[\[\(].*?[\]\)]', '', pat).strip("\\")
    return ""


def check_call(call: dict, deals_by_owner: dict) -> list:
    """Проверяет один звонок на все триггеры.
    Возвращает список (trigger_key, message) для каждого срабатывания.
    """
    alerts = []
    summary = call.get("bitrixgpt_summary", "") or ""
    mgr     = call.get("manager_name", "Менеджер")
    call_id = str(call.get("ID", "?"))
    dur     = int(call.get("DURATION", 0))
    dur_str = f"{dur // 60}м{dur % 60}с" if dur > 0 else "—"
    subj    = call.get("SUBJECT", "")
    owner_id = str(call.get("OWNER_ID", ""))

    # Нет резюме — пропускаем
    if not summary and not subj:
        return alerts

    # ── Триггер 1: ЖАЛОБА / УГРОЗА ──────────────────────────
    found = match_words(summary, COMPLAINT_WORDS)
    if found:
        alerts.append((
            f"complaint:{call_id}",
            f"🚨 ЖАЛОБА / УГРОЗА\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 Менеджер: {mgr} · {dur_str}\n"
            f"📝 {summary[:300]}\n"
            f"🔑 Триггер: «{found}»\n"
            f"📋 Звонок ID: {call_id}"
        ))

    # ── Триггер 2: ГРУБОСТЬ ──────────────────────────────────
    found = match_words(summary, RUDENESS_WORDS)
    if found:
        alerts.append((
            f"rude:{call_id}",
            f"😡 ГРУБОСТЬ МЕНЕДЖЕРА\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 Менеджер: {mgr} · {dur_str}\n"
            f"📝 {summary[:300]}\n"
            f"🔑 Слово-маркер: «{found}»\n"
            f"📋 Звонок ID: {call_id}"
        ))

    # ── Триггер 3: КРУПНАЯ СДЕЛКА НЕ ЗАКРЫТА ───────────────
    if dur >= 60:  # только реальные разговоры (>1 мин)
        # Ищем сумму в резюме: "20 000 руб", "15тыс", "150 голов × 90₽" → считаем
        amount = extract_amount_from_summary(summary)
        is_open = bool(match_words(summary, OPEN_DEAL_WORDS))

        # Также проверяем OPPORTUNITY из связанной сделки
        deal_amount = 0.0
        if owner_id and owner_id in deals_by_owner:
            deal_amount = float(deals_by_owner[owner_id].get("OPPORTUNITY", 0) or 0)

        big_amount = max(amount, deal_amount)
        if big_amount >= BIG_DEAL_THRESHOLD and is_open:
            alerts.append((
                f"bigdeal:{call_id}",
                f"💰 КРУПНАЯ СДЕЛКА НЕ ЗАКРЫТА\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"👤 Менеджер: {mgr} · {dur_str}\n"
                f"💵 Сумма: ~{big_amount:,.0f}₽".replace(",", " ") + "\n"
                f"📝 {summary[:300]}\n"
                f"📋 Звонок ID: {call_id}\n"
                f"👉 Нужен перезвон сегодня!"
            ))

    return alerts


def extract_amount_from_summary(text: str) -> float:
    """Пытается извлечь сумму сделки из текста резюме.
    
    Стратегии:
    1. Явная сумма: «5100 руб», «15 000 рублей», «22 000₽»
    2. Расчёт: «60 голов × 85 руб» → 5100
    """
    text_lower = text.lower()

    # 1. Явная сумма
    m = re.search(r'([\d\s]{4,})\s*(?:руб|рублей|₽|тыс)', text_lower)
    if m:
        try:
            return float(m.group(1).replace(" ", ""))
        except ValueError:
            pass

    # 2. Расчёт: "N голов по M руб" или "N × M руб"
    m = re.search(r'(\d+)\s*(?:голов|шт|цыплят).*?(\d+)\s*(?:руб|₽)', text_lower)
    if m:
        try:
            qty = float(m.group(1))
            price = float(m.group(2))
            return qty * price
        except ValueError:
            pass

    return 0.0


# ──────────────────────────────────────────────────────────
# Основная функция
# ──────────────────────────────────────────────────────────
def run_alerts():
    print(f"\n{'='*50}")
    print(f"🔔 CALL ALERTS — {datetime.now(MSK).strftime('%Y-%m-%d %H:%M MSK')}")
    print(f"{'='*50}\n")

    # Загружаем последний скан
    scan_files = sorted(glob.glob(os.path.join(SCAN_DIR, "scan_*.json")))
    if not scan_files:
        print("❌ Нет scan_*.json файлов")
        return

    scan_file = scan_files[-1]
    print(f"📂 Скан: {os.path.basename(scan_file)}")

    with open(scan_file, 'r', encoding='utf-8') as f:
        scan = json.load(f)

    calls = scan.get("activities", {}).get("calls", [])
    deals_list = scan.get("deals", {}).get("items", [])
    
    # Индекс сделок по ID для быстрого поиска
    deals_by_owner = {str(d.get("ID")): d for d in deals_list}

    print(f"📞 Звонков для проверки: {len(calls)}")
    print(f"💼 Сделок в индексе: {len(deals_by_owner)}")

    # Загружаем уже отправленные алерты
    sent = load_sent()
    new_alerts = []

    for call in calls:
        triggered = check_call(call, deals_by_owner)
        for key, message in triggered:
            aid = alert_id(key, "v1")
            if aid not in sent:
                new_alerts.append((aid, message))

    print(f"\n🔔 Новых алертов: {len(new_alerts)}")

    if not new_alerts:
        print("✅ Всё спокойно — алертов нет.")
        return

    # Отправляем алерты
    now_str = datetime.now(MSK).strftime("%d.%m %H:%M")
    for aid, message in new_alerts:
        full_msg = f"⚡ АЛЕРТ Анжелочки · {now_str}\n\n{message}"
        
        # ⛔ Андрею — НИКАКИХ отчётов/алертов в TG! (решение от 12.05.2026)
        ok_owner = send_tg(OWNER_ID, full_msg)
        
        if ok_owner:
            sent.add(aid)
            print(f"  ✅ Отправлено Игорю: {message[:60]}...")
        else:
            print("  ❌ Ошибка отправки алерта")

    save_sent(sent)
    print(f"\n✅ Готово. Отправлено {len(new_alerts)} алертов.")


if __name__ == "__main__":
    run_alerts()
