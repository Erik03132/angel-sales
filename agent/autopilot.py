import os
import sys
import time
import schedule
import requests
from datetime import datetime

# Загружаем .env (как это делает tg_bot.py)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Добавляем папку routines в путь
sys.path.insert(0, os.path.dirname(__file__))
from routines import system_check

# Конфиг Телеграма — берём ПРАВИЛЬНОЕ имя переменной
BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID", "176203333")
PROXY = os.getenv("TELEGRAM_PROXY")

def send_to_admin(text):
    """Отправить сообщение админу через Telegram бота Анжелочки."""
    if not BOT_TOKEN:
        print("❌ ANGELOCHKA_BOT_TOKEN не найден в .env!")
        return False
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    proxies = {}
    if PROXY:
        proxies = {"https": PROXY, "http": PROXY}
    
    try:
        resp = requests.post(
            url,
            json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "Markdown"},
            proxies=proxies,
            timeout=10
        )
        if resp.status_code == 200:
            print(f"✅ Отчёт отправлен в Telegram (Admin ID: {ADMIN_ID})")
            return True
        else:
            print(f"❌ Telegram API ошибка: {resp.status_code} — {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Не удалось отправить в Telegram: {e}")
        return False

def get_timed_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Доброе утро"
    if 12 <= hour < 18: return "Добрый день"
    if 18 <= hour < 23: return "Добрый вечер"
    return "Доброй ночи"

def morning_job(is_startup=False):
    """Утренняя рутина или отчет о запуске."""
    status = "запущена" if is_startup else "по расписанию"
    print(f"🌅 Запуск рутины ({status})...")
    report = system_check.run_check()
    
    if is_startup:
        greeting = "🐣 Система перезагружена и готова к работе!"
    else:
        greeting = f"🐣 {get_timed_greeting()}, бро!"
        
    send_to_admin(f"{greeting}\n\n{report}")

def evening_job():
    """Вечерняя рутина: итоги дня."""
    print("🌙 Запуск вечернего отчёта...")
    report = system_check.run_check()
    send_to_admin(f"🌙 Бро, день закончен.\n\n{report}\n\nОтдыхай, завтра продолжим!")

# Расписание
schedule.every().day.at("09:00").do(morning_job)
schedule.every().day.at("21:00").do(evening_job)

if __name__ == "__main__":
    print("🚀 Автопилот Antigravity запущен...")
    print(f"   BOT_TOKEN: {'✅ Найден' if BOT_TOKEN else '❌ НЕ НАЙДЕН'}")
    print(f"   ADMIN_ID: {ADMIN_ID}")
    print(f"   PROXY: {'✅ ' + PROXY[:20] + '...' if PROXY else '❌ Нет'}")
    
    # Тестовый запуск при старте (с нейтральным сообщением)
    morning_job(is_startup=True)
    
    while True:
        schedule.run_pending()
        time.sleep(60)
