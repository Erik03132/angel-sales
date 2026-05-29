#!/usr/bin/env python3
"""
DTMF + STT Monitor — monitors baresip for DTMF and voice responses.
v2: base model + crop last 8s + resample 16kHz + fuzzy classifier
"""
import glob
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, "/opt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dtmf-monitor")

DTMF_HANDLER_URL = os.getenv("DTMF_HANDLER_URL", "http://localhost:8086/")
SCREEN_SESSION = os.getenv("BARESIP_SCREEN", "sip_bot")
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "0.5"))
HARDCOPY_PATH = "/tmp/baresip_screen.txt"
RECORDINGS_DIR = "/tmp/call_recordings"
STT_ENABLED = os.getenv("STT_ENABLED", "1") == "1"
# Сколько секунд с конца записи брать для STT (ответ человека — в конце)
CROP_LAST_SECS = int(os.getenv("CROP_LAST_SECS", "8"))

DTMF_PATTERN = re.compile(r"received event:\s*'(\d)'\s*\(end=1\)")
CALL_PATTERN = re.compile(r"Call established:\s*sip:(\d+)@")
HANGUP_PATTERN = re.compile(r"Call with sip:(\d+)@.*termi")
HANGUP_DURATION = re.compile(r"(?:termi)?nated\s*\(duration:\s*(\d+)\s*secs?\)")

_last_content = ""
_current_call_phone = ""
_current_call_start = 0
_got_dtmf = False
_processed_events = set()
_whisper = None


def _get_whisper():
    global _whisper
    if _whisper is None and STT_ENABLED:
        try:
            from faster_whisper import WhisperModel
            log.info("Loading Whisper base...")
            t0 = time.time()
            _whisper = WhisperModel("base", device="cpu", compute_type="int8")
            log.info(f"Whisper base ready in {time.time()-t0:.1f}s")
        except ImportError:
            log.error("pip install faster-whisper")
        except Exception as e:
            log.error(f"Whisper error: {e}")
    return _whisper


