#!/usr/bin/env python3
"""
Mango Office Webhook Server — приём событий звонков + DTMF

Обрабатывает:
- call/answer  — клиент ответил → воспроизводим аудио
- call/disconnect — звонок завершён
- dtmf          — нажатие клавиши (1=подтверждение, 0=отмена)
- callback/result — итог автодозвона

Интегрировано с Bitrix24: обновляет стадию сделки по DTMF.

PM2: mango-webhook (порт 8085)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Загрузка секретов из .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")
VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "")
MAPNGO_API_BASE = "https://app.mango-office.ru/vpbx/"
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")

STAGE_CONFIRMED = os.getenv("BX_STAGE_CONFIRMED", "PREPARATION")
STAGE_CANCELLED = os.getenv("BX_STAGE_CANCELLED", "LOSE")

# Лог файл для DTMF событий
DTMF_LOG = Path('/Users/igorvasin/freelance-2026/ai-eggs/data/mango/dtmf_events.jsonl')
CALL_LOG = Path('/Users/igorvasin/freelance-2026/ai-eggs/data/mango/callback_results.jsonl')

# Активные звонки: call_id → {deal_id, phone, audio_filename, answered}
# Заполняется при инициации звонка из auto_confirm_call.py
active_calls: dict = {}


def _mango_request(endpoint: str, json_data: dict) -> dict:
    """POST запрос к Mango API."""
    import hashlib
    json_str = json.dumps(json_data, separators=(",", ":"), ensure_ascii=False)
    sign = hashlib.sha256((VPBX_API_KEY + json_str + VPBX_API_SALT).encode()).hexdigest()
    try:
        resp = requests.post(
            f"https://app.mango-office.ru/vpbx/{endpoint}",
            data={"vpbx_api_key": VPBX_API_KEY, "json": json_str, "sign": sign},
            timeout=15,
        )
        return resp.json()
    except Exception as e:
        print(f"  Mango API err ({endpoint}): {e}")
        return {}


def play_audio_on_call(call_id: str, audio_filename: str):
    """Воспроизводит аудио на активном звонке."""
    if not audio_filename:
        print(f"  ⚠️ play_audio: нет файла для call_id={call_id}")
        return
    result = _mango_request("play/start", {
        "call_id": call_id,
        "filename": audio_filename,
        "after_playback": "hangup",  # положить трубку после воспроизведения
    })
    print(f"  🎵 play/start → {result}")


def update_bitrix_deal(deal_id: str, stage: str, comment: str):
    """Обновляет стадию сделки и добавляет комментарий."""
    if not BITRIX_URL or not deal_id:
        return
    try:
        requests.post(f"{BITRIX_URL}/crm.deal.update",
                     json={"id": deal_id, "fields": {"STAGE_ID": stage}}, timeout=10)
        requests.post(f"{BITRIX_URL}/crm.timeline.comment.add",
                     json={"fields": {"ENTITY_ID": deal_id,
                                      "ENTITY_TYPE": "deal", "COMMENT": comment}}, timeout=10)
        print(f"  📝 Bitrix: сделка {deal_id} → {stage}")
    except Exception as e:
        print(f"  Bitrix err: {e}")


def _analyze_voice_async(call_id: str, deal_id: str, timestamp: str):
    """
    Фоновый STT-анализ записи звонка (запускается в отдельном потоке).

    Флоу:
      1. Ждём 10 сек — Mango должен сохранить запись
      2. Скачиваем запись через Mango API
      3. Whisper → транскрипция
      4. Классифицируем ДА/НЕТ
      5. Обновляем Bitrix
    """
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    import time
    time.sleep(10)  # ждём пока Mango сохранит запись

    print(f"\n  🎤 STT: анализирую запись call_id={call_id}...")

    try:
        from speech_analyzer import analyze_call_recording
        result = analyze_call_recording(call_id=call_id)
    except Exception as e:
        print(f"  ❌ STT ошибка: {e}")
        result = {"answer": "unclear", "confidence": 0.0, "text": "", "matched": ""}

    answer = result.get("answer", "unclear")
    text = result.get("text", "")
    confidence = result.get("confidence", 0.0)

    emoji = {"yes": "✅", "no": "❌", "unclear": "❓"}.get(answer, "❓")
    print(f"  {emoji} STT результат: {answer} | '{text}' ({confidence:.0%})")

    if not deal_id or not BITRIX_URL:
        return

    if answer == "yes":
        update_bitrix_deal(
            deal_id, STAGE_CONFIRMED,
            f"🤖 Автодозвон (голос): клиент сказал ДА ✅\n"
            f"Транскрипция: «{text}»\n"
            f"Уверенность: {confidence:.0%} | {timestamp[:16]}"
        )
    elif answer == "no":
        update_bitrix_deal(
            deal_id, STAGE_CANCELLED,
            f"🤖 Автодозвон (голос): клиент сказал НЕТ ❌\n"
            f"Транскрипция: «{text}»\n"
            f"Уверенность: {confidence:.0%} | {timestamp[:16]}"
        )
    else:
        # Непонятно — оставляем сделку без изменения, добавляем комментарий
        if BITRIX_URL:
            try:
                requests.post(f"{BITRIX_URL}/crm.timeline.comment.add",
                              json={"fields": {
                                  "ENTITY_ID": deal_id,
                                  "ENTITY_TYPE": "deal",
                                  "COMMENT": (
                                      f"🤖 Автодозвон (голос): ответ не распознан ❓\n"
                                      f"Транскрипция: «{text or 'тишина'}»\n"
                                      f"{timestamp[:16]} — требует ручной проверки"
                                  ),
                              }}, timeout=10)
            except Exception:
                pass


class MangoWebhookHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        # Ответ сразу (Mango не ждёт)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

        timestamp = datetime.now().isoformat()
        path = self.path.rstrip("/")
        print(f"\n[{timestamp}] POST {path} | {len(body)} bytes")

        try:
            data = json.loads(body)
            self._handle_event(path, data, timestamp)
        except Exception as e:
            print(f"  ❌ parse error: {e} | body: {body[:200]}")

    def _handle_event(self, path: str, data: dict, timestamp: str):
        """Маршрутизация событий Mango."""
        # --- Клиент ответил → воспроизводим аудио ---
        if "/call/answer" in path or data.get("event") == "answer":
            call_id = data.get("call_id") or data.get("entry_id", "")
            print(f"  📞 ANSWER: call_id={call_id}")
            if call_id in active_calls:
                info = active_calls[call_id]
                info["answered"] = True
                play_audio_on_call(call_id, info.get("audio_filename"))
            self._save_event(timestamp, "answer", data)

        # --- DTMF нажатие ---
        elif "/dtmf" in path or data.get("event") == "dtmf" or "dtmf" in str(data).lower():
            call_id = data.get("call_id") or data.get("entry_id", "")
            digit = str(data.get("dtmf") or data.get("digit", ""))
            print(f"  🔢 DTMF: call_id={call_id}, digit={digit}")
            self._handle_dtmf(call_id, digit, timestamp, data)

        # --- Звонок завершён ---
        elif "/call/disconnect" in path or data.get("event") == "disconnect":
            call_id = data.get("call_id") or data.get("entry_id", "")
            print(f"  ☎️ DISCONNECT: call_id={call_id}")
            if call_id in active_calls:
                info = active_calls[call_id]
                answered = info.get("answered", False)
                dtmf_done = info.get("dtmf_received", False)
                deal_id = info.get("deal_id")

                if not answered:
                    # Клиент не взял трубку
                    if deal_id:
                        update_bitrix_deal(
                            deal_id, STAGE_CANCELLED,
                            f"🤖 Автодозвон: клиент не ответил ({timestamp[:16]})"
                        )
                elif answered and not dtmf_done:
                    # Ответил, но не нажал кнопку → анализируем голос
                    print("  🎙️ DTMF не получен — запускаем STT анализ")
                    t = threading.Thread(
                        target=_analyze_voice_async,
                        args=(call_id, deal_id, timestamp),
                        daemon=True,
                    )
                    t.start()

                del active_calls[call_id]
            self._save_event(timestamp, "disconnect", data)

        # --- Callback результат ---
        elif "/callback" in path or "callback" in str(data).lower():
            print(f"  📋 CALLBACK RESULT: {json.dumps(data)[:200]}")
            self._save_event(timestamp, "callback_result", data)

        else:
            print(f"  📋 EVENT: {json.dumps(data)[:200]}")
            self._save_event(timestamp, "unknown", data)

    def _handle_dtmf(self, call_id: str, digit: str, timestamp: str, raw: dict):
        """Обрабатываем нажатие DTMF."""
        info = active_calls.get(call_id, {})
        deal_id = info.get("deal_id")
        # Отмечаем что DTMF получен (чтобы не запускать STT после)
        if call_id in active_calls:
            active_calls[call_id]["dtmf_received"] = True

        if digit == "1":
            print(f"  ✅ DTMF 1 — ПОДТВЕРЖДЕНИЕ | deal_id={deal_id}")
            if deal_id:
                update_bitrix_deal(
                    deal_id, STAGE_CONFIRMED,
                    f"🤖 Автодозвон: клиент подтвердил заказ (нажал 1) ✅ {timestamp[:16]}"
                )
        elif digit == "0":
            print(f"  ❌ DTMF 0 — ОТМЕНА | deal_id={deal_id}")
            if deal_id:
                update_bitrix_deal(
                    deal_id, STAGE_CANCELLED,
                    f"🤖 Автодозвон: клиент отменил заказ (нажал 0) ❌ {timestamp[:16]}"
                )
        else:
            print(f"  ⚠️ DTMF: неизвестная клавиша '{digit}'")

        self._save_event(timestamp, "dtmf", {"digit": digit, **raw})

    def _save_event(self, timestamp: str, event_type: str, data: dict):
        event = {"timestamp": timestamp, "event_type": event_type, "data": data}
        DTMF_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DTMF_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def save_callback_result(self, timestamp: str, data: dict):
        event = {"timestamp": timestamp, "event_type": "callback_result", "data": data}
        CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CALL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")



def main():
    import argparse
    parser = argparse.ArgumentParser(description='Mango Office Webhook Server')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()
    
    server = HTTPServer((args.host, args.port), MangoWebhookHandler)
    
    print("\n🤖 Mango Office Webhook Server")
    print(f"   Listening on {args.host}:{args.port}")
    print(f"   Webhook URL: http://{args.host}:{args.port}/vpbx/result/callback")
    print(f"\n💾 DTMF события: {DTMF_LOG}")
    print("\n   Для тестов с ngrok:")
    print(f"   ngrok http {args.port}")
    print("\n   Ожидаю события от Mango Office...\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервера...")
        server.shutdown()


if __name__ == '__main__':
    main()
