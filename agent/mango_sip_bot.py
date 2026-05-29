#!/usr/bin/env python3
"""
📞 Mango SIP-бот для автодозвона с персонализированным аудио

Архитектура:
    1. Регистрируется как SIP-клиент в ВАТС Mango Office
    2. При callback — автоматически отвечает на входящий от Mango
    3. Проигрывает персонализированный MP3 через RTP-поток
    4. DTMF приходят через webhook сервер (отдельный процесс)

Зависимости (VPS):
    pip install pjsua2  # или apt install python3-pjsip
    # Альтернатива без pjsua:
    apt install linphone-cli  # linphonec
    # Или:
    apt install baresip

Использование:
    # Шаг 1: Запустить SIP-бота (фон)
    python3 mango_sip_bot.py --register
    
    # Шаг 2: Запустить webhook-сервер (фон)
    python3 mango_webhook_server.py --port 8080
    
    # Шаг 3: Обзвон
    python3 mango_autocall.py clients.csv

Переменные .env:
    MANGO_SIP_USER=user2
    MANGO_SIP_PASSWORD=<из ЛК Mango>
    MANGO_SIP_DOMAIN=vpbx400161137.mangosip.ru
    MANGO_SIP_EXTENSION=25
"""

import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("mango-sip")

# === КОНФИГУРАЦИЯ ===
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
API_BASE = os.getenv("MANGO_API_BASE", "https://app.mango-office.ru/vpbx/")

SIP_USER = os.getenv("MANGO_SIP_USER", "")
SIP_PASSWORD = os.getenv("MANGO_SIP_PASSWORD", "")
SIP_DOMAIN = os.getenv("MANGO_SIP_DOMAIN", "vpbx400161137.mangosip.ru")
SIP_EXTENSION = os.getenv("MANGO_SIP_EXTENSION", "25")

# Директория с MP3 файлами для обзвона
AUDIO_DIR = Path(__file__).resolve().parent / "audio_calls"


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


def make_callback(to_number: str, command_id: str = None) -> dict:
    """
    Инициировать callback через Mango API.
    from.extension = наш SIP-бот (авто-ответ)
    to_number = телефон клиента
    """
    if command_id is None:
        command_id = f"ac_{int(time.time())}_{to_number[-4:]}"

    json_data = {
        "command_id": command_id,
        "from": {
            "extension": SIP_EXTENSION,
        },
        "to_number": to_number,
    }

    result = api_call("commands/callback", json_data)
    log.info(f"Callback → {to_number} | result: {result.get('result')}")
    return result


