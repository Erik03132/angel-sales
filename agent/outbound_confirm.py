#!/usr/bin/env python3
"""outbound_confirm.py — Фаза 14.3

Автоматический исходящий звонок для подтверждения заказа.
Триггер: новый лид в Bitrix24 → звонок через 30 минут.

Требуется: .env.mango с ключами Mango Office и Yandex SpeechKit
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv(Path(__file__).parent / ".env.mango")

# ───────────────────────────────────────────────────────────────
# Конфигурация
# ───────────────────────────────────────────────────────────────
MANGO_API_URL = os.getenv("MANGO_API_URL", "https://api.mango-office.ru/v1/calls/outbound")
MANGO_API_KEY = os.getenv("MANGO_API_KEY")
MANGO_VIRTUAL_NUMBER = os.getenv("MANGO_VIRTUAL_NUMBER")

SPEECHKIT_API_URL = os.getenv("SPEECHKIT_API_URL", "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize")
SPEECHKIT_IAM_TOKEN = os.getenv("SPEECHKIT_IAM_TOKEN")

BITRIX_WEBHOOK_URL = os.getenv("BITRIX_WEBHOOK_URL")
BITRIX_LEAD_WEBHOOK = os.getenv("BITRIX_LEAD_WEBHOOK")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_OWNER_CHAT_ID = os.getenv("TELEGRAM_OWNER_CHAT_ID", "176203333")

# ───────────────────────────────────────────────────────────────
# Проверка заглушек
# ───────────────────────────────────────────────────────────────
REQUIRED_KEYS = [
    ("MANGO_API_KEY", MANGO_API_KEY),
    ("SPEECHKIT_IAM_TOKEN", SPEECHKIT_IAM_TOKEN),
    ("BITRIX_WEBHOOK_URL", BITRIX_WEBHOOK_URL),
]

MISSING_KEYS = [name for name, value in REQUIRED_KEYS if not value or "your_" in value]

if MISSING_KEYS:
    print(f"🔴 ЗАГЛУШКИ: Отсутствуют ключи: {', '.join(MISSING_KEYS)}")
    print("   Скопируйте .env.mango.example → .env.mango и заполните значения")
    sys.exit(1)

# ───────────────────────────────────────────────────────────────
# Функции
# ───────────────────────────────────────────────────────────────


def generate_tts(message: str) -> bytes:
    """Генерация аудио через Yandex SpeechKit."""
    headers = {"Authorization": f"Bearer {SPEECHKIT_IAM_TOKEN}"}
    data = {
        "text": message,
        "lang": "ru-RU",
        "voice": "oksana",
        "format": "mp3",
        "speed": "1.0",
    }
    resp = requests.post(SPEECHKIT_API_URL, headers=headers, data=data, timeout=30)
    resp.raise_for_status()
    return resp.content


def send_outbound_call(phone: str, audio_bytes: bytes) -> dict:
    """Исходящий звонок через Mango Office API."""
    files = {"audio": ("message.mp3", audio_bytes, "audio/mpeg")}
    payload = {
        "to": phone,
        "from": MANGO_VIRTUAL_NUMBER,
    }
    headers = {"Authorization": f"ApiKey {MANGO_API_KEY}"}
    resp = requests.post(MANGO_API_URL, headers=headers, data=payload, files=files, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_lead_data(lead_id: str) -> dict:
    """Получение данных лида из Bitrix24."""
    resp = requests.get(
        f"{BITRIX_WEBHOOK_URL}crm.lead.get",
        params={"ID": lead_id},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def update_lead_status(lead_id: str, status: str, dtmf_response: str = None):
    """Обновление статуса лида в Bitrix24."""
    comment = f"Автодозвон: {status}"
    if dtmf_response:
        comment += f" | DTMF: {dtmf_response}"

    requests.post(
        f"{BITRIX_WEBHOOK_URL}crm.lead.update",
        json={"ID": lead_id, "COMMENTS": comment},
        timeout=30,
    )


def send_telegram_notification(message: str):
    """Отправка уведомления в Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_OWNER_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    requests.post(url, json=data, timeout=10)


def confirm_lead(lead_id: str, phone: str):
    """Основная логика подтверждения лида."""
    print(f"📞 Автодозвон: лид #{lead_id}, тел: {phone}")

    # Генерация TTS-сообщения
    message = (
        "Здравствуйте! Это Анжела Заботкина из Азовского Инкубатора. "
        "Ваш заказ подтверждён. Пожалуйста, нажмите 1, если всё в силе, "
        "или 2, чтобы перезвонить позже."
    )

    try:
        # Генерация аудио
        print("   🎤 Генерация голоса...")
        audio = generate_tts(message)

        # Отправка звонка
        print("   📞 Звонок...")
        call_result = send_outbound_call(phone, audio)
        call_id = call_result.get("callId", "unknown")

        print(f"   ✅ Звонок инициирован (call_id: {call_id})")

        # Обновление лида
        update_lead_status(lead_id, "Звонок инициирован", call_id)

        # Уведомление
        send_telegram_notification(
            f"📞 Автодозвон #{lead_id}\n"
            f"Тел: `{phone}`\n"
            f"Call ID: `{call_id}`\n"
            f"Статус: Звонок инициирован"
        )

        return {"status": "initiated", "call_id": call_id}

    except requests.exceptions.RequestException as e:
        error_msg = f"Ошибка автодозвона: {e}"
        print(f"   🔴 {error_msg}")

        update_lead_status(lead_id, "Ошибка автодозвона", str(e))

        send_telegram_notification(f"🔴 {error_msg}\nЛид: #{lead_id}")

        return {"status": "error", "error": str(e)}


# ───────────────────────────────────────────────────────────────
# Webhook handler (для Bitrix24)
# ───────────────────────────────────────────────────────────────


def handle_webhook(request_data: dict):
    """Обработчик вебхука от Bitrix24."""
    lead_id = request_data.get("data", {}).get("ID")
    if not lead_id:
        return {"error": "No lead_id"}

    # Задержка 30 минут перед звонком
    print(f"⏰ Лид #{lead_id}: ожидание 30 минут перед автодозвоном...")
    time.sleep(30 * 60)

    # Получение данных лида
    lead = get_lead_data(lead_id)
    phone = lead.get("PHONE", [{}])[0].get("VALUE")

    if not phone:
        return {"error": "No phone in lead"}

    return confirm_lead(lead_id, phone)


# ───────────────────────────────────────────────────────────────
# CLI (для тестирования)
# ───────────────────────────────────────────────────────────────


def main():
    """CLI для ручного тестирования."""
    if len(sys.argv) < 3:
        print("Использование: python outbound_confirm.py <lead_id> <phone>")
        print("Пример: python outbound_confirm.py 12345 +79781234567")
        sys.exit(1)

    lead_id = sys.argv[1]
    phone = sys.argv[2]

    result = confirm_lead(lead_id, phone)
    print(f"Результат: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
