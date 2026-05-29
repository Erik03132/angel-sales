#!/usr/bin/env python3
"""
📞 Mango Hourly Retry — звонит каждый час, пока клиент не возьмёт трубку

Использование:
    python3 mango_hourly_retry.py +79883518413 "Андрей" "100 гусят" "Керчь"
    
Запускается в фоне через nohup или screen.
Останавливается автоматически, когда клиент берёт трубку (talk_time > 0).
"""

import argparse
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# === CONFIG ===
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/")
SIP_EXTENSION = os.getenv("MANGO_SIP_EXTENSION", "22")
VPS_HOST = os.getenv("VPS_HOST", "72.56.38.19")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

AUDIO_DIR = Path(__file__).resolve().parent / "audio_calls"
LOG_FILE = Path(__file__).resolve().parent / "hourly_retry.log"

# Шаблон текста для TTS
CALL_SCRIPT_TEMPLATE = """
Андрей, добрый день, это служба доставки А-Зов-ского инкубатора.
Ваш заказ из двух цыпочек и одного гуся доставят вам завтра в банный комплекс в Симферополе.
Водитель свяжется с вами.
Подтвердите заказ, нажав на один, или нажмите ноль, если не сможете принять.
Спасибо, всего доброго!
"""

SILENCE_PADDING_SEC = 8
END_PADDING_SEC = 3

MAX_RETRIES = 10  # Максимум попыток (часов)
RETRY_INTERVAL_SEC = 3600  # 1 час


