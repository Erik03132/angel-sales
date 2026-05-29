"""
Project Report — Ежедневный отчёт Анжелы Птенчиковой по проекту INCUBIRD 2.0.
Собирает РЕАЛЬНЫЕ данные из report-day, хроник дня, VK-контента.

⚠️ НЕ ИСПОЛЬЗУЕТ Битрикс Песочницы (там нет актуальных данных).
Источники:
  1. report-day (~/freelance-2026/reports/) — стенограмма сессий
  2. Хроника дня (~/freelance-2026/chronicles/) — автозапись действий
  3. VK-контент (vk_content/) — посты для Подворья и ВезёмЦыплят
  4. ACTIVE_TASKS.md — дорожная карта

Отправляется ТОЛЬКО Игорю (176203333) в 20:05 MSK.
Формат — произвольный (решение от 12.05.2026).
"""
import glob
import json
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
IGOR_ID = 176203333
PROXY_URL = os.getenv("TELEGRAM_PROXY")

DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR_OUT = os.path.join(DATA_DIR, "daily_reports")
# Источники данных — report-day и хроники
REPORT_DAY_DIR = os.path.join(os.path.dirname(BASE_DIR), "reports")
CHRONICLES_DIR = os.path.join(os.path.dirname(BASE_DIR), "chronicles")
VK_CONTENT_DIR = os.path.join(BASE_DIR, "vk_content")
ACTIVE_TASKS_PATH = os.path.join(os.path.dirname(BASE_DIR), "ACTIVE_TASKS.md")

os.makedirs(REPORTS_DIR_OUT, exist_ok=True)


def _send_tg(chat_id, text):
    """Отправка в TG (ТОЛЬКО Игорю)."""
    if not TELEGRAM_TOKEN:
        print("⚠️ TELEGRAM_TOKEN не задан")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        p = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": p, "http": p}
    
    try:
        # Telegram limit: 4096 chars
        if len(text) > 4000:
            text = text[:3900] + "\n\n... (обрезано)"
        
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }, proxies=proxies, timeout=15)
        
        if resp.status_code == 200:
            print(f"✅ Отправлено Игорю ({chat_id})")
        else:
            print(f"⚠️ TG error: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")


