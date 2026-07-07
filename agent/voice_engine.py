#!/usr/bin/env python3
"""
🎙️ VOICE ENGINE — Модуль генерации голосовых ответов Анжелочки.

Каскад TTS:
1. Gemini Kore (gemini-2.5-flash-preview-tts) — основной, через US прокси
2. edge-tts (Microsoft, Светлана) — fallback, бесплатный
3. Silero TTS (v4_ru, Baya) — локальный fallback, без интернета

Два режима вывода:
  - generate_voice()   → OGG OPUS (Telegram voice messages)
  - generate_call_tts() → WAV 8000 Hz (Mango voice calls)

Использование:
    from voice_engine import generate_voice, generate_call_tts
    await generate_voice("Привет!", "user123")        # → temp_voices/voice_user123.ogg
    generate_call_tts("Привет!")                       # → tts_cache/r_....wav
"""
import os
import asyncio
import logging
import re
import base64
import subprocess
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── Пути ──────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
for _env in (BASE.parent / ".env", BASE / ".env"):
    if _env.exists():
        load_dotenv(_env, override=True)
        break

VOICE_DIR = BASE / "temp_voices"
VOICE_DIR.mkdir(exist_ok=True)

TTS_DIR = BASE / "tts_cache"
TTS_DIR.mkdir(exist_ok=True)

# ── Прокси для Gemini TTS (РФ блокирует Google API) ─────────────────────────
_TTS_PROXY = None
for _k in ("ALL_PROXY", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    _v = os.environ.get(_k, "")
    if _v and "socks" in _v:
        _TTS_PROXY = {"https": _v, "http": _v}
        logger.info("🌐 TTS прокси обнаружен")
        break

# ── Gemini API Key ──────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── Silero TTS (fallback) ───────────────────────────────────────────────────
_silero_model = None
_silero_device = None


def _load_silero():
    global _silero_model, _silero_device
    if _silero_model is not None:
        return _silero_model
    try:
        import torch
        _silero_device = torch.device('cpu')
        LOCAL_MODEL_FILE = BASE / 'v4_ru.pt'
        if not LOCAL_MODEL_FILE.exists():
            logger.info("⬇️ Скачиваю Silero TTS (~50 MB)...")
            torch.hub.download_url_to_file(
                'https://models.silero.ai/models/tts/ru/v4_ru.pt',
                str(LOCAL_MODEL_FILE)
            )
        logger.info("🧠 Загружаю Silero TTS...")
        _silero_model = torch.package.PackageImporter(str(LOCAL_MODEL_FILE)).load_pickle("tts_models", "model")
        _silero_model.to(_silero_device)
        return _silero_model
    except Exception as e:
        logger.error(f"⚠️ Silero недоступен: {e}")
        return None


def _sync_silero(text: str, file_path: str, sample_rate: int = 48000):
    import torch
    import soundfile as sf
    model = _load_silero()
    if not model:
        raise RuntimeError("Silero model not loaded")
    audio = model.apply_tts(
        text=text, speaker='baya', sample_rate=sample_rate,
        put_accent=True, put_yo=True
    )
    sf.write(file_path, audio.numpy(), sample_rate, format='WAV' if sample_rate == 8000 else 'OGG', subtype='PCM_16' if sample_rate == 8000 else 'OPUS')


# ── Kore TTS (синхронный вызов) ─────────────────────────────────────────────

def _generate_kore_sync(text: str, file_path: str, sample_rate: int = 24000) -> bool:
    """Gemini Kore TTS → сохраняет raw PCM, конвертирует в target.

    Возвращает True при успехе.
    """
    if not GEMINI_API_KEY:
        return False

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}
            }
        }
    }
    try:
        import requests as _req
        r = _req.post(url, headers={"Content-Type": "application/json"},
                      json=payload, proxies=_TTS_PROXY, timeout=30)
        if r.status_code != 200:
            logger.warning(f"⚠️ Kore: HTTP {r.status_code}")
            return False

        result = r.json()
        parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for part in parts:
            if "inlineData" in part:
                audio_data = base64.b64decode(part["inlineData"]["data"])
                raw_path = TTS_DIR / f"kore_{int(os.times()[4]*1000)}.raw"
                with open(raw_path, "wb") as f:
                    f.write(audio_data)
                subprocess.run(
                    ["ffmpeg", "-y",
                     "-f", "s16le", "-ar", "24000", "-ac", "1",
                     "-i", str(raw_path),
                     "-ar", str(sample_rate), "-ac", "1",
                     "-sample_fmt", "s16", "-f", "wav" if sample_rate == 8000 else "ogg",
                     str(file_path)] + ([] if sample_rate == 8000 else ["-c:a", "libopus", "-b:a", "64k"]),
                    capture_output=True, timeout=15
                )
                raw_path.unlink(missing_ok=True)
                if Path(file_path).exists():
                    logger.info("✅ Kore TTS: аудио сгенерировано")
                    return True
        return False
    except Exception as e:
        logger.error(f"⚠️ Kore error: {e}")
        return False


