#!/usr/bin/env python3
"""generate_turkey_july24.py — WAV: дата 24 июля: текст от заказчика"""

import base64
import os
import sys
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROXY = os.getenv("HTTPS_PROXY")

if not GEMINI_API_KEY:
    print("GEMINI_API_KEY not found!")
    sys.exit(1)

CONFIRM_CALL_TEXT = (
    "Здравствуйте, это Азовский инкубатор. "
    "Ранее вы заказывали у нас индюшат — и мы рады сообщить: "
    "следующая партия породы Хайбрид конвертер, Канада доставляется двадцать четвёртого июля. "
    "Если вам интересно — скажите ДА или нажмите цифру один. "
    "Если не интересует — скажите нет или нажмите цифру ноль. "
    "Наши менеджеры свяжутся с вами для уточнения заказа. Ждём вашего ответа!"
)

OUTPUT_FILE = Path(__file__).parent / "tts_cache" / "turkey_july24.wav"

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

print(f"📝 Текст:\n{CONFIRM_CALL_TEXT}\n")
print("📡 Запрос к Gemini TTS...")

resp = requests.post(url, headers={"Content-Type": "application/json"},
    json=payload, proxies=proxies, timeout=60)
print(f"HTTP {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text[:500]}")
    sys.exit(1)

result = resp.json()
candidates = result.get("candidates", [])
if not candidates:
    print("No candidates")
    sys.exit(1)

parts = candidates[0].get("content", {}).get("parts", [])
for part in parts:
    if "inlineData" in part:
        audio_bytes = base64.b64decode(part["inlineData"]["data"])
        os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
        with wave.open(str(OUTPUT_FILE), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(audio_bytes)
        duration = len(audio_bytes) / (2 * 24000)
        print(f"✅ WAV: {OUTPUT_FILE} ({duration:.2f}s, {os.path.getsize(OUTPUT_FILE)//1024}KB)")
        break