def get_latest_report_day():
    """Получает данные из последнего report-day за сегодня или вчера."""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Ищем отчёты за сегодня, потом за вчера
    for date_str in [today, yesterday]:
        pattern = os.path.join(REPORT_DAY_DIR, f"report-day_{date_str}*.md")
        files = sorted(glob.glob(pattern))
        if files:
            latest = files[-1]
            try:
                with open(latest, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Извлекаем ключевые секции
                works = []
                in_works = False
                for line in content.split("\n"):
                    if "Выполненные работы" in line or "выполненные" in line.lower():
                        in_works = True
                        continue
                    if in_works and line.startswith("## "):
                        break
                    if in_works and line.strip().startswith("- "):
                        works.append(line.strip())
                
                return {
                    "date": date_str,
                    "file": os.path.basename(latest),
                    "works": works[:10],
                    "full_text_len": len(content),
                }
            except Exception as e:
                print(f"⚠️ Ошибка чтения report-day: {e}")
    
    return None


def get_today_chronicle():
    """Получает хронику сегодняшнего дня."""
    today = datetime.now().strftime("%Y-%m-%d")
    chronicle_path = os.path.join(CHRONICLES_DIR, f"chronicle_{today}.md")
    
    if not os.path.exists(chronicle_path):
        return None
    
    try:
        with open(chronicle_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        entries = [l for l in content.split("\n") if l.startswith("- **")]
        sessions = [l for l in content.split("\n") if l.startswith("## 🕐")]
        
        return {
            "entries_count": len(entries),
            "sessions_count": len(sessions),
            "last_entries": entries[-5:] if entries else [],
        }
    except Exception:
        return None


def get_vk_content_status():
    """Получает статус VK-контента."""
    status = {"podvorye_posts": 0, "vezemcyp_posts": 0, "published": 0}
    
    for f in glob.glob(os.path.join(VK_CONTENT_DIR, "podvorye", "*.md")):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                status["podvorye_posts"] += fh.read().count("# ПОСТ")
        except Exception:
            pass
    
    for f in glob.glob(os.path.join(VK_CONTENT_DIR, "vezemcyp", "*.md")):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                status["vezemcyp_posts"] += fh.read().count("# ПОСТ")
        except Exception:
            pass
    
    posted_log = os.path.join(VK_CONTENT_DIR, "podvorye", "posted_log.json")
    if os.path.exists(posted_log):
        try:
            with open(posted_log, 'r', encoding='utf-8') as f:
                status["published"] = len(json.load(f))
        except Exception:
            pass
    
    return status


def get_active_tasks_summary():
    """Краткая сводка из ACTIVE_TASKS.md."""
    if not os.path.exists(ACTIVE_TASKS_PATH):
        return None
    
    try:
        with open(ACTIVE_TASKS_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        
        done = content.count("[x]") + content.count("[X]")
        todo = content.count("[ ]")
        
        return {"done": done, "todo": todo, "total": done + todo}
    except Exception:
        return None


def run_project_report():
    print("📋 Генерация отчёта Птенчиковой по проекту INCUBIRD 2.0...")
    
    today = datetime.now().strftime("%d.%m.%Y")
    now_time = datetime.now().strftime("%H:%M")
    
    # === Собираем данные ===
    report_day = get_latest_report_day()
    chronicle = get_today_chronicle()
    vk_status = get_vk_content_status()
    active_tasks = get_active_tasks_summary()
    
    # === Формируем отчёт ===
    lines = [
        "🚀 <b>ОТЧЁТ ПО ПРОЕКТУ: IncuBird 2.0</b>",
        f"📅 Дата: {today} | {now_time} MSK",
        "──────────────────────",
        "",
    ]
    
    # --- Блок 1: Что сделано (из report-day) ---
    if report_day:
        lines.append(f"🛠 <b>ВЫПОЛНЕННЫЕ РАБОТЫ</b> (из report-day {report_day['date']}):")
        if report_day["works"]:
            for work in report_day["works"]:
                # Убираем markdown
                clean = work.replace("**", "").replace("- ", "• ", 1).strip()
                if len(clean) > 120:
                    clean = clean[:117] + "..."
                lines.append(f"  {clean}")
        else:
            lines.append("  (секция 'Выполненные работы' не найдена)")
        lines.append("")
    else:
        lines.append("🛠 <b>ВЫПОЛНЕННЫЕ РАБОТЫ:</b> report-day за сегодня/вчера не найден")
        lines.append("")
    
    # --- Блок 2: Хроника дня ---
    if chronicle:
        lines.append(f"📜 <b>ХРОНИКА ДНЯ:</b> {chronicle['entries_count']} записей, {chronicle['sessions_count']} сессий")
        if chronicle["last_entries"]:
            lines.append("<b>Последние действия:</b>")
            for entry in chronicle["last_entries"][-3:]:
                clean = entry.replace("**", "").strip()
                if len(clean) > 100:
                    clean = clean[:97] + "..."
                lines.append(f"  {clean}")
        lines.append("")
    else:
        lines.append("📜 <b>ХРОНИКА ДНЯ:</b> Нет записей")
        lines.append("")
    
    # --- Блок 3: Контент ---
    lines.append("📢 <b>КОНТЕНТ:</b>")
    lines.append(f"  VK Подворье: {vk_status['podvorye_posts']} постов")
    lines.append(f"  VK ВезёмЦыплят: {vk_status['vezemcyp_posts']} постов")
    lines.append(f"  Опубликовано: {vk_status['published']}")
    lines.append("")
    
    # --- Блок 4: Дорожная карта ---
    if active_tasks and active_tasks["total"] > 0:
        lines.append(f"📋 <b>ДОРОЖНАЯ КАРТА:</b> {active_tasks['done']}/{active_tasks['total']} выполнено")
    
    lines.append("")
    lines.append("🐥 <i>Анжела Птенчикова: отчёт из report-day + хроника</i>")
    
    report_text = "\n".join(lines)
    
    # === Сохраняем ===
    report_file = os.path.join(REPORTS_DIR_OUT, f"project_report_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"💾 Отчёт: {report_file}")
    
    # === Отправляем ТОЛЬКО Игорю ===
    _send_tg(IGOR_ID, report_text)
    
    return report_text


if __name__ == "__main__":
    run_project_report()
