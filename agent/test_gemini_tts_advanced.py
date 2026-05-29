#!/usr/bin/env python3
"""test_gemini_tts_advanced.py — Продвинутый TTS с настройкой голоса

Запуск: python3 test_gemini_tts_advanced.py
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
# Текст сценария с паузами (SSML-подобный синтаксис)
# ───────────────────────────────────────────────────────────────
SCRIPT = {
    "text": "Андрей, добрый вечер! <pause:500ms> Вы недавно сделали заказ на 100 гусят с доставкой в Джанкой на 15 мая. <pause:300ms> Водитель с вами завтра свяжется! <pause:400ms> Если вы подтверждаете заказ на завтра — нажмите цифру один. <pause:600ms> Если у вас не получится — нажмите цифру ноль. <pause:400ms> Мы свяжемся с вами для уточнения. <pause:300ms> Всего доброго!",
    "style": "friendly",  # friendly, professional, warm, authoritative
    "pitch": 0.0,  # -2.0 до +2.0 (0 = нормально)
    "rate": 1.0,  # 0.5 до 2.0 (1.0 = нормально)
    "volume": 0.0,  # -10 до +10 dB (0 = нормально)
}

# ───────────────────────────────────────────────────────────────
# Доступные голоса
# ───────────────────────────────────────────────────────────────
VOICES = {
    "Kore": "Нейтральный, профессиональный (по умолчанию)",
    "Puck": "Дружелюбный, тёплый",
    "Charon": "Авторитетный, серьёзный",
    "Fenrir": "Энергичный, молодой",
    "Aoede": "Мягкий, заботливый",
    "Callirrhoe": "Уверенный, деловой",
}

# ───────────────────────────────────────────────────────────────
# Конфигурация запроса
# ───────────────────────────────────────────────────────────────
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"

# Инструкция для модели с настройками
instruction = f"""Сгенерируй речь на русском языке с параметрами:
- Стиль: {SCRIPT['style']}
- Тон: {SCRIPT['pitch']} (pitch)
- Скорость: {SCRIPT['rate']}x
- Громкость: {SCRIPT['volume']} dB

Текст для озвучки:
{SCRIPT['text']}

Важно: соблюдай паузы между предложениями для естественности."""

payload = {
    "contents": [{"parts": [{"text": instruction}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {
                "prebuiltVoiceConfig": {"voiceName": "Kore"}  # Можно менять: Puck, Charon, Fenrir, Aoede, Callirrhoe
            }
        }
    }
}

proxies = {"https": PROXY, "http": PROXY} if PROXY else None

# ───────────────────────────────────────────────────────────────
# Запрос к API
# ───────────────────────────────────────────────────────────────
print("=" * 60)
print("🎤 Продвинутый TTS с настройкой")
print("=" * 60)
print(f"\n📝 Текст:\n{SCRIPT['text']}\n")
print("⚙️ Параметры:")
print("   Голос: Kore")
print(f"   Стиль: {SCRIPT['style']}")
print(f"   Pitch: {SCRIPT['pitch']}")
print(f"   Rate: {SCRIPT['rate']}x")
print(f"   Volume: {SCRIPT['volume']} dB")
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
            output_wav = Path(__file__).parent / "test_tts_advanced.wav"
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
            break
    else:
        print("⚠️ Аудио не найдено")
        
except Exception as e:
    print(f"🔴 Ошибка: {e}")
    sys.exit(1)
