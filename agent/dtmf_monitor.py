#!/usr/bin/env python3
"""
👁️ DTMF + STT Monitor — мониторит baresip на DTMF и голосовые ответы.

Логика:
1. Парсит screen baresip на DTMF: received event: '1' (end=1)
2. При завершении звонка без DTMF → ищет запись (sndfile) → STT → ДА/НЕТ
3. Отправляет результат на http://localhost:8086/ (dtmf_handler.py)

Запуск: pm2 start /opt/dtmf_monitor.py --name dtmf-monitor --interpreter python3
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

# Добавляем /opt в path для speech_analyzer
sys.path.insert(0, "/opt")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dtmf-monitor")

# Конфигурация
DTMF_HANDLER_URL = os.getenv("DTMF_HANDLER_URL", "http://localhost:8086/")
SCREEN_SESSION = os.getenv("BARESIP_SCREEN", "sip_bot")
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "0.5"))
HARDCOPY_PATH = "/tmp/baresip_screen.txt"
RECORDINGS_DIR = "/tmp/call_recordings"
STT_ENABLED = os.getenv("STT_ENABLED", "1") == "1"

# Паттерны
DTMF_PATTERN = re.compile(r"received event:\s*'(\d)'\s*\(end=1\)")
CALL_PATTERN = re.compile(r"Call established:\s*sip:(\d+)@")
# Полная строка: Call with sip:79859234644@mangosip.ru terminated (duration: 22 secs)
HANGUP_PATTERN = re.compile(r"Call with sip:(\d+)@.*termi")
# Обрезанная строка screen: nated (duration: 22 secs)
HANGUP_DURATION = re.compile(r"(?:termi)?nated\s*\(duration:\s*(\d+)\s*secs?\)")

# Состояние
_last_content = ""
_current_call_phone = ""
_current_call_start = 0
_got_dtmf = False
_processed_events = set()

# Lazy-load Whisper
_whisper = None


def _get_whisper():
    """Загружаем Whisper модель один раз."""
    global _whisper
    if _whisper is None and STT_ENABLED:
        try:
            from faster_whisper import WhisperModel
            log.info("📥 Whisper: загружаю модель tiny...")
            t0 = time.time()
            _whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
            log.info(f"✅ Whisper: готов за {time.time()-t0:.1f}с")
        except ImportError:
            log.error("❌ Whisper: pip install faster-whisper")
        except Exception as e:
            log.error(f"❌ Whisper: {e}")
    return _whisper


def transcribe_and_classify(audio_path: str) -> dict:
    """STT → классификация ДА/НЕТ."""
    model = _get_whisper()
    if not model or not os.path.exists(audio_path):
        return {"answer": "unclear", "text": "", "confidence": 0.0}

    try:
        t0 = time.time()
        segments, info = model.transcribe(
            audio_path,
            language="ru",
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 100},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        elapsed = time.time() - t0
        log.info(f"🎤 STT: '{text}' ({elapsed:.1f}с)")

        # Классификация
        text_lower = text.lower()
        yes_re = re.compile(r'\b(да|ага|угу|конечно|подтвержд|хорошо|ладно|окей|ок|согласе|yes|ok)\b', re.I)
        no_re = re.compile(r'\b(нет|не надо|не буду|отмен|откаж|ноль|no|cancel)\b', re.I)

        yes_m = yes_re.search(text_lower)
        no_m = no_re.search(text_lower)

        if yes_m and not no_m:
            return {"answer": "yes", "text": text, "confidence": 0.85, "matched": yes_m.group()}
        elif no_m and not yes_m:
            return {"answer": "no", "text": text, "confidence": 0.85, "matched": no_m.group()}
        else:
            return {"answer": "unclear", "text": text, "confidence": 0.3, "matched": ""}
    except Exception as e:
        log.error(f"❌ STT error: {e}")
        return {"answer": "unclear", "text": "", "confidence": 0.0}


def find_latest_recording() -> str | None:
    """Найти последнюю ВХОДЯЩУЮ запись (dec = decoded = голос клиента)."""
    # sndfile создаёт 2 файла: *-enc.wav (наш голос) и *-dec.wav (голос клиента)
    # Нам нужен ТОЛЬКО dec!
    patterns = ["/root/*-dec.wav", "/tmp/call_recordings/*-dec.wav"]
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat))

    if not files:
        return None

    # Самый свежий файл
    latest = max(files, key=os.path.getmtime)
    age = time.time() - os.path.getmtime(latest)

    # Только если создан менее 30 сек назад
    if age < 30:
        log.info(f"📁 Найдена запись: {latest} ({age:.0f}с назад)")
        return latest

    return None


def send_result(digit: str, phone: str = "", source: str = "dtmf", text: str = ""):
    """Отправить результат на handler."""
    payload = json.dumps({
        "digit": digit,
        "phone": phone,
        "call_id": f"baresip_{int(time.time())}",
        "source": source,
        "text": text,
        "timestamp": datetime.now().isoformat(),
    }).encode("utf-8")

    try:
        req = Request(DTMF_HANDLER_URL, data=payload, headers={"Content-Type": "application/json"})
        resp = urlopen(req, timeout=5)
        result = resp.read().decode()
        log.info(f"✅ {source} '{digit}' отправлен → {result}")
        return True
    except URLError as e:
        log.error(f"❌ Не удалось отправить: {e}")
        return False


def get_screen_content() -> str:
    """Получить текущий вывод screen-сессии baresip."""
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
    """Обработать новые строки из baresip."""
    global _current_call_phone, _current_call_start, _got_dtmf

    for line in new_content.split("\n"):
        line = line.strip()
        if not line:
            continue

        # === DTMF ===
        dtmf_match = DTMF_PATTERN.search(line)
        if dtmf_match:
            digit = dtmf_match.group(1)
            event_key = f"{digit}_{int(time.time())}"
            if event_key not in _processed_events:
                _processed_events.add(event_key)
                _got_dtmf = True
                log.info(f"🔢 DTMF: '{digit}' от {_current_call_phone or 'unknown'}")
                send_result(digit, _current_call_phone, source="dtmf")

        # === Звонок установлен ===
        call_match = CALL_PATTERN.search(line)
        if call_match:
            _current_call_phone = call_match.group(1)
            _current_call_start = time.time()
            _got_dtmf = False
            log.info(f"📞 Звонок установлен: {_current_call_phone}")

        # === Звонок завершён ===
        # Ловим полную строку ИЛИ обрезанную (screen разбивает на 2 строки)
        hangup_match = HANGUP_PATTERN.search(line)
        if hangup_match:
            phone = hangup_match.group(1)
            _current_call_phone = phone  # запоминаем для следующей строки

        # Ловим duration (может быть на той же или следующей строке)
        duration_match = HANGUP_DURATION.search(line)
        if duration_match:
            duration = int(duration_match.group(1))
            phone = _current_call_phone or "unknown"
            log.info(f"📴 Звонок завершён: {phone} ({duration}с)")

            if not _got_dtmf and duration > 5 and STT_ENABLED:
                # Нет DTMF — пробуем STT
                log.info("🎤 Нет DTMF — запускаю STT анализ...")
                time.sleep(1)  # Даём sndfile дозаписать

                recording = find_latest_recording()
                if recording:
                    result = transcribe_and_classify(recording)
                    answer = result.get("answer", "unclear")
                    text = result.get("text", "")

                    if answer == "yes":
                        send_result("1", phone, source="stt", text=text)
                    elif answer == "no":
                        send_result("0", phone, source="stt", text=text)
                    else:
                        log.info(f"❓ STT: непонятный ответ — '{text}'")
                        send_result("?", phone, source="stt", text=text)
                else:
                    log.warning("⚠️ Нет записи для STT")

            _current_call_phone = ""
            _got_dtmf = False

    # Чистка старых событий
    now = int(time.time())
    old = {k for k in _processed_events if int(k.split("_")[-1]) < now - 60}
    _processed_events.difference_update(old)


def main():
    """Основной цикл мониторинга."""
    global _last_content

    log.info("🚀 DTMF+STT Monitor запущен")
    log.info(f"   Screen: {SCREEN_SESSION}")
    log.info(f"   Handler: {DTMF_HANDLER_URL}")
    log.info(f"   STT: {'✅ enabled' if STT_ENABLED else '❌ disabled'}")

    # Прогреваем Whisper
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
        log.info("🛑 Stopped")

