"""
Daily Report — Ежедневный отчёт Анжелочки для Андрея.
Собирает данные из последнего скана Bitrix24, генерирует AI-сводку,
отправляет в Telegram.
Запускается через cron в 20:00 MSK.
"""
import os
import sys
import json
import glob
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
ADMIN_ID = 444248782  # Андрей (реальный TG ID из history.md)
OWNER_ID = 176203333  # Игорь — контроль качества отчётов
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PROXY_URL = os.getenv("TELEGRAM_PROXY")

SCAN_LOG_DIR = os.path.join(BASE_DIR, "data", "bitrix_scans")
REPORTS_DIR = os.path.join(BASE_DIR, "data", "daily_reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def get_latest_scan():
    """Находит ЛУЧШИЙ файл сканирования за сегодня.
    
    Проблема: если последний скан пустой (за 30 мин ничего не случилось),
    он перезатирает богатый предыдущий скан. Поэтому берём скан с
    максимальным количеством данных (менеджеры + сделки) за сегодня.
    """
    today = datetime.now().strftime("%Y%m%d")
    all_files = sorted(glob.glob(os.path.join(SCAN_LOG_DIR, "scan_*.json")))
    if not all_files:
        return None
    
    # Сначала ищем сканы за сегодня
    today_files = [f for f in all_files if f"scan_{today}" in f]
    candidates = today_files if today_files else [all_files[-1]]
    
    best_scan = None
    best_score = -1
    
    for fpath in candidates:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                scan = json.load(f)
            # Оцениваем «богатство» скана: менеджеры + сделки + звонки
            score = (
                len(scan.get("manager_stats", {})) * 10 +
                scan.get("deals", {}).get("count", 0) +
                scan.get("activities", {}).get("calls_count", 0)
            )
            if score > best_score:
                best_score = score
                best_scan = scan
        except Exception:
            continue
    
    return best_scan


def build_report_text(scan):
    """Формирует текстовый отчёт из данных скана."""
    now = datetime.now().strftime("%d.%m.%Y")
    
    deals = scan.get("deals", {})
    activities = scan.get("activities", {})
    tasks = scan.get("tasks", {})
    products = scan.get("products", {})
    managers = scan.get("manager_stats", {})

    lines = [
        f"📋 ЕЖЕДНЕВНЫЙ ОТЧЁТ АНЖЕЛОЧКИ",
        f"📅 {now}",
        "",
        f"🆕 Новые сделки: {deals.get('count', 0)} (на {deals.get('total_amount', 0):,.0f}₽)".replace(",", " "),
        "",
        f"📞 РЕАЛЬНЫЕ звонки: {activities.get('calls_count', 0)}",
        f"💬 Чаты (TG/Avito): {activities.get('chats_ol_count', 0)}",
        f"📱 SMS: {activities.get('sms_count', 0)}",
        f"📋 Веб-формы: {activities.get('webforms_count', 0)}",
        f"✅ Задач открыто: {tasks.get('open', 0)}",
        f"📦 Товаров в каталоге: {products.get('count', 0)}",
        "",
    ]

    # Менеджеры
    if managers:
        lines.append("👩‍💼 АКТИВНОСТЬ ПО МЕНЕДЖЕРАМ:")
        for name, stats in sorted(managers.items(), key=lambda x: x[1].get("deals", 0), reverse=True):
            if name in ("СРМ Б24", "Служебный", "Admin"):
                continue
            deals_count = stats.get("deals", 0)
            calls_count = stats.get("calls", 0)
            amount = stats.get("amount", 0)
            lines.append(f"  • {name}: {deals_count} сделок, {calls_count} звонков ({amount:,.0f}₽)".replace(",", " "))
        lines.append("")

    # Обучение (новое!)
    learning_path = os.path.join(BASE_DIR, "data", "daily_learning.json")
    if os.path.exists(learning_path):
        try:
            with open(learning_path, 'r', encoding='utf-8') as f:
                learning_data = json.load(f).get(datetime.now().strftime("%Y-%m-%d"), [])
            if learning_data:
                lines.append("🎓 ЧЕМУ Я НАУЧИЛАСЬ СЕГОДНЯ:")
                for i, fact in enumerate(learning_data[:5], 1):
                    lines.append(f"  {i}. {fact}")
                lines.append("")
        except Exception:
            pass

    return "\n".join(lines)


def generate_ai_insights(report_text, scan):
    """AI-выводы и рекомендации через LLM."""
    prompt = f"""Ты — Анжелочка, AI-менеджер инкубатора птиц. 
Проанализируй данные за день и дай 3-4 коротких вывода/рекомендации для руководителя Андрея.
Будь конкретной, используй цифры из отчёта. Максимум 5 строк.

ДАННЫЕ:
{report_text}
"""
    
    # Попытка 1: Gemini
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"⚠️ Gemini error: {e}")
    
    # Попытка 2: OpenRouter
    if OPENROUTER_API_KEY:
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3
                },
                timeout=15
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"⚠️ OpenRouter error: {e}")
    
    return "💡 AI-анализ временно недоступен."


