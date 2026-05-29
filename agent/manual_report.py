#!/usr/bin/env python3.12
"""
Manual Report v2 — Единый ежедневный отчёт (CRM + Звонки + AI-анализ + Проект).
ЗАПУСКАЕТСЯ ЛОКАЛЬНО ВРУЧНУЮ после рабочего дня.

Использование:
    python3.12 agent/manual_report.py                    # Собрать + показать + сохранить
    python3.12 agent/manual_report.py --send             # + отправить в Telegram
    python3.12 agent/manual_report.py --preview          # Только превью
    python3.12 agent/manual_report.py --date 20260422    # Отчёт за конкретную дату

Логика:
    1. Читает CRM-скан (bitrix_scans/) — сделки, звонки, менеджеры
    2. Анализирует звонки (топ-5 значимых) из скана + shadow_learning
    3. Генерирует AI-выводы через каскад LLM (OpenRouter)
    4. Собирает статус проекта (Песочница, VK, роадмап)
    5. Сохраняет в data/manual_reports/
    6. При --send отправляет ТОЛЬКО Игорю в Telegram (решение от 12.05.2026)

Заменяет: daily_report.py + call_quality_report.py + project_report.py
Создано: 02.05.2026 | v2 — AI + звонки
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

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

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ANDREY_ID = 444248782
IGOR_ID = 176203333
PROXY_URL = os.getenv("TELEGRAM_PROXY")

DATA_DIR = os.path.join(BASE_DIR, "data")
SCAN_LOG_DIR = os.path.join(DATA_DIR, "bitrix_scans")
SANDBOX_SCAN_DIR = os.path.join(DATA_DIR, "sandbox_scans")
REPORTS_DIR = os.path.join(DATA_DIR, "manual_reports")
VK_CONTENT_DIR = os.path.join(BASE_DIR, "vk_content")
CALLS_DIR = os.path.join(DATA_DIR, "shadow_learning", "calls")
ACTIVE_TASKS_PATH = os.path.join(os.path.dirname(BASE_DIR), "ACTIVE_TASKS.md")

os.makedirs(REPORTS_DIR, exist_ok=True)


# ════════════════════════════════════════════
# ЧАСТЬ 1: Сбор данных CRM
# ════════════════════════════════════════════

def get_crm_scan(target_date=None):
    """Находит лучший скан CRM. target_date='20260422' или None (последний)."""
    if target_date:
        pattern = os.path.join(SCAN_LOG_DIR, f"scan_{target_date}*.json")
    else:
        pattern = os.path.join(SCAN_LOG_DIR, "scan_*.json")

    all_files = sorted(glob.glob(pattern))
    if not all_files:
        if target_date:
            # Фоллбэк на все файлы
            all_files = sorted(glob.glob(os.path.join(SCAN_LOG_DIR, "scan_*.json")))
        if not all_files:
            return None, "Нет файлов сканов"

    # Берём самый содержательный из последних 5
    best, best_score = None, -1
    for fpath in all_files[-5:]:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            score = (
                len(data.get("manager_stats", {})) * 10 +
                data.get("deals", {}).get("count", 0) * 5 +
                data.get("activities", {}).get("calls_count", 0)
            )
            if score > best_score:
                best_score = score
                best = (data, os.path.basename(fpath))
        except Exception:
            continue

    if best:
        mtime = os.path.getmtime(os.path.join(SCAN_LOG_DIR, best[1]))
        age_h = (datetime.now().timestamp() - mtime) / 3600
        age_str = f"{age_h:.1f}ч назад" if age_h < 48 else f"{age_h / 24:.0f} дн. назад"
        return best[0], f"{best[1]} ({age_str})"

    return None, "Не удалось прочитать сканы"


def build_crm_section(scan, scan_info):
    """Формирует секцию CRM отчёта."""
    if not scan:
        return f"❌ CRM: {scan_info}\n"

    deals = scan.get("deals", {})
    activities = scan.get("activities", {})
    managers = scan.get("manager_stats", {})

    since_str = _fmt_iso(scan.get("since", ""))
    scan_time_str = _fmt_iso(scan.get("scan_time", ""))

    lines = [
        "📊 CRM BITRIX24",
        f"   Источник: {scan_info}",
        f"   Период: {since_str} → {scan_time_str}",
        "",
        f"   🆕 Сделки: {deals.get('count', 0)} (на {deals.get('total_amount', 0):,.0f}₽)".replace(",", " "),
        f"   📞 Звонки: {activities.get('calls_count', 0)}",
        f"   💬 Чаты: {activities.get('chats_ol_count', 0)}",
        f"   📱 SMS: {activities.get('sms_count', 0)}",
        f"   📋 Веб-формы: {activities.get('webforms_count', 0)}",
        "",
    ]

    # Менеджеры
    if managers:
        filtered = {k: v for k, v in managers.items()
                    if k not in ("СРМ Б24", "Служебный", "Admin")}
        if filtered:
            lines.append("   👩‍💼 По менеджерам:")
            for name, stats in sorted(filtered.items(),
                                       key=lambda x: x[1].get("deals", 0), reverse=True):
                d = stats.get("deals", 0)
                c = stats.get("calls", 0)
                a = stats.get("amount", 0)
                lines.append(f"      • {name}: {d} сделок, {c} звонков ({a:,.0f}₽)".replace(",", " "))
            lines.append("")

    # Конверсия
    calls = activities.get("calls_count", 0)
    chats = activities.get("chats_ol_count", 0)
    total_leads = calls + chats
    deals_count = deals.get("count", 0)
    conv = f"{deals_count / total_leads * 100:.1f}%" if total_leads > 0 else "н/д"
    lines.append(f"   📈 Конверсия (сделки / лиды): {conv}")
    lines.append("")

    # ── ВОРОНКА СДЕЛОК (стадии + крупнейшие покупатели) ──
    deal_items = deals.get("items", [])
    users = scan.get("users", {})
    contacts = scan.get("contacts", {})  # {contact_id: "Имя Фамилия"} — если сканер резолвит

    if deal_items:
        stage_map = {
            "NEW": "🆕 Новые (ждут обработки)",
            "PREPARATION": "📋 Подготовка документов",
            "PREPAYMENT_INVOICE": "💳 Выставлен счёт",
            "EXECUTING": "🚚 В доставке",
            "WON": "✅ Оплачено / Закрыто",
            "LOSE": "❌ Проиграна",
            "APOLOGY": "😔 Отказ клиента",
            "7": "✅ Закрыта",
            "8": "⏳ Ожидает предоплаты",
            "9": "🚚 В работе",
            "10": "📦 Отправлено",
            "11": "🔄 Повторное обращение",
            "12": "❌ Отменена",
            "13": "🗑 Удалена",
        }
        stages = {}
        stage_deals = {}
        for d in deal_items:
            s = d.get("STAGE_ID", "?")
            stages[s] = stages.get(s, 0) + 1
            stage_deals.setdefault(s, []).append(d)

        lines.append("   📊 СТАТУС СДЕЛОК (где что):")
        for stage_id, count in sorted(stages.items(), key=lambda x: -x[1]):
            label = stage_map.get(stage_id, f"Стадия {stage_id}")
            stage_amount = sum(float(d.get("OPPORTUNITY") or 0) for d in stage_deals[stage_id])
            lines.append(f"      {label}: {count} шт. ({stage_amount:,.0f}₽)".replace(",", " "))

            # Топ-3 крупных в стадии — с покупателем и менеджером
            stage_top = sorted(stage_deals[stage_id],
                               key=lambda x: float(x.get("OPPORTUNITY") or 0), reverse=True)[:3]
            for d in stage_top:
                amt = float(d.get("OPPORTUNITY") or 0)
                if amt > 0:
                    cid = str(d.get("CONTACT_ID") or "")
                    cname = contacts.get(cid, f"#{cid}") if cid else "—"
                    mgr_id = str(d.get("ASSIGNED_BY_ID") or "")
                    mgr_name = users.get(mgr_id, "")
                    mgr_part = f" ({mgr_name})" if mgr_name else ""
                    lines.append(f"         → {amt:,.0f}₽ — {cname}{mgr_part}".replace(",", " "))
        lines.append("")

    # ── ЗАБЫТЫЕ СДЕЛКИ ──
    forgotten = scan.get("forgotten_deals", {})
    forgotten_items = forgotten.get("deals", [])
    if forgotten_items:
        lines.append(f"   ⏰ ЗАБЫТЫЕ СДЕЛКИ ({forgotten.get('count', len(forgotten_items))} шт.):")
        top_forgotten = sorted(forgotten_items,
                               key=lambda x: float(x.get("OPPORTUNITY") or 0), reverse=True)[:3]
        for d in top_forgotten:
            amt = float(d.get("OPPORTUNITY") or 0)
            cid = str(d.get("CONTACT_ID") or "")
            cname = contacts.get(cid, f"#{cid}") if cid else "—"
            mgr_id = str(d.get("ASSIGNED_BY_ID") or "")
            mgr_name = users.get(mgr_id, "")
            title = d.get("TITLE", "")
            days_ago = ""
            created = d.get("DATE_CREATE", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    days = (datetime.now(MSK) - dt.replace(tzinfo=MSK)).days
                    days_ago = f", {days} дн. без движения"
                except Exception:
                    pass
            lines.append(f"      ⚠️ {amt:,.0f}₽ — {cname} ({mgr_name}{days_ago})".replace(",", " "))
        lines.append("")
    elif forgotten.get("count", 0) == 0:
        lines.append("   ✅ Забытых сделок нет")
        lines.append("")

    # ── ЛИДЫ ──
    leads_data = scan.get("leads", {})
    if leads_data and leads_data.get("count", 0) > 0:
        leads_count = leads_data.get("count", 0)
        leads_items = leads_data.get("items", [])
        lines.append(f"   📥 ЛИДЫ: {leads_count}")
        if leads_items:
            for l in leads_items[:5]:
                name = f"{l.get('NAME', '')} {l.get('LAST_NAME', '')}".strip()
                name = name or l.get("TITLE", "—")
                source = l.get("SOURCE_ID", "?")
                lines.append(f"      • {name} (источник: {source})")
        lines.append("")

    # ── ТОП ПРОДАЖ ПО ПОРОДАМ (из товарных строк 1С) ──
    breed_stats = scan.get("breed_stats", {})
    if breed_stats:
        sorted_breeds = sorted(breed_stats.items(),
                               key=lambda x: x[1].get("revenue", 0), reverse=True)
        lines.append("   🐔 ТОП ПРОДАЖ (что покупают):")
        for name, stats in sorted_breeds[:7]:
            qty = int(stats.get("quantity", 0))
            rev = stats.get("revenue", 0)
            deals_n = stats.get("deals", 0)
            rev_str = f"{rev:,.0f}₽".replace(",", " ")
            lines.append(f"      • {name}: {qty} шт. ({rev_str}, {deals_n} сделок)")
        lines.append("")

    # ── СТАТУС ОПЛАТ (данные 1С) ──
    payment = scan.get("payment_summary", {})
    if payment and payment.get("total_count", 0) > 0:
        paid_c = payment.get("paid_count", 0)
        paid_a = payment.get("paid_amount", 0)
        total_c = payment.get("total_count", 0)
        total_a = payment.get("total_amount", 0)
        unpaid_c = total_c - paid_c
        unpaid_a = total_a - paid_a
        lines.append("   💰 ОПЛАТЫ (1С):")
        lines.append(f"      ✅ Оплачено: {paid_c} сделок ({paid_a:,.0f}₽)".replace(",", " "))
        if unpaid_c > 0:
            lines.append(f"      ⏳ Не оплачено: {unpaid_c} сделок ({unpaid_a:,.0f}₽)".replace(",", " "))
        lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════
# ЧАСТЬ 2: Анализ звонков
# ════════════════════════════════════════════

def _get_all_calls(scan):
    """Собирает звонки из скана + транскрипты из shadow_learning."""
    calls = []
    if scan:
        calls = scan.get("activities", {}).get("calls", [])
        if not calls:
            calls = scan.get("activities", {}).get("calls_items", [])
        if not calls:
            for name, stats in scan.get("manager_stats", {}).items():
                for c in stats.get("calls_items", []):
                    c["_manager_name"] = name
                    calls.append(c)
    # Дополняем транскриптами
    today = datetime.now(MSK).strftime("%Y%m%d")
    candidates = sorted(glob.glob(os.path.join(CALLS_DIR, f"calls_{today}*.json")))
    if not candidates:
        candidates = sorted(glob.glob(os.path.join(CALLS_DIR, "calls_*.json")))
    if candidates:
        try:
            with open(candidates[-1], 'r', encoding='utf-8') as f:
                transcript_calls = json.load(f)
            if transcript_calls and not calls:
                calls = transcript_calls
        except Exception:
            pass
    return calls


def _is_missed(call):
    """Определяет, пропущенный ли звонок.

    Признаки пропущенного:
    - SUBJECT содержит 'Пропущенный' / 'Missed'
    - DURATION == 0 при DIRECTION == 1 (входящий без ответа)
    - RESULT_STATUS указывает на miss
    """
    subj = (call.get("SUBJECT") or call.get("subject") or "").lower()
    if "пропущен" in subj or "missed" in subj:
        return True
    # Входящий без длительности = пропущенный
    direction = str(call.get("DIRECTION", ""))
    dur = int(call.get("duration", 0) or call.get("DURATION", 0) or 0)
    if direction == "1" and dur == 0:
        return True
    return False


def _has_real_content(call):
    """Проверяет, есть ли у звонка реальное содержание (не просто номер телефона)."""
    # Транскрипт — лучший вариант
    transcript = call.get("transcript", "")
    if transcript and "РЕЗЮМЕ:" in transcript:
        return True
    # DESCRIPTION с текстом (не номер)
    desc = (call.get("DESCRIPTION") or call.get("description") or "").strip()
    if desc and not re.match(r'^[\d\s\+\-\(\)]+$', desc):
        return True
    # SUBJECT с реальным содержанием (не «Исходящий на +7...»)
    subj = (call.get("SUBJECT") or call.get("subject") or "").strip()
    if subj and not re.match(r'^(Исходящий|Входящий|Пропущенный)\s+(на|от)\s+[\d\s\+\-\(\)]+$', subj):
        return True
    return False


def _call_content(call):
    """Извлекает содержание звонка. Возвращает текст или None."""
    # 1. Транскрипт
    transcript = call.get("transcript", "")
    if transcript:
        m = re.search(r"РЕЗЮМЕ:\s*(.+?)(?=\n\n|$)", transcript, re.DOTALL)
        if m:
            return re.sub(r"\s+", " ", m.group(1).strip())
    # 2. DESCRIPTION
    desc = (call.get("DESCRIPTION") or call.get("description") or "").strip()
    if desc and not re.match(r'^[\d\s\+\-\(\)]+$', desc):
        return desc
    return None


def _call_score(call):
    """Оценка значимости звонка (для ранжирования)."""
    score = 0.0
    dur = int(call.get("duration", 0) or call.get("DURATION", 0) or 0)
    score += min(dur / 30, 10)
    content = (_call_content(call) or "").lower()
    for kw in ["груб", "негатив", "проблем", "жалоб", "отказ", "скандал"]:
        if kw in content:
            score += 5
    for kw in ["заказ", "оплат", "доставк", "подтверд", "оптов", "сделк"]:
        if kw in content:
            score += 2
    return score


def build_calls_section(scan):
    """Формирует секцию звонков.

    Логика:
    - Считаем только состоявшиеся звонки (не пропущенные)
    - Пропущенные — справочно, с привязкой к менеджеру
    - ТОП-5 только если есть реальное содержание (транскрипт/описание)
    """
    calls = _get_all_calls(scan)
    users = scan.get("users", {}) if scan else {}

    # Общая статистика из скана (более точная чем массив calls[])
    stats_total = 0
    if scan:
        stats_total = scan.get("activities", {}).get("calls_count", 0)

    if not calls and stats_total == 0:
        return "📞 ЗВОНКИ: данных нет\n"

    # Разделяем на состоявшиеся и пропущенные
    completed = []
    missed = []
    for c in calls:
        if _is_missed(c):
            missed.append(c)
        else:
            completed.append(c)

    # Подсчёт по менеджерам
    mgr_calls = {}  # менеджер → кол-во состоявшихся
    mgr_missed = {}  # менеджер → кол-во пропущенных
    for c in completed:
        rid = str(c.get("RESPONSIBLE_ID") or c.get("manager_id") or c.get("ASSIGNED_BY_ID") or "")
        name = c.get("_manager_name") or users.get(rid, "")
        if name:
            mgr_calls[name] = mgr_calls.get(name, 0) + 1
    for c in missed:
        rid = str(c.get("RESPONSIBLE_ID") or c.get("manager_id") or c.get("ASSIGNED_BY_ID") or "")
        name = c.get("_manager_name") or users.get(rid, "")
        if name:
            mgr_missed[name] = mgr_missed.get(name, 0) + 1

    # Используем stats_total если он больше (массив calls[] может быть неполным)
    display_total = max(stats_total, len(completed))

    lines = [
        "📞 ЗВОНКИ",
        f"   Состоявшихся: {display_total}",
    ]

    # Пропущенные справочно
    if missed:
        missed_parts = []
        for name, cnt in sorted(mgr_missed.items(), key=lambda x: -x[1]):
            missed_parts.append(f"{name}: {cnt}")
        missed_str = ", ".join(missed_parts) if missed_parts else f"{len(missed)} шт."
        lines.append(f"   ⚠️ Пропущенных: {len(missed)} ({missed_str})")
    lines.append("")

    # По менеджерам (из массива calls[])
    if mgr_calls:
        lines.append("   👩‍💼 Звонки по менеджерам:")
        for name, cnt in sorted(mgr_calls.items(), key=lambda x: -x[1]):
            m_miss = mgr_missed.get(name, 0)
            miss_note = f" + {m_miss} пропущ." if m_miss > 0 else ""
            lines.append(f"      • {name}: {cnt} звонков{miss_note}")
        lines.append("")

    # ТОП-5 только если есть реальное содержание (транскрипт/описание)
    calls_with_content = [c for c in completed if _has_real_content(c)]
    if calls_with_content:
        for c in calls_with_content:
            c["_score"] = _call_score(c)
        calls_with_content.sort(key=lambda x: x["_score"], reverse=True)
        top5 = calls_with_content[:5]

        lines.append("   🔥 ТОП-5 ЗНАЧИМЫХ ЗВОНКОВ:")
        for i, c in enumerate(top5, 1):
            rid = str(c.get("RESPONSIBLE_ID") or c.get("manager_id") or c.get("ASSIGNED_BY_ID") or "")
            mgr_name = c.get("_manager_name") or users.get(rid, f"ID_{rid}")
            dur = int(c.get("duration", 0) or c.get("DURATION", 0) or 0)
            dur_str = f"{dur // 60}м{dur % 60}с" if dur > 0 else "—"
            content = (_call_content(c) or "—")[:150]
            call_id = c.get("call_id", c.get("ID", "-"))
            icon = "🔴" if c["_score"] >= 8 else "🟡" if c["_score"] >= 4 else "🟢"
            lines.append(f"      {icon} {i}. [{call_id}] {mgr_name} ({dur_str})")
            lines.append(f"         {content}")

    lines.append("")
    return "\n".join(lines)


# ════════════════════════════════════════════
# ЧАСТЬ 3: AI-анализ (каскад LLM)
# ════════════════════════════════════════════

def generate_ai_insights(report_text, scan):
    """AI-выводы через каскад OpenRouter. Защита от галлюцинаций."""
    if not OPENROUTER_API_KEY:
        print("   ⚠️ OPENROUTER_API_KEY не задан — fallback на безопасный отчёт")
        return _safe_fallback(scan)

    # Подготовка данных о сделках
    deals_raw = scan.get("deals", {}).get("items", []) if scan else []
    deals_summary = ""
    has_real_deals = False
    for d in deals_raw[:30]:
        title = d.get('TITLE', '').strip()
        if not title:
            continue
        has_real_deals = True
        opp = d.get('OPPORTUNITY', '0')
        comment = (d.get('COMMENTS') or '').strip() or 'нет'
        deals_summary += f"- {title} | Сумма: {opp}₽ | Коммент: {comment}\n"

    if has_real_deals:
        deals_block = f"""
