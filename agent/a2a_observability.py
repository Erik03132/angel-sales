"""Observability слой A2A-шины («glass-box» трассы).

Аналог observability / execution traces из Gemini Enterprise.
Пишет в data/a2a_mailbox/traces.jsonl структурированные трассы каждого
вызова агента: кто → кому, intent, длительность, статус, ошибка, саммари результата.
Даёт единый обзор активности агентов («unified inbox» для отладки).
"""
import os
import json
import time
from datetime import datetime
from typing import Optional

from a2a_protocol import MAILBOX_DIR

TRACE_FILE = os.path.join(MAILBOX_DIR, "traces.jsonl")
os.makedirs(MAILBOX_DIR, exist_ok=True)


def _summarize_result(result: dict) -> str:
    if not isinstance(result, dict):
        return str(result)[:200]
    if result.get("error"):
        return f"error: {str(result['error'])[:160]}"
    if "result" in result:
        inner = result["result"]
        if isinstance(inner, dict) and "echo" in inner:
            return "echo ok"
        return f"ok: {json.dumps(inner, ensure_ascii=False)[:160]}"
    return "ok"


def start_trace(msg: dict) -> dict:
    return {
        "trace_id": f"tr_{int(time.time()*1000)}_{msg.get('id','?')}",
        "msg_id": msg.get("id"),
        "sender": msg.get("sender"),
        "receiver": msg.get("receiver"),
        "intent": msg.get("intent"),
        "enqueued_at": msg.get("timestamp"),
        "dispatched_at": datetime.now().isoformat(),
        "duration_ms": None,
        "status": "running",
        "error": None,
        "result_summary": None,
    }


def end_trace(trace: dict, status: str, error: Optional[str] = None, result: Optional[dict] = None):
    trace["duration_ms"] = int((time.time() - _parse(trace["dispatched_at"])) * 1000)
    trace["status"] = status
    trace["error"] = error
    trace["result_summary"] = _summarize_result(result) if result is not None else None
    _append(trace)
    return trace


def _parse(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp()
    except Exception:
        return time.time()


def _append(trace: dict):
    try:
        with open(TRACE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    except Exception:
        pass


def get_traces(limit: int = 50, agent: Optional[str] = None) -> list:
    try:
        with open(TRACE_FILE, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    traces = [json.loads(l) for l in lines if l.strip()]
    if agent:
        traces = [t for t in traces if t.get("receiver") == agent or t.get("sender") == agent]
    return traces[-limit:]


def summarize() -> dict:
    traces = get_traces(limit=10000)
    if not traces:
        return {"total": 0}
    by_agent = {}
    errors = 0
    lat = []
    for t in traces:
        a = t.get("receiver", "?")
        by_agent.setdefault(a, {"calls": 0, "errors": 0, "latency_ms": []})
        by_agent[a]["calls"] += 1
        if t.get("status") == "error":
            by_agent[a]["errors"] += 1
            errors += 1
        if t.get("duration_ms") is not None:
            by_agent[a]["latency_ms"].append(t["duration_ms"])
            lat.append(t["duration_ms"])
    return {
        "total": len(traces),
        "errors": errors,
        "avg_latency_ms": int(sum(lat) / len(lat)) if lat else 0,
        "by_agent": {
            a: {
                "calls": v["calls"],
                "errors": v["errors"],
                "avg_latency_ms": int(sum(v["latency_ms"]) / len(v["latency_ms"])) if v["latency_ms"] else 0,
            } for a, v in by_agent.items()
        },
    }
