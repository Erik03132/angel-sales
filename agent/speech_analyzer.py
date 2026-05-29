#!/usr/bin/env python3
"""
🎤 Speech Analyzer — распознавание ДА/НЕТ из записи звонка
Используется как fallback к DTMF: если клиент не нажал кнопку,
но ответил голосом — ловим его ответ из записи.

Стек:
  - faster-whisper (tiny модель, ~40MB, CPU, ~3сек на 15сек аудио)
  - Mango API для скачивания записи звонка

Использование:
    from speech_analyzer import analyze_call_recording
    result = analyze_call_recording(call_id="abc123")
    # result: {"answer": "yes"/"no"/"unclear", "text": "...", "confidence": 0.9}
"""

import os
import re
import time
from pathlib import Path

# ============================================================
# СЛОВАРИ ДА/НЕТ
# ============================================================

YES_WORDS = {
    "да", "дa", "ага", "угу", "конечно", "подтверждаю",
    "подтверждаем", "хорошо", "ладно", "окей", "ок",
    "согласен", "согласна", "верно", "правильно", "буду",
    "yes", "ok", "okay", "sure", "yep",
}

NO_WORDS = {
    "нет", "нет,", "не", "нe", "отмена", "отменить",
    "отказываюсь", "откажусь", "не надо", "ненадо",
    "не буду", "нeт", "ноль", "no", "cancel", "нет!",
}

# Паттерны для поиска (regex)
YES_PATTERN = re.compile(
    r'\b(да|ага|угу|конечно|подтвержд|хорошо|ладно|окей|ок|согласе|yes|ok)\b',
    re.IGNORECASE | re.UNICODE,
)
NO_PATTERN = re.compile(
    r'\b(нет|не надо|не буду|отмен|откаж|ноль|no|cancel)\b',
    re.IGNORECASE | re.UNICODE,
)

# ============================================================
# WHISPER МОДЕЛЬ (lazy-load, tiny = ~40MB)
# ============================================================

_whisper_model = None


def _get_whisper():
    """Загружаем модель один раз."""
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print("📥 Whisper: загружаю модель tiny...")
            t0 = time.time()
            # tiny: быстро (~3сек на 15сек аудио), достаточно для ДА/НЕТ
            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
            print(f"✅ Whisper: готов за {time.time()-t0:.1f}с")
        except ImportError:
            print("❌ Whisper: pip install faster-whisper")
            return None
        except Exception as e:
            print(f"❌ Whisper: ошибка загрузки: {e}")
            return None
    return _whisper_model


# ============================================================
# ТРАНСКРИПЦИЯ
# ============================================================

def transcribe_audio(audio_path: str) -> dict:
    """
    Транскрибирует аудио файл.
    Возвращает {"text": "...", "language": "ru", "duration": 12.3}
    """
    model = _get_whisper()
    if model is None:
        return {"text": "", "language": "ru", "duration": 0}

    if not os.path.exists(audio_path):
        print(f"❌ Файл не найден: {audio_path}")
        return {"text": "", "language": "ru", "duration": 0}

    try:
        t0 = time.time()
        segments, info = model.transcribe(
            audio_path,
            language="ru",         # форсируем русский
            beam_size=1,           # быстрый режим для коротких фраз
            vad_filter=True,       # убираем тишину
            vad_parameters={
                "min_silence_duration_ms": 300,
                "speech_pad_ms": 100,
            },
        )

        text = " ".join(seg.text.strip() for seg in segments).strip()
        elapsed = time.time() - t0

        print(f"🎤 Whisper: '{text}' ({elapsed:.1f}с, lang={info.language})")
        return {
            "text": text,
            "language": info.language,
            "duration": info.duration,
        }

    except Exception as e:
        print(f"❌ Whisper transcribe error: {e}")
        import traceback
        traceback.print_exc()
        return {"text": "", "language": "ru", "duration": 0}


# ============================================================
# АНАЛИЗ ОТВЕТА
# ============================================================

def classify_answer(text: str) -> dict:
    """
    Классифицирует текст как ДА/НЕТ/НЕПОНЯТНО.

    Возвращает:
        {"answer": "yes"/"no"/"unclear", "confidence": 0.0-1.0, "matched": "..."}
    """
    if not text:
        return {"answer": "unclear", "confidence": 0.0, "matched": ""}

    text_lower = text.lower().strip()

    yes_match = YES_PATTERN.search(text_lower)
    no_match = NO_PATTERN.search(text_lower)

    if yes_match and not no_match:
        return {"answer": "yes", "confidence": 0.9, "matched": yes_match.group()}
    elif no_match and not yes_match:
        return {"answer": "no", "confidence": 0.9, "matched": no_match.group()}
    elif yes_match and no_match:
        # Оба найдены — смотрим что первее
        if yes_match.start() < no_match.start():
            return {"answer": "yes", "confidence": 0.6, "matched": f"{yes_match.group()} (then {no_match.group()})"}
        else:
            return {"answer": "no", "confidence": 0.6, "matched": f"{no_match.group()} (after {yes_match.group()})"}
    else:
        return {"answer": "unclear", "confidence": 0.0, "matched": ""}