class SIPBot:
    """
    Минимальный SIP-бот через linphonec (CLI).
    
    Альтернативы:
    - pjsua (если установлен)
    - baresip
    - Python pjsip bindings
    """

    def __init__(self):
        self.process = None
        self.registered = False
        self._check_tools()

    def _check_tools(self):
        """Проверить какой SIP-клиент доступен."""
        for tool in ["linphonec", "pjsua", "baresip"]:
            result = subprocess.run(
                ["which", tool], capture_output=True, text=True
            )
            if result.returncode == 0:
                self.sip_tool = tool
                log.info(f"✅ Найден SIP-клиент: {tool} ({result.stdout.strip()})")
                return
        
        log.error("❌ Не найден SIP-клиент!")
        log.error("   Установите один из:")
        log.error("   • apt install linphone-cli    (рекомендуется)")
        log.error("   • pip install pjsua2")
        log.error("   • apt install baresip")
        self.sip_tool = None

    def register(self, audio_file: str = None):
        """
        Регистрация SIP-учётки и ожидание входящих звонков.
        
        При входящем звонке — автоответ + проигрывание audio_file.
        """
        if not SIP_USER or not SIP_PASSWORD:
            log.error("❌ SIP-данные не заданы в .env!")
            log.error("   Нужно:")
            log.error(f"   MANGO_SIP_USER={SIP_USER or '<логин из ЛК>'}")
            log.error("   MANGO_SIP_PASSWORD=<пароль из ЛК>")
            log.error(f"   MANGO_SIP_DOMAIN={SIP_DOMAIN}")
            return False

        sip_uri = f"sip:{SIP_USER}@{SIP_DOMAIN}"
        log.info(f"🔗 Регистрация: {sip_uri}")

        if self.sip_tool == "linphonec":
            return self._register_linphone(audio_file)
        elif self.sip_tool == "pjsua":
            return self._register_pjsua(audio_file)
        else:
            log.error(f"SIP-клиент {self.sip_tool} не поддержан")
            return False

    def _register_linphone(self, audio_file: str = None):
        """Регистрация через linphonec."""
        # Создаём конфиг
        config = f"""[sip]
sip_port=5060
default_proxy=0

[proxy_0]
reg_proxy=sip:{SIP_DOMAIN}
reg_identity=sip:{SIP_USER}@{SIP_DOMAIN}
reg_expires=3600
reg_sendregister=1
publish=0

[auth_info_0]
username={SIP_USER}
passwd={SIP_PASSWORD}
realm={SIP_DOMAIN}

[misc]
auto_answer=1
auto_answer_replacing_calls=1
"""
        config_path = Path("/tmp/mango_linphone.conf")
        config_path.write_text(config)

        cmd = ["linphonec", "-c", str(config_path)]
        if audio_file:
            cmd.extend(["--play", audio_file])

        log.info(f"🚀 Запуск: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.registered = True
        log.info("✅ SIP-бот запущен, ожидает входящих звонков")
        return True

    def _register_pjsua(self, audio_file: str = None):
        """Регистрация через pjsua."""
        cmd = [
            "pjsua",
            f"--id=sip:{SIP_USER}@{SIP_DOMAIN}",
            f"--registrar=sip:{SIP_DOMAIN}",
            "--realm=*",
            f"--username={SIP_USER}",
            f"--password={SIP_PASSWORD}",
            "--auto-answer=200",  # Автоответ!
            "--null-audio",  # Без реального звука (для VPS)
            "--no-vad",
        ]

        if audio_file:
            cmd.extend([f"--play-file={audio_file}"])

        log.info(f"🚀 Запуск: {' '.join(cmd)}")
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.registered = True
        log.info("✅ SIP-бот (pjsua) запущен, ожидает входящих звонков")
        return True

    def stop(self):
        """Остановить SIP-бота."""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            log.info("🛑 SIP-бот остановлен")

    def play_audio(self, audio_file: str):
        """Проиграть аудио в текущем звонке (linphonec)."""
        if self.process and self.sip_tool == "linphonec":
            cmd = f"play {audio_file}\n"
            self.process.stdin.write(cmd.encode())
            self.process.stdin.flush()
            log.info(f"🎵 Играю: {audio_file}")


def check_prerequisites():
    """Проверить готовность к запуску."""
    print("=" * 60)
    print("📋 ПРОВЕРКА ГОТОВНОСТИ SIP-БОТА")
    print("=" * 60)

    checks = []

    # 1. API ключи
    ok = bool(VPBX_API_KEY and VPBX_API_SALT)
    checks.append(("Mango API ключи (.env)", ok))

    # 2. SIP-данные
    ok = bool(SIP_USER and SIP_PASSWORD)
    checks.append(("SIP учётка (.env)", ok))
    if not ok:
        print("   ⚠️  Нужно добавить в .env:")
        print("   MANGO_SIP_USER=user2  (или другой — из ЛК)")
        print("   MANGO_SIP_PASSWORD=xxxxx  (из ЛК → Сотрудники → SIP)")

    # 3. SIP-клиент
    bot = SIPBot()
    ok = bot.sip_tool is not None
    checks.append((f"SIP-клиент ({bot.sip_tool or 'не найден'})", ok))

    # 4. Аудио-директория
    AUDIO_DIR.mkdir(exist_ok=True)
    mp3s = list(AUDIO_DIR.glob("*.mp3")) + list(AUDIO_DIR.glob("*.wav"))
    checks.append((f"Аудиофайлы ({len(mp3s)} шт.)", len(mp3s) > 0))

    # 5. Баланс
    try:
        result = api_call("account/balance", {})
        balance = result.get("balance", 0)
        ok = float(balance) > 50
        checks.append((f"Баланс Mango ({balance} ₽)", ok))
    except Exception:
        checks.append(("Баланс Mango", False))

    # Итого
    print()
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"   {status} {name}")

    all_ok = all(ok for _, ok in checks)
    print()
    if all_ok:
        print("🟢 ВСЁ ГОТОВО — можно запускать!")
    else:
        print("🔴 Есть нерешённые проблемы (см. выше)")

    return all_ok


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mango SIP-бот")
    parser.add_argument("--check", action="store_true", help="Проверить готовность")
    parser.add_argument("--register", action="store_true", help="Запустить SIP-бота")
    parser.add_argument("--audio", help="MP3/WAV файл для проигрывания")
    parser.add_argument("--call", help="Позвонить на номер (тест)")
    args = parser.parse_args()

    if args.check or not any([args.register, args.call]):
        check_prerequisites()

    elif args.register:
        bot = SIPBot()
        if bot.register(args.audio):
            try:
                log.info("⏳ Ожидаю входящих звонков... (Ctrl+C для остановки)")
                bot.process.wait()
            except KeyboardInterrupt:
                bot.stop()

    elif args.call:
        log.info(f"📞 Тестовый звонок на {args.call}")
        result = make_callback(args.call)
        if result.get("result") == 1000:
            log.info("✅ Callback инициирован!")
            log.info("⏳ SIP-бот должен автоответить → клиент услышит MP3")
        else:
            log.error(f"❌ Ошибка: {result}")
