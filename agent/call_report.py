#!/usr/bin/env python3
"""
call_report.py — Отчёт по автодозвону Mango Office.
Поддерживает два режима:
  1. register-based (auto_confirm_call.py) — через mango-webhook 'register' события
  2. callback-based (mango_autocall.py / mango_outbound_caller.py) — через 'events/result/callback'

Запуск:
    python3 call_report.py --mode register --since 10:00 --until 11:00
    python3 call_report.py --mode callback --since 13:30 --until 14:30 --batch "ДОСТАВКА 19 ИЮНЯ"
    python3 call_report.py                                                     # auto (register, last 3h)
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))

VPS_USER = "root"
VPS_IP = "72.56.38.19"
SSH_KEY = os.path.expanduser("~/freelance-2026/.ssh_agent_key")
VPS_WEBHOOK_LOG = "/root/.pm2/logs/mango-webhook-error.log"
VPS_DTMF_LOG = "/root/.pm2/logs/dtmf-handler-error.log"


def ssh_cat(remote_path: str) -> list[str]:
    cmd = (
        f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no "
        f"-o ConnectTimeout=10 {VPS_USER}@{VPS_IP} 'cat {remote_path}'"
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"  ⚠️ SSH error: {result.stderr[:200]}", file=sys.stderr)
        return []
    return result.stdout.splitlines()


def _ts(s: str) -> int:
    """Convert HH:MM to seconds."""
    h, m = s.split(":")
    return int(h) * 3600 + int(m) * 60


def _parse_time(t_str: str) -> str:
    parts = t_str.strip().split(":")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "  0.0%"
    pct = n / total * 100
    return f"({pct:.1f}%)" if pct < 10 else f"({pct:.1f}%)"


# ─── Mode 1: register-based (auto_confirm_call.py) ───────────────────


def parse_register_mode(lines: list[str], since: str, until: str) -> dict:
    calls: dict[str, dict] = {}
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        m_time = re.match(r"^(\d{2}:\d{2}):", line)
        if not m_time:
            continue
        ts = m_time.group(1)
        if ts < since or ts > until:
            continue

        m_reg = re.search(r"register command_id=(\S+) phone=(\d+)", line)
        if m_reg:
            phone = m_reg.group(2)
            if phone not in calls:
                calls[phone] = {"phone": phone, "state": "registered", "connected": False}
            continue

        if "CLIENT Connected" in line or "events/call | Connected" in line:
            m_phone = re.search(r"→\+?(\d+)", line)
            if m_phone and m_phone.group(1) in calls:
                calls[m_phone.group(1)]["connected"] = True

    return calls


def parse_dtmf(lines: list[str], since_date: str) -> dict:
    results: dict[str, dict] = {}
    for line in lines:
        m_dict = re.search(r"DTMF лог: (\{.+})", line)
        if not m_dict:
            continue
        try:
            data = ast.literal_eval(m_dict.group(1))
        except (ValueError, SyntaxError):
            continue
        phone = data.get("phone", "").lstrip("+")
        ts_raw = data.get("timestamp", "")
        digit = data.get("digit", "")
        if not phone or not ts_raw:
            continue
        try:
            d = datetime.fromisoformat(ts_raw).strftime("%Y-%m-%d")
        except ValueError:
            d = ""
        if d != since_date:
            continue
        if phone not in results:
            results[phone] = {"phone": phone, "digit": digit, "action": data.get("action", "")}
    return results


# ─── Mode 2: callback-based (mango_autocall.py) ───────────────────


def extract_callback_phones(lines: list[str], since: str, until: str) -> dict:
    """Extract unique callback events with phone numbers and call states.

    Parses multi-line format:
        HH:MM:SS | 📥 EVENT: events/result/callback
        HH:MM:SS |    📦 Full data: {...}

    Returns dict[phone] -> {state_history: [(ts, call_state)], last_state, connected, from_number}
    """
    calls: dict[str, dict] = {}
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        m_time = re.match(r"^(\d{2}:\d{2}):", line)
        if not m_time:
            i += 1
            continue
        ts = m_time.group(1)
        if ts < since or ts > until:
            i += 1
            continue

        # Look for Full data JSON line
        m_json = re.search(r"📦 Full data:\s*(\{.+)", line)
        if not m_json:
            i += 1
            continue

        try:
            data = json.loads(m_json.group(1))
        except json.JSONDecodeError:
            i += 1
            continue

        # Extract call info
        call_state = data.get("call_state", "")
        command_id = data.get("command_id", "")
        callback_init = data.get("callback_initiator", "")

        # Highlight API-initiated callbacks
        if callback_init != "API":
            i += 1
            continue

        # Extract numbers
        from_data = data.get("from", {})
        to_data = data.get("to", {})

        # The client number is in 'from' if it starts with +7
        from_num = from_data.get("number", "")
        to_num = to_data.get("number", "")

        # Client is usually the one that's NOT a SIP URI and NOT the line number
        client_phone = ""
        for num in [from_num, to_num]:
            n = num.lstrip("+")
            if re.match(r"^7\d{10}$", n) or re.match(r"^89\d{9}$", n):
                client_phone = n
                break

        if not client_phone:
            i += 1
            continue

        if client_phone not in calls:
            calls[client_phone] = {
                "phone": client_phone,
                "command_id": command_id,
                "states": [],
                "connected": False,
                "disconnect_reason": None,
            }

        calls[client_phone]["states"].append((ts, call_state))
        if call_state == "Connected":
            calls[client_phone]["connected"] = True
        if call_state == "Disconnected":
            calls[client_phone]["disconnect_reason"] = data.get("disconnect_reason")
        if command_id:
            calls[client_phone]["command_id"] = command_id

        i += 1

    return calls


def extract_simple_callback_phones(lines: list[str], since: str, until: str) -> dict:
    """Extract phones from simple format events/result/callback and events/events/call."""
    phones: dict[str, dict] = {}

    for line in lines:
        line = line.rstrip()
        m_time = re.match(r"^(\d{2}:\d{2}):", line)
        if not m_time:
            continue
        ts = m_time.group(1)
        if ts < since or ts > until:
            continue

        # events/events/call | Connected/Disconnected with phone
        m_call = re.search(r"events/events/call\s*\|\s*(\w+)\s*\|\s*(.+?)→(\+?\d+)", line)
        if m_call:
            state = m_call.group(1)
            phone = m_call.group(3).lstrip("+")
            if re.match(r"^7\d{10}$", phone):
                if phone not in phones:
                    phones[phone] = {"phone": phone, "states": [], "connected": False, "disconnect_reason": None}
                phones[phone]["states"].append((ts, state))
                if state == "Connected":
                    phones[phone]["connected"] = True

        # events/result/callback simple format
        m_cb = re.search(r"events/result/callback\s*\|\s*\?\s*\|\s*\?→\?\s*\|\s*cmd=(\S+)", line)
        if m_cb:
            pass  # No phone in simple format

    return phones


# ─── Report generation ───────────────────


def determine_status(phone: str, call: dict, dtmf: dict | None) -> str:
    if dtmf:
        digit = dtmf.get("digit", "")
        if digit == "1":
            return "confirmed"
        elif digit == "0":
            return "cancelled"
        else:
            return "unclear"

    if call.get("connected"):
        return "unclear"

    # Check disconnect reason
    reason = call.get("disconnect_reason")
    if reason in (1131, 1120):
        return "unavailable"
    if reason == 1110:
        return "no_answer"

    return "no_answer"


def generate_report(calls: dict, dtmf: dict, batch: str, date: str, since: str, until: str):
    total = len(calls)
    cats = {"confirmed": [], "cancelled": [], "unavailable": [], "unclear": [], "no_answer": []}
    labels = {
        "confirmed": ("✅", "Подтвердили → сделки в «Подтверждено»"),
        "cancelled": ("❌", "Отказали"),
        "unavailable": ("📵", "Недоступны"),
        "unclear": ("❓", "НЕРАЗБОРЧИВО — перезвонить вручную"),
        "no_answer": ("📵", "НЕ ОТВЕТИЛИ"),
    }

    for phone, call in calls.items():
        status = determine_status(phone, call, dtmf.get(phone))
        cats[status].append(phone)

    confirmed = len(cats["confirmed"])
    cancelled = len(cats["cancelled"])
    unavailable = len(cats["unavailable"])
    unclear = len(cats["unclear"])
    no_answer = len(cats["no_answer"])
    accounted = confirmed + cancelled + unavailable + unclear + no_answer

    # Find time range
    times = []
    for c in calls.values():
        for s in c.get("states", []):
            times.append(s[0])
    tr = f"{min(times)}–{max(times)}" if times else f"{since}–{until}"

    lines = []
    lines.append(f"ОТЧЁТ: {batch}")
    lines.append(f"Дата: {date} | {tr} MSK | {accounted} номеров")
    lines.append("=" * 48)
    lines.append("")
    lines.append("ИТОГИ")
    lines.append("─" * 37)
    lines.append(f"Подтвердили:     {confirmed:2d} {_pct(confirmed, accounted):>8s}")
    lines.append(f"Отказали:         {cancelled:2d} {_pct(cancelled, accounted):>8s}")
    lines.append(f"Недоступны:      {unavailable:2d} {_pct(unavailable, accounted):>8s}")
    lines.append(f"Неразборчиво:    {unclear:2d} {_pct(unclear, accounted):>8s}")
    lines.append(f"Не ответили:     {no_answer:2d} {_pct(no_answer, accounted):>8s}")
    lines.append("─" * 37)
    lines.append(f"ВСЕГО:          {accounted}")
    lines.append("")

    for cat in ["confirmed", "cancelled", "unavailable"]:
        phones = cats[cat]
        if not phones:
            continue
        icon, label = labels[cat]
        lines.append("═" * 48)
        lines.append(f"{icon} {label}")
        lines.append("═" * 48)
        for p in phones:
            d = dtmf.get(p)
            extra = " (DTMF)" if d and d.get("action") in ("confirmed", "cancelled") else ""
            lines.append(f"+{p}{extra}")
        lines.append("")

    for cat in ["unclear", "no_answer"]:
        phones = cats[cat]
        if not phones:
            continue
        icon, label = labels[cat]
        lines.append("═" * 48)
        lines.append(f"{icon} {label}")
        lines.append("═" * 48)
        for p in phones:
            lines.append(f"+{p}")
        lines.append("")

    return "\n".join(lines)


# ─── Main ───────────────────


def main():
    parser = argparse.ArgumentParser(description="Отчёт по автодозвону Mango")
    parser.add_argument("--mode", choices=["register", "callback", "auto"], default="auto")
    parser.add_argument("--date", default="")
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    parser.add_argument("--batch", default="АВТОДОЗВОН")
    args = parser.parse_args()

    now = datetime.now(MSK)
    today_str = now.strftime("%Y-%m-%d")
    report_date = args.date or today_str

    # Auto-detect mode: try register first, fallback to callback
    mode = args.mode
    if mode == "auto":
        mode = "callback"  # default to callback for manual batches

    # Time window
    if args.since and args.until:
        since = _parse_time(args.since)
        until = _parse_time(args.until)
    else:
        until = now.strftime("%H:%M")
        since = (now - timedelta(hours=3)).strftime("%H:%M")
        print(f"🔍 Auto-window: {since} – {until} MSK", file=sys.stderr)

    print(f"📊 {args.batch} | {report_date} {since}–{until} | mode={mode}", file=sys.stderr)

    # Fetch logs
    print("🔌 Fetching logs from VPS...", file=sys.stderr)
    webhook_lines = ssh_cat(VPS_WEBHOOK_LOG)
    dtmf_lines = ssh_cat(VPS_DTMF_LOG)
    print(f"   webhook: {len(webhook_lines)} lines", file=sys.stderr)
    print(f"   dtmf: {len(dtmf_lines)} lines", file=sys.stderr)

    dtmf = {}

    if mode == "register":
        calls = parse_register_mode(webhook_lines, since, until)
        dtmf = parse_dtmf(dtmf_lines, report_date)
        print(f"   Calls: {len(calls)}, DTMF: {len(dtmf)}", file=sys.stderr)
    else:
        # Callback mode: parse full data events
        calls = extract_callback_phones(webhook_lines, since, until)
        print(f"   Calls (callback): {len(calls)}", file=sys.stderr)
        if not calls:
            # Fallback to simple event parsing
            calls = extract_simple_callback_phones(webhook_lines, since, until)
            print(f"   Calls (simple events): {len(calls)}", file=sys.stderr)

    if not calls:
        print("⚠️ No calls found in the specified window", file=sys.stderr)
        return

    report = generate_report(calls, dtmf, args.batch, report_date, since, until)
    print()
    print(report)


if __name__ == "__main__":
    main()
