"""
Планировщик Анжелочки — замена cron.
Работает как фоновый демон, не зависит от терминала.
Расписание:
  - Сканирование Bitrix: 08:00, 11:00, 14:00, 17:00
  - Ежедневный отчёт: 20:00
Запуск: bash manage_angela.sh start (уже включён)
"""
import time
import subprocess
import sys
import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(os.path.dirname(SCRIPT_DIR), "venv", "bin", "python3")
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Расписание:
SCAN_HOUR = 19                   # Вечерний скан CRM (один раз в день)
REPORT_HOUR = 20                 # Вечерний отчёт

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(os.path.join(LOG_DIR, "scheduler.log"), "a") as f:
        f.write(line + "\n")

def run_script(name, args=None):
    """Запускает скрипт в subprocess."""
    path = os.path.join(SCRIPT_DIR, name)
    cmd = [VENV_PYTHON, path]
    if args:
        cmd.extend(args)
        
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300, # Увеличил таймаут для глубокого скана
            cwd=SCRIPT_DIR
        )
        if result.returncode == 0:
            log(f"  ✅ {name} завершён")
            return True
        else:
            log(f"  ⚠️ {name} ошибка: {result.stderr[:200]}")
    except Exception as e:
        log(f"  ❌ {name} exception: {e}")
    return False

def main():
    log("🕐 ПЛАНИРОВЩИК АНЖЕЛОЧКИ v2.1 (Оптимизированный)")
    log(f"   Ежедневный цикл: {SCAN_HOUR}:00 (Скан) -> {REPORT_HOUR}:00 (Отчёт)")
    
    executed_today = set()
    
    while True:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hour = now.hour
        minute = now.minute

        # --- ГЛАВНЫЙ ЦИКЛ (в 19:00) ---
        task_main = f"{today}-main-focus"
        if hour == SCAN_HOUR and minute < 5 and task_main not in executed_today:
            log(f"🔍 ЗАПУСК ВЕЧЕРНЕГО АУДИТА...")
            run_script("bitrix_scanner.py")
            run_script("sync_products.py")
            run_script("proactive_engine.py")
            executed_today.add(task_main)
        
        # --- DAILY REPORT (в 20:00) ---
        task_report = f"{today}-report"
        if hour == REPORT_HOUR and minute < 5 and task_report not in executed_today:
            log(f"📋 ГЕНЕРАЦИЯ ОТЧЁТА...")
            run_script("auto_learner.py")    
            run_script("daily_report.py")    
            executed_today.add(task_report)
        
        # Чистим кэш раз в день (в 00:00)
        if hour == 0 and minute < 5:
            executed_today.clear()
            log("♻️ Кэш задач очищен")
            # Очистка старой облачной истории (30+ дней)
            try:
                from persistent_history import chat_db
                deleted = chat_db.cleanup_old()
                if deleted:
                    log(f"🧹 Удалено {deleted} старых записей из chat_history")
            except Exception as e:
                log(f"⚠️ Очистка chat_history: {e}")
        
        time.sleep(60)

if __name__ == "__main__":
    main()
