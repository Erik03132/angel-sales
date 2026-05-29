#!/usr/bin/env python3
"""generate_call_script.py — Генерация аудио для автодозвона

Мой вариант скрипта (17 секунд)
"""

import base64
import os
import sys
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка .env
ENV_FILE = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_FILE)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROXY = os.getenv("HTTPS_PROXY")

if not GEMINI_API_KEY:
    print("🔴 GEMINI_API_KEY не найден!")
    sys.exit(1)

# ───────────────────────────────────────────────────────────────
# МОЙ ВАРИАНТ СКРИПТА (17 секунд)
# ───────────────────────────────────────────────────────────────
SCRIPT_TEXT = (
    "Андрей, добрый вечер! <pause:200ms> Это Анжела, Азовский Инкубатор. "
    "<pause:300ms> Вы заказали 100 гусят на 15 мая, Джанкой. "
    "<pause:400ms> Водитель позвонит вам завтра. "
    "<pause:500ms> Для подтверждения — нажмите 1. <pause:300ms> Для переноса — нажмите 0. "
    "<pause:400ms> Спасибо!"
)

# ───────────────────────────────────────────────────────────────
# Запрос к Gemini TTS
# ───────────────────────────────────────────────────────────────
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"

instruction = f"""Сгенерируй речь на русском языке.
Голос: тёплый, дружелюбный, но деловой.
Скорость: чуть медленнее обычного для чёткости цифр.
Тон: уверенный, позитивный.

Текст для озвучки:
{SCRIPT_TEXT}

Важно: соблюдай паузы между фразами. Цифры (100, 15, 1, 0) произноси чётко."""

payload = {
    "contents": [{"parts": [{"text": instruction}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": "Kore"}  # Нейтральный, профессиональный
            }
        }
    }
}

proxies = {"https": PROXY, "http": PROXY} if PROXY else None

# ───────────────────────────────────────────────────────────────
# Генерация
# ───────────────────────────────────────────────────────────────
print("=" * 60)
print("🎤 Генерация скрипта автодозвона (МОЙ ВАРИАНТ)")
print("=" * 60)
print(f"\n📝 Текст:\n{SCRIPT_TEXT.replace('<pause:200ms>', '').replace('<pause:300ms>', '').replace('<pause:400ms>', '').replace('<pause:500ms>', '')}\n")
print("⚙️ Параметры:")
print("   Голос: Kore (нейтральный, профессиональный)")
print("   Стиль: деловой, уверенный")
print()

try:
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, proxies=proxies, timeout=60)
    print(f"HTTP {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"🔴 Error: {resp.text[:500]}")
        sys.exit(1)
    
    result = resp.json()
    candidates = result.get("candidates", [])
    
    if not candidates:
        print("🔴 Нет candidates")
        sys.exit(1)
    
    parts = candidates[0].get("content", {}).get("parts", [])
    
    for part in parts:
        if "inlineData" in part:
            mime = part["inlineData"].get("mimeType", "")
            data = part["inlineData"].get("data", "")
            
            audio_bytes = base64.b64decode(data)
            
            # Сохранение WAV
            output_wav = Path(__file__).parent / "andrej_call_100_gosyat.wav"
            with wave.open(str(output_wav), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(audio_bytes)
            
            duration = len(audio_bytes) / (2 * 24000)
            
            print("✅ Готово!")
            print(f"   💾 {output_wav}")
            print(f"   ⏱️ {duration:.2f} сек")
            print(f"   📊 {len(audio_bytes):,} байт")
            print()
            print("🎯 Скрипт готов для загрузки в Mango Office!")
            break
    else:
        print("⚠️ Аудио не найдено в ответе")
        
except Exception as e:
    print(f"🔴 Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
