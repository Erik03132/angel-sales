#!/usr/bin/env python3
"""
voice_bridge.py — голосовой мост для входящих звонков.

Поток:
1. Ждёт событие inbound_call из mango_webhook → {call_id, phone}
2. Когда dec.wav (sndfile) начинает расти — клиент говорит
3. VAD + faster-whisper STT
4. CRM lookup (Bitrix24) по номеру
5. Angela (OpenRouter) → ответ
6. TTS (edge-tts) → upload to Mango → play/start
7. Loop до конца звонка
8. Логирование transcript + уведомление в TG

PM2: voice-angela
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Пути ──────────────────────────────────────────────────────────────────────
AGENT_DIR = Path(__file__).resolve().parent
BASE_DIR = AGENT_DIR.parent
for _env in (BASE_DIR / ".env", AGENT_DIR / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

# Import voice engine before clearing proxy — captures proxy/api_key at import time
from voice_engine import generate_call_tts

# Чистим прокси для прямых API (Mango, Bitrix, OpenRouter работают из РФ напрямую)
for _proxy in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
               "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_proxy, None)

# ── Конфиг ────────────────────────────────────────────────────────────────────
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
MANGO_API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/").rstrip("/") + "/"
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")
TELEGRAM_TOKEN = os.getenv("ANGELOCHKA_BOT_TOKEN", "")
OWNER_CHAT_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "176203333"))

EVENTS_PATH = Path("/var/log/voice-angela/events.jsonl")
DEC_WAV_PATH = Path("/root/dec.wav")
TTS_DIR = AGENT_DIR / "tts_cache"
TTS_DIR.mkdir(exist_ok=True)
LOG_DIR = Path("/var/log/voice-angela")
LOG_DIR.mkdir(parents=True, exist_ok=True)

SR = 8000
VAD_SILENCE_SEC = 1.2
MIN_SPEECH_SEC = 0.6
POLL_INTERVAL = 0.2
MAX_TURNS = 20

# Pre-uploaded audio IDs for common phrases (set by setup or first use)
GREETING_AUDIO_ID = os.getenv("VA_GREETING_AUDIO_ID", "")


# ── Mango API ─────────────────────────────────────────────────────────────────

def _sign(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((VPBX_API_KEY + raw + VPBX_API_SALT).encode()).hexdigest()


def mango_api(endpoint: str, data: dict) -> dict:
    url = MANGO_API_BASE + endpoint
    payload = {
        "vpbx_api_key": VPBX_API_KEY,
        "json": json.dumps(data, separators=(",", ":"), ensure_ascii=False),
        "sign": _sign(data),
    }
    try:
        resp = requests.post(url, data=payload, timeout=30,
                             headers={"User-Agent": "VoiceAngela/1.0"})
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:100]}"}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def mango_play(call_id: str, audio_id: str) -> bool:
    if not call_id or not audio_id:
        return False
    result = mango_api("commands/play/start", {
        "call_id": call_id,
        "command_id": f"va_{int(time.time()*1000)}",
        "audi_file_id": audio_id,
    })
    return result.get("result") == "SUCCESS" or "audi_file_id" in result


def mango_upload(path: Path) -> str:
    url = MANGO_API_BASE + "uploads/upload"
    ts = int(time.time() * 1000)
    s = hashlib.sha256((VPBX_API_KEY + str(ts) + VPBX_API_SALT).encode()).hexdigest()
    try:
        with open(path, "rb") as f:
            resp = requests.post(url,
                data={"vpbx_api_key": VPBX_API_KEY, "timestamp": ts, "sign": s},
                files={"file": (path.name, f, "audio/wav")},
                timeout=30, headers={"User-Agent": "VoiceAngela/1.0"})
        if resp.status_code != 200:
            return ""
        r = resp.json()
        return str(r.get("audi_file_id") or r.get("audio_id") or r.get("id", ""))
    except Exception as e:
        print(f"  ⚠ upload: {e}")
        return ""


# ── Events reader (tails events.jsonl) ─────────────────────────────────────────

class EventWatcher:
    def __init__(self, path: Path):
        self.path = path
        self._pos = path.stat().st_size if path.exists() else 0

    def read_events(self) -> list[dict]:
        if not self.path.exists() or self.path.stat().st_size <= self._pos:
            return []
        with open(self.path) as f:
            f.seek(self._pos)
            new = f.read()
            self._pos = f.tell()
        events = []
        for line in new.strip().splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return events


# ── VAD ────────────────────────────────────────────────────────────────────────

def energy_vad(audio: bytes, threshold: float = 0.02) -> bool:
    count = len(audio) // 2
    if count < 10:
        return False
    samples = struct.unpack(f"<{count}h", audio[:count * 2])
    rms = (sum(s * s for s in samples) / count) ** 0.5
    return rms > threshold * 32768


# ── STT ────────────────────────────────────────────────────────────────────────

_stt = None


def load_stt():
    global _stt
    if _stt is not None:
        return
    try:
        from faster_whisper import WhisperModel
        _stt = WhisperModel("base", device="cpu", compute_type="int8")
        print("  ✅ Whisper base loaded")
    except Exception as e:
        print(f"  ⚠ Whisper: {e}")


def transcribe(path: Path) -> str:
    load_stt()
    if _stt is None:
        return ""
    try:
        segs, _ = _stt.transcribe(str(path), language="ru", beam_size=3, vad_filter=True)
        return " ".join(s.text.strip() for s in segs)
    except Exception as e:
        print(f"  ⚠ STT: {e}")
        return ""


# ── TTS ────────────────────────────────────────────────────────────────────────

def generate_tts(text: str) -> Path | None:
    wav = generate_call_tts(text)
    return Path(wav) if wav else None


def generate_tts_and_upload(text: str, call_id: str) -> bool:
    wav = generate_tts(text)
    if not wav:
        return False
    audio_id = mango_upload(wav)
    if not audio_id:
        return False
    return mango_play(call_id, audio_id)


# ── CRM ────────────────────────────────────────────────────────────────────────

def find_contact(phone: str) -> dict | None:
    if not BITRIX_URL or not phone:
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
    except Exception as e:
        print(f"  ⚠ CRM: {e}")
    return None


# ── FAQ Cache ─────────────────────────────────────────────────────────────────

_faq_cache: dict[str, str] = {}
_faq_path = BASE_DIR / "data" / "faq_cache.json"
if _faq_path.exists():
    with open(_faq_path, "r", encoding="utf-8") as f:
        _faq_cache = json.load(f)
    print(f"  ✅ FAQ cache: {len(_faq_cache)} записей")

_NOISE = {
    "а", "и", "в", "на", "у", "вас", "ваш", "ваши", "мне", "мой",
    "ли", "бы", "же", "то", "не", "да", "нет", "как", "что",
    "есть", "это", "вот", "ещё", "еще", "уже", "или", "но",
    "здравствуйте", "добрый", "день", "привет", "пожалуйста",
    "подскажите", "скажите", "можно", "хотел", "хотела", "бы",
}


def _fingerprint(text: str) -> set[str]:
    q = re.sub(r"[^а-яёa-z0-9\s]", "", text.lower().strip())
    return {w for w in q.split() if w not in _NOISE and len(w) > 2}


_BREED_KEYWORDS = {
    "бройлер": "есть ли бройлеры",
    "цыпленок": "есть ли бройлеры",
    "цыплята": "есть ли бройлеры",
    "кобб": "цена бройлера",
    "росс": "цена бройлера",
    "муллард": "есть ли мулларды",
    "мулард": "муларды",
    "утка": "утки",
    "уток": "утки",
    "индюк": "индюки",
    "индейк": "индюки",
    "гусь": "гуси",
    "гусей": "гуси",
    "цесарк": "цесарки",
    "перепел": "перепела",
    "несушк": "несушки",
    "кур": "несушки",
}

_BREED_PATTERNS = [
    (r"какие.*(пород|вид|ассортимент|есть|наличи)", "что у вас есть"),
    (r"что.*(есть|продаёте|предлага)", "что у вас есть"),
    (r"расскаж.*(бройлер|цыпл)", "есть ли бройлеры"),
]


def lookup_faq(text: str) -> str | None:
    exact = text.lower().strip()
    for q, a in _faq_cache.items():
        if len(exact) < 40 and q.lower().strip() == exact:
            return a

    fp = _fingerprint(text)
    if not fp:
        return None

    best_score = 0
    best_answer = None
    for q, a in _faq_cache.items():
        qfp = _fingerprint(q)
        if not qfp:
            continue
        overlap = len(fp & qfp)
        score = overlap / max(len(qfp), 1)
        if score > best_score and score >= 0.6:
            best_score = score
            best_answer = a

    if best_answer:
        print(f"  ⚡ FAQ HIT (score={best_score:.1f}): '{text[:40]}' → '{best_answer[:60]}...'")
        return best_answer

    text_lower = text.lower()
    for keyword, faq_key in _BREED_KEYWORDS.items():
        if keyword in text_lower and faq_key in _faq_cache:
            print(f"  ⚡ FAQ BREED HIT: '{keyword}' → '{_faq_cache[faq_key][:60]}...'")
            return _faq_cache[faq_key]

    for pattern, faq_key in _BREED_PATTERNS:
        if re.search(pattern, text_lower) and faq_key in _faq_cache:
            print(f"  ⚡ FAQ PATTERN HIT: '{pattern}' → '{_faq_cache[faq_key][:60]}...'")
            return _faq_cache[faq_key]

    return None


# ── Knowledge (породы и цены) ─────────────────────────────────────────────────

_PRICE_CACHE: str | None = None


def load_price_context() -> str:
    global _PRICE_CACHE
    if _PRICE_CACHE:
        return _PRICE_CACHE

    price_path = BASE_DIR / "config" / "prices.json"
    if not price_path.exists():
        _PRICE_CACHE = ""
        return ""

    try:
        with open(price_path) as f:
            data = json.load(f)
        cats = data.get("categories", {})
        lines = ["Прайс-лист ВезёмЦыплят:"]
        for cat_key, cat_val in cats.items():
            if not isinstance(cat_val, dict):
                continue
            label = cat_val.get("label", cat_key)
            lines.append(f"\n{label}:")
            items = cat_val.get("items", {})
            for name, info in items.items():
                price = info.get("price", "?")
                desc = info.get("description", "")
                line = f"  {name}: {price}₽"
                if desc:
                    line += f" — {desc[:80]}"
                lines.append(line)

        contacts = data.get("contacts", {})
        lines.append(f"\nКонтакты: {contacts.get('phone_primary', '')}")
        lines.append(f"Доставка: {data.get('delivery', {}).get('days', '')}")

        _PRICE_CACHE = "\n".join(lines)
        return _PRICE_CACHE
    except Exception as e:
        print(f"  ⚠ price load: {e}")
        return ""


# ── Angela ─────────────────────────────────────────────────────────────────────

def angela_response(transcript: str, crm: dict | None = None, context: str = "") -> str:
    if not OPENROUTER_KEY:
        return "Извините, я временно недоступна. Оставьте номер — я перезвоню."

    crm_info = ""
    if crm:
        c = crm["contact"]
        name = f"{c.get('NAME','')} {c.get('LAST_NAME','')}".strip()
        if name:
            crm_info = f"\nКлиент: {name}"
        if crm.get("deals"):
            crm_info += "\nАктивные сделки: " + "; ".join(
                f"{d.get('TITLE','')} ({d.get('STAGE_ID','')})" for d in crm["deals"][:3]
            )

    price_ctx = load_price_context()

    prompt = (
        "Ты — Анжела, голосовой ассистент птицеводческого бизнеса ВезёмЦыплят (Азовский инкубатор). "
        "Разговор по телефону с потенциальным клиентом. Отвечай КРАТКО (1-3 предложения), "
        "естественно, как в живом разговоре. Не зачитывай весь прайс — отвечай по делу.\n"
        f"{crm_info}\n"
        f"{price_ctx}\n"
        f"{context}\n"
        "Если клиент просит оператора — ответь одной строкой: 'ПЕРЕКЛЮЧАЮ_ОПЕРАТОРА'\n"
        f"Клиент: {transcript}"
    )

    # Cascade: cloud → fast cloud → local
    for model in ["deepseek/deepseek-chat", "qwen/qwen-2.5-7b-instruct"]:
        try:
            r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 256, "temperature": 0.3},
                timeout=20)
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"].strip()
                print(f"  ✅ Angela [{model.split('/')[0]}]: {txt[:80]}...")
                return txt
        except Exception as e:
            print(f"  ⚠ Angela {model}: {str(e)[:60]}")

    # Local LLM fallback (Ollama llama3.2:1b)
    try:
        r = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3.2:1b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 120}
        }, timeout=45)
        if r.status_code == 200:
            txt = r.json().get("response", "").strip()
            print(f"  ✅ Angela [local]: {txt[:80]}...")
            return txt
    except Exception as e:
        print(f"  ⚠ Angela local: {str(e)[:60]}")

    return "Извините, повторите, пожалуйста."


# ── Utilities ─────────────────────────────────────────────────────────────────

def write_wav(path: Path, audio: bytes):
    with open(path, "wb") as f:
        f.write(struct.pack("<4sI4s", b"RIFF", 36 + len(audio), b"WAVE"))
        f.write(struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(struct.pack("<4sI", b"data", len(audio)))
        f.write(audio)


def tg_notify(text: str):
    if not TELEGRAM_TOKEN:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": OWNER_CHAT_ID, "text": text, "parse_mode": "HTML"})
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

class VoiceBridge:
    def __init__(self):
        self.running = True
        self.watcher = EventWatcher(EVENTS_PATH)
        self.call_id = ""
        self.phone = ""
        self.transcript: list[dict] = []
        self._last_dec_size = 0
        self._phrase = b""
        self._speech_end = 0.0
        self._prev_greeting_id = GREETING_AUDIO_ID

    def _wait_dec(self, timeout: float = 30) -> bool:
        """Wait for dec.wav to appear and start growing."""
        deadline = time.time() + timeout
        while self.running and time.time() < deadline:
            if DEC_WAV_PATH.exists():
                sz = DEC_WAV_PATH.stat().st_size
                if sz > 44:
                    self._last_dec_size = sz
                    return True
            time.sleep(POLL_INTERVAL)
        return False

    def _read_client_audio(self) -> bytes | None:
        if not DEC_WAV_PATH.exists():
            return None
        sz = DEC_WAV_PATH.stat().st_size
        if sz <= self._last_dec_size:
            return None
        with open(DEC_WAV_PATH, "rb") as f:
            f.seek(self._last_dec_size if self._last_dec_size > 44 else 44)
            data = f.read()
        self._last_dec_size = sz
        return data

    def _detect_phrase(self, audio: bytes) -> bytes | None:
        self._phrase += audio
        if len(self._phrase) < SR * 2 * MIN_SPEECH_SEC:
            return None
        # Check recent energy
        recent = self._phrase[-SR * 2:]
        has_speech = energy_vad(recent, 0.015)
        if has_speech:
            self._speech_end = time.time()
        elif self._speech_end > 0 and (time.time() - self._speech_end) > VAD_SILENCE_SEC:
            phrase = self._phrase
            self._phrase = b""
            self._speech_end = 0.0
            return phrase
        return None

    def run(self):
        print(f"{'='*50}")
        print(f"VOICE BRIDGE — {datetime.now():%Y-%m-%d %H:%M}")
        print(f"{'='*50}\n")
        tg_notify("🤖 Voice Angela запущена")

        while self.running:
            try:
                # Check for inbound call event
                events = self.watcher.read_events()
                inbound = None
                for ev in events:
                    if ev.get("type") == "inbound_call":
                        inbound = ev
                    elif ev.get("type") == "call_end":
                        pass  # handled below

                if not inbound:
                    time.sleep(0.5)
                    continue

                self.call_id = inbound.get("call_id", "")
                self.phone = inbound.get("phone", "")
                print(f"\n📞 Звонок! call_id={self.call_id[:20]} phone={self.phone}")

                # Wait for baresip to answer + dec.wav to appear
                if not self._wait_dec():
                    print("  ⚠ Нет dec.wav в течение 30с — пропускаю")
                    continue

                print("  ✅ dec.wav появился, обработка...")
                crm_ctx = find_contact(self.phone) if self.phone else None

                # Greeting
                self.transcript = [{"role": "system", "text": f"call_id={self.call_id} phone={self.phone}"}]
                greeting = "Здравствуйте! Это Анжела, ассистент ВезёмЦыплят. Чем могу помочь?"
                if self._prev_greeting_id:
                    mango_play(self.call_id, self._prev_greeting_id)
                else:
                    generate_tts_and_upload(greeting, self.call_id)

                # Conversation loop
                turn = 0
                while self.running:
                    if not DEC_WAV_PATH.exists():
                        print("  ⚠ dec.wav исчез — звонок завершён")
                        break

                    audio = self._read_client_audio()
                    if audio is None:
                        time.sleep(POLL_INTERVAL)
                        continue

                    phrase = self._detect_phrase(audio)
                    if not phrase:
                        continue

                    turn += 1
                    utt_path = TTS_DIR / f"utt_{turn}_{int(time.time())}.wav"
                    write_wav(utt_path, phrase)
                    text = transcribe(utt_path)

                    if not text.strip():
                        continue

                    self.transcript.append({"role": "client", "text": text})
                    print(f"\n  🗣 [t{turn}] {text[:120]}")

                    faq_answer = lookup_faq(text)
                    if faq_answer:
                        response = faq_answer
                    else:
                        context = ""
                        if turn > 2:
                            recent = self.transcript[-4:]
                            context = "История разговора:\n" + "\n".join(
                                f"{t['role']}: {t['text']}" for t in recent if t['role'] != 'system'
                            )
                        response = angela_response(text, crm_ctx, context)

                    if "ПЕРЕКЛЮЧАЮ_ОПЕРАТОРА" in response:
                        print("  🔄 Оператор")
                        break

                    self.transcript.append({"role": "angela", "text": response})
                    print(f"  🤖 [t{turn}] {response[:120]}")

                    generate_tts_and_upload(response, self.call_id)

                    if turn >= MAX_TURNS:
                        break

                # Call ended
                transcript_text = "\n".join(
                    f"{t['role']}: {t['text']}" for t in self.transcript
                )
                log_path = LOG_DIR / f"call_{self.call_id[:16]}.json"
                with open(log_path, "w") as f:
                    json.dump({"call_id": self.call_id, "phone": self.phone,
                               "transcript": self.transcript}, f, ensure_ascii=False, indent=2)

                short = transcript_text[:300].replace("<", "&lt;").replace(">", "&gt;")
                tg_notify(
                    f"📞 <b>Звонок завершён</b>\n"
                    f"📱 {self.phone or '?'} | {turn} реплик\n"
                    f"<code>{short}</code>"
                )
                print(f"  ✅ Звонок завершён ({turn} реплик)\n")

            except Exception as e:
                print(f"  ⚠ Error: {e}")
                traceback.print_exc()
                time.sleep(5)


def main():
    bridge = VoiceBridge()
    try:
        bridge.run()
    except KeyboardInterrupt:
        print("\nInterrupted")
        bridge.running = False
        tg_notify("🛑 Voice Angela остановлена")


if __name__ == "__main__":
    main()
