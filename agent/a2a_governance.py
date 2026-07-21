"""Governance слой A2A-шины.

Аналог Agent Identity / Agent Gateway / zero-trust из Gemini Enterprise,
адаптированный под нашу self-hosted шину:
  - sign_message / verify_message — HMAC-подпись сообщений (защита от подмены sender).
  - scan_injection — детект prompt-injection в теле сообщения.
  - check_message — единая точка политики (signature + injection + sender trust).

Режимы:
  A2A_GOVERNANCE_ENFORCE=1  → нарушения БЛОКИРУЮТСЯ (production).
  иначе                      → warn-only (dev-режим, не ломает старые флоу).
"""
import os
import json
import hmac
import hashlib
from typing import Optional

import a2a_registry as reg

SECRET = os.getenv("A2A_SECRET", "")
ENFORCE = os.getenv("A2A_GOVERNANCE_ENFORCE", "0") == "1"

# Доверенные внешние отправители (через запятую в env), плюс любые зарегистрированные агенты.
TRUSTED_SENDERS = set(
    s.strip() for s in os.getenv("A2A_TRUSTED_SENDERS", "smoke,test,external").split(",") if s.strip()
)

# Маркеры prompt-injection (нижний регистр).
INJECTION_MARKERS = [
    "ignore previous", "ignore all previous", "disregard previous", "disregard all",
    "ignore the above", "system prompt", "<system>", "you are now", "new instructions",
    "override", "jailbreak", "developer mode", "ignore your", "forget your",
    "disregard your instructions", "assume the role", "you must now",
]


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def sign_message(msg: dict) -> dict:
    """Добавляет HMAC-подпись сообщению (мутирует и возвращает)."""
    if not SECRET:
        return msg
    payload = {k: v for k, v in msg.items() if k != "signature"}
    mac = hmac.new(SECRET.encode(), _canonical(payload).encode(), hashlib.sha256).hexdigest()
    msg["signature"] = mac
    return msg


def verify_message(msg: dict) -> Optional[bool]:
    """None — подписи нет (dev-режим); True/False — валидна/нет."""
    sig = msg.get("signature")
    if not sig:
        return None
    if not SECRET:
        return None
    payload = {k: v for k, v in msg.items() if k != "signature"}
    expected = hmac.new(SECRET.encode(), _canonical(payload).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def scan_injection(obj, path: str = "") -> list:
    """Рекурсивно ищет маркеры инъекции в строковых полях payload."""
    hits = []
    if isinstance(obj, str):
        low = obj.lower()
        for m in INJECTION_MARKERS:
            if m in low:
                hits.append({"path": path, "marker": m})
    elif isinstance(obj, dict):
        for k, v in obj.items():
            hits += scan_injection(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += scan_injection(v, f"{path}[{i}]")
    return hits


def check_message(msg: dict) -> dict:
    """Возвращает {'status': 'ok'|'blocked'|'warn', 'reasons': [...]}."""
    reasons = []

    sig = verify_message(msg)
    if sig is False:
        reasons.append("invalid_signature")
    elif sig is None and ENFORCE:
        reasons.append("unsigned_in_enforce_mode")

    hits = scan_injection(msg.get("payload", {}))
    if hits:
        reasons.append(f"injection:{hits[0]['marker']}")

    sender = msg.get("sender", "")
    if sender not in reg.REGISTRY and sender not in TRUSTED_SENDERS:
        reasons.append(f"unknown_sender:{sender}")

    if not reasons:
        return {"status": "ok", "reasons": []}

    blocked = ENFORCE and any(
        r.startswith(("invalid_signature", "unsigned", "injection")) for r in reasons
    )
    if blocked:
        return {"status": "blocked", "reasons": reasons}
    return {"status": "warn", "reasons": reasons}
