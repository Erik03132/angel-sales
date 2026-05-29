# ═══════════════════════════════════════════════════════════════
# HEARTBEAT RULES v1.0 — Правила молчания Анжелочки
# ═══════════════════════════════════════════════════════════════
#
# ЗОЛОТОЕ ПРАВИЛО: Молчи когда всё ок. Пиши ТОЛЬКО когда нужно внимание.
#
# Вдохновлено: OpenClaw HEARTBEAT.md принципом
# "Ночью без срочности не пиши. CRITICAL — ВСЕГДА."
#
# Используется: health_monitor.py, scheduler.py, daily_report.py,
#               call_quality_report.py
# ═══════════════════════════════════════════════════════════════

# ──────────────────────────────────
# ТИХИЕ ЧАСЫ (не беспокоить)
# ──────────────────────────────────
QUIET_HOURS_START = 22    # 22:00 MSK — начало тишины
QUIET_HOURS_END = 7       # 07:00 MSK — конец тишины

# ──────────────────────────────────
# УРОВНИ СЕРЬЁЗНОСТИ
# ──────────────────────────────────
# CRITICAL — сайт упал, данные потеряны → пиши ВСЕГДА, даже ночью
# WARNING  — процесс упал но вылечен → пиши ТОЛЬКО в рабочие часы
# INFO     — отчёт, дайджест → пиши ТОЛЬКО по расписанию, не ночью
# SILENT   — всё ок, heartbeat alive → НИКОГДА не пиши

# ──────────────────────────────────
# ПРАВИЛА ОТПРАВКИ
# ──────────────────────────────────
# 1. Отчёт — ОДИН раз в день, в рабочее время (19:00-21:00)
# 2. Health Monitor — молчит если всё ок
# 3. Call Quality — ТОЛЬКО если есть содержание (транскрипт)
# 4. Алерты — cooldown 2 часа (не спамить одну проблему)
# 5. Ночью (22-07) — ТОЛЬКО CRITICAL (сайт упал)
# 6. Не повторять уже сообщённое

# ──────────────────────────────────
# КОМУ ОТПРАВЛЯТЬ
# ──────────────────────────────────
# Андрей (ADMIN) — ТОЛЬКО готовый ежедневный отчёт
# Игорь (OWNER) — алерты, копия отчёта, дебаг
# НИКОГДА не слать Андрею: алерты, мусорные отчёты, health monitor


def is_quiet_hours(hour):
    """Проверяет, попадает ли час в тихое время (22:00 - 07:00 MSK)."""
    if QUIET_HOURS_START > QUIET_HOURS_END:
        # Ночной диапазон: 22-23, 0-6
        return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END
    return QUIET_HOURS_START <= hour < QUIET_HOURS_END


def should_send(severity, hour):
    """Решает, нужно ли отправлять сообщение.
    
    Args:
        severity: "CRITICAL", "WARNING", "INFO", "SILENT"
        hour: текущий час MSK (0-23)
    
    Returns:
        bool: True = отправить, False = промолчать
    """
    if severity == "SILENT":
        return False
    if severity == "CRITICAL":
        return True  # Всегда, даже ночью
    if is_quiet_hours(hour):
        return False  # Ночью — только CRITICAL
    return True  # Днём — WARNING и INFO разрешены


def should_send_report(hour):
    """Можно ли отправлять ежедневный отчёт в это время?
    
    Окно отправки: 19:00 - 21:00 MSK.
    За пределами — не отправлять (и не пытаться экстренно).
    """
    return 19 <= hour <= 21


def classify_health_issue(issues_count, healed_count):
    """Классифицирует серьёзность по результатам health check.
    
    Returns:
        severity: "CRITICAL", "WARNING", "SILENT"
    """
    if issues_count > 0:
        return "CRITICAL"  # Есть нерешённые проблемы
    if healed_count > 0:
        return "WARNING"   # Проблемы были, но решены
    return "SILENT"        # Всё ок — молчим
