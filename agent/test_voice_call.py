#!/usr/bin/env python3
"""
test_voice_call.py — тестовый звонок для Voice Angela.

Делает исходящий звонок через Mango API, ждёт пока baresip ответит,
запускает диалог: клиент говорит → STT → Angela → TTS → play/start.

Запуск: python3 test_voice_call.py --phone "+79859234644"
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
BASE_DIR = AGENT_DIR.parent
for _env in (BASE_DIR / ".env", AGENT_DIR / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

# Import voice engine before clearing proxy — captures proxy/api_key at import time
from voice_engine import generate_call_tts

# Clear proxy for direct APIs (Mango, OpenRouter, Bitrix — работают из РФ напрямую)
for _p in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
           "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_p, None)

VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
MANGO_API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/").rstrip("/") + "/"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
OWNER_CHAT_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "176203333"))

DEC_PATH = Path("/root/dec.wav")
EVENTS_PATH = Path("/var/log/voice-angela/events.jsonl")
TTS_DIR = AGENT_DIR / "tts_cache"
TTS_DIR.mkdir(exist_ok=True)
SR = 8000
POLL = 0.2
VAD_SILENCE = 1.2
MIN_SPEECH = 0.6


def _sign(data: dict) -> str:
    r = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((VPBX_API_KEY + r + VPBX_API_SALT).encode()).hexdigest()


def mango_api(endpoint: str, data: dict) -> dict:
    url = MANGO_API_BASE + endpoint
    payload = {
        "vpbx_api_key": VPBX_API_KEY,
        "json": json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        "sign": _sign(data),
    }
    r = requests.post(url, data=payload, timeout=30,
                      headers={"User-Agent": "VoiceAngelaTest/1.0"})
    return r.json()


def mango_upload(path: Path) -> str:
    url = MANGO_API_BASE + "uploads/upload"
    ts = int(time.time() * 1000)
    s = hashlib.sha256((VPBX_API_KEY + str(ts) + VPBX_API_SALT).encode()).hexdigest()
    with open(path, "rb") as f:
        r = requests.post(url,
            data={"vpbx_api_key": VPBX_API_KEY, "timestamp": ts, "sign": s},
            files={"file": (path.name, f, "audio/wav")},
            timeout=30, headers={"User-Agent": "VoiceAngelaTest/1.0"})
    print(f"     upload HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code != 200:
        return ""
    data = r.json()
    # Mango может возвращать разные ключи
    for key in ("audi_file_id", "audio_id", "id", "internal_id"):
        if key in data:
            return str(data[key])
    return ""


def mango_play(call_id: str, audio_id: str) -> bool:
    if not call_id or not audio_id:
        return False
    r = mango_api("commands/play/start", {
        "call_id": call_id,
        "command_id": f"test_{int(time.time()*1000)}",
        "audi_file_id": audio_id,
    })
    print(f"     play/start result: {r}")
    # Mango возвращает result: 1000 при успехе, не строку "SUCCESS"
    return r.get("result") in (1000, "SUCCESS") or "audi_file_id" in r


def make_call(phone: str) -> str | None:
    data = {
        "command_id": f"test_call_{int(time.time())}",
        "from": {"extension": "22"},
        "to_number": phone,
    }
    print(f"  📞 Звоню {phone}...")
    r = mango_api("commands/callback", data)
    if "error" in r:
        print(f"  ⚠ Call error: {r}")
        return None

    # Callback response may lack call_id — try events.jsonl from webhook
    call_id = r.get("call_id", "")
    if call_id:
        print(f"  ✅ call_id={call_id}")
        return call_id

    print("  ⏳ Жду call_id из событий mango_webhook...")
    pn = re.sub(r"[^0-9]", "", phone)[-10:]
    deadline = time.time() + 20
    last_pos = EVENTS_PATH.stat().st_size if EVENTS_PATH.exists() else 0
    while time.time() < deadline:
        if EVENTS_PATH.exists() and EVENTS_PATH.stat().st_size > last_pos:
            with open(EVENTS_PATH) as f:
                f.seek(last_pos)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("type") == "callback_connected" and pn in ev.get("phone", ""):
                        call_id = ev.get("call_id", "")
                        if call_id:
                            print(f"  ✅ call_id={call_id} (из webhook)")
                            return call_id
                last_pos = f.tell()
        time.sleep(0.3)

    print("  ⚠ call_id не получен (ни из API, ни из webhook)")
    return None


def wait_dec(timeout: int = 45, initial_size: int = 0) -> bool:
    """Wait for baresip to (re)create/dec.wav after a new call connects."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if DEC_PATH.exists():
            sz = DEC_PATH.stat().st_size
            if sz > 44 and sz != initial_size:
                return True
        time.sleep(POLL)
    return False


def transcribe(path: Path) -> str:
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(path), language="ru", beam_size=3, vad_filter=True)
    return " ".join(s.text.strip() for s in segs)


def generate_tts(text: str) -> Path | None:
    wav = generate_call_tts(text)
    return Path(wav) if wav else None


