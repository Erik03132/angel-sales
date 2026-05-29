#!/usr/bin/env python3
"""
📞 Auto Confirm Call — Автодозвон для подтверждения заказа
Текст звонка ФИКСИРОВАННЫЙ — меняется только номер телефона клиента.

Флоу:
  1. WAV берём из кэша (генерируется один раз в tts_engine.py)
  2. Загружаем WAV в Mango Office
  3. Звоним клиенту
  4. Webhook ловит DTMF (1=ДА, 0=НЕТ) → обновляет Bitrix

Запуск:
    python3 auto_confirm_call.py                   # все сделки из Bitrix
    python3 auto_confirm_call.py --dry-run         # показать без звонков
    python3 auto_confirm_call.py +79001234567      # позвонить одному номеру
    python3 auto_confirm_call.py --regen-wav       # пересоздать WAV файл
"""

import fcntl
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# === Конфигурация ===
BASE_DIR = Path(__file__).resolve().parent.parent
AGENT_DIR = Path(__file__).resolve().parent

_env_path = BASE_DIR / ".env"
if not _env_path.exists():
    _env_path = AGENT_DIR / ".env"
load_dotenv(_env_path, override=True)

# Прокси из .env предназначен ТОЛЬКО для Gemini/Google API.
# Для российских API (Mango, Bitrix) прокси не нужен — убираем из os.environ,
# чтобы requests/urllib не подхватывали его автоматически.
for _proxy_var in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY",
                   "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(_proxy_var, None)

MANGO_API_BASE = "https://app.mango-office.ru/vpbx/"
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")

CALLER_EXTENSION = os.getenv("MANGO_CALLER_EXTENSION", "22")  # SIP-бот (baresip user4)
MANGO_SIP_USER = os.getenv("MANGO_SIP_USER", "user4")
MANGO_SIP_DOMAIN = os.getenv("MANGO_SIP_DOMAIN", "vpbx400161137.mangosip.ru")
MANGO_SIP_URI = os.getenv(
    "MANGO_SIP_URI",
    f"{MANGO_SIP_USER}@{MANGO_SIP_DOMAIN}",
)
# НЕ передавать GSM-номер в callback — иначе Mango звонит ВАМ (обратный звонок)!
CALLER_NUMBER = os.getenv("MANGO_CALLER_NUMBER", "")  # только для логов/отображения

# Аудио в ЛК Mango (имя БЕЗ расширения; internal_id для play/start)
MANGO_AUDIO_NAME = os.getenv(
    "MANGO_AUDIO_NAME",
    os.getenv("MANGO_MP3_FILENAME", "confirm_call_kore"),
).removesuffix(".mp3").removesuffix(".wav")
MANGO_AUDIO_ID = os.getenv("MANGO_AUDIO_ID", "1000550776")
WEBHOOK_REGISTER_URL = os.getenv(
    "MANGO_WEBHOOK_REGISTER_URL",
    "http://127.0.0.1:8085/register",
)

STAGE_AWAITING_CONFIRM = os.getenv("BX_STAGE_AWAITING_CONFIRM", "NEW")
STAGE_CONFIRMED = os.getenv("BX_STAGE_CONFIRMED", "PREPARATION")
STAGE_CANCELLED = os.getenv("BX_STAGE_CANCELLED", "LOSE")

# Задержка перед сводкой (сек) — клиенты могут ответить позже
SUMMARY_DELAY_SEC = int(os.getenv("SUMMARY_DELAY_SEC", "180"))
DTMF_HANDLER_URL = os.getenv("DTMF_HANDLER_URL", "http://localhost:8086/")

MAX_CALL_ATTEMPTS = 3  # Макс попыток дозвона при отсутствии ответа
RETRY_DELAY_SEC = 600  # Пауза между попытками (10 мин)

