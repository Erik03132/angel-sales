"""A2A Dispatcher — активный цикл маршрутизации сообщений шины.

Читает pending-сообщения из a2a_protocol.AgentBus, вызывает зарегистрированный
обработчик агента, пишет результат через mark_done, шлёт TG-алерт при ошибке.
Это «оживляет» спящую шину: превращает mailbox в live digital assembly line.

Запуск:
    python3 a2a_dispatcher.py            # вечный цикл (daemon/pm2)
    python3 a2a_dispatcher.py --once     # один проход (cron/тесты)
"""
import os
import sys
import time
import argparse
import traceback
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'), override=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from a2a_protocol import bus, AgentMessage
import a2a_registry as reg
import a2a_agents  # регистрирует реальных агентов
import a2a_governance as gov
import a2a_observability as obs

BOT_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN")
PROXY_URL = os.getenv("TELEGRAM_PROXY")
OWNER_ID = int(os.getenv("OWNER_ID", "176203333"))


def tg_alert(text: str):
    if not BOT_TOKEN:
        return
    import requests
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    proxies = {}
    if PROXY_URL:
        p = PROXY_URL.replace("socks5://", "socks5h://")
        proxies = {"https": p, "http": p}
    try:
        requests.post(url, json={"chat_id": OWNER_ID, "text": text, "parse_mode": "HTML"},
                      proxies=proxies, timeout=15)
    except Exception as e:
        print(f"tg_alert error: {e}")


def handle_message(msg: AgentMessage):
    # --- Governance: подпись / injection / trust ---
    verdict = gov.check_message(msg.to_dict())
    if verdict["status"] == "blocked":
        reason = ", ".join(verdict["reasons"])
        bus.mark_done(msg.id, {"error": f"governance_blocked: {reason}"})
        tg_alert(f"🛡️ A2A BLOCKED <b>{msg.sender}→{msg.receiver}</b>: {reason}")
        obs.end_trace(obs.start_trace(msg.to_dict()), "blocked", error=f"governance:{reason}")
        print(f"[governance] BLOCKED {msg.sender} -> {msg.receiver}: {reason}")
        return
    if verdict["status"] == "warn":
        print(f"[governance] WARN {msg.sender} -> {msg.receiver}: {', '.join(verdict['reasons'])}")

    spec = reg.get_agent(msg.receiver)
    if not spec:
        bus.mark_done(msg.id, {"error": f"no agent registered: {msg.receiver}"})
        tg_alert(f"⚠️ A2A: нет зарегистрированного агента <b>{msg.receiver}</b>")
        return
    if not spec.handler:
        bus.mark_done(msg.id, {"error": f"agent {msg.receiver} has no handler"})
        return

    trace = obs.start_trace(msg.to_dict())
    try:
        result = spec.handler(msg.payload or {})
        bus.mark_done(msg.id, {"ok": True, "result": result})
        obs.end_trace(trace, "ok", result={"ok": True, "result": result})
        print(f"[dispatch] {msg.sender} -> {msg.receiver} ({msg.intent}) OK")
    except Exception as e:
        bus.mark_done(msg.id, {"error": str(e)})
        obs.end_trace(trace, "error", error=str(e))
        tg_alert(f"🔥 A2A dispatch error <b>{msg.receiver}</b>:\n{str(e)}")
        print(traceback.format_exc())


def run_once() -> int:
    processed = 0
    for aid in reg.REGISTRY:
        for msg in bus.get_messages(aid, "pending"):
            handle_message(msg)
            processed += 1
    return processed


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="один проход вместо вечного цикла")
    ap.add_argument("--traces", action="store_true", help="показать сводку observability и выйти")
    args = ap.parse_args()

    print(f"🚌 A2A Dispatcher — зарегистрировано агентов: {len(reg.REGISTRY)}")
    for a in reg.list_agents():
        print(f"   • {a['id']:10s} {a['name']:18s} [{a['project']}] handler={'✅' if a['has_handler'] else '➖'}")

    if args.traces:
        import json as _json
        print("📊 Observability summary:")
        print(_json.dumps(obs.summarize(), ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.once:
        n = run_once()
        print(f"dispatched {n} message(s)")
    else:
        print("🔁 вечный цикл (Ctrl+C для выхода)")
        while True:
            try:
                run_once()
            except Exception as e:
                tg_alert(f"🔥 A2A dispatcher loop error:\n{str(e)}")
                print(traceback.format_exc())
            time.sleep(5)
