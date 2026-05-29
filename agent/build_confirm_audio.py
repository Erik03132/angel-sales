#!/usr/bin/env python3
"""
Сборка confirm_call_kore для Mango: сообщение + бипер 800Hz + пауза для DTMF/голоса.

По хронике 22.05:
  7с тишина (для baresip/SIP) + голос Kore + 0.5с БИП + 10с тишина

Для play/start (Mango) достаточно: голос + БИП + 10с тишина.

Выход:
  tts_cache/confirm_call_kore_full.wav  → загрузить в ЛК Mango как confirm_call_kore
  tts_cache/confirm_call_kore_full.mp3  → для baresip / отладки

Использование:
  python3 build_confirm_audio.py
  python3 build_confirm_audio.py --with-lead-silence  # +7с в начале (для baresip)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
CACHE = AGENT_DIR / "tts_cache"
MESSAGE_MP3 = CACHE / "confirm_call_kore.mp3"
OUT_MP3 = CACHE / "confirm_call_kore_full.mp3"
OUT_WAV = CACHE / "confirm_call_kore_full.wav"
# WAV для Mango play/start (БЕЗ lead-silence)
MANGO_WAV = CACHE / "confirm_call_kore_mango.wav"
WORK = CACHE / "_build_work"
SR = 8000  # телефония Mango / baresip


def run(cmd: list[str]) -> None:
    print("$", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-lead-silence",
        action="store_true",
        help="Добавить 7с тишины в начало (для baresip aufile)",
    )
    args = parser.parse_args()

    if not MESSAGE_MP3.exists():
        print(f"❌ Нет файла: {MESSAGE_MP3}")
        return 1

    WORK.mkdir(parents=True, exist_ok=True)
    msg_wav = WORK / "message.wav"
    beep_wav = WORK / "beep.wav"
    tail_wav = WORK / "tail_silence.wav"
    lead_wav = WORK / "lead_silence.wav"
    concat_list = WORK / "concat.txt"
    merged_wav = WORK / "merged.wav"

    # Голос → 8 kHz mono + обрезка encoder delay (первые ~150ms тишины от MP3)
    run([
        "ffmpeg", "-y", "-i", str(MESSAGE_MP3),
        "-af", "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05",
        "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le",
        str(msg_wav),
    ])

    # Бип 800 Hz, 0.5 с
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=800:duration=0.5",
        "-ar", str(SR), "-ac", "1",
        str(beep_wav),
    ])

    # Пауза 10 с — окно для «1» / «0» / голосового ДА-НЕТ
    run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono:d=10",
        str(tail_wav),
    ])

    parts = [msg_wav, beep_wav, tail_wav]

    if args.with_lead_silence:
        lead = WORK / "lead_silence.wav"
        run([
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono:d=7",
            str(lead),
        ])
        parts.insert(0, lead)

    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts),
        encoding="utf-8",
    )

    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "pcm_s16le",
        str(merged_wav),
    ])

    run(["ffmpeg", "-y", "-i", str(merged_wav), "-b:a", "64k", str(OUT_MP3)])
    run([
        "ffmpeg", "-y", "-i", str(merged_wav),
        "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le",
        str(OUT_WAV),
    ])

    # WAV для Mango play/start — БЕЗ lead-silence (если есть)
    if not args.with_lead_silence:
        run(["cp", str(OUT_WAV), str(MANGO_WAV)])
        print(f"✅ WAV для Mango ЛК: {MANGO_WAV}")
    else:
        # Собираем второй WAV без lead-silence для Mango
        mango_parts = [msg_wav, beep_wav, tail_wav]
        mango_list = WORK / "concat_mango.txt"
        mango_list.write_text(
            "".join(f"file '{p.resolve()}'\n" for p in mango_parts),
            encoding="utf-8",
        )
        run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(mango_list),
            "-c:a", "pcm_s16le",
            str(MANGO_WAV),
        ])
        print(f"✅ WAV для Mango ЛК (без lead-silence): {MANGO_WAV}")

    print(f"✅ WAV для baresip VPS:     {OUT_WAV}")
    print(f"✅ MP3 для отладки:         {OUT_MP3}")
    print("\n📋 Дальше:")
    print("   1. ЛК Mango → Аудиофайлы → заменить confirm_call_kore (WAV) — исп. mango версию")
    print("   2. VPS: scp confirm_call_kore_full.wav → /tmp/mango_play.wav")
    print("   3. python3 mango_recon.py — проверить internal_id (может смениться)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
