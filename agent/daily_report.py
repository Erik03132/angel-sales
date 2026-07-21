"""
Daily Report — Ежедневный отчёт Заботкиной по CRM Bitrix24.
Собирает данные из последнего скана Bitrix24, генерирует AI-сводку.

⚠️ ПОЛУЧАТЕЛИ: ТОЛЬКО Игорь (176203333).
   Андрею — НИКАКИХ отчётов в TG! (решение от 12.05.2026)

Запускается через scheduler в 20:00 MSK.

ФОРМАТ ОТЧЁТА: строго по docs/REPORTS_FORMAT.md (обновлено 12.05.2026)
"""
import glob
import json
import os
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    requests = None

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OWNER_ID = 176203333  # Игорь
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PROXY_URL = os.getenv("TELEGRAM_PROXY")

# === КАСКАД OpenRouter (бесплатные модели) ===
# Актуально на июль 2026. DeepSeek/Gemini free больше нет на OpenRouter.
# Rate limit: ~20 req/min, ~200-1000 req/day для free моделей.
CASCADE_MODELS = [
    "google/gemma-4-31b-it:free",              # Tier 1: Gemma 4 31B — лучшая free для инструкций
    "nvidia/nemotron-3-super-120b-a12b:free",  # Tier 2: 1M контекст, сильное reasoning
    "meta-llama/llama-3.3-70b-instruct:free",  # Tier 3: 131K, надёжная классика
    "openai/gpt-oss-20b:free",                 # Tier 4: быстрый лёгкий fallback
    "deepseek/deepseek-chat",                  # Tier 5: платный $0.14/1M — последний рубеж
]
SEND_REPORT_CHAT_ID = OWNER_ID