def load_prices() -> str:
    pp = BASE_DIR / "config" / "prices.json"
    if not pp.exists():
        return ""
    with open(pp) as f:
        d = json.load(f)
    cats = d.get("categories", {})
    lines = ["Прайс-лист:"]
    for ck, cv in cats.items():
        if not isinstance(cv, dict):
            continue
        lbl = cv.get("label", ck)
        lines.append(f"\n{lbl}:")
        for name, info in cv.get("items", {}).items():
            p = info.get("price", "?")
            desc = info.get("description", "")
            line = f"  {name}: {p}₽"
            if desc:
                line += f" — {desc[:80]}"
            lines.append(line)
    return "\n".join(lines)


def angela(text: str, history: str = "") -> str:
    price_ctx = load_prices()
    prompt = (
        "Ты — Анжела, голосовой ассистент ВезёмЦыплят (птицеводческий бизнес). "
        "Разговор по телефону. Отвечай КРАТКО (1-3 предложения), естественно.\n"
        f"{price_ctx}\n{history}\n"
        "Если клиент просит оператора: 'ПЕРЕКЛЮЧАЮ_ОПЕРАТОРА'\n"
        f"Клиент: {text}"
    )
    for model in ["deepseek/deepseek-chat", "qwen/qwen-turbo"]:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 256, "temperature": 0.3},
                timeout=20)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  ⚠ Angela {model}: {e}")
    return "Извините, повторите, пожалуйста."


def main():
    phone = "+78612025110"
    if "--phone" in sys.argv:
        idx = sys.argv.index("--phone")
        phone = sys.argv[idx + 1]

    print(f"{'='*50}")
    print(f"TEST VOICE CALL — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"Звонок на: {phone}")
    print(f"{'='*50}\n")

    # Capture initial dec.wav size so we wait for a FRESH call connection
    dec_initial_size = DEC_PATH.stat().st_size if DEC_PATH.exists() else 0
    print(f"  📄 initial dec.wav size={dec_initial_size}")

    call_id = make_call(phone)
    if not call_id:
        return

    print("  ⏳ Ожидание ответа baresip...")
    if not wait_dec(60, dec_initial_size):
        print("  ⚠ Нет dec.wav в течение 60 секунд")
        return

    print("  ✅ Baresip ответил! Начинаем диалог.")
    time.sleep(2)

    # Greeting
    print("\n  🤖 Анжела: Здравствуйте!...")
    wav = generate_tts("Здравствуйте! Это Анжела, ассистент ВезёмЦыплят. Чем могу помочь?")
    if wav:
        aid = mango_upload(wav)
        if aid:
            mango_play(call_id, aid)

    # Conversation
    last_size = DEC_PATH.stat().st_size if DEC_PATH.exists() else 0
    phrase = b""
    speech_end = 0.0
    turn = 0
    transcript = []
    silence_start = time.time()

    while time.time() - silence_start < 60:
        if not DEC_PATH.exists():
            print("\n  ⚠ dec.wav пропал — звонок завершён")
            break

        sz = DEC_PATH.stat().st_size
        if sz <= last_size:
            time.sleep(POLL)
            continue

        with open(DEC_PATH, "rb") as f:
            f.seek(last_size if last_size > 44 else 44)
            data = f.read()
        last_size = sz

        if not data:
            time.sleep(POLL)
            continue

        phrase += data

        if len(phrase) > SR * 2 * MIN_SPEECH:
            recent = phrase[-SR * 2:]
            count = len(recent) // 2
            if count > 0:
                samples = struct.unpack(f"<{count}h", recent[:count * 2])
                rms = (sum(s * s for s in samples) / count) ** 0.5
                is_speech = rms > 0.015 * 32768
            else:
                is_speech = False

            if is_speech:
                speech_end = time.time()
                silence_start = time.time()
            elif speech_end > 0 and (time.time() - speech_end) > VAD_SILENCE:
                turn += 1
                utt_path = TTS_DIR / f"utt_{turn}.wav"
                write_wav(utt_path, phrase)
                phrase = b""
                speech_end = 0.0

                print(f"\n  🗣 [t{turn}] Распознавание...")
                text = transcribe(utt_path)
                if not text.strip():
                    continue

                transcript.append(f"Клиент: {text}")
                print(f"  🗣 [t{turn}] {text[:120]}")

                hist = "\n".join(transcript[-4:])
                response = angela(text, hist)

                if "ПЕРЕКЛЮЧАЮ" in response or "ОПЕРАТОРА" in response:
                    print("  🔄 Оператор requested")
                    break

                transcript.append(f"Анжела: {response}")
                print(f"  🤖 [t{turn}] {response[:120]}")

                wav = generate_tts(response)
                if wav:
                    aid = mango_upload(wav)
                    if aid:
                        mango_play(call_id, aid)

                if turn >= 10:
                    break

    print(f"\n{'='*50}")
    print(f"Звонок завершён ({turn} реплик)")
    transcript_text = "\n".join(transcript)
    print(transcript_text[:500])

    if TELEGRAM_TOKEN:
        short = transcript_text[:400].replace("<", "&lt;").replace(">", "&gt;")
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": OWNER_CHAT_ID, "text":
                f"📞 <b>Тестовый звонок Angela</b>\n"
                f"📱 {phone} | {turn} реплик\n<code>{short}</code>",
                "parse_mode": "HTML"})


def write_wav(path: Path, audio: bytes):
    with open(path, "wb") as f:
        f.write(struct.pack("<4sI4s", b"RIFF", 36 + len(audio), b"WAVE"))
        f.write(struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(struct.pack("<4sI", b"data", len(audio)))
        f.write(audio)


if __name__ == "__main__":
    main()
