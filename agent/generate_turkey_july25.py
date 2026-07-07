#!/usr/bin/env python3
"""
Генерация WAV для обзвона клиентов индюшат — июль 2026.
Текст: предложение индюшат с доставкой 25 июля.
Голос: Gemini TTS Kore. Формат: 8kHz mono pcm_s16le.
Структура: 7с тишина + голос + 0.5с бип 800Hz + 10с тишина
"""
import base64
import os
import subprocess
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv("/root/antigravity/ai-eggs/.env", override=True)

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
PROXY   = os.getenv("HTTPS_PROXY") or os.getenv("TELEGRAM_PROXY")

TEXT = (
    "Здравствуйте! Это Азовский инкубатор. "
    "Ранее вы заказывали у нас индюшат — и мы рады сообщить: "
    "следующая партия доставляется двадцать пятого июля. "
    "Если вам интересно — скажите ДА или нажмите цифру один. "
    "Если не интересует — скажите нет или нажмите цифру ноль. "
    "Наши менеджеры свяжутся с вами для уточнения заказа. Ждём вашего ответа!"
)

OUT_DIR = Path("/root/antigravity/ai-eggs/agent/tts_cache")
OUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_WAV  = OUT_DIR / "turkey_july25.wav"
FINAL_WAV = Path("/tmp/mango_play_turkey_july25.wav")

print(f"Текст ({len(TEXT)} символов):")
print(f"  {TEXT[:80]}...")
print(f"Прокси: {PROXY or 'нет'}")

# === Шаг 1: Gemini TTS (Kore) ===
print("\n=== Шаг 1: Gemini TTS ===")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={API_KEY}"
payload = {
    "contents": [{"parts": [{"text": TEXT}]}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}
        }
    }
}
proxies = {"https": PROXY, "http": PROXY} if PROXY else None
r = requests.post(url, json=payload, proxies=proxies, timeout=60)
if r.status_code != 200:
    print(f"ОШИБКА: HTTP {r.status_code}")
    print(r.text[:500])
    exit(1)

data = r.json()
audio_b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
audio_bytes = base64.b64decode(audio_b64)
print(f"  Получено: {len(audio_bytes)} байт аудио (PCM 24kHz)")

# Сохраняем RAW WAV 24kHz
with wave.open(str(RAW_WAV), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(24000)
    w.writeframes(audio_bytes)
dur = len(audio_bytes) / 2 / 24000
print(f"  Сохранено: {RAW_WAV} ({dur:.1f}с, 24kHz)")

# === Шаг 2: Сборка финального WAV (8kHz) ===
print("\n=== Шаг 2: Сборка финального WAV ===")
WORK = Path("/tmp/_turkey_build")
WORK.mkdir(exist_ok=True)

voice_8k   = WORK / "voice_8k.wav"
silence_7s = WORK / "silence_7s.wav"
bip        = WORK / "bip.wav"
silence_10 = WORK / "silence_10s.wav"
list_txt   = WORK / "concat.txt"

# Конвертируем голос 24kHz → 8kHz mono
subprocess.run([
    "ffmpeg", "-y", "-i", str(RAW_WAV),
    "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", str(voice_8k)
], check=True, capture_output=True)

dur8 = int(subprocess.check_output(
    ["soxi", "-D", str(voice_8k)]).decode().strip().split(".")[0])
print(f"  Голос 8kHz: {dur8}с")

# Части
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "anullsrc=r=8000:cl=mono",
    "-t", "7", "-acodec", "pcm_s16le", str(silence_7s)
], check=True, capture_output=True)

subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "sine=frequency=800:sample_rate=8000",
    "-t", "0.5", "-acodec", "pcm_s16le", str(bip)
], check=True, capture_output=True)

subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", "anullsrc=r=8000:cl=mono",
    "-t", "10", "-acodec", "pcm_s16le", str(silence_10)
], check=True, capture_output=True)

# Склейка: 7с тишина + голос + бип + 10с тишина
subprocess.run([
    "ffmpeg", "-y",
    "-i", str(silence_7s),
    "-i", str(voice_8k),
    "-i", str(bip),
    "-i", str(silence_10),
    "-filter_complex", "[0:a][1:a][2:a][3:a]concat=n=4:v=0:a=1[out]",
    "-map", "[out]",
    "-acodec", "pcm_s16le",
    str(FINAL_WAV)
], check=True, capture_output=True)

# Проверка
with wave.open(str(FINAL_WAV)) as w:
    total_sec = w.getnframes() / w.getframerate()
    print(f"  Готово: {FINAL_WAV}")
    print(f"  Формат: {w.getframerate()}Hz, {w.getnchannels()}ch, {total_sec:.1f}с")

print("\n✅ Медиафайл создан!")
print(f"   Голос (24kHz): {RAW_WAV}")
print(f"   Финальный WAV: {FINAL_WAV}")
print("\nДля активации скопируй в рабочий путь:")
print(f"   cp {FINAL_WAV} /tmp/mango_play.wav")
