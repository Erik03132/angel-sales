#!/usr/bin/env python3
"""
morning_audit_report.py — Утренняя отправка отчёта ночного аудита в Telegram.
Запускается ежедневно в 08:00 MSK.

Отправляет Игорю (176203333):
1. Результаты ночного аудита (ruff ошибки, Claude анализ)
2. Dream report (паттерны за 3 дня)
3. Краткую сводку по проекту
"""
import glob
import os
from datetime import datetime

import requests
from dotenv import load_dotenv

# Загрузка .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(BASE_DIR, "..", "reports")
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
OWNER_ID = 176203333  # Игорь
PROXY_URL = os.getenv("TELEGRAM_PROXY")

# Прокси
proxies = {}
if PROXY_URL:
    proxy = PROXY_URL.replace("socks5://", "socks5h://")
    proxies = {"https": proxy, "http": proxy}


def find_latest_night_audit():
    """Находит последний отчёт ночного аудита."""
    pattern = os.path.join(REPORTS_DIR, "night_audit_ai-eggs_*.md")
    files = sorted(glob.glob(pattern))
    if files:
        return files[-1]
    return None


def find_latest_dream():
    """Находит последний dream report."""
    pattern = os.path.join(BASE_DIR, "..", "dreams", "dream_*.md")
    files = sorted(glob.glob(pattern))
    if files:
        return files[-1]
    return None


def read_file_preview(filepath, max_lines=50):
    """Читает первые N строк файла."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:max_lines]
            return ''.join(lines)
    except Exception as e:
        return f"⚠️ Ошибка чтения: {e}"


def parse_audit_summary(audit_text):
    """Извлекает ключевые метрики из аудита."""
    summary = []
    
    # Ищем таблицу с итогами
    if "📋 Итоговая сводка" in audit_text:
        start = audit_text.find("📋 Итоговая сводка")
        end = audit_text.find("\n\n", start + 50)
        if end == -1:
            end = start + 500
        summary.append(audit_text[start:end])
    
    # Ищем ошибки ruff
    if "ruff ошибок" in audit_text:
        for line in audit_text.split('\n'):
            if "ruff ошибок" in line or "Критических" in line:
                summary.append(line.strip())
    
    return '\n'.join(summary[:10]) if summary else "Нет данных"


def send_telegram(chat_id, text, parse_mode="HTML"):
    """Отправка в Telegram."""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN не задан")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        # Разбиваем на части если > 4000 символов
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        
        for i, part in enumerate(parts):
            resp = requests.post(url, json={
                "chat_id": chat_id,
                "text": part,
                "parse_mode": parse_mode
            }, proxies=proxies, timeout=30)
            
            if resp.status_code == 200:
                print(f"✅ Часть {i+1}/{len(parts)} отправлена")
            else:
                print(f"⚠️ Telegram error: {resp.status_code}")
                return False
        
        return True
    except Exception as e:
        print(f"⚠️ Send error: {e}")
        return False


def build_morning_report():
    """Собирает утренний отчёт."""
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    
    # Находим отчёты
    audit_file = find_latest_night_audit()
    dream_file = find_latest_dream()
    
    lines = [
        f"🌞 <b>УТРЕННИЙ ОТЧЁТ — {now}</b>",
        "",
        "══════════════════════════════════════════",
        "",
    ]
    
    # Ночной аудит
    if audit_file:
        audit_text = read_file_preview(audit_file, 80)
        audit_summary = parse_audit_summary(audit_text)
        
        lines.extend([
            "🌙 <b>НОЧНОЙ АУДИТ (02:00 MSK)</b>",
            f"Файл: <code>{os.path.basename(audit_file)}</code>",
            "",
            audit_summary,
            "",
        ])
    else:
        lines.extend([
            "🌙 <b>НОЧНОЙ АУДИТ</b>",
            "⚠️ Отчёт не найден",
            "",
        ])
    
    # Dream report
    if dream_file:
        dream_text = read_file_preview(dream_file, 40)
        
        lines.extend([
            "══════════════════════════════════════════",
            "",
            "🌙 <b>DREAM REPORT (паттерны за 3 дня)</b>",
            f"Файл: <code>{os.path.basename(dream_file)}</code>",
            "",
            dream_text[:1500] + "..." if len(dream_text) > 1500 else dream_text,
            "",
        ])
    
    # Призыв к действию
    lines.extend([
        "══════════════════════════════════════════",
        "",
        "🚀 <b>План на сегодня:</b>",
        "1. Исправить критические ошибки из ночного аудита",
        "2. Проверить транскрибацию звонков",
        "3. Обновить chp.md",
        "",
        "🤖 <i>Отчёт собран morning_audit_report.py</i>",
    ])
    
    return '\n'.join(lines)


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"🌞 MORNING AUDIT REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")
    
    # Генерация отчёта
    report = build_morning_report()
    
    # Отправка Игорю
    print("📤 Отправка в Telegram...")
    send_telegram(OWNER_ID, report)
    
    print("\n✅ Готово!")
