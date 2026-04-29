#!/usr/bin/env python3
"""
call_quality_report.py — Отчёт «Топ-5 значимых звонков дня».
Запускается сразу после основного daily_report.py (20:01 MSK).

Логика:
  1. Забирает звонки за сегодня из последнего скана Bitrix24
     (scan_*.json — поле activities.calls_items) или из
     data/shadow_learning/calls/ (транскрипты).
  2. Ранжирует по «значимости»: длительность, ключевые слова в резюме.
  3. Формирует компактный TG-отчёт: общее кол-во звонков + 5 самых ярких.
  4. Отправляет Андрею (Заботкиной) и Игорю (контроль).

Запуск: python3 call_quality_report.py
"""

import os
import sys
import json
import re
import glob
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import requests

# ─────────────────────────────────────────────
# Конфигурация
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
ADMIN_ID = 444248782    # Андрей (Заботкина)
OWNER_ID = 176203333    # Игорь
PROXY_URL = os.getenv("TELEGRAM_PROXY", "")
BITRIX_URL = os.getenv("BITRIX_WEBHOOK_URL", "").rstrip("/")

MSK = timezone(timedelta(hours=3))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCAN_DIR = os.path.join(DATA_DIR, "bitrix_scans")
CALLS_DIR = os.path.join(DATA_DIR, "shadow_learning", "calls")


# ─────────────────────────────────────────────
# Имена менеджеров
# ─────────────────────────────────────────────
# Маппинг ID → Имя (кэшируется при первом вызове)
_MANAGER_CACHE = {}

def get_manager_names() -> dict:
    """Получаем имена менеджеров из Bitrix24 API."""
    global _MANAGER_CACHE
    if _MANAGER_CACHE:
        return _MANAGER_CACHE
    if not BITRIX_URL:
        return {}
    try:
        resp = requests.get(
            f"{BITRIX_URL}/user.get.json",
            params={"auth": os.getenv("BITRIX24_TOKEN", "")},
            timeout=15,
            proxies={"http": "", "https": ""}
        )
        resp.raise_for_status()
        data = resp.json()
        for u in data.get("result", []):
            uid = str(u.get("ID"))
            name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
            _MANAGER_CACHE[uid] = name if name else f"ID_{uid}"
    except Exception as e:
        print(f"⚠️ Не удалось получить имена менеджеров: {e}")
    return _MANAGER_CACHE


# ─────────────────────────────────────────────
# Источники звонков
# ─────────────────────────────────────────────
def get_calls_from_scan() -> list:
    """Берём звонки из последнего скана CRM (activities → calls_items)."""
    scan_files = sorted(glob.glob(os.path.join(SCAN_DIR, "scan_*.json")))
    if not scan_files:
        return []
    try:
        with open(scan_files[-1], 'r', encoding='utf-8') as f:
            scan = json.load(f)
        # В скане звонки хранятся в activities.calls_items или manager_stats.*.calls_items
        calls = scan.get("activities", {}).get("calls_items", [])
        if calls:
            return calls
        # Альтернативно — собираем из manager_stats
        managers = scan.get("manager_stats", {})
        all_calls = []
        for name, stats in managers.items():
            for c in stats.get("calls_items", []):
                c["_manager_name"] = name
                all_calls.append(c)
        return all_calls
    except Exception as e:
        print(f"⚠️ Ошибка чтения скана: {e}")
        return []


def get_calls_from_transcripts() -> list:
    """Берём звонки из транскрибированных файлов (shadow_learning)."""
    today = datetime.now(MSK).strftime("%Y%m%d")
    # Ищем файл за сегодня
    candidates = sorted(glob.glob(os.path.join(CALLS_DIR, f"calls_{today}*.json")))
    if not candidates:
        # Если за сегодня нет — берём самый свежий
        candidates = sorted(glob.glob(os.path.join(CALLS_DIR, "calls_*.json")))
    if not candidates:
        return []
    try:
        with open(candidates[-1], 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Ошибка чтения транскриптов: {e}")
        return []


def get_all_calls() -> list:
    """Объединяем звонки из обоих источников, предпочитая скан."""
    scan_calls = get_calls_from_scan()
    if scan_calls:
        return scan_calls
    return get_calls_from_transcripts()


# ─────────────────────────────────────────────
# Анализ звонков
# ─────────────────────────────────────────────
def extract_summary(call: dict) -> str:
    """Извлечь краткое содержание (РЕЗЮМЕ) из транскрипта."""
    transcript = call.get("transcript", "")
    if not transcript:
        return ""
    m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\n\n|$)", transcript, re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    # Альтернативно — берём description/subject
    desc = call.get("DESCRIPTION", call.get("description", ""))
    subj = call.get("SUBJECT", call.get("subject", ""))
    return desc or subj or ""


