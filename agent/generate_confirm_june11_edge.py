#!/usr/bin/env python3
"""
generate_confirm_june11_edge.py — Генерация WAV через edge-tts (без прокси).

Текст: одиннадцатого июня
Голос: ru-RU-SvetlanaNeural (женский, похож на Kore)
Выход: tts_cache/confirm_call_june11.wav (24kHz, 16-bit, mono → потом конвертируем в 8kHz для Mango)
"""
import asyncio
import os
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    print("❌ edge-tts не установлен. Запустите: pip3 install edge-tts --break-system-packages")
    sys.exit(1)

TEXT = (
    "Здравствуйте, это Азовский инкубатор, "
    "ваш заказ доставим одиннадцатого июня. "
    "Для подтверждения заказа скажите ДА "
    "или нажмите цифру один на телефоне, "
    "или скажите НЕТ "
    "и нажмите цифру ноль. "
    "Всего вам доброго!"
)

VOICE = "ru-RU-SvetlanaNeural"  # женский, чёткий, деловой
OUTPUT_DIR = Path(__file__).parent / "tts_cache"
OUTPUT_MP3 = OUTPUT_DIR / "confirm_call_june11_edge.mp3"
OUTPUT_WAV = OUTPUT_DIR / "confirm_call_june11.wav"
OUTPUT_WAV_8K = OUTPUT_DIR / "confirm_call_june11_mango.wav"  # 8kHz для Mango


async def generate():
    print("=" * 60)
    print("🎤 edge-tts: генерация WAV (одиннадцатого июня)")
    print("=" * 60)
    print(f"\n📝 Текст:\n{TEXT}\n")
    print(f"🎙  Голос: {VOICE}")
    print()

    OUTPUT_DIR.mkdir(exist_ok=True)

    communicate = edge_tts.Communicate(TEXT, VOICE)
    print("📡 Запрос к Microsoft Edge TTS...")
    await communicate.save(str(OUTPUT_MP3))
    print(f"✅ MP3 сохранён: {OUTPUT_MP3} ({OUTPUT_MP3.stat().st_size // 1024} KB)")

    # Конвертируем MP3 → WAV (нужен ffmpeg)
    print("\n🔄 Конвертация MP3 → WAV 24kHz...")
    ret = os.system(f'ffmpeg -y -i "{OUTPUT_MP3}" -ar 24000 -ac 1 -sample_fmt s16 "{OUTPUT_WAV}" 2>/dev/null')
    if ret == 0 and OUTPUT_WAV.exists():
        print(f"✅ WAV 24kHz: {OUTPUT_WAV} ({OUTPUT_WAV.stat().st_size // 1024} KB)")
    else:
        print("⚠️ ffmpeg не найден или ошибка. MP3 файл готов для ручной конвертации.")

    # Конвертируем → 8kHz для Mango Office
    print("🔄 Конвертация → WAV 8kHz (для Mango)...")
    ret2 = os.system(f'ffmpeg -y -i "{OUTPUT_MP3}" -ar 8000 -ac 1 -sample_fmt s16 "{OUTPUT_WAV_8K}" 2>/dev/null')
    if ret2 == 0 and OUTPUT_WAV_8K.exists():
        print(f"✅ WAV 8kHz: {OUTPUT_WAV_8K} ({OUTPUT_WAV_8K.stat().st_size // 1024} KB)")
    else:
        print("⚠️ Конвертация 8kHz не удалась")

    print()
    print("🎯 Файлы готовы:")
    if OUTPUT_WAV.exists():
        print(f"   📁 {OUTPUT_WAV}")
    if OUTPUT_WAV_8K.exists():
        print(f"   📁 {OUTPUT_WAV_8K}  ← загрузить в Mango ЛК")
    print(f"   📁 {OUTPUT_MP3}  ← исходный MP3")


asyncio.run(generate())
