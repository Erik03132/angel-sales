"""Autopilot v4 — оркестратор рутины поверх A2A-шины.

Вместо прямых вызовов Autopilot ПУБЛИКУЕТ задачи в шину; диспетчер
(pm2 a2a-dispatcher) их исполняет и возвращает результаты через call_agent.
Autopilot только планирует расписание и сводит отчёты владельцу в TG.

Расписание (время сервера = MSK):
  09:00 — Утренняя рутина: reporter + scanner + health всех агентов → сводка.
  21:00 — Вечерний аудит: health всех агентов → краткая сводка.

Запуск: python3 autopilot.py            # вечный цикл (pm2 a2a-autopilot)
        python3 autopilot.py --once     # одна утренняя рутина (для тестов)
"""
import os
import sys
import time
import argparse
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'), override=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import a2a_agents  # регистрирует агентов в шине
from a2a_protocol import call_agent, delegate_task
import a2a_registry as reg

BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY")
OWNER_ID = int(os.getenv("OWNER_ID", "176203333"))


def send_to_owner(text, parse_mode="HTML"):
    if not BOT_TOKEN:
        print("⚠️ BOT_TOKEN не задан, пропускаю отправку")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        p = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": p, "http": p}
    try:
        requests.post(url, json={"chat_id": OWNER_ID, "text": text, "parse_mode": parse_mode},
                      proxies=proxies, timeout=15)
    except Exception as e:
        print(f"⚠️ TG send error: {e}")


def health_check_all() -> dict:
    """Прозванивает всех зарегистрированных агентов через шину."""
    results = {}
    for aid in reg.REGISTRY:
        try:
            r = call_agent("autopilot", aid, "health", params={"probe": True},
                           timeout=30, poll=1)
            err = r.get("error") if isinstance(r, dict) else "bad_response"
            results[aid] = {"ok": err is None, "detail": r if err is None else err}
        except Exception as e:
            results[aid] = {"ok": False, "detail": str(e)}
    return results


def morning_routine(is_startup=False):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"🌅 Утренняя рутина ({'старт' if is_startup else 'по расписанию'}) — {now}")

    # 1) Делегируем тяжёлые задачи диспетчеру (асинхронно, не ждём)
    delegate_task("autopilot", "reporter", "daily_report")
    delegate_task("autopilot", "scanner", "crm_scan")

    # 2) Health-check всех агентов (синхронно через шину)
    health = health_check_all()
    alive = [a for a, v in health.items() if v["ok"]]
    dead = [a for a, v in health.items() if not v["ok"]]

    lines = [f"🌅 <b>Утренняя рутина</b> — {now}"]
    lines.append(f"🤖 Агентов в шине: {len(reg.REGISTRY)} | живых: {len(alive)} | не отвечают: {len(dead)}")
    if dead:
        lines.append("⚠️ <b>Не отвечают:</b> " + ", ".join(f"{a} ({health[a]['detail']})" for a in dead))
    else:
        lines.append("✅ Все агенты отвечают")
    lines.append("📊 reporter + scanner запущены (ежедневный отчёт + скан CRM).")

    send_to_owner("\n".join(lines))
    print(f"[autopilot] рутина завершена: живых {len(alive)}/{len(reg.REGISTRY)}")


def evening_routine():
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"🌙 Вечерний аудит — {now}")
    health = health_check_all()
    dead = [a for a, v in health.items() if not v["ok"]]
    msg = f"🌙 <b>Вечерний аудит</b> — {now}\n"
    msg += (f"✅ Все {len(reg.REGISTRY)} агентов живы" if not dead
            else f"⚠️ Не отвечают: {', '.join(dead)}")
    send_to_owner(msg)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="одна утренняя рутина и выход")
    args = ap.parse_args()

    print("🚀 A2A Autopilot v4 — оркестратор рутины")
    print(f"   Зарегистрировано агентов в шине: {len(reg.REGISTRY)}")
    print(f"   Время сервера: {datetime.now().strftime('%H:%M %Z')}")

    if args.once:
        morning_routine(is_startup=True)
        print("✅ --once завершён")
    else:
        # Лёгкий time-based планировщик без внешних зависимостей.
        morning_done = evening_done = None  # даты последнего запуска
        morning_routine(is_startup=True)
        morning_done = datetime.now().date()
        while True:
            now = datetime.now()
            today = now.date()
            if now.hour == 9 and morning_done != today:
                morning_routine()
                morning_done = today
            elif now.hour == 21 and evening_done != today:
                evening_routine()
                evening_done = today
            time.sleep(60)