def significance_score(call: dict) -> float:
    """Чем выше — тем значимее звонок. Используется для ранжирования."""
    score = 0.0
    # Длительность
    dur = int(call.get("duration", call.get("DURATION", 0)))
    score += min(dur / 30, 10)  # макс +10 за длительность

    # Ключевые слова в резюме/описании
    summary = extract_summary(call).lower()
    bad_kw = ["груб", "негатив", "проблем", "требуется уточн", "жалоб", "отказ", "скандал"]
    good_kw = ["заказ", "оплат", "доставк", "подтверд", "оптов"]
    for kw in bad_kw:
        if kw in summary:
            score += 5  # проблемные звонки — в топ
    for kw in good_kw:
        if kw in summary:
            score += 2

    return score


def build_quality_report(calls: list) -> str:
    """Формирует текст TG-сообщения: кол-во + топ-5."""
    now_str = datetime.now(MSK).strftime("%d.%m.%Y")
    total = len(calls)
    manager_names = get_manager_names()

    # Ранжируем
    scored = []
    for c in calls:
        s = significance_score(c)
        c["_score"] = s
        scored.append(c)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    top5 = scored[:5]

    lines = [
        f"📞 АНАЛИЗ ЗВОНКОВ — {now_str}",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"",
        f"📊 Всего звонков за день: {total}",
        f"",
    ]

    if not top5:
        lines.append("ℹ️ Нет звонков для анализа.")
    else:
        lines.append("🔥 ТОП-5 ЗНАЧИМЫХ ЗВОНКОВ:")
        lines.append("")
        for i, c in enumerate(top5, 1):
            # Определяем менеджера
            mgr_id = str(c.get("manager_id", c.get("ASSIGNED_BY_ID", "")))
            mgr_name = c.get("_manager_name", "")
            if not mgr_name:
                mgr_name = manager_names.get(mgr_id, f"ID_{mgr_id}")

            # Длительность
            dur = int(c.get("duration", c.get("DURATION", 0)))
            dur_str = f"{dur // 60}м{dur % 60}с" if dur > 0 else "—"

            # Краткое содержание
            summary = extract_summary(c)
            if not summary:
                summary = "Описание отсутствует"
            # Ограничиваем длину
            if len(summary) > 200:
                summary = summary[:197] + "..."

            call_id = c.get("call_id", c.get("ID", "-"))

            icon = "🔴" if c["_score"] >= 8 else "🟡" if c["_score"] >= 4 else "🟢"
            lines.append(f"{icon} {i}. [{call_id}] — {mgr_name} ({dur_str})")
            lines.append(f"   {summary}")
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("Отчёт: Анжелочка — Контроль качества 🐣")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Отправка в Telegram
# ─────────────────────────────────────────────
def _send_tg(chat_id: int, text: str, label: str = "") -> bool:
    """Отправляет сообщение через Telegram Bot API."""
    if not TELEGRAM_TOKEN:
        print("❌ ANGELOCHKA_BOT_TOKEN не задан!")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        proxy = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": proxy, "http": proxy}
    try:
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
        }, proxies=proxies, timeout=15)
        if resp.status_code == 200:
            print(f"✅ Отчёт по звонкам отправлен {label} (chat_id={chat_id})")
            return True
        else:
            print(f"⚠️ TG error [{label}]: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ TG send error [{label}]: {e}")
        return False


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────
def run_call_quality_report():
    """Основная функция: собрать, проанализировать, отправить."""
    print(f"\n{'='*50}")
    print(f"📞 CALL QUALITY REPORT — {datetime.now(MSK).strftime('%Y-%m-%d %H:%M MSK')}")
    print(f"{'='*50}\n")

    calls = get_all_calls()
    print(f"📊 Найдено звонков: {len(calls)}")

    if not calls:
        print("ℹ️ Звонков не найдено. Пропускаю генерацию отчёта.")
        return

    report = build_quality_report(calls)
    print(f"\n{report}\n")

    # Отправляем Андрею (Заботкиной)
    _send_tg(ADMIN_ID, report, label="Андрей/Заботкина")

    # Копия Игорю
    _send_tg(OWNER_ID, f"🔍 КОНТРОЛЬ КАЧЕСТВА ЗВОНКОВ\n{'─'*30}\n\n{report}", label="Игорь/Owner")

    print("✅ Отчёт по качеству звонков завершён!")


if __name__ == "__main__":
    run_call_quality_report()
