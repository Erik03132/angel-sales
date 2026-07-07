#!/usr/bin/env python3
"""generate_confirm_june11.py — Генерация WAV для автодозвона (дата: одиннадцатого июня)

Замена "завтра" → "одиннадцатого июня" в тексте CONFIRM_CALL_TEXT.
Голос: Kore (Gemini TTS), тот же что и в текущем WAV.

Запуск: python3 generate_confirm_june11.py
"""

import base64
import json
import os
import sys
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка .env
ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE)

# Очищаем прокси — Gemini TTS доступен напрямую с Mac, прокси только для VPS
for _pv in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
            "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_pv, None)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROXY = os.getenv("HTTPS_PROXY")

if not GEMINI_API_KEY:
    print("🔴 GEMINI_API_KEY не найден!")
    sys.exit(1)

# ───────────────────────────────────────────────────────────────
# ТЕКСТ АВТОДОЗВОНА — "завтра" заменено на "одиннадцатого июня"
# ───────────────────────────────────────────────────────────────
CONFIRM_CALL_TEXT = (
    "Здравствуйте, это Азовский инкубатор, "
    "ваш заказ доставим одиннадцатого июня. "
    "Для подтверждения заказа скажите ДА "
    "или нажмите цифру один на телефоне, "
    "или скажите НЕТ "
    "и нажмите цифру ноль. "
    "Всего вам доброго!"
)

OUTPUT_FILE = Path(__file__).parent / "tts_cache" / "confirm_call_june11.wav"

# ───────────────────────────────────────────────────────────────
# Gemini TTS запрос (голос Kore)
# ───────────────────────────────────────────────────────────────
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"

payload = {
    "contents": [{"parts": [{"text": CONFIRM_CALL_TEXT}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": "Kore"}
            }
        }
    }
}

proxies = {"https": PROXY, "http": PROXY} if PROXY else None

# ───────────────────────────────────────────────────────────────
# Генерация
# ───────────────────────────────────────────────────────────────
print("=" * 60)
print("🎤 Генерация WAV для автодозвона (одиннадцатого июня)")
print("=" * 60)
print(f"\n📝 Текст:\n{CONFIRM_CALL_TEXT}\n")
print("⚙️ Параметры:")
print("   Голос: Kore")
print(f"   🌐 Прокси: {PROXY}")
print()

try:
    print("📡 Отправляю запрос к Gemini TTS...")
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
        proxies=proxies,
        timeout=60,
    )
    print(f"HTTP {resp.status_code}")

    if resp.status_code != 200:
        print(f"🔴 Error: {resp.text[:500]}")
        sys.exit(1)

    result = resp.json()
    candidates = result.get("candidates", [])

    if not candidates:
        print("🔴 Нет candidates в ответе")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        sys.exit(1)

    parts = candidates[0].get("content", {}).get("parts", [])

    for part in parts:
        if "inlineData" in part:
            data = part["inlineData"].get("data", "")
            audio_bytes = base64.b64decode(data)

            # Gemini TTS: PCM 24kHz, 16-bit, mono
            os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
            with wave.open(str(OUTPUT_FILE), "wb") as wav_file:
                wav_file.setnchannels(1)       # mono
                wav_file.setsampwidth(2)       # 16-bit
                wav_file.setframerate(24000)   # 24kHz
                wav_file.writeframes(audio_bytes)

            duration = len(audio_bytes) / (2 * 24000)
            size_kb = os.path.getsize(OUTPUT_FILE) // 1024

            print("\n✅ WAV готов!")
            print(f"   💾 Файл: {OUTPUT_FILE}")
            print(f"   ⏱️ Длительность: {duration:.2f} сек")
            print(f"   📊 Размер: {size_kb} KB")
            print("\n🎯 Загрузите этот файл в ЛК Mango Office вместо старого!")
            break
    else:
        print("⚠️ Аудио не найдено в ответе")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        sys.exit(1)

except Exception as e:
    print(f"🔴 Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
