#!/usr/bin/env python3
"""
angela_outbound.py — Исходящий обзвон Анжелой + запись заказа в Битрикс24.

Сценарий:
1. Звонок клиенту через Mango callback API
2. Приветствие + информация об акции/продукте
3. Ожидание ответа клиента (VAD + Whisper STT)
4. Ответ Angela на вопросы (OpenRouter → локальный LLM fallback)
5. При согласии клиента — создание сделки в Битрикс24
6. Отчёт в Telegram

Запуск: python3 angela_outbound.py --phone "+79031234567" --topic "Акция на бройлеров"
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
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

_TTS_PROXY = None
for _k in ("ALL_PROXY", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    _v = os.environ.get(_k, "")
    if _v and "socks" in _v and "localhost" not in _v:
        _TTS_PROXY = {"https": _v, "http": _v}
        break

for _p in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_p, None)

VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
MANGO_API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/").rstrip("/") + "/"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
OWNER_CHAT_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "176203333"))
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

DEC_PATH = Path("/root/dec.wav")
TTS_DIR = AGENT_DIR / "tts_cache"
TTS_DIR.mkdir(exist_ok=True)
LOG_DIR = Path("/var/log/voice-angela")
LOG_DIR.mkdir(parents=True, exist_ok=True)

SR = 8000
VAD_SILENCE = 1.2
MIN_SPEECH = 0.6
POLL = 0.2
MAX_TURNS = 15


# ── Mango API ─────────────────────────────────────────────────────────────────

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
    r = requests.post(url, data=payload, timeout=30, headers={"User-Agent": "AngelaOutbound/1.0"})
    try:
        return r.json()
    except Exception:
        return {"error": r.text[:100]}


def mango_upload(path: Path) -> str:
    url = MANGO_API_BASE + "uploads/upload"
    ts = int(time.time() * 1000)
    s = hashlib.sha256((VPBX_API_KEY + str(ts) + VPBX_API_SALT).encode()).hexdigest()
    with open(path, "rb") as f:
        r = requests.post(url,
            data={"vpbx_api_key": VPBX_API_KEY, "timestamp": ts, "sign": s},
            files={"file": (path.name, f, "audio/wav")}, timeout=30,
            headers={"User-Agent": "AngelaOutbound/1.0"})
    return str(r.json().get("audi_file_id", "")) if r.status_code == 200 else ""


def mango_play(call_id: str, audio_id: str) -> bool:
    if not call_id or not audio_id:
        return False
    r = mango_api("commands/play/start", {
        "call_id": call_id, "command_id": f"ao_{int(time.time()*1000)}",
        "audi_file_id": audio_id,
    })
    return r.get("result") == "SUCCESS"


def mango_callback(phone: str, ext: str = "22") -> str | None:
    """Make outbound call via Mango callback."""
    data = {
        "command_id": f"angela_out_{int(time.time())}",
        "from": {"extension": ext},
        "to_number": phone,
    }
    r = mango_api("commands/callback", data)
    if r.get("result") == "SUCCESS":
        return r.get("call_id", "")
    print(f"  ⚠ Callback error: {r}")
    return None


# ── Baresip / Audio ───────────────────────────────────────────────────────────

def wait_dec(timeout: int = 45) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if DEC_PATH.exists() and DEC_PATH.stat().st_size > 44:
            return True
        time.sleep(POLL)
    return False


def write_wav(path: Path, audio: bytes):
    count = len(audio) // 2
    with open(path, "wb") as f:
        f.write(struct.pack("<4sI4s", b"RIFF", 36 + len(audio), b"WAVE"))
        f.write(struct.pack("<4sI4sI", b"fmt ", 16, 1, SR, SR * 2, 2, 16))
        f.write(struct.pack("<4sI", b"data", len(audio)))
        f.write(audio)


def energy_vad(audio: bytes, threshold: float = 0.015) -> bool:
    count = len(audio) // 2
    if count < 10:
        return False
    samples = struct.unpack(f"<{count}h", audio[:count * 2])
    rms = (sum(s * s for s in samples) / count) ** 0.5
    return rms > threshold * 32768


# ── STT ───────────────────────────────────────────────────────────────────────

_stt = None

def load_stt():
    global _stt
    if _stt:
        return
    from faster_whisper import WhisperModel
    _stt = WhisperModel("base", device="cpu", compute_type="int8")


def transcribe(path: Path) -> str:
    load_stt()
    if _stt is None:
        return ""
    segs, _ = _stt.transcribe(str(path), language="ru", beam_size=3, vad_filter=True)
    return " ".join(s.text.strip() for s in segs)


# ── TTS ───────────────────────────────────────────────────────────────────────

def generate_tts(text: str) -> Path | None:
    import base64
    ts = int(time.time() * 1000)
    out = TTS_DIR / f"ao_{ts}.wav"
    if not GEMINI_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_KEY}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}
        }
    }
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, proxies=_TTS_PROXY, timeout=30)
        if r.status_code != 200:
            return None
        parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                audio = base64.b64decode(part["inlineData"]["data"])
                raw = TTS_DIR / f"ao_{ts}.raw"
                with open(raw, "wb") as f:
                    f.write(audio)
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                     "-i", str(raw), "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16", "-f", "wav", str(out)],
                    capture_output=True, timeout=15)
                if out.exists():
                    return out
    except Exception as e:
        print(f"  ⚠ TTS: {e}")
    return None


def tts_and_play(call_id: str, text: str) -> bool:
    wav = generate_tts(text)
    if not wav:
        return False
    aid = mango_upload(wav)
    if not aid:
        return False
    return mango_play(call_id, aid)


# ── Price Context ─────────────────────────────────────────────────────────────

_PRICE_CACHE: str | None = None

def load_price_context() -> str:
    global _PRICE_CACHE
    if _PRICE_CACHE:
        return _PRICE_CACHE
    price_path = BASE_DIR / "config" / "prices.json"
    if not price_path.exists():
        _PRICE_CACHE = ""
        return ""
    with open(price_path) as f:
        data = json.load(f)
    cats = data.get("categories", {})
    lines = ["Прайс-лист ВезёмЦыплят:"]
    for ck, cv in cats.items():
        if not isinstance(cv, dict):
            continue
        lbl = cv.get("label", ck)
        lines.append(f"\n{lbl}:")
        for name, info in cv.get("items", {}).items():
            p = info.get("price", "?")
            desc = info.get("description", "")[:80]
            lines.append(f"  {name}: {p}₽ — {desc}")
    contacts = data.get("contacts", {})
    lines.append(f"\n📞 {contacts.get('phone_primary', '')}")
    lines.append(f"🚚 Доставка: {data.get('delivery', {}).get('days', '')}")
    _PRICE_CACHE = "\n".join(lines)
    return _PRICE_CACHE


# ── Angela (LLM cascade) ─────────────────────────────────────────────────────

def angela_response(text: str, crm_ctx: dict | None = None, context: str = "", topic: str = "") -> str:
    crm_info = ""
    if crm_ctx:
        c = crm_ctx.get("contact", {})
        name = f"{c.get('NAME','')} {c.get('LAST_NAME','')}".strip()
        if name:
            crm_info = f"\nКлиент: {name}"
        if crm_ctx.get("deals"):
            crm_info += "\nАктивные сделки: " + "; ".join(
                f"{d.get('TITLE','')} ({d.get('STAGE_ID','')})" for d in crm_ctx["deals"][:3])

    price_ctx = load_price_context()
    topic_info = f"\nТема разговора: {topic}" if topic else ""

    prompt = (
        "Ты — Анжела, голосовой ассистент ВезёмЦыплят (Азовский инкубатор). "
        "Разговор по телефону. Отвечай КРАТКО (1-3 предложения), естественно.\n"
        f"{topic_info}{crm_info}\n{price_ctx}\n{context}\n"
        "Если клиент хочет заказать/купить — ответь: 'ОФОРМЛЯЮ_ЗАКАЗ'\n"
        "Если клиент просит оператора — ответь: 'ПЕРЕКЛЮЧАЮ_ОПЕРАТОРА'\n"
        f"Клиент: {text}"
    )

    # 1. OpenRouter
    for model in ["deepseek/deepseek-chat", "qwen/qwen-2.5-7b-instruct"]:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 256, "temperature": 0.3}, timeout=20)
            if r.status_code == 200:
                ans = r.json()["choices"][0]["message"]["content"].strip()
                print(f"  ✅ OpenRouter [{model.split('/')[0]}]: {ans[:60]}...")
                return ans
        except Exception as e:
            print(f"  ⚠ OpenRouter {model}: {str(e)[:60]}")

    # 2. Local Ollama fallback
    try:
        r = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3.2:1b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 120}
        }, timeout=45)
        if r.status_code == 200:
            ans = r.json().get("response", "").strip()
            print(f"  ✅ Ollama: {ans[:60]}...")
            return ans
    except Exception as e:
        print(f"  ⚠ Ollama: {str(e)[:60]}")

    return "Извините, повторите, пожалуйста."


# ── Bitrix24 CRM ──────────────────────────────────────────────────────────────

def find_or_create_contact(phone: str) -> dict | None:
    """Find contact by phone, or create new one."""
    if not BITRIX_URL:
        return None
    p = re.sub(r"[^0-9]", "", phone)[-10:]
    try:
        r = requests.post(f"{BITRIX_URL}crm.contact.list", json={
            "filter": {"PHONE": f"%{p}%"},
            "select": ["ID", "NAME", "LAST_NAME", "PHONE"],
        }, timeout=15)
        if r.status_code == 200:
            contacts = r.json().get("result", [])
            if contacts:
                c = contacts[0]
                r2 = requests.post(f"{BITRIX_URL}crm.deal.list", json={
                    "filter": {"CONTACT_ID": c["ID"]},
                    "select": ["ID", "TITLE", "STAGE_ID", "OPPORTUNITY"],
                }, timeout=15)
                deals = r2.json().get("result", []) if r2.status_code == 200 else []
                return {"contact": c, "deals": deals}
        return {"contact": {"ID": 0, "NAME": "", "LAST_NAME": "Новый клиент", "PHONE": [{"VALUE": phone}]}, "deals": []}
    except Exception as e:
        print(f"  ⚠ CRM lookup: {e}")
        return None


def create_deal(phone: str, contact_name: str, title: str, amount: float = 0) -> int | None:
    """Create a deal in Bitrix24. Returns deal ID or None."""
    if not BITRIX_URL:
        return None
    p = re.sub(r"[^0-9]", "", phone)[-10:]

    # Find or create contact
    crm = find_or_create_contact(phone)
    if not crm:
        return None

    contact_id = crm["contact"]["ID"]
    if not contact_id:
        try:
            r = requests.post(f"{BITRIX_URL}crm.contact.add", json={
                "fields": {
                    "NAME": contact_name or "Клиент",
                    "PHONE": [{"VALUE": phone, "VALUE_TYPE": "WORK"}],
                }
            }, timeout=15)
            if r.status_code == 200:
                contact_id = r.json().get("result")
        except Exception as e:
            print(f"  ⚠ Contact create: {e}")
            return None

    if not contact_id:
        print("  ⚠ No contact ID")
        return None

    # Create deal
    try:
        r = requests.post(f"{BITRIX_URL}crm.deal.add", json={
            "fields": {
                "TITLE": title,
                "CONTACT_ID": contact_id,
                "OPPORTUNITY": amount,
                "STAGE_ID": "NEW",
                "COMMENTS": f"Создано через Анжелу (голосовой обзвон) {datetime.now():%d.%m.%Y}",
            }
        }, timeout=15)
        if r.status_code == 200:
            deal_id = r.json().get("result")
            print(f"  ✅ Сделка создана: #{deal_id} [{title}] {amount}₽")
            return deal_id
    except Exception as e:
        print(f"  ⚠ Deal create: {e}")
    return None


# ── Telegram ──────────────────────────────────────────────────────────────────

def tg_notify(text: str):
    if not TELEGRAM_TOKEN:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": OWNER_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def listen_and_respond(call_id: str, phone: str, crm_ctx: dict | None, topic: str) -> dict:
    """Main conversation loop. Returns result dict."""
    result = {"turns": 0, "transcript": [], "deal_id": None, "operator": False}

    last_size = DEC_PATH.stat().st_size if DEC_PATH.exists() else 0
    phrase = b""
    speech_end = 0.0
    silence_start = time.time()

    while time.time() - silence_start < 60 and result["turns"] < MAX_TURNS:
        if not DEC_PATH.exists():
            print("  ⚠ dec.wav пропал — звонок завершён")
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
                is_speech = energy_vad(recent, 0.015)
            else:
                is_speech = False

            if is_speech:
                speech_end = time.time()
                silence_start = time.time()
            elif speech_end > 0 and (time.time() - speech_end) > VAD_SILENCE:
                result["turns"] += 1
                turn = result["turns"]
                utt_path = TTS_DIR / f"ao_utt_{turn}.wav"
                write_wav(utt_path, phrase)
                phrase = b""
                speech_end = 0.0

                text = transcribe(utt_path)
                if not text.strip():
                    continue

                result["transcript"].append(f"Клиент: {text}")
                print(f"  🗣 [{turn}] {text[:100]}")

                hist = "\n".join(result["transcript"][-4:])
                response = angela_response(text, crm_ctx, hist, topic)

                if "ПЕРЕКЛЮЧАЮ" in response:
                    result["operator"] = True
                    result["transcript"].append(f"Анжела: {response}")
                    break

                if "ОФОРМЛЯЮ_ЗАКАЗ" in response:
                    result["transcript"].append(f"Анжела: {response}")
                    print(f"  🛒 [{turn}] Клиент хочет заказать!")

                    # Ask what to order
                    confirm_text = "Что именно и сколько вам нужно? Назовите породу и количество."
                    tts_and_play(call_id, confirm_text)
                    result["transcript"].append(f"Анжела: {confirm_text}")

                    # Wait for order details
                    time.sleep(3)
                    order_phrase = b""
                    deadline = time.time() + 30
                    while time.time() < deadline:
                        if not DEC_PATH.exists():
                            break
                        sz = DEC_PATH.stat().st_size
                        if sz > last_size:
                            with open(DEC_PATH, "rb") as f:
                                f.seek(last_size if last_size > 44 else 44)
                                order_phrase += f.read()
                            last_size = sz
                        if energy_vad(order_phrase[-SR * 2:] if len(order_phrase) > SR * 2 else order_phrase, 0.015):
                            speech_end = time.time()
                        elif speech_end > 0 and time.time() - speech_end > VAD_SILENCE:
                            break
                        time.sleep(POLL)

                    if order_phrase:
                        order_path = TTS_DIR / f"ao_order_{turn}.wav"
                        write_wav(order_path, order_phrase)
                        order_text = transcribe(order_path)
                        result["transcript"].append(f"Клиент: {order_text}")
                        print(f"  📝 [{turn}] Заказ: {order_text}")

                        # Create deal
                        cname = crm_ctx["contact"].get("NAME", "") if crm_ctx else ""
                        deal_id = create_deal(phone, cname, f"Заказ через Анжелу: {order_text[:100]}", 0)
                        result["deal_id"] = deal_id

                        thanks = "Спасибо! Я оформила заказ. Менеджер свяжется с вами для уточнения. Хорошего дня!"
                        tts_and_play(call_id, thanks)
                        result["transcript"].append(f"Анжела: {thanks}")
                    break

                result["transcript"].append(f"Анжела: {response}")
                print(f"  🤖 [{turn}] {response[:100]}")

                tts_and_play(call_id, response)

    return result


def main():
    phone = ""
    topic = "Продукция ВезёмЦыплят"

    for i, arg in enumerate(sys.argv):
        if arg == "--phone" and i + 1 < len(sys.argv):
            phone = sys.argv[i + 1]
        elif arg == "--topic" and i + 1 < len(sys.argv):
            topic = sys.argv[i + 1]

    if not phone:
        print("Использование: python3 angela_outbound.py --phone '+79031234567' [--topic 'Тема']")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"ANGELA OUTBOUND CALL — {datetime.now():%Y-%m-%d %H:%M}")
    print(f"Телефон: {phone} | Тема: {topic}")
    print(f"{'='*60}\n")

    # Step 1: Call
    print("📞 Звоню...")
    call_id = mango_callback(phone)
    if not call_id:
        print("❌ Не удалось позвонить")
        return
    print(f"  ✅ call_id={call_id}")

    # Step 2: Wait for answer
    print("⏳ Жду ответа...")
    if not wait_dec(60):
        print("❌ Клиент не ответил")
        tg_notify(f"📞 Анжела звонила {phone} — не ответили")
        return
    print("  ✅ Клиент ответил!")

    # Step 3: CRM lookup
    print("🔍 CRM lookup...")
    crm_ctx = find_or_create_contact(phone)
    time.sleep(1)

    # Step 4: Greeting
    greeting = f"Здравствуйте! Это Анжела, ассистент ВезёмЦыплят. {topic}. Рассказать подробнее?"
    print(f"\n🤖 Анжела: {greeting}")
    tts_and_play(call_id, greeting)
    time.sleep(3)

    # Step 5: Conversation
    result = listen_and_respond(call_id, phone, crm_ctx, topic)

    # Step 6: Report
    transcript_text = "\n".join(result["transcript"])
    print(f"\n{'='*60}")
    print(f"ЗВОНОК ЗАВЕРШЁН — {result['turns']} реплик")
    if result["deal_id"]:
        print(f"🛒 Сделка #{result['deal_id']}")
    print(transcript_text[:500])

    short = transcript_text[:300].replace("<", "&lt;").replace(">", "&gt;")
    deal_info = f"\n🛒 Сделка #{result['deal_id']}" if result['deal_id'] else ""
    op_info = "\n🔄 Запрошен оператор" if result["operator"] else ""
    tg_notify(
        f"📞 <b>Анжела обзвонила {phone}</b>\n"
        f"📋 Тема: {topic} | {result['turns']} реплик{deal_info}{op_info}\n"
        f"<code>{short}</code>"
    )


if __name__ == "__main__":
    main()
