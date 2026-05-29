"""
🛡️ HEALTH MONITOR v2.0 — Железобетонный мониторинг ВСЕЙ инфраструктуры.

УРОВНИ ЗАЩИТЫ:
  Level 1: PM2 autorestart + crash-loop protection (max_restarts: 10)
  Level 2: Cron watchdog (15 мин) — проверяет heartbeat scheduler'а
  Level 3: Health Monitor v2 (этот скрипт, 30 мин):
           — HTTP health-checks (angela-server, vezem-web)
           — PM2 crash-loop детект для ВСЕХ процессов
           — AUTO-HEAL: перезапуск упавших процессов (до 2 раз/час)
           — TG-алерт Игорю если проблема не решена
           — Экстренная отправка отчёта в 20:30

v2.0 vs v1.0:
  + HTTP health-checks для angela-server и vezem-web
  + Auto-heal: перезапуск упавших процессов
  + Лимит auto-heal (2 раза/час, чтобы не зациклиться)
  + Мониторинг ВСЕХ процессов (а не только scheduler)
  + Подробные алерты с action taken

Crontab:
  */30 * * * * /root/antigravity/ai-eggs/venv/bin/python3 /root/antigravity/ai-eggs/agent/health_monitor.py >> /root/antigravity/ai-eggs/agent/logs/health_monitor.log 2>&1
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

# Правила молчания (вдохновлено OpenClaw HEARTBEAT.md)
from heartbeat_rules import classify_health_issue, should_send

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(AGENT_DIR, "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "data", "daily_reports")
HEARTBEAT_FILE = os.path.join(LOG_DIR, "scheduler_heartbeat.json")
ALERT_COOLDOWN_FILE = os.path.join(LOG_DIR, "last_alert.json")
HEAL_LOG_FILE = os.path.join(LOG_DIR, "auto_heal.json")

# Загружаем .env
from dotenv import load_dotenv

load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY", "")
OWNER_ID = 176203333  # Игорь

MSK = timezone(timedelta(hours=3))

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ═══════════════════════════════════════════════
# КОНФИГУРАЦИЯ МОНИТОРИНГА
# ═══════════════════════════════════════════════

# Все процессы, которые ДОЛЖНЫ быть online
REQUIRED_PROCESSES = [
    "angela-server",
    "angela-bot",
    "ptenchikova-bot",
    "angela-autopilot",
    "angela-scheduler",
    "vezem-web",
]

# HTTP endpoints для проверки
HTTP_CHECKS = {
    "angela-server": {"url": "http://localhost:5000/api/health", "timeout": 5},
    "vezem-web": {"url": "http://localhost:4321/", "timeout": 5},
}

# Лимит auto-heal: максимум N перезапусков в час на процесс
MAX_HEALS_PER_HOUR = 2

# Порог crash-loop: больше N рестартов = проблема
CRASH_LOOP_THRESHOLD = 10


def now_msk():
    return datetime.now(MSK)


def log(msg):
    ts = now_msk().strftime("%Y-%m-%d %H:%M:%S MSK")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


def send_tg_alert(text):
    """Отправляет АЛЕРТ в Telegram Игорю."""
    if not TELEGRAM_TOKEN:
        log("⚠️ Нет TELEGRAM_TOKEN, алерт не отправлен")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        proxy = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": proxy, "http": proxy}

    try:
        resp = requests.post(url, json={
            "chat_id": OWNER_ID,
            "text": text,
            "parse_mode": "HTML",
        }, proxies=proxies, timeout=15)
        if resp.status_code == 200:
            log("📨 Алерт отправлен Игорю")
            return True
        else:
            log(f"⚠️ TG error: {resp.status_code}")
            return False
    except Exception as e:
        log(f"⚠️ TG exception: {e}")
        return False


def should_alert(alert_type, cooldown_minutes=60):
    """Проверяет cooldown — не спамим одинаковые алерты чаще чем раз в N минут."""
    try:
        if os.path.exists(ALERT_COOLDOWN_FILE):
            with open(ALERT_COOLDOWN_FILE, 'r') as f:
                data = json.load(f)
            last_time = data.get(alert_type, "")
            if last_time:
                last_dt = datetime.fromisoformat(last_time)
                if (now_msk() - last_dt).total_seconds() < cooldown_minutes * 60:
                    return False  # Слишком рано для повторного алерта
    except Exception:
        pass
    return True


def record_alert(alert_type):
    """Записываем время алерта для cooldown."""
    try:
        data = {}
        if os.path.exists(ALERT_COOLDOWN_FILE):
            with open(ALERT_COOLDOWN_FILE, 'r') as f:
                data = json.load(f)
        data[alert_type] = now_msk().isoformat()
        with open(ALERT_COOLDOWN_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ═══════════════════════════════════════════════
# AUTO-HEAL: перезапуск упавших процессов
# ═══════════════════════════════════════════════

def _load_heal_log():
    """Загружает журнал auto-heal."""
    try:
        if os.path.exists(HEAL_LOG_FILE):
            with open(HEAL_LOG_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_heal_log(data):
    """Сохраняет журнал auto-heal."""
    try:
        with open(HEAL_LOG_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def can_auto_heal(process_name):
    """Проверяет, можно ли ещё лечить этот процесс (лимит 2/час)."""
    heal_log = _load_heal_log()
    key = f"{process_name}_{now_msk().strftime('%Y%m%d_%H')}"
    count = heal_log.get(key, 0)
    return count < MAX_HEALS_PER_HOUR


def do_auto_heal(process_name):
    """Перезапускает процесс через PM2 и записывает в журнал.

    Логика:
    - Если процесс есть в PM2 но упал → pm2 restart
    - Если процесс НЕ НАЙДЕН в PM2 → pm2 start ecosystem.config.cjs (Level 2 resurrect)

    Возвращает (success, message).
    """
    heal_log = _load_heal_log()
    key = f"{process_name}_{now_msk().strftime('%Y%m%d_%H')}"
    heal_count = heal_log.get(key, 0)

    if heal_count >= MAX_HEALS_PER_HOUR:
        return False, f"лимит auto-heal исчерпан ({heal_count}/{MAX_HEALS_PER_HOUR} в этот час)"

    # Определяем — процесс есть в PM2 или вообще не найден
    processes = _get_pm2_processes()
    is_in_pm2 = processes and any(p.get("name") == process_name for p in (processes or []))

    if is_in_pm2:
        # Просто упал — pm2 restart
        log(f"🔧 AUTO-HEAL [restart]: {process_name}...")
        cmd = ["pm2", "restart", process_name]
    else:
        # Не найден в PM2 — воскрешаем через ecosystem
        log(f"🔧 AUTO-HEAL [resurrect]: {process_name} не в PM2, запускаю через ecosystem...")
        cmd = _build_resurrect_cmd(process_name)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        time.sleep(10)
        ok, status = _check_pm2_process(process_name)
        heal_log[key] = heal_count + 1
        _save_heal_log(heal_log)
        if ok:
            # Сохраняем dump чтобы следующий reboot тоже поднял
            subprocess.run(["pm2", "save"], capture_output=True, timeout=10)
            log(f"✅ AUTO-HEAL: {process_name} восстановлен! ({status})")
            return True, "восстановлен, работает"
        else:
            log(f"⚠️ AUTO-HEAL: {process_name} запущен, но статус: {status}")
            return False, f"запущен, но {status}"
    except Exception as e:
        return False, f"exception: {e}"


def _build_resurrect_cmd(process_name):
    """Строит команду для старта упавшего процесса через ecosystem."""
    # Список ecosystem файлов в порядке приоритета
    ecosystems = [
        "/root/antigravity/ecosystem.config.cjs",
        "/root/antigravity/ecosystem.config.js",
        "/root/antigravity/ai-eggs/agent/ecosystem.config.cjs",
        "/root/antigravity/ai-eggs/agent/ecosystem.config.js",
    ]

    # Ищем .cjs — если только .js, копируем в .cjs на лету
    for eco in ecosystems:
        if eco.endswith(".cjs") and os.path.exists(eco):
            return ["pm2", "start", eco]
        if eco.endswith(".js") and os.path.exists(eco):
            cjs = eco.replace(".js", ".cjs")
            try:
                import shutil
                shutil.copy2(eco, cjs)
                log(f"  Скопировал {eco} → {cjs}")
            except Exception:
                pass
            return ["pm2", "start", cjs if os.path.exists(cjs) else eco]

    # Fallback — pm2 resurrect из dump
    log("  ⚠️ Ecosystem не найден, пробую pm2 resurrect...")
    return ["pm2", "resurrect"]


# ═══════════════════════════════════════════════
# ПРОВЕРКИ
# ═══════════════════════════════════════════════

def _get_pm2_processes():
    """Получает список всех PM2 процессов."""
    try:
        result = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def _check_pm2_process(process_name):
    """Проверяет конкретный процесс в PM2. Возвращает (ok, message)."""
    processes = _get_pm2_processes()
    if processes is None:
        return False, "PM2 не отвечает"

    for p in processes:
        if p.get("name") == process_name:
            status = p.get("pm2_env", {}).get("status", "unknown")
            restarts = p.get("pm2_env", {}).get("restart_time", 0)
            uptime = p.get("pm2_env", {}).get("pm_uptime", 0)

            if status == "online":
                if restarts > CRASH_LOOP_THRESHOLD:
                    return False, f"online но {restarts}x рестартов (crash-loop)"
                return True, f"online, {restarts}x рестартов"
            elif status == "stopped":
                return False, f"stopped ({restarts}x рестартов)"
            elif status == "errored":
                return False, f"errored ({restarts}x рестартов)"
            else:
                return False, f"статус: {status} ({restarts}x рестартов)"

    return False, "НЕ НАЙДЕН в PM2"


def check_all_pm2_processes():
    """Проверяет ВСЕ обязательные процессы в PM2."""
    results = {}
    for name in REQUIRED_PROCESSES:
        ok, msg = _check_pm2_process(name)
        results[name] = {"ok": ok, "msg": msg}
    return results


def check_http_endpoints():
    """Проверяет HTTP health-endpoints."""
    results = {}
    for name, cfg in HTTP_CHECKS.items():
        try:
            resp = requests.get(cfg["url"], timeout=cfg["timeout"])
            if resp.status_code == 200:
                results[name] = {"ok": True, "msg": "HTTP 200 OK"}
            else:
                results[name] = {"ok": False, "msg": f"HTTP {resp.status_code}"}
        except requests.exceptions.ConnectionError:
            results[name] = {"ok": False, "msg": f"Connection refused ({cfg['url']})"}
        except requests.exceptions.Timeout:
            results[name] = {"ok": False, "msg": f"Timeout ({cfg['timeout']}s)"}
        except Exception as e:
            results[name] = {"ok": False, "msg": f"{type(e).__name__}: {e}"}
    return results


def check_heartbeat():
    """Проверка: heartbeat свежий (< 10 минут)?"""
    if not os.path.exists(HEARTBEAT_FILE):
        return False, "heartbeat файл не найден"

    try:
        mtime = os.path.getmtime(HEARTBEAT_FILE)
        age_seconds = datetime.now().timestamp() - mtime
        age_minutes = age_seconds / 60

        with open(HEARTBEAT_FILE, 'r') as f:
            data = json.load(f)
        status = data.get("status", "unknown")

        if age_minutes > 10:
            return False, f"heartbeat устарел: {age_minutes:.0f} мин назад (status={status})"
        return True, f"свежий ({age_minutes:.0f} мин назад, status={status})"
    except Exception as e:
        return False, f"heartbeat error: {e}"


def check_today_report():
    """Проверка: есть ли сегодняшний отчёт?"""
    today = now_msk().strftime("%Y%m%d")
    report_file = os.path.join(REPORTS_DIR, f"report_{today}.txt")
    if os.path.exists(report_file):
        size = os.path.getsize(report_file)
        return True, f"report_{today}.txt ({size} bytes)"
    return False, f"report_{today}.txt НЕ НАЙДЕН"


# ═══════════════════════════════════════════════
# ЭКСТРЕННАЯ ОТПРАВКА ОТЧЁТА (Level 3)
# ═══════════════════════════════════════════════

def emergency_send_report():
    """Level 3: Если в 20:30 отчёт не ушёл — отправляем сами."""
    log("🚨 EMERGENCY: Отчёт не отправлен! Запускаю экстренную отправку...")
    venv_python = os.path.join(BASE_DIR, "venv", "bin", "python3")
    if not os.path.exists(venv_python):
        venv_python = sys.executable

    report_script = os.path.join(AGENT_DIR, "daily_report.py")
    try:
        result = subprocess.run(
            [venv_python, report_script],
            capture_output=True, text=True,
            timeout=300, cwd=AGENT_DIR
        )
        if result.returncode == 0:
            log("✅ EMERGENCY: Отчёт отправлен!")
            return True
        else:
            log(f"❌ EMERGENCY: Ошибка: {result.stderr[:300]}")
            return False
    except Exception as e:
        log(f"❌ EMERGENCY exception: {e}")
        return False


# ═══════════════════════════════════════════════
# ГЛАВНАЯ ПРОВЕРКА v2.0
# ═══════════════════════════════════════════════

def run_health_check():
    now = now_msk()
    hour = now.hour
    log("=" * 60)
    log(f"🏥 HEALTH CHECK v2.0 ({now.strftime('%H:%M MSK')})")

    issues = []
    healed = []

    # ──────────────────────────────────────────
    # 1. PM2 процессы — ВСЕ обязательные
    # ──────────────────────────────────────────
    log("  📋 PM2 процессы:")
    pm2_results = check_all_pm2_processes()
    for name, result in pm2_results.items():
        icon = "✅" if result["ok"] else "❌"
        log(f"    {icon} {name}: {result['msg']}")

        if not result["ok"]:
            # Пробуем AUTO-HEAL
            if can_auto_heal(name):
                heal_ok, heal_msg = do_auto_heal(name)
                if heal_ok:
                    healed.append(f"🔧 {name}: {heal_msg}")
                    continue  # Проблема решена
                else:
                    issues.append(f"❌ {name}: {result['msg']} (auto-heal: {heal_msg})")
            else:
                issues.append(f"❌ {name}: {result['msg']} (auto-heal лимит исчерпан)")

    # ──────────────────────────────────────────
    # 2. HTTP health-checks
    # ──────────────────────────────────────────
    log("  🌐 HTTP endpoints:")
    http_results = check_http_endpoints()
    for name, result in http_results.items():
        icon = "✅" if result["ok"] else "❌"
        log(f"    {icon} {name}: {result['msg']}")

        if not result["ok"]:
            # Если PM2 показывает online, но HTTP не отвечает — рестартим
            pm2_status = pm2_results.get(name, {})
            if pm2_status.get("ok"):
                log(f"    ⚠️ {name}: PM2=online, но HTTP не отвечает. Перезапуск...")
                if can_auto_heal(name):
                    heal_ok, heal_msg = do_auto_heal(name)
                    if heal_ok:
                        healed.append(f"🔧 {name}: HTTP был down, перезапущен")
                        continue
                    else:
                        issues.append(f"❌ {name}: HTTP down, auto-heal: {heal_msg}")
                else:
                    issues.append(f"❌ {name}: HTTP down (auto-heal лимит)")
            else:
                # PM2 уже упал — проблема зарегистрирована в секции 1
                pass

    # ──────────────────────────────────────────
    # 3. Heartbeat scheduler'а
    # ──────────────────────────────────────────
    ok, msg = check_heartbeat()
    log(f"  {'✅' if ok else '❌'} Heartbeat: {msg}")
    if not ok:
        issues.append(f"❌ Heartbeat: {msg}")

    # ──────────────────────────────────────────
    # 4. Отчёт дня (только в окне 20:00-21:00)
    # ──────────────────────────────────────────
    if 20 <= hour <= 21:
        ok, msg = check_today_report()
        log(f"  {'✅' if ok else '❌'} Отчёт дня: {msg}")
        if not ok:
            issues.append(f"❌ Отчёт: {msg}")
            # Экстренная отправка только в окне 20:25-21:00
            if hour == 20 and now.minute >= 25:
                emergency_send_report()

    # ──────────────────────────────────────────
    # ИТОГ + HEARTBEAT RULES (молчим если всё ок)
    # ──────────────────────────────────────────
    severity = classify_health_issue(len(issues), len(healed))
    
    if healed:
        log(f"  🔧 AUTO-HEAL: {len(healed)} процессов восстановлено:")
        for h in healed:
            log(f"    {h}")

    if issues:
        log(f"  🚨 НЕРЕШЁННЫЕ ПРОБЛЕМЫ: {len(issues)}")

    # РЕШЕНИЕ: отправлять ли алерт?
    if not should_send(severity, hour):
        if severity == "SILENT":
            log("  ✅ ВСЁ В ПОРЯДКЕ — молчим (heartbeat rules)")
        else:
            log(f"  🌙 Тихие часы ({hour}:00 MSK) — алерт отложен до утра")
        log("=" * 60)
        return

    # Отправляем алерт (severity позволяет)
    if issues:
        alert_key = "health_v2_" + now.strftime("%Y%m%d_%H")
        if should_alert(alert_key, cooldown_minutes=120):
            issues_text = "\n".join(issues)
            healed_text = "\n".join(healed) if healed else "—"

            alert_text = (
                f"🚨 <b>HEALTH MONITOR v2.1 ALERT</b>\n"
                f"⏰ {now.strftime('%Y-%m-%d %H:%M MSK')}\n"
                f"{'─' * 30}\n\n"
                f"<b>❌ Проблемы ({len(issues)}):</b>\n"
                f"{issues_text}\n\n"
                f"<b>🔧 Auto-heal ({len(healed)}):</b>\n"
                f"{healed_text}\n\n"
                f"🔧 Проверь: <code>ssh root@72.56.38.19</code>"
            )
            send_tg_alert(alert_text)
            record_alert(alert_key)
        else:
            log("  ⏳ Cooldown — алерт уже был недавно")
    elif healed:
        log(f"  ✅ Проблемы решены auto-heal'ом ({len(healed)} восстановлено)")
        # INFO о починке — НЕ ночью, cooldown 4 часа
        alert_key = "heal_info_" + now.strftime("%Y%m%d")
        if should_alert(alert_key, cooldown_minutes=240):
            healed_text = "\n".join(healed)
            info_text = (
                f"🔧 <b>AUTO-HEAL</b>\n"
                f"⏰ {now.strftime('%H:%M MSK')}\n"
                f"{', '.join(healed)}\n"
                f"✅ Всё работает."
            )
            send_tg_alert(info_text)
            record_alert(alert_key)

    log("=" * 60)


if __name__ == "__main__":
    run_health_check()
