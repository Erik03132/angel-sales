#!/usr/bin/env python3
"""test_gemini_tts.py — Тест Gemini TTS для автодозвона

Запуск: python3 test_gemini_tts.py
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

# ───────────────────────────────────────────────────────────────
# Конфигурация
# ───────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PROXY = os.getenv("HTTPS_PROXY")

MESSAGE = (
    "Андрей, добрый вечер, вы недавно сделали заказ на 100 гусят с доставкой в Джанкой на 15 мая! "
    "Водитель с вами завтра свяжится! Если вы подтверждаете заказ на завтра — нажмите цифру один! "
    "Если у вас не получится — нажмите цифру ноль. Мы свяжемся с вами для уточнения. "
    "Всего доброго!"
)

if not GEMINI_API_KEY:
    print("🔴 GEMINI_API_KEY не найден!")
    sys.exit(1)

print(f"🔑 Gemini API Key: {GEMINI_API_KEY[:15]}...")
print(f"🌐 Прокси: {PROXY}")
print()

# ───────────────────────────────────────────────────────────────
# TTS запрос
# ───────────────────────────────────────────────────────────────
print("=" * 60)
print("🎤 Генерация речи через Gemini TTS")
print("=" * 60)
print(f"Текст: {MESSAGE}\n")

# Используем модель с TTS поддержкой
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"

payload = {
    "contents": [{"parts": [{"text": MESSAGE}]}],
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

try:
    resp = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, proxies=proxies, timeout=60)
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
            mime = part["inlineData"].get("mimeType", "")
            data = part["inlineData"].get("data", "")
            
            print("✅ Аудио найдено!")
            print(f"   MIME: {mime}")
            print(f"   Размер (base64): {len(data):,} символов")
            
            # Декодируем base64
            audio_bytes = base64.b64decode(data)
            print(f"   Размер (bytes): {len(audio_bytes):,}")
            
            # Gemini TTS выдает PCM 24kHz, 16-bit, mono
            # Сохраняем как WAV
            output_wav = Path(__file__).parent / "test_tts_output.wav"
            
            with wave.open(str(output_wav), "wb") as wav_file:
                wav_file.setnchannels(1)  # mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(24000)  # 24kHz
                wav_file.writeframes(audio_bytes)
            
            print(f"   💾 Сохранено: {output_wav}")
            
            # Длительность
            duration = len(audio_bytes) / (2 * 24000)  # 2 bytes per sample
            print(f"   ⏱️ Длительность: {duration:.2f} сек")
            
            # Также сохраним сырой PCM для теста
            output_pcm = Path(__file__).parent / "test_tts_output.pcm"
            with open(output_pcm, "wb") as f:
                f.write(audio_bytes)
            print(f"   💾 PCM: {output_pcm}")
            
            print("\n✅ TTS тест УСПЕШЕН!")
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