СДЕЛКИ ДЛЯ АНАЛИЗА (только из этого списка!):
{deals_summary}

📞 КЛЮЧЕВЫЕ СДЕЛКИ (только реальные из списка):
✅ для оплаченных, 🟡 для в работе, 🟠 для раздумий.
НЕ ДОБАВЛЯЙ сделки, которых нет в списке!"""
    else:
        deals_block = """
⚠️ Детализация по сделкам отсутствует. НЕ ВЫДУМЫВАЙ сделки!"""

    prompt = f"""Ты — Анжела Заботкина, AI-аналитик CRM инкубатора птиц.

🚨 ЗАПРЕТ НА ВЫДУМКУ ДАННЫХ — используй ТОЛЬКО факты из данных ниже.
Если данных нет — пиши «данных недостаточно».

ДАННЫЕ ЗА ДЕНЬ:
{report_text}
{deals_block}

ШАБЛОН:
🏆 ИТОГИ ДНЯ
1. [Общее впечатление по цифрам]
2. [Лучший менеджер — из данных]
3. [Активность: звонки/чаты/SMS]
4. [Проблемы]

📊 Конверсия лид→сделка: [рассчитай]

Отчёт сформирован Анжелой Заботкиной 👩‍💼"""

    CASCADE = [
        ("deepseek/deepseek-chat", 45),
        ("google/gemini-2.5-flash-preview", 45),
        ("moonshotai/moonshot-v1-32k", 45),
    ]

    for model_name, timeout in CASCADE:
        try:
            print(f"   🤖 AI: пробую {model_name}...")
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.15
                },
                timeout=timeout,
                proxies={"http": "", "https": ""}
            )
            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data:
                    ai_text = data["choices"][0]["message"]["content"]
                    # Детект галлюцинаций
                    markers = ["доставка в Москву", "доставка в Санкт-Петербург",
                               "клиент подтвердил заказ", "клиент готов к оплате"]
                    suspicious = sum(1 for m in markers if m.lower() in ai_text.lower())
                    if suspicious >= 2 and not has_real_deals:
                        print(f"   🚨 HALLUCINATION! {model_name} — fallback")
                        return _safe_fallback(scan)
                    print(f"   ✅ AI-отчёт через {model_name}")
                    return ai_text
            print(f"   ⚠️ {model_name}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"   ⚠️ {model_name}: {e}")

    return _safe_fallback(scan)


def _safe_fallback(scan):
    """Безопасный отчёт без AI — только факты."""
    if not scan:
        return "🏆 ИТОГИ ДНЯ: данные CRM недоступны.\n"
    deals = scan.get("deals", {})
    activities = scan.get("activities", {})
    managers = scan.get("manager_stats", {})
    calls = activities.get("calls_count", 0)
    chats = activities.get("chats_ol_count", 0)
    total = calls + chats
    d_count = deals.get("count", 0)
    conv = f"{(d_count / total * 100):.0f}%" if total > 0 else "н/д"

    best_mgr = "н/д"
    filtered = {k: v for k, v in managers.items() if k not in ("СРМ Б24", "Служебный", "Admin")}
    if filtered:
        best = max(filtered, key=lambda x: filtered[x].get("calls", 0))
        best_mgr = f"{best} ({filtered[best].get('calls', 0)} звонков, {filtered[best].get('deals', 0)} сделок)"

    return f"""🏆 ИТОГИ ДНЯ (без AI-анализа)

