#!/usr/bin/env python3
"""
call_quality_report.py — Отчёт по качеству телефонных разговоров менеджеров.

Анализирует bitrixgpt_summary каждого звонка из CRM-скана и формирует:
  1. Профиль каждого менеджера (результативные / в работе / пустые)
  2. Сводная таблица (звонков, % результативности, не взяли контакт)
  3. Повторяющиеся проблемы дня
  4. ТОП-3 лучших + ТОП-5 проблемных звонков
  5. AI-рекомендации

Источник данных: bitrix_scanner.py → scan_*.json → activities.calls[]

Запуск:
    python3 call_quality_report.py               # Сформировать + показать
    python3 call_quality_report.py --send         # + отправить в Telegram
    python3 call_quality_report.py --preview      # Только превью

Утверждён: 06.05.2026 | v3 — маркерный анализ из bitrixgpt_summary
"""

import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MSK = timezone(timedelta(hours=3))


def _load_env(env_path):
    """Ручной парсер .env — не требует python-dotenv."""
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env(os.path.join(BASE_DIR, '.env'))

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ANDREY_ID = 444248782
IGOR_ID = 176203333
PROXY_URL = os.getenv("TELEGRAM_PROXY")

SCAN_DIR = os.path.join(BASE_DIR, "data", "bitrix_scans")
REPORTS_DIR = os.path.join(BASE_DIR, "data", "call_quality_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


# ════════════════════════════════════════════
# МАРКЕРЫ ДЛЯ АНАЛИЗА bitrixgpt_summary
# ════════════════════════════════════════════

# Результативные (заказ/доставка подтверждены)
MARKERS_SUCCESS = [
    "заказ подтвержден", "заказ подтверждён", "заказ оформлен",
    "доставка запланирована", "доставка подтверждена",
    "оплата получена", "оплата подтверждена",
    "заказано", "подтвердил доставку", "подтвердила доставку",
    "согласовано", "бронирование подтверждено",
]

# В работе (клиент думает / перезвонит)
MARKERS_PENDING = [
    "ожидается повторное обращение", "обещает перезвонить",
    "обещал перезвонить", "обещала перезвонить",
    "клиент подумает", "будет принято после",
    "ожидается до", "рассматривает", "планирует",
    "на стадии предварительного", "предварительный запрос",
    "окончательное решение", "уточнение",
]

# Пустые / безрезультатные
MARKERS_EMPTY = [
    "диалог не содержит достаточной информации",
    "диалог не содержит достаточного объема",
    "проверка слышимости", "разговор ограничивается",
    "информации для заполнения карточки",
    "не содержит достаточн",
]

# Контакт не взят
MARKERS_NO_CONTACT = [
    "контактные данные не предоставлены",
    "контактная информация не предоставлена",
    "адрес не был указан", "email не был указан",
    "email не указан", "фио не указан",
    "данные не зафиксированы",
]

# Отказ клиента
MARKERS_REJECTION = [
    "отказался", "отказалась", "отказ клиента",
    "нет планов", "не заинтересован", "не нуждается",
    "отменил заказ", "отменила заказ",
]

# Заказ не оформлен (упущенная возможность)
MARKERS_MISSED_SALE = [
    "заказ не оформлен", "сделка не заключена",
    "не оформлен окончательно",
]

# Проблемные ключевые слова (конфликты, жалобы)
MARKERS_PROBLEM = [
    "груб", "негатив", "проблем", "жалоб", "скандал",
    "компенсац", "недоволен", "недовольна", "ругается",
    "кричит", "бросил трубку", "претензия", "хамство",
]

# Апселл (допродажи)
MARKERS_UPSELL = [
    "петуш", "корм", "аптечк", "добавки", "витамин", 
    "всего по пять", "дополнительно", "в подарок",
]


def classify_call(summary: str) -> dict:
    """Классифицирует звонок по маркерам из bitrixgpt_summary.

    Возвращает dict:
        category: 'success' | 'pending' | 'empty' | 'rejection' | 'missed_sale' | 'unknown'
        flags: list[str] — сработавшие флаги
        icon: str — иконка
    """
    s = summary.lower()
    flags = []
    category = "unknown"
    icon = "⚪"

    # Приоритет: success > rejection > missed_sale > empty > pending > unknown

    # Проблемный (критический уровень)
    for m in MARKERS_PROBLEM:
        if m in s:
            flags.append("🔴 КРИТИЧНО: конфликт/жалоба")
            category = "problem"
            icon = "☢️"
            break

    # Апселл (допродажа)
    for m in MARKERS_UPSELL:
        if m in s:
            flags.append("💰 Апселл (предложен доп)")
            break

    # Пустой
    for m in MARKERS_EMPTY:
        if m in s:
            category = "empty"
            icon = "⚫"
            flags.append("пустой звонок")
            break

    # Отказ
    if category == "unknown":
        for m in MARKERS_REJECTION:
            if m in s:
                category = "rejection"
                icon = "🔴"
                flags.append("отказ")
                break

    # Заказ не оформлен
    if category == "unknown":
        for m in MARKERS_MISSED_SALE:
            if m in s:
                category = "missed_sale"
                icon = "🟠"
                flags.append("заказ не оформлен")
                break

    # Успех
    if category == "unknown":
        for m in MARKERS_SUCCESS:
            if m in s:
                category = "success"
                icon = "🟢"
                flags.append("успешная продажа")
                break

    # В работе
    if category == "unknown":
        for m in MARKERS_PENDING:
            if m in s:
                category = "pending"
                icon = "🟡"
                flags.append("клиент думает")
                break

    # Контакт не взят (дополнительный флаг, не категория)
    for m in MARKERS_NO_CONTACT:
        if m in s:
            flags.append("контакт не взят")
            break

    return {"category": category, "flags": flags, "icon": icon}


# ════════════════════════════════════════════
# СБОР ДАННЫХ
# ════════════════════════════════════════════

def load_calls_from_scan(target_date=None):
    """Загружает звонки из последнего CRM-скана."""
    if target_date:
        pattern = os.path.join(SCAN_DIR, f"scan_{target_date}*.json")
    else:
        pattern = os.path.join(SCAN_DIR, "scan_*.json")

    files = sorted(glob.glob(pattern))
    if not files:
        return [], None, {}

    scan_path = files[-1]
    with open(scan_path, 'r', encoding='utf-8') as f:
        scan = json.load(f)

    calls = scan.get("activities", {}).get("calls", [])
    if not calls:
        calls = scan.get("activities", {}).get("calls_items", [])

    users = scan.get("users", {})
    scan_info = os.path.basename(scan_path)
    return calls, scan_info, users


def is_missed(call):
    """Определяет пропущенный звонок.

    ВАЖНО: поле DURATION не приходит в скане (bitrix_scanner.py
    не запрашивает его в crm.activity.list). Поэтому определяем
    только по SUBJECT и RESULT_STATUS.
    Сканер уже фильтрует пропущенные, в скане только состоявшиеся.
    """
    subj = (call.get("SUBJECT") or "").lower()
    if "пропущен" in subj or "missed" in subj:
        return True
    # RESULT_STATUS: 4 = missed в некоторых версиях Bitrix
    if str(call.get("RESULT_STATUS", "")) == "4":
        return True
    return False


# ════════════════════════════════════════════
# ПОСТРОЕНИЕ ОТЧЁТА
# ════════════════════════════════════════════

def build_quality_report(calls, scan_info, users):
    """Формирует полный отчёт по качеству звонков."""
    now = datetime.now(MSK)
    date_str = now.strftime("%d.%m.%Y")

    # Разделяем: состоявшиеся vs пропущенные
    completed = []
    missed_count = 0
    for c in calls:
        if is_missed(c):
            missed_count += 1
        else:
            completed.append(c)

    # Звонки с содержанием (bitrixgpt_summary)
    with_content = [c for c in completed if c.get("bitrixgpt_summary")]

    # ── КЛАССИФИКАЦИЯ ──
    for c in with_content:
        c["_classification"] = classify_call(c.get("bitrixgpt_summary", ""))

    # ── ПО МЕНЕДЖЕРАМ ──
    mgr_profiles = defaultdict(lambda: {
        "total": 0,          # всего звонков (состоявшихся)
        "with_content": 0,   # с содержанием
        "missed": 0,         # пропущенных
        "incoming": 0,
        "outgoing": 0,
        "success": 0,
        "pending": 0,
        "empty": 0,
        "rejection": 0,
        "missed_sale": 0,
        "unknown": 0,
        "no_contact": 0,     # не взяли контакт
        "problem": 0,        # проблемные
        "calls": [],         # все звонки с содержанием
    })

    # Считаем пропущенные по менеджерам
    for c in calls:
        mgr = c.get("manager_name", "")
        if not mgr or mgr.startswith("ID_"):
            mgr_id = str(c.get("RESPONSIBLE_ID", ""))
            mgr = users.get(mgr_id, f"ID_{mgr_id}")
        if is_missed(c):
            mgr_profiles[mgr]["missed"] += 1

    # Считаем состоявшиеся
    for c in completed:
        mgr = c.get("manager_name", "")
        if not mgr or mgr.startswith("ID_"):
            mgr_id = str(c.get("RESPONSIBLE_ID", ""))
            mgr = users.get(mgr_id, f"ID_{mgr_id}")
        mgr_profiles[mgr]["total"] += 1
        # DIRECTION: 1=входящий, 2=исходящий (Bitrix CRM стандарт)
        direction = str(c.get("DIRECTION", ""))
        if direction == "1":
            mgr_profiles[mgr]["incoming"] += 1
        elif direction == "2":
            mgr_profiles[mgr]["outgoing"] += 1

    # Классификация по менеджерам
    for c in with_content:
        mgr = c.get("manager_name", "")
        if not mgr or mgr.startswith("ID_"):
            mgr_id = str(c.get("RESPONSIBLE_ID", ""))
            mgr = users.get(mgr_id, f"ID_{mgr_id}")
        cl = c["_classification"]
        mgr_profiles[mgr]["with_content"] += 1
        mgr_profiles[mgr][cl["category"]] += 1
        mgr_profiles[mgr]["calls"].append(c)
        if "контакт не взят" in cl["flags"]:
            mgr_profiles[mgr]["no_contact"] += 1
        if "🔴 проблемный" in cl["flags"]:
            mgr_profiles[mgr]["problem"] += 1

    # Фильтруем системных
    skip = {"СРМ Б24", "Служебный", "Admin", "ID_", ""}
    mgr_profiles = {k: v for k, v in mgr_profiles.items()
                    if k not in skip and not k.startswith("ID_")}

    # ── ПОСТРОЕНИЕ ТЕКСТА ──
    lines = [
        f"{'═' * 42}",
        f"📞 КАЧЕСТВО ЗВОНКОВ — {date_str}",
        f"   Проанализировано: {len(with_content)} из {len(calls)} звонков",
        f"   Источник: {scan_info}",
        f"{'═' * 42}",
        "",
    ]

    # ПРОФИЛИ МЕНЕДЖЕРОВ
    for mgr_name in sorted(mgr_profiles.keys(),
                            key=lambda x: mgr_profiles[x]["with_content"],
                            reverse=True):
        p = mgr_profiles[mgr_name]
        if p["with_content"] == 0 and p["total"] == 0:
            continue

        lines.append(f"👩‍💼 {mgr_name.upper()} ({p['with_content']} звонков с содержанием)")
        lines.append(f"   {'─' * 36}")
        lines.append(f"   📊 Вх: {p['incoming']} | Исх: {p['outgoing']} | Пропущ: {p['missed']}")
        lines.append("")

        # Категории
        if p["with_content"] > 0:
            lines.append(f"   ✅ Результативные (заказ/доставка): {p['success']}")
            lines.append(f"   🟡 В работе (клиент думает): {p['pending']}")
            lines.append(f"   🟠 Заказ не оформлен: {p['missed_sale']}")
            lines.append(f"   🔴 Отказы клиентов: {p['rejection']}")
            lines.append(f"   ⚫ Пустые/тестовые: {p['empty']}")
            if p["unknown"] > 0:
                lines.append(f"   ⚪ Прочие: {p['unknown']}")
            lines.append("")

            # Не взяли контакт
            if p["no_contact"] > 0:
                lines.append(f"   ❌ Контакт не взят: {p['no_contact']} звонков")

            # Проблемные
            if p["problem"] > 0:
                lines.append(f"   🔴 Проблемные (негатив/жалобы): {p['problem']}")

            # Процент результативности
            if p["with_content"] > 0:
                pct = p["success"] / p["with_content"] * 100
                lines.append(f"   📈 Результативность: {pct:.0f}%")
            lines.append("")

            # Примеры хороших звонков
            good = [c for c in p["calls"]
                    if c["_classification"]["category"] == "success"]
            if good:
                best = good[0]
                summary = best.get("bitrixgpt_summary", "")[:150]
                lines.append(f"   🟢 Лучший: «{summary}»")

            # Примеры проблемных
            bad = [c for c in p["calls"]
                   if c["_classification"]["category"] in ("empty", "rejection")
                   or "контакт не взят" in c["_classification"]["flags"]]
            if bad:
                worst = bad[0]
                summary = worst.get("bitrixgpt_summary", "")[:150]
                lines.append(f"   🔴 Проблемный: «{summary}»")

        lines.append("")
        lines.append(f"{'─' * 42}")
        lines.append("")

    # ── СВОДНАЯ ТАБЛИЦА ──
    lines.append("📊 СВОДКА ДНЯ")
    lines.append("")
    header = f"   {'Менеджер':<12} | Звон. | Успех | %Рез. | ❌Конт | ⭐Рейтинг"
    lines.append(header)
    lines.append(f"   {'─' * 12}-+-{'─' * 5}-+-{'─' * 5}-+-{'─' * 5}-+-{'─' * 5}-+-{'─' * 8}")
    for mgr_name in sorted(mgr_profiles.keys(),
                            key=lambda x: mgr_profiles[x]["with_content"],
                            reverse=True):
        p = mgr_profiles[mgr_name]
        if p["with_content"] == 0:
            continue
        pct_val = p['success'] / p['with_content'] * 100 if p["with_content"] > 0 else 0
        pct = f"{pct_val:.0f}%"
        
        # Расчет рейтинга (субъективно-математический)
        # База 3 звезды. +1 за высокую рез (>35%), -1 за низкую (<25%), -1 за много "без контакта" (>20%)
        stars = 3
        if pct_val > 35: stars += 1
        if pct_val > 50: stars += 1
        if pct_val < 25: stars -= 1
        
        no_contact_pct = (p['no_contact'] / p['with_content'] * 100) if p['with_content'] > 0 else 0
        if no_contact_pct > 20: stars -= 1
        if p['problem'] > 0: stars -= 2
        
        stars = max(1, min(5, stars))
        rating_str = "⭐" * stars
        
        short_name = mgr_name[:12]
        lines.append(f"   {short_name:<12} | {p['with_content']:>5} | {p['success']:>5} | {pct:>5} | {p['no_contact']:>5} | {rating_str}")
    lines.append("")
    lines.append(f"{'─' * 42}")
    lines.append("")

    # ── ПОВТОРЯЮЩИЕСЯ ПРОБЛЕМЫ ──
    # Подсчёт маркеров по всем звонкам
    problem_counts = defaultdict(int)
    for c in with_content:
        cl = c["_classification"]
        if cl["category"] == "empty":
            problem_counts["Пустые звонки (тест слышимости)"] += 1
        if "контакт не взят" in cl["flags"]:
            problem_counts["Контакт не взят (нет email/телефона)"] += 1
        if cl["category"] == "pending":
            problem_counts["Клиент обещает перезвонить (нет фиксации даты)"] += 1
        if cl["category"] == "missed_sale":
            problem_counts["Заказ не оформлен (упущенная продажа)"] += 1
        if cl["category"] == "rejection":
            problem_counts["Отказ клиента"] += 1

    if problem_counts:
        lines.append("🔍 ПОВТОРЯЮЩИЕСЯ ПРОБЛЕМЫ:")
        for problem, count in sorted(problem_counts.items(), key=lambda x: -x[1]):
            if count >= 2:
                lines.append(f"   {count}× {problem}")
        lines.append("")
        lines.append(f"{'─' * 42}")
        lines.append("")

    # ── ТОП-3 ЛУЧШИХ (дедуплицированные по содержанию) ──
    all_success = [c for c in with_content
                   if c["_classification"]["category"] == "success"]
    # Дедупликация: одно саммари = один звонок в ТОП
    seen_summaries = set()
    unique_success = []
    for c in all_success:
        s = c.get("bitrixgpt_summary", "")[:100]
        if s not in seen_summaries:
            seen_summaries.add(s)
            unique_success.append(c)

    if unique_success:
        lines.append("🏆 ТОП-3 ЛУЧШИХ ЗВОНКА:")
        for i, c in enumerate(unique_success[:3], 1):
            mgr = c.get("manager_name", "?")
            subj = c.get("SUBJECT", "")
            summary = c.get("bitrixgpt_summary", "")[:180]
            lines.append(f"   🟢 {i}. {mgr} [{subj}]")
            lines.append(f"      «{summary}»")
        lines.append("")

    # ── ТОП-5 ПРОБЛЕМНЫХ (дедуплицированные) ──
    # Ранжируем: problem > rejection > empty > missed_sale > no_contact
    def problem_score(c):
        cl = c["_classification"]
        s = 0
        if "🔴 проблемный" in cl["flags"]:
            s += 10
        if cl["category"] == "rejection":
            s += 5
        if cl["category"] == "empty":
            s += 4
        if cl["category"] == "missed_sale":
            s += 3
        if "контакт не взят" in cl["flags"]:
            s += 2
        return s

    problem_calls = [c for c in with_content if problem_score(c) > 0]
    problem_calls.sort(key=problem_score, reverse=True)

    # Дедупликация проблемных
    seen_p = set()
    unique_problems = []
    for c in problem_calls:
        s = c.get("bitrixgpt_summary", "")[:100]
        if s not in seen_p:
            seen_p.add(s)
            unique_problems.append(c)

    if unique_problems:
        lines.append("🔴 ТОП-5 ПРОБЛЕМНЫХ ЗВОНКОВ:")
        for i, c in enumerate(unique_problems[:5], 1):
            mgr = c.get("manager_name", "?")
            subj = c.get("SUBJECT", "")
            cl = c["_classification"]
            summary = c.get("bitrixgpt_summary", "")[:180]
            icon = cl["icon"]
            flags_str = ", ".join(cl["flags"])
            lines.append(f"   {icon} {i}. {mgr} [{subj}] ({flags_str})")
            lines.append(f"      «{summary}»")
        lines.append("")

    lines.append(f"{'─' * 42}")
    lines.append("")

    # ── РЕКОМЕНДАЦИИ (на основе маркеров) ──
    lines.append("💡 РЕКОМЕНДАЦИИ:")
    recommendations = []
    total_no_contact = sum(p["no_contact"] for p in mgr_profiles.values())
    total_pending = sum(p["pending"] for p in mgr_profiles.values())
    total_empty = sum(p["empty"] for p in mgr_profiles.values())
    total_missed_sale = sum(p["missed_sale"] for p in mgr_profiles.values())
    total_success = sum(p["success"] for p in mgr_profiles.values())
    total_with_content = sum(p["with_content"] for p in mgr_profiles.values())

    if total_no_contact >= 3:
        recommendations.append(
            f"   1. Фиксировать email/телефон в КАЖДОМ разговоре "
            f"({total_no_contact} звонков без контакта)")
    if total_pending >= 3:
        recommendations.append(
            f"   2. При «клиент подумает» — назначать дату перезвона "
            f"({total_pending} звонков «клиент обещает перезвонить»)")
    if total_empty >= 2:
        recommendations.append(
            f"   3. Сократить пустые звонки — {total_empty} тестовых/бессодержательных")
    if total_missed_sale >= 2:
        recommendations.append(
            f"   4. Предлагать альтернативу при отсутствии товара "
            f"({total_missed_sale} неоформленных заказов)")
    if total_with_content > 0:
        pct = total_success / total_with_content * 100
        if pct < 30:
            recommendations.append(
                f"   5. Общая результативность {pct:.0f}% — ниже нормы (цель: 35%+)")

    if not recommendations:
        recommendations.append("   Критичных проблем не выявлено 👍")

    lines.extend(recommendations)
    lines.append("")
    lines.append(f"{'═' * 42}")
    lines.append("📞 Анализ: Анжела Заботкина | IncuBird v2")
    lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════════

def send_to_telegram(text, chat_id, label=""):
    """Отправка в Telegram."""
    if not TELEGRAM_TOKEN:
        print("   ⚠️ TELEGRAM_TOKEN не задан — отправка невозможна")
        return False

    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Telegram limit: 4096 chars — разбиваем если надо
    chunks = []
    if len(text) <= 4000:
        chunks = [text]
    else:
        # Разбиваем по строкам
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > 3900:
                chunks.append(current)
                current = line + "\n"
            else:
                current += line + "\n"
        if current:
            chunks.append(current)

    for i, chunk in enumerate(chunks):
        if len(chunks) > 1:
            chunk = f"[{i+1}/{len(chunks)}]\n{chunk}"

        payload = {"chat_id": chat_id, "text": chunk}

        # Попытка 1: напрямую
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                print(f"   ✅ Отправлено {label} (direct) chunk {i+1}")
                continue
        except Exception:
            pass

        # Попытка 2: через прокси
        if PROXY_URL:
            try:
                p = PROXY_URL.replace("socks5://", "socks5h://")
                resp = requests.post(url, json=payload,
                                     proxies={"https": p, "http": p}, timeout=15)
                if resp.status_code == 200:
                    print(f"   ✅ Отправлено {label} (proxy) chunk {i+1}")
                    continue
                else:
                    print(f"   ⚠️ TG [{label}]: {resp.status_code}")
                    return False
            except Exception as e:
                print(f"   ❌ TG [{label}] proxy: {e}")
                return False

        print(f"   ❌ TG [{label}]: не удалось отправить")
        return False

    return True


# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════

def main():
    args = sys.argv[1:]
    do_send = "--send" in args
    preview_only = "--preview" in args

    target_date = None
    if "--date" in args:
        idx = args.index("--date")
        if idx + 1 < len(args):
            target_date = args[idx + 1]

    print()
    print("📞 Собираю данные для отчёта по качеству звонков...")
    if target_date:
        print(f"   📅 Целевая дата: {target_date}")
    print()

    calls, scan_info, users = load_calls_from_scan(target_date)

    if not calls:
        print("❌ Звонков не найдено в скане.")
        return

    print(f"   📊 Звонков в скане: {len(calls)}")
    with_content = [c for c in calls if c.get("bitrixgpt_summary")]
    print(f"   🤖 С содержанием (bitrixgpt_summary): {len(with_content)}")
    print()

    report = build_quality_report(calls, scan_info, users)

    # Показываем
    print(report)

    if preview_only:
        print("👀 Режим превью — файл не сохранён, не отправлен.")
        return

    # Сохраняем
    now = datetime.now(MSK)
    filename = f"quality_{now.strftime('%Y%m%d_%H%M')}.md"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"💾 Сохранён: {filepath}")

    if do_send:
        print()
        print("📤 Отправляю в Telegram (ТОЛЬКО Игорю)...")
        # ⛔ Андрею — НИКАКИХ отчётов в TG! (решение от 12.05.2026)
        send_to_telegram(report, IGOR_ID, "Игорь")

    print("✅ Готово!")


if __name__ == "__main__":
    main()