DATA_DIR = os.path.join(BASE_DIR, "data")
SCAN_LOG_DIR = os.path.join(DATA_DIR, "bitrix_scans")
REPORTS_DIR = os.path.join(DATA_DIR, "daily_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def _auto_run_scanner():
    """Запускает bitrix_scanner.py синхронно — вызывается при устаревших данных."""
    try:
        import subprocess
        agent_dir = os.path.dirname(os.path.abspath(__file__))
        venv_python = os.path.normpath(os.path.join(agent_dir, "..", "venv", "bin", "python3"))
        python_cmd = venv_python if os.path.exists(venv_python) else sys.executable
        scanner_path = os.path.join(agent_dir, "bitrix_scanner.py")
        print("🔄 AUTO-SCAN: запускаю сканер (данные устарели)...")
        result = subprocess.run(
            [python_cmd, scanner_path],
            timeout=60,
            capture_output=True,
            text=True,
            cwd=agent_dir
        )
        if result.returncode == 0:
            print("✅ AUTO-SCAN: завершён успешно")
            return True
        else:
            print(f"⚠️ AUTO-SCAN error: {result.stderr[:300]}")
            return False
    except subprocess.TimeoutExpired:
        print("⚠️ AUTO-SCAN: таймаут 60с")
        return False
    except Exception as e:
        print(f"⚠️ AUTO-SCAN exception: {e}")
        return False


def _is_scan_stale(fpath, max_age_hours=2):
    """Проверяет, устарел ли скан."""
    try:
        mtime = os.path.getmtime(fpath)
        age_hours = (datetime.now().timestamp() - mtime) / 3600
        if age_hours > max_age_hours:
            return True, age_hours
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        scan_time_str = data.get("scan_time", "")
        if scan_time_str:
            scan_dt = datetime.fromisoformat(scan_time_str)
            age_hours = (datetime.now() - scan_dt).total_seconds() / 3600
            return age_hours > max_age_hours, age_hours
    except Exception:
        pass
    return False, 0


def get_latest_scan(auto_scan_if_stale=True):
    """Находит самый свежий и содержательный скан CRM."""
    all_files = sorted(glob.glob(os.path.join(SCAN_LOG_DIR, "scan_*.json")))

    if all_files:
        newest_file = all_files[-1]
        is_stale, age_h = _is_scan_stale(newest_file, max_age_hours=2)
        if is_stale and auto_scan_if_stale:
            print(f"⚠️ Последний скан устарел на {age_h:.1f}ч — запускаю авто-обновление...")
            scan_ok = _auto_run_scanner()
            if scan_ok:
                all_files = sorted(glob.glob(os.path.join(SCAN_LOG_DIR, "scan_*.json")))

    if not all_files:
        if auto_scan_if_stale:
            _auto_run_scanner()
            all_files = sorted(glob.glob(os.path.join(SCAN_LOG_DIR, "scan_*.json")))
        if not all_files:
            return None

    today = datetime.now().strftime("%Y%m%d")
    today_files = sorted([f for f in all_files if f"scan_{today}" in f], reverse=True)
    for fpath in today_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data:
                    return data
        except:
            continue

    last_candidates = all_files[-10:]
    best_scan_data = None
    max_score = -1

    for fpath in reversed(last_candidates):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            score = (
                len(data.get("manager_stats", {})) * 10 +
                data.get("deals", {}).get("count", 0) * 5 +
                data.get("activities", {}).get("calls_count", 0)
            )
            if score > max_score:
                max_score = score
                best_scan_data = data
            if score > 5:
                return data
        except:
            continue

    return best_scan_data or (json.load(open(all_files[-1])) if all_files else None)


def format_rubles(amount):
    """Форматирует рубли с пробелами (1 000 000)."""
    try:
        return f"{int(float(amount)):,}".replace(",", " ")
    except:
        return str(amount)


def build_report_text(scan):
    """Формирует текстовый отчёт СТРОГО по REPORTS_FORMAT.md от 12.05.2026."""
    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")

    deals = scan.get("deals", {})
    activities = scan.get("activities", {})
    tasks = scan.get("tasks", {})
    products = scan.get("products", {})
    managers = scan.get("manager_stats", {})
    leads = scan.get("leads", {})
    payments = scan.get("payments", {})

    # Период данных
    since_raw = scan.get("since", "")
    if since_raw:
        try:
            since_dt = datetime.fromisoformat(since_raw)
            since_str = since_dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            since_str = since_raw[:16]
    else:
        since_str = "н/д"

    lines = [
        "══════════════════════════════════════════",
        f"📋 ЕЖЕДНЕВНЫЙ ОТЧЁТ — {today_str}",
        f"⏰ Сформирован: {time_str} MSK",
        "══════════════════════════════════════════",
        "",
        "📊 CRM BITRIX24",
        f"   Источник: файл скана (свежесть: {since_str})",
        "",
        f"   🆕 Сделки: {deals.get('count', 0)} (на {format_rubles(deals.get('total_amount', 0))}₽)",
        f"   📞 Звонки: {activities.get('calls_count', 0)}",
        f"   💬 Чаты: {activities.get('chats_ol_count', 0)}",
        f"   📱 SMS: {activities.get('sms_count', 0)}",
        f"   📋 Веб-формы: {activities.get('webforms_count', 0)}",
        "",
    ]

    # По менеджерам
    if managers:
        lines.append("   👩‍💼 По менеджерам:")
        for name, stats in sorted(managers.items(), key=lambda x: x[1].get("deals", 0), reverse=True):
            if name in ("СРМ Б24", "Служебный", "Admin"):
                continue
            deals_count = stats.get("deals", 0)
            calls_count = stats.get("calls", 0)
            amount = stats.get("amount", 0)
            lines.append(f"      • {name}: {deals_count} сделок, {calls_count} звонков ({format_rubles(amount)}₽)")
        lines.append("")

    # Конверсия
    calls = activities.get("calls_count", 0)
    chats = activities.get("chats_ol_count", 0)
    total_leads_count = calls + chats
    deals_count = deals.get("count", 0)
    conversion = f"{(deals_count / total_leads_count * 100):.0f}%" if total_leads_count > 0 else "н/д"
    lines.append(f"   📈 Конверсия (сделки / лиды): {conversion}")
    lines.append("")

    # СТАТУСЫ СДЕЛОК
    deal_items = deals.get("items", [])
    stage_stats = {}
    for d in deal_items:
        stage = d.get("STAGE_ID", "UNKNOWN")
        stage_name = d.get("STAGE_NAME", stage)
        opp = float(d.get("OPPORTUNITY", 0) or 0)
        if stage_name not in stage_stats:
            stage_stats[stage_name] = {"count": 0, "amount": 0, "deals": []}
        stage_stats[stage_name]["count"] += 1
        stage_stats[stage_name]["amount"] += opp
        stage_stats[stage_name]["deals"].append(d)

    if stage_stats:
        lines.append("   📊 СТАТУС СДЕЛОК (где что):")
        stage_icons = {
            "NEW": "🆕",
            "PREPAYMENT": "⏳",
            "INVOICE": "📝",
            "WON": "✅",
            "LOSE": "❌",
        }
        for stage_name, stats in sorted(stage_stats.items(), key=lambda x: -x[1]["amount"]):
            icon = stage_icons.get(stage_name.split(":")[0].strip(), "📋")
            lines.append(f"      {icon} {stage_name}: {stats['count']} шт. ({format_rubles(stats['amount'])}₽)")
            # ТОП-3 по сумме в статусе
            top_deals = sorted(stats["deals"], key=lambda x: float(x.get("OPPORTUNITY", 0) or 0), reverse=True)[:3]
            for td in top_deals:
                title = td.get("TITLE", "Без названия")
                mgr_id = str(td.get("ASSIGNED_BY_ID", ""))
                mgr_name = get_manager_name(mgr_id)
                opp = format_rubles(td.get("OPPORTUNITY", 0))
                lines.append(f"         → {opp}₽ — {mgr_name} ({title})")
        lines.append("")

    # ЗАБЫТЫЕ СДЕЛКИ
    forgotten = find_forgotten_deals(deal_items, days=3)
    if forgotten:
        lines.append("   ⏰ ЗАБЫТЫЕ СДЕЛКИ (без движения >3 дней):")
        for fd in forgotten[:5]:
            title = fd.get("TITLE", "Без названия")
            modified = fd.get("DATE_MODIFY", "")[:10]
            opp = format_rubles(fd.get("OPPORTUNITY", 0))
            lines.append(f"      • {title} ({modified}) — {opp}₽")
        lines.append("")

    # ЛИДЫ
    lead_items = leads.get("items", [])
    if lead_items or leads.get("count", 0) > 0:
        lines.append(f"   📥 ЛИДЫ: {leads.get('count', len(lead_items))}")
        # По источникам
        lead_sources = {}
        for l in lead_items[:50]:
            src = l.get("SOURCE_ID", "UNKNOWN")
            lead_sources[src] = lead_sources.get(src, 0) + 1
        if lead_sources:
            lines.append("      По источникам:")
            for src, cnt in sorted(lead_sources.items(), key=lambda x: -x[1]):
                src_label = {"CALL": "📞 Звонки", "OPENLINE": "💬 Чаты", "EMAIL": "📧 Email",
                             "VK": "📱 VK", "WEBFORM": "🌐 Сайт", "FACEBOOK": "FB"}.get(src, src)
                lines.append(f"         • {src_label}: {cnt}")
        lines.append("")

    # ТОП ПРОДАЖ (породы)
    product_stats = aggregate_product_sales(deal_items)
    if product_stats:
        lines.append("   🐔 ТОП ПРОДАЖ (что покупают):")
        for prod_name, stats in sorted(product_stats.items(), key=lambda x: -x[1]["total_amount"])[:5]:
            lines.append(f"      • {prod_name}: {stats['count']} шт. ({format_rubles(stats['total_amount'])}₽, {stats['deals_count']} сделок)")
        lines.append("")

    # ОПЛАТЫ 1С
    paid_count = payments.get("paid_count", 0)
    paid_amount = payments.get("paid_amount", 0)
    unpaid_count = payments.get("unpaid_count", 0)
    unpaid_amount = payments.get("unpaid_amount", 0)
    if paid_count > 0 or unpaid_count > 0:
        lines.append("   💰 ОПЛАТЫ (1С):")
        lines.append(f"      ✅ Оплачено: {paid_count} сделок ({format_rubles(paid_amount)}₽)")
        lines.append(f"      ⏳ Не оплачено: {unpaid_count} сделок ({format_rubles(unpaid_amount)}₽)")
        lines.append("")

    lines.append("──────────────────────────────────────────")
    lines.append("")

    # ЗВОНКИ
    lines.append("📞 ЗВОНКИ")
    lines.append(f"   Состоявшихся: {activities.get('calls_count', 0)}")
    missed_calls = activities.get("missed_calls", 0)
    if missed_calls > 0:
        lines.append(f"   ⚠️ Пропущенных: {missed_calls}")
        # По менеджерам
        missed_by_mgr = {}
        call_items = scan.get("activities", {}).get("call_items", [])
        for c in call_items:
            if str(c.get("DIRECTION")) == "1" and c.get("STATUS_CODE") == "4":  # Входящий пропущенный
                mgr_id = str(c.get("RESPONSIBLE_ID", ""))
                mgr_name = get_manager_name(mgr_id)
                missed_by_mgr[mgr_name] = missed_by_mgr.get(mgr_name, 0) + 1
        if missed_by_mgr:
            lines.append("      По менеджерам:")
            for mgr, cnt in sorted(missed_by_mgr.items(), key=lambda x: -x[1]):
                lines.append(f"         • {mgr}: {cnt} пропущ.")
    lines.append("")
    lines.append("──────────────────────────────────────────")
    lines.append("")

    return "\n".join(lines)


def get_manager_name(mgr_id):
    """Возвращает имя менеджера по ID."""
    users = {
        "1": "Андрей", "22": "Олег Мосин", "124": "Татьяна",
        "1528": "Аня", "1586": "Менеджер", "4388": "Эльзара",
        "40318": "Марина Е", "40994": "Ольга М.", "41624": "Анжелочка"
    }
    return users.get(mgr_id, f"ID:{mgr_id}")


def find_forgotten_deals(deal_items, days=3):
    """Находит сделки без движения > N дней."""
    forgotten = []
    now = datetime.now()
    for d in deal_items:
        modified = d.get("DATE_MODIFY", "")
        if modified:
            try:
                mod_dt = datetime.fromisoformat(modified)
                age = (now - mod_dt).days
                if age > days:
                    forgotten.append(d)
            except:
                pass
    return sorted(forgotten, key=lambda x: x.get("DATE_MODIFY", ""))


def aggregate_product_sales(deal_items):
    """Агрегирует продажи по товарам/породам из 1С-полей."""
    product_stats = {}
    for d in deal_items:
        products = d.get("PRODUCTS", [])
        for p in products:
            name = p.get("NAME", "Неизвестно")
            qty = int(p.get("QUANTITY", 1) or 1)
            price = float(p.get("PRICE", 0) or 0)
            if name not in product_stats:
                product_stats[name] = {"count": 0, "total_amount": 0, "deals_count": 0}
            product_stats[name]["count"] += qty
            product_stats[name]["total_amount"] += qty * price
            product_stats[name]["deals_count"] += 1
    return product_stats


def generate_ai_insights(report_text, scan):
    """AI-анализ отчёта по каскаду бесплатных OpenRouter-моделей.

    КАСКАД МОДЕЛЕЙ (обновлено 21.07.2026):
    1→N: OpenRouter free модели из CASCADE_MODELS (бесплатно)
    N+1: DeepSeek Chat (платный fallback $0.14/1M)
    Fallback: безопасный отчёт без AI

    ⚠️ IRON_RULE: ВСЕ API-запросы — ТОЛЬКО через USA прокси (TELEGRAM_PROXY)!
    """
    if not requests or not OPENROUTER_API_KEY:
        return _safe_fallback_insights(report_text, scan)

    proxies = {}
    if PROXY_URL:
        proxy = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": proxy, "http": proxy}

    prompt = f"""Ты — Анжела Заботкина, AI-аналитик CRM инкубатора птиц.

🚨 ПРАВИЛО: Используй ТОЛЬКО данные из отчёта. НЕ ВЫДУМЫВАЙ имена, породы, города, цены!

ДАННЫЕ ЗА ДЕНЬ:
{report_text}

ШАБЛОН ВЫВОДОВ:

🏆 ИТОГИ ДНЯ

1. [Общее впечатление — на основе цифр]
2. [Самый результативный менеджер — ТОЛЬКО из данных]
3. [Активность: соотношение звонков/чатов/SMS]
4. [Проблемы: что бросается в глаза]

📊 Конверсия лид→сделка: [из данных или рассчитай]

Отчёт сформирован Анжелой Заботкиной (CRM Аналитика) 👩‍💼"""

    for model in CASCADE_MODELS:
        label = f"free/{model}" if ":free" in model else "paid"
        try:
            print(f"🤖 Отчёт: пробую {model} ({label})...")
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.15,
                },
                proxies=proxies,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                if "choices" in data and data["choices"]:
                    ai_text = data["choices"][0]["message"]["content"]
                    print(f"✅ Отчёт сгенерирован через {model}")
                    return ai_text
            else:
                print(f"⚠️ {model}: {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"⚠️ {model} failed: {e}")

    return _safe_fallback_insights(report_text, scan)


def _safe_fallback_insights(report_text, scan):
    """Безопасный отчёт БЕЗ AI — только факты."""
    deals = scan.get("deals", {})
    activities = scan.get("activities", {})
    managers = scan.get("manager_stats", {})

    calls = activities.get("calls_count", 0)
    chats = activities.get("chats_ol_count", 0)
    total_leads = calls + chats
    deals_count = deals.get("count", 0)
    conversion = f"{(deals_count / total_leads * 100):.0f}%" if total_leads > 0 else "н/д"

    best_mgr = "н/д"
    if managers:
        filtered = {k: v for k, v in managers.items() if k not in ("СРМ Б24", "Служебный", "Admin")}
        if filtered:
            best_name = max(filtered, key=lambda x: filtered[x].get("calls", 0))
            best_calls = filtered[best_name].get("calls", 0)
            best_deals = filtered[best_name].get("deals", 0)
            best_mgr = f"{best_name} ({best_calls} звонков, {best_deals} сделок)"

    return f"""🏆 ИТОГИ ДНЯ (автоматический отчёт без AI)

1. Сделок за день: {deals_count} на {format_rubles(deals.get('total_amount', 0))}₽
2. Самый активный менеджер: {best_mgr}
3. Активность: {calls} звонков, {chats} чатов
4. Конверсия: {conversion}

Отчёт сформирован Анжелой Заботкиной (CRM Аналитика) 👩‍💼"""


def _send_tg(chat_id, text, label=""):
    """Низкоуровневая отправка в Telegram."""
    if not requests:
        print("⚠️ requests не доступен, отправка в TG невозможна")
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
            "parse_mode": "HTML"
        }, proxies=proxies, timeout=15)

        if resp.status_code == 200:
            print(f"✅ Отчёт отправлен {label} (chat_id={chat_id})")
            return True
        else:
            print(f"⚠️ Telegram error [{label}]: {resp.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ Telegram send error [{label}]: {e}")
        return False