# ── edge-tts (асинхронный, Microsoft Светлана) ──────────────────────────────

async def _generate_edge_tts(text: str, file_path: str, sample_rate: int = 48000) -> bool:
    try:
        import edge_tts
        voice = "ru-RU-SvetlanaNeural"
        communicate = edge_tts.Communicate(text, voice)
        mp3_path = str(Path(file_path).with_suffix('.mp3'))
        await communicate.save(mp3_path)

        codec_args = []
        ext = Path(file_path).suffix
        if ext == '.wav':
            codec_args = ["-ar", str(sample_rate), "-ac", "1", "-sample_fmt", "s16", "-f", "wav"]
        else:
            codec_args = ["-ar", "48000", "-ac", "1", "-c:a", "libopus", "-b:a", "64k"]

        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path] + codec_args + [str(file_path)],
            capture_output=True, timeout=15
        )
        Path(mp3_path).unlink(missing_ok=True)
        if Path(file_path).exists():
            logger.info("✅ edge-tts (Светлана): аудио сгенерировано")
            return True
        return False
    except Exception as e:
        logger.error(f"⚠️ edge-tts error: {e}")
        return False


# ── Очистка текста ──────────────────────────────────────────────────────────

def _clean_tts_text(text: str) -> str:
    if not text:
        return ""
    clean = text
    clean = re.sub(r'[*_`]', '', clean)
    clean = clean.replace("₽", " рублей").replace(" шт.", " штук")
    try:
        from num2words import num2words
        def convert_num(m):
            return " " + num2words(int(m.group(0)), lang='ru') + " "
        clean = re.sub(r'\d+', convert_num, clean)
    except ImportError:
        pass
    clean = re.sub(r'[^\w\s.,!?А-Яа-яЁёA-Za-z\-:;()]+', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) < 2:
        return ""
    if len(clean) > 1000:
        clean = clean[:1000] + "..."
    return clean


# ── Публичный API ───────────────────────────────────────────────────────────

async def generate_voice(text: str, user_id: str) -> str:
    """
    Генерирует голосовое сообщение для Telegram (OGG OPUS).

    Каскад: Kore → edge-tts → Silero

    Returns:
        str: Путь к .ogg файлу, либо None.
    """
    clean = _clean_tts_text(text)
    if not clean:
        return None

    file_path = str(VOICE_DIR / f"voice_{user_id}.ogg")

    # 1. Kore
    try:
        if await asyncio.to_thread(_generate_kore_sync, clean, file_path, 48000):
            logger.info(f"🎙️ Kore → голосовое для {user_id}")
            return file_path
    except Exception:
        pass

    # 2. edge-tts
    try:
        if await _generate_edge_tts(clean, file_path, 48000):
            logger.info(f"🎙️ edge-tts → голосовое для {user_id}")
            return file_path
    except Exception:
        pass

    # 3. Silero
    try:
        await asyncio.to_thread(_sync_silero, clean, file_path, 48000)
        logger.info(f"🎙️ Silero → голосовое для {user_id}")
        return file_path
    except Exception as e:
        logger.error(f"⚠️ Все TTS упали: {e}")

    return None


def generate_call_tts(text: str) -> str | None:
    """
    Генерирует аудио для Mango-звонка (WAV, 8000 Гц, s16le, mono).

    Каскад: Kore → edge-tts → Silero.
    Синхронная (блокирующая) — для простоты вызова из voice_bridge.

    Returns:
        str: Путь к .wav файлу, либо None.
    """
    clean = _clean_tts_text(text)
    if not clean:
        return None

    ts = int(__import__('time').time() * 1000)
    file_path = str(TTS_DIR / f"call_{ts}.wav")

    # 1. Kore (конвертирует в 8000 Hz WAV)
    if _generate_kore_sync(clean, file_path, 8000):
        return file_path

    # 2. edge-tts (синхронная обёртка)
    try:
        async def _do():
            return await _generate_edge_tts(clean, file_path, 8000)
        if asyncio.run(_do()):
            return file_path
    except Exception:
        pass

    # 3. Silero
    try:
        _sync_silero(clean, file_path, 8000)
        return file_path
    except Exception as e:
        logger.error(f"⚠️ Все call TTS упали: {e}")

    return None


def cleanup_voice(file_path: str):
    if file_path and Path(file_path).exists():
        try:
            Path(file_path).unlink()
        except Exception:
            pass


# ── Test ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def test():
        print("🎙️ Тест Voice Engine (Telegram OGG)...")
        path = await generate_voice("Здравствуйте! Кобб-500 стоит 65 рублей.", "test_user")
        if path:
            print(f"✅ OGG: {path}")
        else:
            print("❌ OGG не сгенерирован")

        print("\n🎙️ Тест Call TTS (WAV 8000)...")
        wav = generate_call_tts("Здравствуйте! Это Анжела.")
        if wav:
            print(f"✅ WAV: {wav}")
        else:
            print("❌ WAV не сгенерирован")

    asyncio.run(test())