1. Сделок: {d_count} на {deals.get('total_amount', 0):,.0f}₽
2. Лучший менеджер: {best_mgr}
3. Активность: {calls} звонков, {chats} чатов
4. Детализация по сделкам недоступна.

📊 Конверсия: {conv}

Отчёт: Анжела Заботкина 👩‍💼""".replace(",", " ")


# ════════════════════════════════════════════
# ЧАСТЬ 4: Данные проекта
# ════════════════════════════════════════════

def build_project_section():
    """Статус проекта: песочница, VK, роадмап."""
    lines = []

    # Песочница
    scan_files = sorted(glob.glob(os.path.join(SANDBOX_SCAN_DIR, "sandbox_scan_*.json")))
    if scan_files:
        try:
            with open(scan_files[-1], 'r', encoding='utf-8') as f:
                data = json.load(f)
            tasks = data.get("tasks_summary", {}).get("items", [])
            total = len(tasks)
            done = sum(1 for t in tasks if str(t.get("status")) == "5")
            wip = sum(1 for t in tasks if str(t.get("status")) == "3")
            new = sum(1 for t in tasks if str(t.get("status")) == "2")
            pct = int(done / total * 100) if total > 0 else 0
            bar = "■" * (pct // 10) + "□" * (10 - pct // 10)
            lines.append("📋 ЗАДАЧИ ПЕСОЧНИЦЫ")
            lines.append(f"   Всего: {total} | ✅ {done} | 🚧 {wip} | 🆕 {new}")
            lines.append(f"   Прогресс: {pct}% [{bar}]")
            active = [t for t in tasks if str(t.get("status")) != "5"]
            if active:
                lines.append("")
                for t in active[:5]:
                    s = {"2": "🆕", "3": "🚧", "4": "⏳"}.get(str(t.get("status")), "❓")
                    lines.append(f"      {s} {t.get('title', '?')[:55]}")
        except Exception:
            lines.append("📋 ЗАДАЧИ ПЕСОЧНИЦЫ: ошибка чтения")
    else:
        lines.append("📋 ЗАДАЧИ ПЕСОЧНИЦЫ: данных нет")
    lines.append("")

    # VK контент
    vk = {"podvorye": 0, "vezemcyp": 0, "published": 0}
    for kind, subdir in [("podvorye", "podvorye"), ("vezemcyp", "vezemcyp")]:
        for f in glob.glob(os.path.join(VK_CONTENT_DIR, subdir, "*.md")):
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    vk[kind] += fh.read().count("# ПОСТ")
            except Exception:
                pass
    log_path = os.path.join(VK_CONTENT_DIR, "podvorye", "posted_log.json")
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                vk["published"] = len(json.load(f))
        except Exception:
            pass
    lines.append(f"📢 VK: Подворье {vk['podvorye']} / опубл. {vk['published']} | ВезёмЦыплят {vk['vezemcyp']}")
    lines.append("")

    # ACTIVE_TASKS
    if os.path.exists(ACTIVE_TASKS_PATH):
        try:
            with open(ACTIVE_TASKS_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
            done = content.count("[x]") + content.count("[X]")
            todo = content.count("[ ]")
            lines.append(f"🎯 РОАДМАП: {done}/{done + todo} выполнено ({todo} осталось)")
        except Exception:
            pass
    lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════
# ЧАСТЬ 5: Сборка + Отправка
# ════════════════════════════════════════════

def _fmt_iso(raw):
    """ISO → dd.mm HH:MM."""
    if not raw:
        return "н/д"
    try:
        return datetime.fromisoformat(raw).strftime("%d.%m %H:%M")
    except Exception:
        return raw[:16]


def build_full_report(target_date=None):
    """Собирает полный отчёт."""
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")

    scan, scan_info = get_crm_scan(target_date)
    crm_section = build_crm_section(scan, scan_info)
    calls_section = build_calls_section(scan)

    # AI-анализ
    print("   🤖 Генерирую AI-выводы...")
    ai_section = generate_ai_insights(crm_section, scan)

    project_section = build_project_section()

    report = f"""{'═' * 42}