def send_telegram_message(text):
    """Отправка сообщения ТОЛЬКО Игорю."""
    return _send_tg(OWNER_ID, text, label="Игорь")


def send_owner_copy(text):
    """Копия отчёта владельцу (Игорь)."""
    header = "🔍 КОНТРОЛЬ КАЧЕСТВА ОТЧЁТА\n" + "─" * 30 + "\n\n"
    return _send_tg(OWNER_ID, header + text, label="Игорь/Owner")


def run_daily_report():
    """Генерация и отправка ежедневного отчёта."""
    print(f"\n{'='*50}")
    print(f"📋 DAILY REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    today = datetime.now().strftime("%Y%m%d")
    sent_flag_file = os.path.join(REPORTS_DIR, f".sent_{today}")
    already_sent = os.path.exists(sent_flag_file)
    if already_sent:
        print(f"ℹ️ Отчёт за {today} уже был отправлен в TG. Обновляю только файл.")

    scan = get_latest_scan()
    if not scan:
        print("❌ Нет данных сканирования. Запустите bitrix_scanner.py сначала.")
        return

    scan_time = scan.get("scan_time", "?")
    print(f"📅 Данные из скана: {scan_time}")

    # 1. Текстовый отчёт по шаблону
    report_text = build_report_text(scan)
    print(f"\n{report_text}")

    # 2. AI-выводы
    print("🤖 Генерирую AI-выводы...")
    insights = generate_ai_insights(report_text, scan)

    full_report = f"{report_text}💡 ВЫВОДЫ АНЖЕЛОЧКИ:\n{insights}"

    # 3. Сохраняем локально
    report_file = os.path.join(REPORTS_DIR, f"report_{today}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(full_report)
    print(f"\n💾 Отчёт сохранён: {report_file}")

    # 4. Отправка в TG (только если ещё не отправлен)
    if not already_sent:
        tg_report = full_report
        if len(tg_report) > 4000:
            tg_report = tg_report[:3900] + "\n\n... (полный отчёт в файле)"

        send_owner_copy(tg_report)
        print("✅ Отчёт Заботкиной отправлен ТОЛЬКО Игорю")

        with open(sent_flag_file, 'w') as f:
            f.write(datetime.now().isoformat())
        print(f"🏁 Флаг отправки установлен: {sent_flag_file}")
    else:
        print("⏭️ TG-отправка пропущена (уже отправлен сегодня)")

    return full_report


if __name__ == "__main__":
    run_daily_report()