def _send_tg(chat_id, text, label=""):
    """Низкоуровневая отправка в Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Используем прокси если настроен
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
            print(f"⚠️ Telegram error [{label}]: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"⚠️ Telegram send error [{label}]: {e}")
        return False


def send_telegram_message(text):
    """Отправка сообщения Андрею через Telegram."""
    return _send_tg(ADMIN_ID, text, label="Андрей")


def send_owner_copy(text):
    """Копия отчёта владельцу (Игорь) для контроля качества. Только Telegram."""
    header = "🔍 КОНТРОЛЬ КАЧЕСТВА ОТЧЁТА\n" + "─" * 30 + "\n\n"
    return _send_tg(OWNER_ID, header + text, label="Игорь/Owner")


def run_daily_report():
    """Генерация и отправка ежедневного отчёта."""
    print(f"\n{'='*50}")
    print(f"📋 DAILY REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # 1. Берём последний скан
    scan = get_latest_scan()
    if not scan:
        print("❌ Нет данных сканирования. Запустите bitrix_scanner.py сначала.")
        return

    scan_time = scan.get("scan_time", "?")
    print(f"📅 Данные из скана: {scan_time}")

    # 2. Формируем отчёт
    report_text = build_report_text(scan)
    print(f"\n{report_text}")

    # 3. AI-выводы
    print("🤖 Генерирую AI-выводы...")
    insights = generate_ai_insights(report_text, scan)
    
    full_report = f"{report_text}\n💡 ВЫВОДЫ АНЖЕЛОЧКИ:\n{insights}"

    # ═══════════════════════════════════════════════════
    # 🔒 SHADOW MODE (активен до особого распоряжения)
    # Все отчёты идут ТОЛЬКО Игорю (OWNER_ID).
    # Андрей, Битрикс, A2A — ОТКЛЮЧЕНЫ.
    # ═══════════════════════════════════════════════════

    # 4. A2A шина — ОТКЛЮЧЕНА (Shadow Mode)
    # try:
    #     from a2a_protocol import report_insight, notify
    #     ...
    # except: pass
    print("🔒 A2A: отключена (Shadow Mode)")

    # 5. Сохраняем локально
    report_file = os.path.join(REPORTS_DIR, f"report_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(full_report)
    print(f"\n💾 Отчёт сохранён: {report_file}")

    tg_report = full_report
    if len(tg_report) > 4000:
        tg_report = tg_report[:3900] + "\n\n... (полный отчёт в файле)"

    # 6. Андрею — ОТКЛЮЧЕНО (Shadow Mode)
    # send_telegram_message(tg_report)
    print("🔒 Андрей: отправка отключена (Shadow Mode)")

    # 7. Bitrix24 — ОТКЛЮЧЕНО (Shadow Mode)
    # send_bitrix_message(full_report)
    print("🔒 Bitrix: отправка отключена (Shadow Mode)")

    # 8. ТОЛЬКО Игорю — единственный получатель
    send_owner_copy(tg_report)

    return full_report


if __name__ == "__main__":
    run_daily_report()