📋 ЕЖЕДНЕВНЫЙ ОТЧЁТ — {date_str}
⏰ Сформирован: {time_str} MSK
{'═' * 42}

{crm_section}
{'─' * 42}

{calls_section}
{'─' * 42}

💡 ВЫВОДЫ АНЖЕЛОЧКИ:
{ai_section}

{'─' * 42}

{project_section}
{'─' * 42}
🐥 Отчёт собран Antigravity (IncuBird v2)
"""
    return report


def save_report(report_text):
    """Сохраняет отчёт в файл."""
    now = datetime.now()
    filename = f"report_{now.strftime('%Y%m%d_%H%M')}.md"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(report_text)
    return filepath


def send_to_telegram(text, chat_id, label=""):
    """Отправка в Telegram. Пробует напрямую, потом через SOCKS-прокси."""
    if not TELEGRAM_TOKEN:
        print("   ⚠️ TELEGRAM_TOKEN не задан — отправка невозможна")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    # Telegram limit: 4096 chars
    if len(text) > 4000:
        text = text[:3900] + "\n\n... (полный отчёт в файле)"

    payload = {"chat_id": chat_id, "text": text}

    # Попытка 1: напрямую (работает если TG не заблокирован)
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"   ✅ Отправлено {label} (direct)")
            return True
    except Exception:
        pass

    # Попытка 2: через SOCKS-прокси
    if PROXY_URL:
        try:
            p = PROXY_URL.replace("socks5://", "socks5h://")
            resp = requests.post(url, json=payload,
                                 proxies={"https": p, "http": p}, timeout=15)
            if resp.status_code == 200:
                print(f"   ✅ Отправлено {label} (proxy)")
                return True
            else:
                print(f"   ⚠️ Telegram [{label}]: {resp.status_code} — {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"   ❌ Telegram [{label}] proxy: {e}")
            return False

    print(f"   ❌ Telegram [{label}]: не удалось отправить")
    return False


def main():
    args = sys.argv[1:]
    do_send = "--send" in args
    preview_only = "--preview" in args

    # Поддержка --date YYYYMMDD
    target_date = None
    if "--date" in args:
        idx = args.index("--date")
        if idx + 1 < len(args):
            target_date = args[idx + 1]

    print()
    print("🔧 Собираю данные для отчёта...")
    if target_date:
        print(f"   📅 Целевая дата: {target_date}")
    print()

    report = build_full_report(target_date)

    # Всегда показываем
    print(report)

    if preview_only:
        print("👀 Режим превью — файл не сохранён, не отправлен.")
        return

    # Сохраняем
    filepath = save_report(report)
    print(f"💾 Сохранён: {filepath}")
    print()

    if do_send:
        print("📤 Отправляю в Telegram (ТОЛЬКО Игорю)...")
        # ⛔ Андрею — НИКАКИХ отчётов в TG! (решение от 12.05.2026)
        send_to_telegram(report, IGOR_ID, label="Игорь")
        print()
        print("✅ Готово!")
    else:
        print("ℹ️  Отчёт НЕ отправлен. Чтобы отправить:")
        print("    python3.12 agent/manual_report.py --send")
        print()


if __name__ == "__main__":
    main()
