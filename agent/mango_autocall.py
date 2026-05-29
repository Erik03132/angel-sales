#!/usr/bin/env python3
"""
📞 Mango Auto-Caller — полный конвейер обзвона

CSV → TTS (персонализация) → WAV → SIP callback → результат

Использование:
    python3 mango_autocall.py data/mango/clients.csv --test
    python3 mango_autocall.py data/mango/clients.csv --dry
    python3 mango_autocall.py data/mango/clients.csv

CSV формат:
    name,phone,product,delivery_location
    Игорь,+79859234644,125 цыплят,Джанкой
    Андрей,+79881234567,100 гусят,Симферополь
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# Прокси из .env — только для Gemini/Google.
# Для российских API (Mango, Bitrix) убираем из os.environ.
for _proxy_var in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                   "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_proxy_var, None)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("autocall")

# === CONFIG ===
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/")
SIP_EXTENSION = os.getenv("MANGO_SIP_EXTENSION", "22")
VPS_HOST = os.getenv("VPS_HOST", "72.56.38.19")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

AUDIO_DIR = Path(__file__).resolve().parent / "audio_calls"
RESULTS_FILE = Path(__file__).resolve().parent / "call_results.json"

# Пауза тишины в начале (секунды) — чтобы начало не обрезалось
# Клиент берёт трубку через ~5-8 сек после авто-ответа бота
SILENCE_PADDING_SEC = 8

# Пауза в конце (секунды) — чтобы последняя фраза не обрезалась
END_PADDING_SEC = 3

# Шаблон текста для TTS (версия для Андрея — цыпочки + гусь, банный комплекс)
CALL_SCRIPT_TEMPLATE = """
Андрей, добрый день, это служба доставки А-Зов-ского инкубатора.
Ваш заказ из двух цыпочек и одного гуся доставят вам завтра в банный комплекс в Симферополе.
Водитель свяжется с вами.
Подтвердите заказ, нажав на один, или нажмите ноль, если не сможете принять.
Спасибо, всего доброго!
"""


def sign(json_data: dict) -> str:
    j = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((VPBX_API_KEY + j + VPBX_API_SALT).encode()).hexdigest()


def api_call(endpoint: str, json_data: dict) -> dict:
    url = f"{API_BASE.rstrip('/')}/{endpoint}"
    payload = {
        "vpbx_api_key": VPBX_API_KEY,
        "json": json.dumps(json_data, separators=(",", ":"), ensure_ascii=False),
        "sign": sign(json_data),
    }
    r = requests.post(url, data=payload, timeout=15)
    return r.json()


def generate_tts_google(text: str, output_path: Path) -> bool:
    """Генерация аудио через Google Gemini TTS API."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voice_name": "Kore"}
                    }
                },
            },
        }
        headers = {"Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code != 200:
            log.error(f"TTS API error: {r.status_code} {r.text[:200]}")
            return False

        data = r.json()
        audio_data = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]

        import base64
        raw_audio = base64.b64decode(audio_data)

        # Сохраняем как raw PCM, конвертируем через ffmpeg
        raw_path = output_path.with_suffix(".raw")
        raw_path.write_bytes(raw_audio)

        # Конвертируем в WAV S16LE 8kHz mono с паузой в начале и в конце
        cmd = [
            "ffmpeg", "-y",
            # Генерируем тишину в начале
            "-f", "lavfi", "-i", f"anullsrc=r=8000:cl=mono:d={SILENCE_PADDING_SEC}",
            # Входной аудиофайл (речь)
            "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw_path),
            # Генерируем тишину в конце
            "-f", "lavfi", "-i", f"anullsrc=r=8000:cl=mono:d={END_PADDING_SEC}",
            # Конкатенация: тишина начала + аудио + тишина конца
            "-filter_complex",
            "[0][1][2]concat=n=3:v=0:a=1[out]",
            "-map", "[out]",
            "-acodec", "pcm_s16le", "-ar", "8000", "-ac", "1",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        raw_path.unlink(missing_ok=True)

        if output_path.exists() and output_path.stat().st_size > 1000:
            log.info(f"✅ TTS: {output_path.name} ({output_path.stat().st_size // 1024}KB)")
            return True
        else:
            log.error("❌ TTS: выходной файл пуст")
            return False

    except Exception as e:
        log.error(f"❌ TTS error: {e}")
        return False


def generate_tts_gtts(text: str, output_path: Path) -> bool:
    """Fallback TTS через gTTS (Google Translate)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="ru")
        mp3_path = output_path.with_suffix(".mp3")
        tts.save(str(mp3_path))

        # Конвертируем MP3 → WAV S16LE 8kHz с паузой в начале и в конце
        cmd = [
            "ffmpeg", "-y",
            # Тишина в начале
            "-f", "lavfi", "-i", f"anullsrc=r=8000:cl=mono:d={SILENCE_PADDING_SEC}",
            # Входной MP3
            "-i", str(mp3_path),
            # Тишина в конце
            "-f", "lavfi", "-i", f"anullsrc=r=8000:cl=mono:d={END_PADDING_SEC}",
            # Конкатенация: начало + речь + конец
            "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[out]",
            "-map", "[out]",
            "-acodec", "pcm_s16le", "-ar", "8000", "-ac", "1",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        mp3_path.unlink(missing_ok=True)

        if output_path.exists():
            log.info(f"✅ gTTS: {output_path.name} ({output_path.stat().st_size // 1024}KB)")
            return True
        return False
    except Exception as e:
        log.error(f"❌ gTTS error: {e}")
        return False


def prepare_audio(client: dict) -> Path:
    """Генерирует персонализированный WAV для клиента."""
    AUDIO_DIR.mkdir(exist_ok=True)

    # Имя файла на основе телефона
    phone_clean = client["phone"].replace("+", "").replace(" ", "")
    wav_path = AUDIO_DIR / f"call_{phone_clean}.wav"

    # Если уже есть — используем
    if wav_path.exists() and wav_path.stat().st_size > 5000:
        log.info(f"♻️  Кэш: {wav_path.name}")
        return wav_path

    # Генерируем текст
    text = CALL_SCRIPT_TEMPLATE.format(
        name=client.get("name", "клиент"),
        product=client.get("product", "ваш заказ"),
        location=client.get("delivery_location", "место доставки"),
    ).strip()

    log.info(f"🎤 TTS: «{text[:80]}...»")

    # Пробуем Gemini TTS, fallback на gTTS
    if GEMINI_API_KEY and generate_tts_google(text, wav_path):
        return wav_path
    elif generate_tts_gtts(text, wav_path):
        return wav_path
    else:
        log.error(f"❌ Не удалось сгенерировать аудио для {client['name']}")
        return None


def upload_wav_to_vps(wav_path: Path) -> str:
    """Загружает WAV на VPS и возвращает путь на VPS."""
    remote_path = "/tmp/mango_play.wav"
    cmd = ["scp", str(wav_path), f"root@{VPS_HOST}:{remote_path}"]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode == 0:
        log.info(f"📤 Загружен на VPS: {remote_path}")
        return remote_path
    else:
        log.error(f"❌ SCP failed: {result.stderr.decode()[:200]}")
        return None


def restart_sip_bot():
    """Перезапускает SIP-бота на VPS с новым аудиофайлом."""
    cmd = f"ssh root@{VPS_HOST} 'pkill -9 baresip; sleep 2; screen -dmS sip_bot baresip -f ~/.baresip -v; sleep 6'"
    subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
    log.info("🔄 SIP-бот перезапущен (ждём 8 сек для регистрации)")


def make_call(phone: str) -> dict:
    """Инициировать callback."""
    command_id = f"ac_{int(time.time())}_{phone[-4:]}"
    jd = {
        "command_id": command_id,
        "from": {"extension": SIP_EXTENSION},
        "to_number": phone,
    }
    result = api_call("commands/callback", jd)
    return {"command_id": command_id, **result}


def process_csv(csv_path: str, dry_run: bool = False, test_mode: bool = False):
    """Обработать CSV и запустить обзвон."""
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        clients = list(reader)

    log.info(f"📋 Загружено {len(clients)} клиентов из {csv_path}")

    results = []

    for i, client in enumerate(clients, 1):
        name = client.get("name", "?")
        phone = client.get("phone", "")
        product = client.get("product", "?")
        location = client.get("delivery_location", "?")

        log.info(f"\n{'='*50}")
        log.info(f"📞 [{i}/{len(clients)}] {name} | {phone} | {product} | {location}")

        if not phone:
            log.error("   ❌ Нет телефона — пропускаю")
            continue

        # 1. Генерация аудио
        wav_path = prepare_audio(client)
        if not wav_path:
            results.append({"name": name, "phone": phone, "status": "tts_failed"})
            continue

        if dry_run:
            log.info("   🧪 DRY-RUN: аудио готово, звонок НЕ делается")
            results.append({"name": name, "phone": phone, "status": "dry_run", "audio": str(wav_path)})
            continue

        # 2. Загрузка на VPS
        remote = upload_wav_to_vps(wav_path)
        if not remote:
            results.append({"name": name, "phone": phone, "status": "upload_failed"})
            continue

        # 3. Перезапуск SIP-бота (чтобы подхватил новый файл)
        restart_sip_bot()

        # 4. Callback
        call_result = make_call(phone)
        log.info(f"   📞 Результат: {call_result}")

        results.append({
            "name": name,
            "phone": phone,
            "product": product,
            "location": location,
            "command_id": call_result.get("command_id"),
            "api_result": call_result.get("result"),
            "status": "called" if call_result.get("result") == 1000 else "call_failed",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

        if test_mode:
            log.info("   🧪 TEST-MODE: только 1 звонок")
            break

        # Пауза между звонками (30 сек — ждём пока аудио доиграет)
        if i < len(clients):
            log.info("   ⏳ Пауза 35 сек перед следующим звонком...")
            time.sleep(35)

    # Сохраняем результаты
    RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    log.info(f"\n{'='*50}")
    log.info(f"📊 ИТОГО: {len(results)} клиентов обработано")
    log.info(f"   Результаты: {RESULTS_FILE}")

    for r in results:
        status_icon = "✅" if r["status"] == "called" else "🧪" if r["status"] == "dry_run" else "❌"
        log.info(f"   {status_icon} {r['name']} ({r['phone']}) → {r['status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mango Auto-Caller")
    parser.add_argument("csv_file", help="CSV файл с контактами")
    parser.add_argument("--dry", action="store_true", help="Только генерация аудио, без звонков")
    parser.add_argument("--test", action="store_true", help="Только 1 звонок (первый из CSV)")
    args = parser.parse_args()

    process_csv(args.csv_file, dry_run=args.dry, test_mode=args.test)