LOG_PATH = AGENT_DIR / "logs" / "auto_confirm_call.log"
LOCK_FILE = "/tmp/auto_confirm_call.lock"
LOG_PATH.parent.mkdir(exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _trigger_summary():
    """Вызывает GET /summary на dtmf_handler — он шлёт Telegram-сводку."""
    try:
        resp = requests.get(f"{DTMF_HANDLER_URL}summary", timeout=10)
        log(f"📊 Сводка запрошена → [{resp.status_code}]")
    except Exception as e:
        log(f"⚠️ Не удалось запросить сводку: {e}")


# ============================================================
# MANGO API
# ============================================================

def _mango_sign(json_data: dict) -> str:
    json_string = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    sign_string = VPBX_API_KEY + json_string + VPBX_API_SALT
    return hashlib.sha256(sign_string.encode("utf-8")).hexdigest()


def mango_request(endpoint: str, json_data: dict) -> dict:
    url = f"{MANGO_API_BASE}{endpoint}"
    payload = {
        "vpbx_api_key": VPBX_API_KEY,
        "json": json.dumps(json_data, separators=(",", ":"), ensure_ascii=False),
        "sign": _mango_sign(json_data),
    }
    try:
        resp = requests.post(url, data=payload, timeout=30)
        return resp.json()
    except Exception as e:
        log(f"  ❌ Mango API error ({endpoint}): {e}")
        return {}


def mango_upload_audio(wav_path: str) -> str | None:
    """Загружает WAV в Mango. Возвращает filename или None."""
    if not os.path.exists(wav_path):
        log(f"  ❌ Файл не найден: {wav_path}")
        return None

    filename = os.path.basename(wav_path)
    command_id = f"cmd_{uuid.uuid4().hex[:8]}"

    with open(wav_path, "rb") as f:
        file_data = f.read()

    log(f"  📤 Загрузка аудио: {filename} ({len(file_data) // 1024} KB)")
    try:
        resp = requests.post(
            f"{MANGO_API_BASE}files/upload",
            files={"file": (filename, file_data, "audio/wav")},
            data={
                "vpbx_api_key": VPBX_API_KEY,
                "json": json.dumps({"command_id": command_id, "filename": filename}),
                "sign": _mango_sign({"command_id": command_id, "filename": filename}),
            },
            timeout=60,
        )
        result = resp.json()
        if result.get("result") == 1000:
            log(f"  ✅ Аудио загружено: {filename}")
        else:
            log(f"  ⚠️ Mango upload response: {result}")
        return filename  # имя файла для play/start
    except Exception as e:
        log(f"  ❌ Ошибка загрузки аудио: {e}")
        return None


def _register_with_webhook(command_id: str, phone: str, deal_id: str | None = None) -> None:
    """Регистрирует звонок в mango-webhook для play/start при ответе клиента."""
    try:
        resp = requests.post(
            WEBHOOK_REGISTER_URL,
            json={
                "command_id": command_id,
                "phone": phone,
                "deal_id": str(deal_id) if deal_id else "",
                "audio": MANGO_AUDIO_NAME,
            },
            timeout=5,
        )
        log(f"  🔗 webhook register [{resp.status_code}] cmd={command_id}")
    except Exception as e:
        log(f"  ⚠️ webhook register: {e}")


def mango_call(to_number: str, deal_id: str | None = None) -> dict | None:
    """Инициирует исходящий звонок."""
    if not VPBX_API_KEY or not VPBX_API_SALT:
        log("  ❌ MANGO_VPBX_API_KEY / MANGO_VPBX_API_SALT не заданы в .env")
        return None

    command_id = f"cmd_{uuid.uuid4().hex[:8]}"
    # Callback: 1-я нога → SIP-бот (baresip авто-ответ), 2-я нога → клиент + play/start
    # ⛔ НЕ добавлять from.number = GSM — это и есть «обратный звонок» на ваш телефон!
    json_data = {
        "command_id": command_id,
        "from": {
            "extension": CALLER_EXTENSION,
            "sip": MANGO_SIP_URI,
        },
        "to_number": to_number,
    }

    log(
        f"  📞 Звоним: {to_number} "
        f"(SIP {MANGO_SIP_URI}, ext {CALLER_EXTENSION}, аудио: {MANGO_AUDIO_NAME})"
    )
    _register_with_webhook(command_id, to_number, deal_id=deal_id)
    result = mango_request("commands/callback", json_data)

    if result.get("result") == 1000:
        log(f"  ✅ Звонок инициирован (command_id: {command_id})")
        result["command_id"] = command_id
        return result
    else:
        log(f"  ❌ Ошибка звонка: {result}")
        return None


# ============================================================
# BITRIX24 API
# ============================================================

def bx_post(method: str, params: dict = None) -> dict:
    try:
        resp = requests.post(
            f"{BITRIX_URL}/{method}",
            json=params or {},
            timeout=20,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log(f"  Bitrix API error ({method}): {e}")
    return {}


def get_deals_awaiting_confirm() -> list:
    """Получает сделки с поставкой ЗАВТРА для автодозвона.
    
    Логика: delivery_date (CLOSEDATE) = завтра + STAGE_ID = NEW
    Звоним за 1 день до поставки для подтверждения.
    """
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    data = bx_post("crm.deal.list", {
        "filter": {
            "STAGE_ID": STAGE_AWAITING_CONFIRM,
            ">=CLOSEDATE": f"{tomorrow}T00:00:00",
            "<=CLOSEDATE": f"{tomorrow}T23:59:59",
        },
        "select": ["ID", "TITLE", "STAGE_ID", "CONTACT_ID", "CLOSEDATE"],
        "order": {"ID": "DESC"},
    })
    deals = data.get("result", []) or []
    log(f"📋 Сделок с поставкой {tomorrow} в стадии '{STAGE_AWAITING_CONFIRM}': {len(deals)}")
    return deals


def get_contact_phone(contact_id: str) -> str | None:
    if not contact_id:
        return None
    data = bx_post("crm.contact.get", {"id": contact_id})
    contact = data.get("result", {})
    for ph in contact.get("PHONE", []):
        if ph.get("VALUE"):
            return ph["VALUE"]
    return None


# ============================================================
# ОСНОВНАЯ ЛОГИКА
# ============================================================

def call_client_with_confirm(phone: str, deal_id: str = None) -> bool:
    """
    Полный цикл: WAV из кэша → загрузка в Mango → звонок.

    phone:   номер клиента, напр. +79001234567
    deal_id: ID сделки в Bitrix24 (опционально)

    Возвращает True если звонок инициирован успешно.
    """
    log(f"\n{'='*50}")
    log(f"📞 Автодозвон: {phone} | deal_id={deal_id}")

    # MP3 уже загружен в ЛК Mango — просто звоним
    log(f"  🎵 Аудио Mango: {MANGO_AUDIO_NAME} (id {MANGO_AUDIO_ID})")

    # Инициируем звонок
    result = mango_call(phone, deal_id=deal_id)
    if not result:
        return False

    # 4. Регистрируем phone→deal_id в dtmf_handler через HTTP (процессы раздельные)
    call_cmd_id = result.get("call_id") or result.get("request_id", f"cmd_{phone}")
    dtmf_handler_url = os.getenv("DTMF_HANDLER_URL", "http://localhost:8086/")
    try:
        reg_payload = {
            "call_id": call_cmd_id,
            "phone": phone,
            "deal_id": str(deal_id) if deal_id else "",
        }
        reg_resp = requests.post(
            dtmf_handler_url,
            json=reg_payload,
            timeout=5,
        )
        log(f"  🔗 Зарегистрирован в dtmf_handler: {phone} → deal={deal_id} [{reg_resp.status_code}]")
    except Exception as e:
        log(f"  ⚠️ dtmf_handler регистрация не удалась: {e} (звонок продолжается)")

    # 5. Комментарий в Bitrix
    if deal_id and BITRIX_URL:
        bx_post("crm.timeline.comment.add", {
            "fields": {
                "ENTITY_ID": deal_id,
                "ENTITY_TYPE": "deal",
                "COMMENT": (
                    f"🤖 Автодозвон {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                    f"Телефон: {phone}\n"
                    f"Аудио: {MANGO_AUDIO_NAME}\n"
                    f"Статус: звонок инициирован ✅"
                ),
            }
        })
        log(f"  📝 Комментарий в сделку {deal_id}")

    log(f"  ✅ Готово → {phone}")
    return True


def process_all_pending(dry_run: bool = False):
    """Обрабатывает все сделки с поставкой завтра. Повторные звонки до 3 раз."""
    lock_fd = None
    try:
        lock_fd = open(LOCK_FILE, "w")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            log("⚠️ Другой экземпляр auto_confirm_call уже работает — пропускаем")
            return

        if not BITRIX_URL:
            log("❌ PRODUCTION_BITRIX_WEBHOOK_URL не задан в .env")
            return

        deals = get_deals_awaiting_confirm()
        if not deals:
            log("ℹ️ Нет сделок для обзвона")
            return

        # Список для обзвона: [{deal_id, phone, contact_id}]
        call_queue = []
        for deal in deals:
            deal_id = deal.get("ID")
            contact_id = deal.get("CONTACT_ID")
            phone = get_contact_phone(contact_id)
            if not phone:
                log(f"  ⚠️ Сделка {deal_id}: нет телефона у контакта {contact_id}")
                continue
            call_queue.append({"deal_id": deal_id, "phone": phone})

        if not call_queue:
            log("ℹ️ Нет номеров для обзвона")
            return

        if dry_run:
            for item in call_queue:
                log(f"  [DRY RUN] Сделка {item['deal_id']}: позвонить {item['phone']}")
            return

        # Обзвон с повторными попытками (MAX_CALL_ATTEMPTS раз)
        pending = list(call_queue)  # очередь на обзвон
        success_total, fail_total = 0, 0

        for attempt in range(1, MAX_CALL_ATTEMPTS + 1):
            if not pending:
                break

            log(f"\n📞 Попытка {attempt}/{MAX_CALL_ATTEMPTS}: {len(pending)} номеров")

            still_pending = []
            for item in pending:
                ok = call_client_with_confirm(phone=item["phone"], deal_id=item["deal_id"])
                if ok:
                    success_total += 1
                else:
                    fail_total += 1
                time.sleep(120)  # пауза 2 мин между звонками

            # Ждём результаты DTMF/STT
            log(f"⏳ Ждём {SUMMARY_DELAY_SEC}с результаты...")
            time.sleep(SUMMARY_DELAY_SEC)

            # Проверяем кто не ответил — сделка всё ещё в NEW
            if attempt < MAX_CALL_ATTEMPTS:
                remaining_deals = get_deals_awaiting_confirm()
                remaining_ids = {d["ID"] for d in remaining_deals}
                still_pending = [item for item in pending if item["deal_id"] in remaining_ids]
                if still_pending:
                    log(f"  🔁 Не ответили: {len(still_pending)} номеров. Повтор через {RETRY_DELAY_SEC // 60} мин...")
                    time.sleep(RETRY_DELAY_SEC)
                else:
                    log("✅ Все ответили!")
            pending = still_pending

        log(f"\n📊 Итог: успешно {success_total}, ошибок {fail_total}, не ответили {len(pending)}")
        _trigger_summary()
    finally:
        if lock_fd:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        log("🚀 Запуск обработки всех сделок в очереди...")
        process_all_pending()

    elif args[0] == "--dry-run":
        log("🔍 DRY RUN — реальных звонков нет")
        process_all_pending(dry_run=True)

    elif args[0] == "--regen-wav":
        log("🎙️ Пересоздаём WAV файл...")
        from tts_engine import TTSEngine
        engine = TTSEngine()
        path = engine.get_confirm_wav(force_regen=True)
        log(f"✅ WAV: {path}")

    elif args[0].startswith("+") or args[0][0].isdigit():
        phone = args[0]
        call_client_with_confirm(phone=phone)

    else:
        print("Использование:")
        print("  python3 auto_confirm_call.py                   # все ожидающие сделки")
        print("  python3 auto_confirm_call.py --dry-run         # показать без звонков")
        print("  python3 auto_confirm_call.py +79001234567      # позвонить одному")
        print("  python3 auto_confirm_call.py --regen-wav       # пересоздать WAV")