def _preprocess_audio(audio_path: str) -> str:
    """Crop last N seconds + resample to 16kHz for better Whisper accuracy."""
    out_path = "/tmp/stt_preprocessed.wav"
    try:
        cmd = [
            "sox", audio_path,
            "-r", "16000",        # resample to 16kHz (Whisper native)
            out_path,
            "trim", f"-{CROP_LAST_SECS}",  # last N seconds only
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and os.path.exists(out_path):
            size = os.path.getsize(out_path)
            log.info(f"Preprocessed: crop -{CROP_LAST_SECS}s, 16kHz, {size} bytes")
            return out_path
        else:
            log.warning(f"sox failed: {result.stderr}")
    except Exception as e:
        log.warning(f"Preprocess error: {e}")
    return audio_path  # fallback to original


def _fuzzy_match(text: str, targets: list, threshold: int = 3) -> bool:
    """Simple edit-distance fuzzy match for garbled STT output."""
    text_lower = text.lower()
    for target in targets:
        # Direct substring
        if target in text_lower:
            return True
        # Check each word
        for word in re.split(r'\s+', text_lower):
            word = re.sub(r'[^\wа-яё]', '', word)
            if not word:
                continue
            # Levenshtein distance
            dist = _levenshtein(word, target)
            if dist <= threshold:
                log.info(f"Fuzzy match: '{word}' ~ '{target}' (dist={dist})")
                return True
    return False


def _levenshtein(s1: str, s2: str) -> int:
    """Classic Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,      # deletion
                curr[j] + 1,           # insertion
                prev[j] + (c1 != c2),  # substitution
            ))
        prev = curr
    return prev[len(s2)]


def transcribe_and_classify(audio_path: str) -> dict:
    model = _get_whisper()
    if not model or not os.path.exists(audio_path):
        return {"answer": "unclear", "text": "", "confidence": 0.0}
    try:
        # Preprocess: crop + resample
        processed = _preprocess_audio(audio_path)

        t0 = time.time()
        # NO vad_filter — мы уже обрезали до последних 8 сек
        segments, info = model.transcribe(
            processed, language="ru", beam_size=3, vad_filter=False,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        elapsed = time.time() - t0

        dur = info.duration
        log.info(f"Processing audio with duration {int(dur//60):02d}:{dur%60:06.3f}")
        log.info(f"STT: '{text}' ({elapsed:.1f}s)")

        text_lower = text.lower().strip()

        if not text_lower:
            return {"answer": "unclear", "text": "", "confidence": 0.0}

        # === PRIORITY-BASED FUZZY CLASSIFIER ===

        # 1. Explicit negation words first (highest priority)
        if re.search(r'\bнет\b', text_lower):
            return {"answer": "no", "text": text, "confidence": 0.95, "matched": "explicit no"}

        # 2. Negated confirmations — "не подтвержд*", "не подтвердал" etc.
        if re.search(r'не\s+(подтвер|соглас|надо|хочу|будем|можем|будет)', text_lower):
            return {"answer": "no", "text": text, "confidence": 0.9, "matched": "negated confirmation"}
        if _fuzzy_match(text, ["неподтверждаю", "неподтвердил", "неподтвердал"], threshold=3):
            return {"answer": "no", "text": text, "confidence": 0.85, "matched": "fuzzy negation"}

        # 3. Cancellation words
        if re.search(r'\b(отмен|откаж|ноль|отказ)\b', text_lower):
            return {"answer": "no", "text": text, "confidence": 0.9, "matched": "cancellation"}

        # 4. Explicit yes
        if re.search(r'\b[оа]?да\b', text_lower):  # "да", "ода", "ада"
            return {"answer": "yes", "text": text, "confidence": 0.95, "matched": "explicit yes"}
        if re.search(r'\b(ага|угу)\b', text_lower):
            return {"answer": "yes", "text": text, "confidence": 0.9, "matched": "explicit yes"}

        # 5. Confirmation words (exact)
        if re.search(r'\b(подтвержд|конечно|хорошо|ладно|окей|ок|ok|соглас|yes|давай|принял|принято)\b', text_lower):
            return {"answer": "yes", "text": text, "confidence": 0.85, "matched": "confirmation"}

        # 6. Fuzzy confirmation — catch garbled "подтверждаю" variants
        #    "подквердая", "потверждаю", "подтвердал" etc.
        if _fuzzy_match(text, ["подтверждаю", "подтвердил", "подтверждаем"], threshold=4):
            return {"answer": "yes", "text": text, "confidence": 0.8, "matched": "fuzzy confirmation"}
        if _fuzzy_match(text, ["согласен", "согласна", "соглашаюсь"], threshold=3):
            return {"answer": "yes", "text": text, "confidence": 0.8, "matched": "fuzzy agreement"}

        # 7. Other negatives
        if re.search(r'\b(не\s+зна|не\s+мог|не\s+нуж|no|cancel)\b', text_lower):
            return {"answer": "no", "text": text, "confidence": 0.7, "matched": "other negative"}

        return {"answer": "unclear", "text": text, "confidence": 0.3, "matched": ""}
    except Exception as e:
        log.error(f"STT error: {e}")
        return {"answer": "unclear", "text": "", "confidence": 0.0}


def find_latest_recording() -> str | None:
    patterns = ["/root/*-dec.wav", "/tmp/call_recordings/*-dec.wav"]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat))
    if not files:
        return None
    latest = max(files, key=os.path.getmtime)
    age = time.time() - os.path.getmtime(latest)
    if age < 30:
        log.info(f"Found recording: {latest} ({age:.0f}s old)")
        return latest
    return None


def send_result(digit: str, phone: str = "", source: str = "dtmf", text: str = ""):
    payload = json.dumps({
        "digit": digit, "phone": phone,
        "call_id": f"baresip_{int(time.time())}",
        "source": source, "text": text,
        "timestamp": datetime.now().isoformat(),
    }).encode("utf-8")
    try:
        req = Request(DTMF_HANDLER_URL, data=payload, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=5)
        result = resp.read().decode()
        log.info(f"Sent '{digit}' -> {result}")
        return True
    except URLError as e:
        log.error(f"Send failed: {e}")
        return False


def get_screen_content() -> str:
    try:
        subprocess.run(
            ["screen", "-S", SCREEN_SESSION, "-X", "hardcopy", HARDCOPY_PATH],
            capture_output=True, timeout=3,
        )
        with open(HARDCOPY_PATH, "r", errors="replace") as f:
            return f.read()
    except Exception as e:
        log.error(f"Screen error: {e}")
        return ""


def process_new_content(new_content: str):
    global _current_call_phone, _current_call_start, _got_dtmf
    for line in new_content.split("\n"):
        line = line.strip()
        if not line:
            continue
        dtmf_match = DTMF_PATTERN.search(line)
        if dtmf_match:
            digit = dtmf_match.group(1)
            event_key = f"{digit}_{int(time.time())}"
            if event_key not in _processed_events:
                _processed_events.add(event_key)
                _got_dtmf = True
                log.info(f"DTMF: '{digit}' from {_current_call_phone or 'unknown'}")
                send_result(digit, _current_call_phone, source="dtmf")
        call_match = CALL_PATTERN.search(line)
        if call_match:
            _current_call_phone = call_match.group(1)
        hangup_match = HANGUP_PATTERN.search(line)
        if hangup_match:
            phone = hangup_match.group(1)
            _current_call_phone = phone
        duration_match = HANGUP_DURATION.search(line)
        if duration_match:
            duration = int(duration_match.group(1))
            phone = _current_call_phone or "unknown"
            log.info(f"Call ended: {phone} ({duration}s)")
            if not _got_dtmf and duration > 5 and STT_ENABLED:
                log.info("No DTMF — running STT...")
                time.sleep(1)
                recording = find_latest_recording()
                if recording:
                    result = transcribe_and_classify(recording)
                    answer = result.get("answer", "unclear")
                    text = result.get("text", "")
                    matched = result.get("matched", "")
                    if answer == "yes":
                        log.info(f"YES detected: '{text}' (matched: {matched})")
                        send_result("1", phone, source="stt", text=text)
                    elif answer == "no":
                        log.info(f"NO detected: '{text}' (matched: {matched})")
                        send_result("0", phone, source="stt", text=text)
                    else:
                        log.info(f"Unclear STT: '{text}'")
                        send_result("?", phone, source="stt", text=text)
                else:
                    log.warning("No recording for STT")
            _current_call_phone = ""
            _got_dtmf = False
    now = int(time.time())
    old = {k for k in _processed_events if int(k.split("_")[-1]) < now - 60}
    _processed_events.difference_update(old)


def main():
    global _last_content
    log.info("DTMF+STT Monitor v2 started (base + crop + fuzzy)")
    log.info(f"  Screen: {SCREEN_SESSION}")
    log.info(f"  Handler: {DTMF_HANDLER_URL}")
    log.info(f"  STT: {'enabled' if STT_ENABLED else 'disabled'}")
    log.info(f"  Crop: last {CROP_LAST_SECS}s + resample 16kHz")
    if STT_ENABLED:
        _get_whisper()
    while True:
        content = get_screen_content()
        if content and content != _last_content:
            if _last_content:
                old_lines = set(_last_content.strip().split("\n"))
                new_lines = [l for l in content.strip().split("\n") if l.strip() not in old_lines]
                new_content = "\n".join(new_lines)
            else:
                new_content = content
            if new_content.strip():
                process_new_content(new_content)
            _last_content = content
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped")
