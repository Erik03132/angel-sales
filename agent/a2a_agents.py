"""Регистрация реальных агентов в шине A2A.

Импорты тяжёлых модулей спрятаны ВНУТРЬ обработчиков, чтобы регистрация
не падала при недоступности зависимостей. Логика: дешево зарегистрировать,
дорого — только при реальном вызове.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2a_registry import agent


@agent("echo", "Echo (demo)", "ai-eggs",
       capabilities=["test.echo"],
       description="Демо-агент: возвращает payload. Для smoke-тестов шины.")
def handle_echo(payload: dict) -> dict:
    return {"echo": payload}


@agent("scanner", "Bitrix Scanner", "ai-eggs",
       capabilities=["crm.scan", "crm.forgotten_deals"],
       description="Сканирует CRM (Битрикс) на забытые сделки и звонки.")
def handle_scanner(payload: dict) -> dict:
    from bitrix_scanner import run_scan
    return run_scan()


@agent("reporter", "Daily Reporter", "ai-eggs",
       capabilities=["report.daily"],
       description="Ежедневный отчёт/KPI.")
def handle_reporter(payload: dict) -> dict:
    from daily_report import run_daily_report
    run_daily_report()
    return {"ok": True}


# ── Кросс-проектные агенты ───────────────────────────────────────────────
# Entrypoint'ы соседних проектов — долгие циклы, поэтому агент делает
# bounded health-пробу через РОДНОЙ venv проекта (без конфликта зависимостей
# ai-eggs). Обработчик — точка расширения под реальные действия (обзвон, отклик).


@agent("levitan", "Levitan Voice Dialer", "levitan",
       capabilities=["voice.health", "crm.health"],
       description="Голосовой обзвон + CRM-обогащение (Mango/Bitrix).")
def handle_levitan(payload: dict) -> dict:
    import subprocess
    import json
    py = "/Users/igorvasin/freelance-2026/projects/levitan/.venv/bin/python3"
    proj = "/Users/igorvasin/freelance-2026/projects/levitan"
    code = (
        "import sys, json; sys.path.insert(0, %r);"
        "from levitan import config;"
        "print(json.dumps({'ok': True, 'mango_configured': bool(config.settings.mango.api_key)}))"
    ) % (proj + "/src",)
    r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                       cwd=proj, timeout=30)
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr.strip()[:500]}
    return json.loads(r.stdout.strip())


@agent("hh", "HH.ru Agent", "hh-ai-agent",
       capabilities=["hh.health"],
       description="Автоотклик на HH.ru (Playwright/Ollama).")
def handle_hh(payload: dict) -> dict:
    import subprocess
    import json
    py = "/Users/igorvasin/freelance-2026/projects/hh-ai-agent/.venv/bin/python3"
    proj = "/Users/igorvasin/freelance-2026/projects/hh-ai-agent"
    code = (
        "import sys, json; sys.path.insert(0, %r);"
        "import config;"
        "print(json.dumps({'ok': True, 'poll_interval_min': config.POLL_INTERVAL_MINUTES}))"
    ) % proj
    r = subprocess.run([py, "-c", code], capture_output=True, text=True,
                       cwd=proj, timeout=30)
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr.strip()[:500]}
    return json.loads(r.stdout.strip())
