#!/usr/bin/env python3
"""
Mango Office Webhook (VPS) — события звонков + play/start для автодозвона.

PM2: mango-webhook, порт 8085
URL в ЛК Mango: http://72.56.38.19:8085/events

Аудио в ЛК Mango: confirm_call_kore (internal_id 1000550776)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import requests
from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
BASE_DIR = AGENT_DIR.parent
for _env in (BASE_DIR / ".env", AGENT_DIR / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

for _proxy in (
    "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
    "https_proxy", "http_proxy", "all_proxy",
):
    os.environ.pop(_proxy, None)

VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
MANGO_API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/").rstrip("/") + "/"
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")

# Имя в ЛК Mango — БЕЗ .mp3
MANGO_AUDIO_NAME = os.getenv("MANGO_AUDIO_NAME", os.getenv("MANGO_MP3_FILENAME", "confirm_call_kore"))
MANGO_AUDIO_NAME = MANGO_AUDIO_NAME.removesuffix(".mp3").removesuffix(".wav")
MANGO_AUDIO_ID = int(os.getenv("MANGO_AUDIO_ID", "1000550776"))
# Отдельный бип в Mango (если нет — ставим 0, тогда только полный файл confirm_call_kore)
MANGO_BEEP_AUDIO_ID = int(os.getenv("MANGO_BEEP_AUDIO_ID", "0"))
MESSAGE_PLAY_SEC = float(os.getenv("MESSAGE_PLAY_SEC", "14"))  # длина голоса до бипа
DTMF_HANDLER_URL = os.getenv("DTMF_HANDLER_URL", "http://127.0.0.1:8086/")

STAGE_CONFIRMED = os.getenv("BX_STAGE_CONFIRMED", "PREPARATION")
STAGE_CANCELLED = os.getenv("BX_STAGE_CANCELLED", "LOSE")

LOG_DIR = Path(os.getenv("MANGO_WEBHOOK_LOG_DIR", "/var/log"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "mango_webhook.log"),
    ],
)
log = logging.getLogger("mango-wh")

# command_id / entry_id → {phone, deal_id, call_id, ...}
pending: dict[str, dict] = {}
played_message: set[str] = set()
played_beep: set[str] = set()

_PHONE_RE = re.compile(r"^\+?7\d{10}$")


def _sign(json_data: dict) -> str:
    j = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((VPBX_API_KEY + j + VPBX_API_SALT).encode()).hexdigest()


def mango_api(endpoint: str, json_data: dict) -> dict:
    j = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    try:
        r = requests.post(
            f"{MANGO_API_BASE}{endpoint}",
            data={"vpbx_api_key": VPBX_API_KEY, "json": j, "sign": _sign(json_data)},
            timeout=20,
        )
        return r.json()
    except Exception as e:
        log.error("Mango API %s: %s", endpoint, e)
        return {}


def play_on_call(call_id: str, internal_id: int, label: str = "msg") -> dict:
    """play/start с обязательным command_id."""
    if not call_id:
        return {}
    payload = {
        "command_id": f"play_{label}_{uuid.uuid4().hex[:8]}",
        "call_id": call_id,
        "internal_id": internal_id,
    }
    result = mango_api("play/start", payload)
    log.info("🎵 play/%s id=%s → %s", label, internal_id, result)
    return result


def _schedule_beep(call_id: str, delay: float) -> None:
    """Второй play — бип после сообщения (если в Mango есть отдельный файл)."""
    if not MANGO_BEEP_AUDIO_ID or call_id in played_beep:
        return

    def _run():
        import time
        time.sleep(delay)
        if call_id in played_beep:
            return
        r = play_on_call(call_id, MANGO_BEEP_AUDIO_ID, label="beep")
        if r.get("result") == 1000:
            played_beep.add(call_id)

    threading.Thread(target=_run, daemon=True).start()


def _forward_dtmf(call_id: str, digit: str, command_id: str, entry_id: str) -> None:
    ctx = _find_pending(command_id, entry_id) or {}
    phone = ctx.get("phone", "")
    deal_id = ctx.get("deal_id", "")
    try:
        requests.post(
            DTMF_HANDLER_URL,
            json={
                "call_id": call_id or command_id,
                "digit": str(digit),
                "phone": phone,
                "deal_id": deal_id,
                "source": "mango_webhook",
            },
            timeout=5,
        )
        log.info("🔢 DTMF %s → handler phone=%s deal=%s", digit, phone, deal_id)
    except Exception as e:
        log.error("DTMF forward: %s", e)


def _norm_phone(num: str) -> str:
    d = re.sub(r"\D", "", num or "")
    if len(d) == 11 and d.startswith("8"):
        d = "7" + d[1:]
    return d


def _is_client_number(num: str) -> bool:
    n = _norm_phone(num)
    return len(n) == 11 and n.startswith("7")


def register_call(command_id: str, phone: str, deal_id: str = "") -> None:
    info = {
        "phone": _norm_phone(phone),
        "deal_id": deal_id or "",
        "created": datetime.now().isoformat(),
    }
    pending[command_id] = info
    log.info("📋 register command_id=%s phone=%s deal=%s", command_id, info["phone"], deal_id)


def _find_pending(command_id: str, entry_id: str) -> dict | None:
    if command_id and command_id in pending:
        return pending[command_id]
    if entry_id and entry_id in pending:
        return pending[entry_id]
    return None


def _maybe_play_client_leg(data: dict) -> None:
    """Клиент ответил на callback — проигрываем Kore."""
    if data.get("callback_initiator") != "API":
        return
    if data.get("call_state") != "Connected":
        return

    to_info = data.get("to") or {}
    to_num = str(to_info.get("number", ""))
    if not _is_client_number(to_num):
        return

    call_id = data.get("call_id") or ""
    command_id = data.get("command_id") or ""
    entry_id = data.get("entry_id") or ""
    client_phone = _norm_phone(str(to_num))

    ctx = _find_pending(command_id, entry_id)
    if ctx and ctx.get("phone") and ctx["phone"] != client_phone:
        log.warning("phone mismatch pending=%s event=%s", ctx["phone"], client_phone)

    if call_id in played_message:
        return

    log.info(
        "▶️ CLIENT Connected → play %s (id=%s)",
        MANGO_AUDIO_NAME,
        MANGO_AUDIO_ID,
    )

    PLAY_DELAY_SEC = float(os.getenv("MANGO_PLAY_DELAY_SEC", "3"))

    def _play_sequence():
        if PLAY_DELAY_SEC > 0:
            log.info("⏳ Задержка %s секунд перед play/start...", PLAY_DELAY_SEC)
            import time as _time
            _time.sleep(PLAY_DELAY_SEC)
        r = play_on_call(call_id, MANGO_AUDIO_ID, label="msg")
        if r.get("result") == 1000:
            played_message.add(call_id)
            if MANGO_BEEP_AUDIO_ID:
                _schedule_beep(call_id, MESSAGE_PLAY_SEC)

    threading.Thread(target=_play_sequence, daemon=True).start()


class WebhookHandler(BaseHTTPRequestHandler):
    def _ok(self, body: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body or {"status": "ok"}).encode())

    def do_GET(self):
        if self.path.rstrip("/") == "/health":
            self._ok({
                "status": "running",
                "audio": MANGO_AUDIO_NAME,
                "audio_id": MANGO_AUDIO_ID,
                "pending": len(pending),
            })
            return
        self._ok({"status": "running", "pending": len(pending)})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        path = self.path.strip("/").rstrip("/")

        # JSON register от auto_confirm_call
        if path == "register" and self.headers.get("Content-Type", "").startswith("application/json"):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            register_call(
                data.get("command_id", f"cmd_{data.get('phone', '')}"),
                data.get("phone", ""),
                str(data.get("deal_id", "")),
            )
            self._ok({"registered": True})
            return

        try:
            params = parse_qs(raw)
            json_str = params.get("json", ["{}"])[0]
            data = json.loads(json_str)
        except json.JSONDecodeError:
            data = {"raw": raw[:300]}

        self._ok()

        command_id = data.get("command_id", "")
        entry_id = data.get("entry_id", data.get("call_id", "?"))
        call_state = data.get("call_state", "?")
        from_num = (data.get("from") or {}).get("number", "?")
        to_num = (data.get("to") or {}).get("number", "?")

        log.info(
            "📥 %s | %s | %s→%s | cmd=%s",
            path, call_state, from_num, to_num, command_id or "-",
        )

        _maybe_play_client_leg(data)

        dtmf = data.get("dtmf")
        if dtmf is not None:
            _forward_dtmf(
                data.get("call_id", ""),
                str(dtmf),
                command_id,
                str(entry_id),
            )

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(os.getenv("MANGO_WEBHOOK_PORT", "8085"))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    log.info("🚀 Mango Webhook port=%s audio=%s id=%s", port, MANGO_AUDIO_NAME, MANGO_AUDIO_ID)
    server.serve_forever()


if __name__ == "__main__":
    main()
