"""Smoke-тест живой A2A шины: roundtrip call_agent -> dispatcher -> mark_done.

Диспетчер крутится в фоновом потоке, call_agent публикует request_data к
demo-агенту 'echo' и ждёт результат. Проверяет, что шина реально живая.

    python3 a2a_smoke.py
"""
import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import a2a_agents  # регистрирует агентов (в т.ч. echo)
from a2a_protocol import call_agent
from a2a_dispatcher import run_once


def _loop():
    while True:
        run_once()
        time.sleep(0.2)


if __name__ == "__main__":
    t = threading.Thread(target=_loop, daemon=True)
    t.start()

    print("→ публикую request_data(echo) и жду ответ...")
    res = call_agent("smoke", "echo", "ping", {"hello": "world"}, timeout=15, poll=0.5)
    print("← RESULT:", res)

    ok = res.get("result", {}).get("echo", {}).get("hello") == "world"
    print("✅ ШИНА ЖИВАЯ" if ok else "❌ ШИНА НЕ ОТВЕТИЛА")
    sys.exit(0 if ok else 1)
