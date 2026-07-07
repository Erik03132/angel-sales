#!/usr/bin/env python3
"""
test_voice_local.py — локальный симулятор звонка Voice Angela.

Не требует Mango, SIP и телефона. Имитирует входящий звонок:
1. Создаёт WAV-файл с вопросом клиента (macOS say)
2. Пропускает через VAD + Whisper
3. Angela формирует ответ
4. Генерирует TTS (macOS say / edge-tts / Gemini Kore)
5. Сохраняет transcript и аудио-ответ

Запуск: python3 test_voice_local.py ["вопрос клиента"]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

AGENT_DIR = Path(__file__).resolve().parent
BASE_DIR = AGENT_DIR.parent
for _env in (BASE_DIR / ".env", AGENT_DIR / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

# Очищаем прокси для прямых API
for _p in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
           "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_p, None)

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
SR = 8000
TTS_DIR = AGENT_DIR / "tts_cache"
TTS_DIR.mkdir(exist_ok=True)


def say_to_wav(text: str, out: Path, voice: str = "Milena") -> Path:
    """Generate WAV 8kHz mono s16 from macOS say."""
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text],
                   capture_output=True, check=True, timeout=30)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(aiff),
        "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16",
        str(out)
    ], capture_output=True, check=True, timeout=15)
    aiff.unlink(missing_ok=True)
    return out


def load_prices() -> str:
    pp = BASE_DIR / "config" / "prices.json"
    if not pp.exists():
        return ""
    with open(pp) as f:
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
    return "\n".join(lines)


def angela(question: str, history: str = "") -> str:
    prompt = (
        "Ты — Анжела, голосовой ассистент птицеводческого бизнеса ВезёмЦыплят. "
        "Отвечай КРАТКО (1-3 предложения), естественно, по делу.\n"
        f"{load_prices()}\n{history}\n"
        "Если клиент просит оператора — ответь: 'ПЕРЕКЛЮЧАЮ_ОПЕРАТОРА'\n"
        f"Клиент: {question}"
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
            print(f"  ⚠ {model}: {e}")
    return "Извините, повторите, пожалуйста."


def tts_macos(text: str, out: Path) -> Path:
    return say_to_wav(text, out)


def tts_kore(text: str, out: Path) -> Path | None:
    if not GEMINI_KEY:
        return None
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_KEY}")
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}}
        }
    }
    try:
        r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
        if r.status_code != 200:
            print(f"  ⚠ Gemini: HTTP {r.status_code}")
            return None
        parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                audio = __import__("base64").b64decode(part["inlineData"]["data"])
                raw = TTS_DIR / f"kore_{int(time.time()*1000)}.raw"
                with open(raw, "wb") as f:
                    f.write(audio)
                subprocess.run([
                    "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                    "-i", str(raw), "-ar", str(SR), "-ac", "1", "-sample_fmt", "s16",
                    str(out)
                ], capture_output=True, timeout=15)
                raw.unlink(missing_ok=True)
                if out.exists():
                    return out
    except Exception as e:
        print(f"  ⚠ Gemini Kore: {e}")
    return None


def generate_tts(text: str) -> Path:
    out = TTS_DIR / f"angela_{int(time.time()*1000)}.wav"
    # Try Gemini Kore first on Mac (will likely fail due to region, fallback to macOS)
    if shutil.which("ffmpeg"):
        kore = tts_kore(text, out)
        if kore:
            print("  🔊 TTS: Gemini Kore")
            return kore
    print("  🔊 TTS: macOS Milena")
    return tts_macos(text, out)


def transcribe(path: Path) -> str:
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(path), language="ru", beam_size=3, vad_filter=True)
        return " ".join(s.text.strip() for s in segs)
    except Exception as e:
        print(f"  ⚠ Whisper: {e}")
        return ""


def play(path: Path):
    if sys.platform == "darwin":
        subprocess.run(["afplay", str(path)], check=False)
    else:
        subprocess.run(["ffplay", "-nodisp", "-autoexit", str(path)], check=False)


def main():
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Сколько стоят бройлеры?"
    print(f"{'='*60}")
    print("ЛОКАЛЬНЫЙ ТЕСТ VOICE ANGELA")
    print(f"Вопрос клиента: {question}")
    print(f"{'='*60}\n")

    # 1. Generate client question audio
    print("1️⃣  Генерирую аудио вопроса клиента...")
    client_wav = TTS_DIR / "client_question.wav"
    say_to_wav(question, client_wav)
    print(f"   ✅ {client_wav} ({client_wav.stat().st_size} bytes)")

    # 2. STT
    print("\n2️⃣  Распознаю речь (Whisper)...")
    recognized = transcribe(client_wav)
    print(f"   🗣 Распознано: {recognized}")

    # 3. Angela
    print("\n3️⃣  Angela думает...")
    answer = angela(recognized)
    print(f"   🤖 Angela: {answer}")

    # 4. TTS
    print("\n4️⃣  Генерирую голосовой ответ...")
    response_wav = generate_tts(answer)
    print(f"   ✅ {response_wav}")

    # 5. Play
    print("\n5️⃣  Воспроизвожу ответ Angela...")
    play(response_wav)

    # 6. Save transcript
    transcript = {
        "client_question": question,
        "recognized": recognized,
        "angela_answer": answer,
        "client_audio": str(client_wav),
        "response_audio": str(response_wav),
    }
    report = TTS_DIR / f"transcript_{int(time.time())}.json"
    with open(report, "w") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    print(f"\n📄 Transcript сохранён: {report}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
