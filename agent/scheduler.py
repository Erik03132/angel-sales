"""
Планировщик Анжелочки v4.0 — ЧИСТЫЙ.
Замена cron. Работает как фоновый демон под PM2.

═══════════════════════════════════════════════════
⚠️ УТВЕРЖДЁННЫЕ ОТЧЁТЫ В TG (решение от 12.05.2026):
  ВСЕ ОТЧЁТЫ — ТОЛЬКО ИГОРЮ (176203333)!
  АНДРЕЮ — НИЧЕГО В TG!

  1. 19:00 — Вечерний аудит CRM (скан)
  2. 20:00 — Заботкина: CRM-отчёт (строго по REPORTS_FORMAT.md)
  3. 20:05 — Птенчикова: отчёт по проекту INCUBIRD 2.0 (произвольная форма)
  4. ~03:30 — Заботкина: качество звонков (после ночной транскрипции)
  БОЛЬШЕ НИКАКИХ ОТЧЁТОВ В ТГ!
═══════════════════════════════════════════════════

КЛЮЧЕВЫЕ УЛУЧШЕНИЯ v3.0:
  - PID-lock: не допускает дублей инстансов
  - Heartbeat-файл для внешнего мониторинга
  - Graceful error handling — одна задача не убивает весь планировщик
  - Таймзона-aware (MSK явно)
  - Retry-логика для критических задач (отчёт)

Запуск через PM2:
  pm2 start scheduler.py --name angela-scheduler --interpreter /root/antigravity/ai-eggs/venv/bin/python3
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
VENV_PYTHON = os.path.join(BASE_DIR, "venv", "bin", "python3")
# Фоллбэк: системный python
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable

LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

PID_FILE = os.path.join(LOG_DIR, "scheduler.pid")
LOCK_FILE = os.path.join(LOG_DIR, "scheduler.lock")
HEARTBEAT_FILE = os.path.join(LOG_DIR, "scheduler_heartbeat.json")

# Московское время (UTC+3)
MSK = timezone(timedelta(hours=3))

# Расписание (часы MSK):
DIGEST_HOUR      = 9     # Утренний дайджест Хабра
SCAN_HOUR        = 19    # Вечерний скан CRM
TRANSCRIBE_HOUR  = 3     # Ночная транскрипция звонков (03:00 MSK — после night_audit в 02:00)
REPORT_MAX_RETRIES = 3   # Попыток для отправки отчёта
REPORT_HOUR = 20  # Ежедневный отчёт в 20:00 MSK
MORNING_REPORT_HOUR = 8  # Утренний отчёт ночного аудита (08:00 MSK)
AUTOCALL_HOUR = 9  # Автодозвон за 1 день до поставки (09:00 MSK)


def now_msk():
    """Текущее время в MSK."""
    return datetime.now(MSK)


def log(msg):
    """Логирование с таймштампом MSK."""
    ts = now_msk().strftime("%Y-%m-%d %H:%M:%S MSK")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        log_path = os.path.join(LOG_DIR, "scheduler.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # Логирование не должно ронять процесс


def write_heartbeat(status="alive", last_task=None):
    """Записываем heartbeat для внешнего мониторинга."""
    try:
        data = {
            "status": status,
            "timestamp": now_msk().isoformat(),
            "pid": os.getpid(),
            "last_task": last_task,
        }
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def acquire_lock():
    """Захватываем файловый лок — предотвращаем дубли."""
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd
    except (IOError, OSError):
        log("❌ LOCK FAILED: Другой инстанс планировщика уже запущен!")
        log(f"   Проверьте: cat {LOCK_FILE}")
        sys.exit(1)


def write_pid():
    """Записываем PID-файл."""
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def run_script(name, args=None, timeout=300):
    """Запускает скрипт в subprocess с таймаутом."""
    path = os.path.join(SCRIPT_DIR, name)
    if not os.path.exists(path):
        log(f"  ⚠️ Скрипт не найден: {name}")
        return False

    cmd = [VENV_PYTHON, path]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SCRIPT_DIR,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        if result.returncode == 0:
            log(f"  ✅ {name} завершён успешно")
            if result.stdout and len(result.stdout.strip()) > 0:
                # Логируем последние 3 строки stdout
                for line in result.stdout.strip().split("\n")[-3:]:
                    log(f"     > {line[:200]}")
            return True
        else:
            log(f"  ⚠️ {name} ошибка (код {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-3:]:
                    log(f"     STDERR: {line[:200]}")
            return False
    except subprocess.TimeoutExpired:
        log(f"  ❌ {name} ТАЙМАУТ ({timeout}с)")
        return False
    except Exception as e:
        log(f"  ❌ {name} exception: {type(e).__name__}: {e}")
        return False


def run_with_retry(name, max_retries=3, delay=30, **kwargs):
    """Запускает скрипт с повторами при неудаче."""
    for attempt in range(1, max_retries + 1):
        log(f"  🔄 Попытка {attempt}/{max_retries}: {name}")
        if run_script(name, **kwargs):
            return True
        if attempt < max_retries:
            log(f"  ⏳ Повтор через {delay}с...")
            time.sleep(delay)
    log(f"  ❌ {name}: все {max_retries} попытки неудачны!")
    return False


def task_scan():
    """Задача: Вечерний аудит CRM."""
    log("🔍 ЗАПУСК ВЕЧЕРНЕГО АУДИТА CRM...")
    run_script("bitrix_scanner.py", timeout=120)
    run_script("sync_products.py", timeout=60)
    run_script("proactive_engine.py", timeout=120)
    write_heartbeat("alive", "scan")


def task_report():
    """Задача: Генерация и отправка ежедневного отчёта."""
    log("📋 ГЕНЕРАЦИЯ ЕЖЕДНЕВНОГО ОТЧЁТА...")
    run_script("auto_learner.py", timeout=60)
    # Отчёт — КРИТИЧЕСКАЯ задача, используем retry
    success = run_with_retry(
        "daily_report.py",
        max_retries=REPORT_MAX_RETRIES,
        delay=60,
        timeout=300
    )
    if success:
        log("📨 ОТЧЁТ УСПЕШНО ОТПРАВЛЕН!")
    else:
        log("🚨 ОТЧЁТ НЕ УДАЛОСЬ ОТПРАВИТЬ ПОСЛЕ ВСЕХ ПОПЫТОК!")
        # Попытка уведомить об ошибке
        try:
            _send_error_notification("Ежедневный отчёт не отправлен после 3 попыток")
        except Exception:
            pass

    write_heartbeat("alive", "report")


def task_call_report():
    """Отчёт по качеству звонков — ТОЛЬКО если есть содержание.
    
    HEARTBEAT RULE: Не слать мусорный отчёт с голыми ID без транскрипций.
    """
    log("📞 Проверка звонков (топ-5)...")
    
    # Проверяем, есть ли транскрипты
    shadow_dir = os.path.join(BASE_DIR, "data", "shadow_learning")
    has_transcripts = False
    if os.path.isdir(shadow_dir):
        for f in os.listdir(shadow_dir):
            if f.endswith(".json"):
                has_transcripts = True
                break
    
    if has_transcripts:
        log("  📞 Транскрипты найдены — генерирую отчёт по звонкам")
        call_ok = run_script("call_quality_report.py", timeout=120)
        if call_ok:
            log("  ✅ Отчёт по звонкам отправлен")
        else:
            log("  ⚠️ Отчёт по звонкам не удалось отправить")
    else:
        log("  🤫 Транскриптов нет — отчёт по звонкам пропущен (heartbeat rules)")


def task_autocall():
    """Задача: Автодозвон для подтверждения поставок завтра."""
    log("📞 АВТОДОЗВОН: звонки для поставок завтра...")
    # Напоминание: проверить/обновить WAV для завтрашней даты
    from datetime import timedelta
    tomorrow = (now_msk() + timedelta(days=1)).strftime("%d.%m.%Y")
    _send_error_notification(
        f"📞 Автодозвон запускается!\n"
        f"📅 Поставка: {tomorrow}\n"
        f"🎤 Проверьте актуальность WAV-файла!\n"
        f"Если дата в аудио не совпадает — обновите WAV и запустите вручную."
    )
    run_script("auto_confirm_call.py", timeout=600)
    write_heartbeat("alive", "autocall")




def _send_error_notification(message):
    """Экстренное уведомление при сбоях."""
    import requests
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)
    
    token = os.getenv("ANGELOCHKA_BOT_TOKEN")
    proxy_url = os.getenv("TELEGRAM_PROXY", "")
    owner_id = 176203333  # Игорь

    if not token:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    proxies = {}
    if proxy_url:
        proxy = proxy_url.replace("socks5://", "socks5h://")
        proxies = {"https": proxy, "http": proxy}

    text = f"🚨 SCHEDULER ALERT\n\n{message}\n\n⏰ {now_msk().strftime('%Y-%m-%d %H:%M MSK')}"
    try:
        requests.post(url, json={
            "chat_id": owner_id,
            "text": text,
        }, proxies=proxies, timeout=15)
    except Exception:
        pass


def task_cleanup():
    """Задача: Очистка кэша в полночь."""
    log("♻️ Полночная очистка кэша")
    try:
        from persistent_history import chat_db
        deleted = chat_db.cleanup_old()
        if deleted:
            log(f"🧹 Удалено {deleted} старых записей из chat_history")
    except ImportError:
        pass  # Модуль не установлен — ок
    except Exception as e:
        log(f"⚠️ Очистка chat_history: {e}")


def main():
    # === PID + LOCK ===
    lock_fd = acquire_lock()
    write_pid()

    log("═" * 50)
    log("🕐 ПЛАНИРОВЩИК АНЖЕЛОЧКИ v3.0 (Надёжный)")
    log(f"   PID: {os.getpid()}")
    log(f"   Python: {VENV_PYTHON}")
    log(f"   Расписание: {SCAN_HOUR}:00 (Скан) | {REPORT_HOUR}:00 (Отчёт) | {AUTOCALL_HOUR}:00 (Автодозвон)")
    log("   Таймзона: MSK (UTC+3)")
    log("═" * 50)

    write_heartbeat("started")

    executed_today = set()
    last_heartbeat = 0

    # Graceful shutdown
    def signal_handler(signum, frame):
        log(f"🛑 Получен сигнал {signum}, завершаю работу...")
        write_heartbeat("stopped")
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            now = now_msk()
            today = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute

            # --- УТРЕННИЙ ДАЙДЖЕСТ ХАБРА (09:00 MSK) → ТОЛЬКО Игорю ---
            task_key = f"{today}-habr"
            if hour == DIGEST_HOUR and minute < 5 and task_key not in executed_today:
                log("📰 HABR DIGEST (→ Игорю)...")
                run_script("habr_intelligence.py", timeout=300)
                executed_today.add(task_key)

            # --- УТРЕННИЙ ОТЧЁТ НОЧНОГО АУДИТА (08:00 MSK) → Игорю ---
            # Объединяет: CRM + транскрибация звонков + ночной аудит
            task_key = f"{today}-morning-audit"
            if hour == MORNING_REPORT_HOUR and minute < 5 and task_key not in executed_today:
                log("🌞 UNIFIED MORNING REPORT (CRM + звонки + аудит → Игорю)...")
                run_script("unified_morning_report.py", timeout=120)
                executed_today.add(task_key)

            # --- АВТОДОЗВОН: звонок за 1 день до поставки (09:00 MSK) ---
            task_key = f"{today}-autocall"
            if hour == AUTOCALL_HOUR and minute < 5 and task_key not in executed_today:
                task_autocall()
                executed_today.add(task_key)

            # --- ВЕЧЕРНИЙ АУДИТ CRM (19:00 MSK) ---
            task_key = f"{today}-scan"
            if hour == SCAN_HOUR and minute < 5 and task_key not in executed_today:
                task_scan()
                executed_today.add(task_key)

            # ═══════════════════════════════════════════════
            # ОТЧЁТ 1: Заботкина CRM (20:00 MSK) → ТОЛЬКО Игорю
            # ОТЧЁТ 2: Птенчикова проект (20:05 MSK) → ТОЛЬКО Игорю
            # АНДРЕЮ — НИЧЕГО! (решение от 12.05.2026)
            # ═══════════════════════════════════════════════
            task_key = f"{today}-report"
            if hour == REPORT_HOUR and minute < 5 and task_key not in executed_today:
                task_report()
                # 20:05 — Отчёт Птенчиковой по проекту
                time.sleep(120)
                log("📋 ОТЧЁТ ПТЕНЧИКОВОЙ ПО ПРОЕКТУ INCUBIRD 2.0...")
                run_script("project_report.py", timeout=120)
                executed_today.add(task_key)

            # ═══════════════════════════════════════════════
            # НОЧНАЯ ТРАНСКРИПЦИЯ + ОТЧЁТ 3: качество звонков
            # (03:00 MSK → транскрипция → отчёт по готовности)
            # ═══════════════════════════════════════════════
            task_key = f"{today}-transcribe"
            if hour == TRANSCRIBE_HOUR and minute < 5 and task_key not in executed_today:
                log("📞 ТРАНСКРИПЦИЯ ЗВОНКОВ (вчерашние)...")
                run_script("call_transcriber.py", args=["--days", "1"], timeout=1800)  # 30 мин макс
                run_script("call_learner.py", timeout=300)  # Извлечение фактов
                # ОТЧЁТ 3: Заботкина — качество звонков → ТОЛЬКО Игорю
                log("📞 ОТЧЁТ ПО КАЧЕСТВУ ЗВОНКОВ (Заботкина)...")
                task_call_report()
                executed_today.add(task_key)
                write_heartbeat("alive", "transcribe+quality_report")

            # --- ПОЛНОЧНАЯ ОЧИСТКА (00:00 MSK) ---
            task_key = f"{today}-cleanup"
            if hour == 0 and minute < 5 and task_key not in executed_today:
                log("🌙 Наступил новый день. Сброс задач.")
                executed_today.clear()
                task_cleanup()
                executed_today.add(task_key)

            # --- HEARTBEAT (каждые 5 минут) ---
            current_time = time.time()
            if current_time - last_heartbeat > 300:
                write_heartbeat("alive")
                last_heartbeat = current_time

        except Exception as e:
            # КРИТИЧНО: ловим ВСЕ ошибки, чтобы цикл не умирал
            log(f"🚨 НЕОБРАБОТАННАЯ ОШИБКА В ГЛАВНОМ ЦИКЛЕ: {type(e).__name__}: {e}")
            # Не падаем — продолжаем работать

        time.sleep(60)


if __name__ == "__main__":
    main()