# ============================================================
# СКАЧИВАНИЕ ЗАПИСИ ИЗ MANGO
# ============================================================

def download_call_recording(call_id: str, output_dir: str = None) -> str | None:
    """
    Скачивает запись звонка из Mango Office.
    Возвращает путь к MP3/WAV файлу или None.
    """
    import hashlib
    import json

    import requests
    from dotenv import load_dotenv

    # Загружаем конфигурацию
    base_dir = Path(__file__).resolve().parent.parent
    env_path = base_dir / ".env"
    if not env_path.exists():
        env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path, override=True)

    api_key = os.getenv("MANGO_VPBX_API_KEY", "")
    api_salt = os.getenv("MANGO_VPBX_API_SALT", "")

    if not api_key or not api_salt:
        print("❌ MANGO_VPBX_API_KEY / MANGO_VPBX_API_SALT не заданы")
        return None

    # Получаем список записей для данного звонка
    json_data = {"call_id": call_id, "action": "download"}
    json_str = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    sign = hashlib.sha256((api_key + json_str + api_salt).encode()).hexdigest()

    try:
        # Шаг 1: получаем ссылку на запись
        resp = requests.post(
            "https://app.mango-office.ru/vpbx/queries/recording/post/",
            data={"vpbx_api_key": api_key, "json": json_str, "sign": sign},
            timeout=30,
        )
        data = resp.json()
        url = data.get("url") or data.get("link")

        if not url:
            print(f"  ⚠️ Mango: нет записи для call_id={call_id}: {data}")
            return None

        # Шаг 2: скачиваем файл
        out_dir = Path(output_dir or "/tmp/mango_recordings")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"call_{call_id}.mp3"

        audio_resp = requests.get(url, timeout=60)
        with open(out_path, "wb") as f:
            f.write(audio_resp.content)

        size_kb = os.path.getsize(out_path) // 1024
        print(f"  📥 Запись скачана: {out_path} ({size_kb} KB)")
        return str(out_path)

    except Exception as e:
        print(f"  ❌ Ошибка скачивания записи: {e}")
        return None


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

def analyze_call_recording(
    call_id: str,
    audio_path: str = None,
    output_dir: str = None,
) -> dict:
    """
    Полный анализ записи звонка: скачивание → STT → классификация.

    call_id:    ID звонка в Mango
    audio_path: готовый файл (если уже скачан, пропускаем загрузку)
    output_dir: куда сохранять временные файлы

    Возвращает:
        {
            "call_id": "...",
            "answer": "yes" / "no" / "unclear",
            "confidence": 0.0-1.0,
            "text": "распознанный текст",
            "matched": "слово которое совпало",
        }
    """
    result_base = {"call_id": call_id, "answer": "unclear", "confidence": 0.0, "text": "", "matched": ""}

    # 1. Скачиваем запись (если не передан готовый файл)
    if not audio_path:
        print(f"📞 Анализирую звонок {call_id}...")
        audio_path = download_call_recording(call_id, output_dir=output_dir)

    if not audio_path:
        print(f"  ⚠️ Нет записи для {call_id} — answer=unclear")
        return result_base

    # 2. Транскрибируем
    transcription = transcribe_audio(audio_path)
    text = transcription.get("text", "")

    # 3. Классифицируем
    classification = classify_answer(text)

    result = {
        **result_base,
        "text": text,
        **classification,
    }

    emoji = {"yes": "✅", "no": "❌", "unclear": "❓"}.get(result["answer"], "❓")
    print(f"  {emoji} Результат: {result['answer']} (уверенность: {result['confidence']:.0%}) | '{text}'")

    return result


# ============================================================
# CLI тест
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        path = sys.argv[1]
        print(f"\n🔍 Тестирую файл: {path}")
        tr = transcribe_audio(path)
        cl = classify_answer(tr["text"])
        emoji = {"yes": "✅", "no": "❌", "unclear": "❓"}.get(cl["answer"], "❓")
        print(f"\n{emoji} Ответ: {cl['answer']}")
        print(f"   Текст:      '{tr['text']}'")
        print(f"   Совпало:    '{cl['matched']}'")
        print(f"   Уверенность: {cl['confidence']:.0%}")
    else:
        # Быстрый тест classify без аудио
        print("=== Тест classify_answer ===\n")
        tests = [
            ("да, всё верно", "yes"),
            ("ага", "yes"),
            ("нет, отменяйте", "no"),
            ("нет", "no"),
            ("не знаю", "unclear"),
            ("алло алло", "unclear"),
            ("конечно подтверждаю", "yes"),
        ]
        all_ok = True
        for text, expected in tests:
            result = classify_answer(text)
            ok = result["answer"] == expected
            status = "✅" if ok else "❌"
            print(f"  {status} '{text}' → {result['answer']} (ожидалось: {expected})")
            all_ok = all_ok and ok

        print(f"\n{'✅ Все тесты прошли' if all_ok else '❌ Есть ошибки'}")