def log(message: str):
    """Логирование в файл и консоль."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


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
            log(f"❌ TTS API error: {r.status_code}")
            return False

        data = r.json()
        audio_data = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]

        import base64
        raw_audio = base64.b64decode(audio_data)

        raw_path = output_path.with_suffix(".raw")
        raw_path.write_bytes(raw_audio)

        # Конвертируем в WAV S16LE 8kHz mono с паузой в начале и в конце
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=8000:cl=mono:d={SILENCE_PADDING_SEC}",
            "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw_path),
            "-f", "lavfi", "-i", f"anullsrc=r=8000:cl=mono:d={END_PADDING_SEC}",
            "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1[out]",
            "-map", "[out]",
            "-acodec", "pcm_s16le", "-ar", "8000", "-ac", "1",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        raw_path.unlink(missing_ok=True)

        if output_path.exists() and output_path.stat().st_size > 1000:
            log(f"✅ TTS: {output_path.name} ({output_path.stat().st_size // 1024}KB)")
            return True
        else:
            log("❌ TTS: выходной файл пуст")
            return False

    except Exception as e:
        log(f"❌ TTS error: {e}")
        return False


def upload_wav_to_vps(wav_path: Path) -> str:
    """Загружает WAV на VPS и возвращает путь на VPS."""
    remote_path = "/tmp/mango_play.wav"
    cmd = ["scp", str(wav_path), f"root@{VPS_HOST}:{remote_path}"]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode == 0:
        log(f"📤 Загружен на VPS: {remote_path}")
        return remote_path
    else:
        log(f"❌ SCP failed: {result.stderr.decode()[:200]}")
        return None


def restart_sip_bot():
    """Перезапускает SIP-бота на VPS с новым аудиофайлом."""
    cmd = f"ssh root@{VPS_HOST} 'pkill -9 baresip; sleep 2; screen -dmS sip_bot baresip -f ~/.baresip -v; sleep 6'"
    subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
    log("🔄 SIP-бот перезапущен (ждём 8 сек для регистрации)")


def make_call(phone: str) -> dict:
    """Инициировать callback."""
    command_id = f"hourly_{int(time.time())}_{phone[-4:]}"
    jd = {
        "command_id": command_id,
        "from": {"extension": SIP_EXTENSION},
        "to_number": phone,
    }
    result = api_call("commands/callback", jd)
    return {"command_id": command_id, **result}


def check_call_result(command_id: str, max_wait: int = 60) -> dict:
    """
    Проверяет результат звонка через webhook-лог.
    Возвращает: {"talk_time": int, "answered": bool}
    """
    log(f"⏳ Жду результат звонка {max_wait} сек...")
    time.sleep(max_wait)
    
    # Проверяем лог на VPS
    try:
        cmd = f"ssh root@{VPS_HOST} 'grep -l \"{command_id}\" /root/.pm2/logs/mango-webhook-out.log 2>/dev/null'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            log("⚠️ Не удалось прочитать лог с VPS")
            return {"talk_time": 0, "answered": False, "status": "unknown"}
        
        # Читаем лог
        cmd = f"ssh root@{VPS_HOST} 'grep \"{command_id}\" /root/.pm2/logs/mango-webhook-out.log | tail -5'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        log_text = result.stdout
        
        # Ищем talk_time
        import re
        match = re.search(r'"talk_time":\s*(\d+)', log_text)
        if match:
            talk_time = int(match.group(1))
            answered = talk_time > 0
            log(f"📊 Результат: talk_time={talk_time} сек, {'✅ ответил' if answered else '❌ не взял трубку'}")
            return {"talk_time": talk_time, "answered": answered, "status": "checked"}
        else:
            log("⚠️ Не нашёл talk_time в логе")
            return {"talk_time": 0, "answered": False, "status": "unknown"}
            
    except Exception as e:
        log(f"❌ Ошибка проверки: {e}")
        return {"talk_time": 0, "answered": False, "status": "error"}


def hourly_retry_loop(phone: str, name: str, product: str, location: str):
    """Основной цикл почасовых звонков."""
    log("=" * 60)
    log("📞 ЗАПУСК ПОЧАСОВЫХ ЗВОНКОВ")
    log(f"   Клиент: {name} ({phone})")
    log(f"   Заказ: {product}, {location}")
    log(f"   Макс. попыток: {MAX_RETRIES}")
    log(f"   Интервал: {RETRY_INTERVAL_SEC // 60} мин")
    log("=" * 60)
    
    # Генерируем аудио один раз
    AUDIO_DIR.mkdir(exist_ok=True)
    phone_clean = phone.replace("+", "").replace(" ", "")
    wav_path = AUDIO_DIR / f"hourly_{phone_clean}.wav"
    
    if not wav_path.exists() or wav_path.stat().st_size < 5000:
        log("🎤 Генерация TTS...")
        if not generate_tts_google(CALL_SCRIPT_TEMPLATE.strip(), wav_path):
            log("❌ Не удалось сгенерировать TTS. Выход.")
            return
    else:
        log(f"♻️  Кэш: {wav_path.name}")
    
    # Загружаем на VPS один раз
    remote = upload_wav_to_vps(wav_path)
    if not remote:
        log("❌ Не удалось загрузить на VPS. Выход.")
        return
    
    # Перезапускаем SIP-бота один раз
    restart_sip_bot()
    time.sleep(8)
    
    attempt = 0
    while attempt < MAX_RETRIES:
        attempt += 1
        log(f"\n{'='*60}")
        log(f"📞 ПОПЫТКА #{attempt} из {MAX_RETRIES}")
        log(f"   Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Звонок
        call_result = make_call(phone)
        log(f"   📞 Callback: {call_result.get('result', 'error')}")
        
        if call_result.get('result') != 1000:
            log(f"   ❌ Ошибка API: {call_result}")
            time.sleep(60)  # Пауза перед следующей попыткой
            continue
        
        # Проверка результата
        check_result = check_call_result(call_result.get('command_id', 'unknown'))
        
        if check_result.get('answered'):
            log(f"\n{'='*60}")
            log("🎉 КЛИЕНТ ВЗЯЛ ТРУБКУ!")
            log(f"   Разговор: {check_result['talk_time']} сек")
            log(f"   Попыток: {attempt}")
            log(f"{'='*60}")
            log("✅ ЗАВЕРШЕНИЕ ЦИКЛА")
            return
        
        # Не взял — ждём следующий час
        if attempt < MAX_RETRIES:
            next_time = datetime.now().timestamp() + RETRY_INTERVAL_SEC
            next_dt = datetime.fromtimestamp(next_time).strftime('%H:%M:%S')
            log(f"⏳ Следующая попытка в {next_dt} (через {RETRY_INTERVAL_SEC // 60} мин)")
            time.sleep(RETRY_INTERVAL_SEC)
    
    log(f"\n{'='*60}")
    log(f"⚠️ ЛИМИТ ПОПЫТОК ИСЧЕРПАН ({MAX_RETRIES})")
    log(f"   Клиент не взял трубку за {MAX_RETRIES} часов")
    log(f"{'='*60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mango Hourly Retry")
    parser.add_argument("phone", help="Номер телефона")
    parser.add_argument("name", help="Имя клиента")
    parser.add_argument("product", help="Продукт")
    parser.add_argument("location", help="Место доставки")
    parser.add_argument("--max-retries", type=int, default=MAX_RETRIES, help="Макс. попыток")
    parser.add_argument("--interval", type=int, default=RETRY_INTERVAL_SEC, help="Интервал (сек)")
    args = parser.parse_args()
    
    MAX_RETRIES = args.max_retries
    RETRY_INTERVAL_SEC = args.interval
    
    hourly_retry_loop(args.phone, args.name, args.product, args.location)
