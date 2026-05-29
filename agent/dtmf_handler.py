#!/usr/bin/env python3
"""
🔢 DTMF Handler — обработчик нажатий клавиш из SIP-звонков.

Два режима работы:
1. HTTP-сервер на VPS — принимает DTMF от baresip через evdev/netrouter
2. Мониторинг baresip stdout — парсит DTMF из консольного вывода

Интеграция:
- Bitrix24: перевод сделки в нужную стадию
- Webhook: логирование в mango_webhook.log
- Telegram: уведомление менеджеру

Использование:
    # На VPS рядом с baresip:
    python3 dtmf_handler.py --mode http --port 8086
    
    # Или мониторинг screen:
    python3 dtmf_handler.py --mode monitor
"""

import csv
import json
import logging
import os
import re
import smtplib
import subprocess
import time
from datetime import datetime
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import requests
from dotenv import load_dotenv

# Загрузка .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=True)

# Убираем прокси для российских API
for v in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
    os.environ.pop(v, None)

_log_handlers = [logging.StreamHandler()]
_log_file = Path(__file__).resolve().parent / "logs" / "dtmf_handler.log"
try:
    _log_file.parent.mkdir(parents=True, exist_ok=True)
    _log_handlers.append(logging.FileHandler(str(_log_file)))
except OSError:
    pass  # нет прав — пишем только в stderr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=_log_handlers,
)
log = logging.getLogger("dtmf")

# === Конфигурация ===
BITRIX_URL = os.getenv("PRODUCTION_BITRIX_WEBHOOK_URL", "").rstrip("/")

# Telegram (поддерживаются оба варианта имён env)
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TG_BOT_TOKEN", "")
TG_ADMIN_CHAT = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or os.getenv("ADMIN_TELEGRAM_ID", "")

# Email (SMTP)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_TO = os.getenv("SMTP_TO", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "").lower() in ("1", "true", "yes")

# Стадии Bitrix24
STAGE_CONFIRMED = os.getenv("BX_STAGE_CONFIRMED", "PREPARATION")
STAGE_CANCELLED = os.getenv("BX_STAGE_CANCELLED", "LOSE")

# Хранилище активных звонков {call_id: {deal_id, phone, dtmf_digits, ...}}
active_calls = {}

# Лог файл для DTMF событий
DTMF_LOG = Path(__file__).resolve().parent.parent / "data" / "mango" / "dtmf_events.jsonl"
DTMF_LOG.parent.mkdir(parents=True, exist_ok=True)

# === CSV результатов и сессионная статистика ===
CSV_RESULTS_PATH = Path(__file__).resolve().parent.parent / "data" / "mango" / "call_results.csv"

_session_stats = {
    "started_at": datetime.now().isoformat(),
    "total": 0,
    "confirmed": 0,
    "cancelled": 0,
    "unclear": 0,
    "calls": [],
}


def _write_csv_row(phone: str, digit: str, source: str, deal_id: str, text: str = ""):
    """Записать строку результата в CSV."""
    file_exists = CSV_RESULTS_PATH.exists()
    with open(CSV_RESULTS_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "phone", "digit", "source", "deal_id", "action", "stt_text"])
        action = "confirmed" if digit == "1" else "cancelled" if digit == "0" else "unclear"
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            phone, digit, source, deal_id, action, text,
        ])
    log.info(f"📄 CSV: {phone} → {action}")


def _build_summary() -> str:
    """Формирует Telegram-сводку по сессии обзвона."""
    s = _session_stats
    total = s["total"]

    if total == 0:
        return "📊 Сводка обзвона: 0 звонков обработано"

    pct_ok = (s["confirmed"] / total * 100) if total else 0
    pct_no = (s["cancelled"] / total * 100) if total else 0

    # Отдельно собираем номера сказавших НЕТ/0
    no_numbers = [c for c in s["calls"] if c["digit"] == "0"]

    lines = [
        "📊 <b>Сводка автообзвона</b>",
        f"🕐 {s['started_at'][:16]}",
        "",
        f"📞 Всего обработано: <b>{total}</b>",
        f"✅ Подтверждено: {s['confirmed']} ({pct_ok:.0f}%)",
        f"❌ Отменено: {s['cancelled']} ({pct_no:.0f}%)",
        f"❓ Не распознано: {s['unclear']}",
        "",
    ]

    if no_numbers:
        lines.append("<b>‼️ Отказались (NO/0):</b>")
        for c in no_numbers:
            src = "🔢" if c["source"] == "dtmf" else "🎤"
            lines.append(f"  ❌ <b>{c['phone']}</b> {src} [{c['time']}]")
        lines.append("")

    if s["calls"]:
        lines.append("<b>Все детали:</b>")
        for c in s["calls"][-20:]:
            icon = "✅" if c["digit"] == "1" else "❌" if c["digit"] == "0" else "❓"
            src = "🔢" if c["source"] == "dtmf" else "🎤"
            lines.append(f"  {icon} {c['phone']} {src} [{c['time']}]")

    lines.extend([
        "",
        f"📄 CSV: {CSV_RESULTS_PATH.name}",
    ])

    return "\n".join(lines)


def _send_email(subject: str, body_html: str):
    """Отправить email через SMTP."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not SMTP_TO:
        log.warning("⚠️ Email не настроен (SMTP_* env vars) — пропускаю")
        return False
    try:
        msg = MIMEText(body_html, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = SMTP_TO

        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as s:
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)

        log.info(f"📧 Email отправлен: {subject} → {SMTP_TO}")
        return True
    except Exception as e:
        log.error(f"❌ Email error: {e}")
        return False


def _build_email_report() -> str:
    """Формирует HTML-отчёт для email с полными номерами."""
    s = _session_stats
    total = s["total"]
    if total == 0:
        return "<p>Нет звонков за сессию.</p>"

    no_calls = [c for c in s["calls"] if c["digit"] == "0"]
    yes_calls = [c for c in s["calls"] if c["digit"] == "1"]
    unclear_calls = [c for c in s["calls"] if c["digit"] not in ("0", "1")]

    def _call_row(c, icon):
        src = "🔢 DTMF" if c["source"] == "dtmf" else "🎤 STT"
        return f"<tr><td>{icon}</td><td><b>{c['phone']}</b></td><td>{src}</td><td>{c['time']}</td></tr>"

    rows = ""
    if no_calls:
        rows += "<tr><td colspan='4' style='background:#ffebee;font-weight:bold;padding:8px'>❌ ОТКАЗАЛИСЬ</td></tr>"
        for c in no_calls:
            rows += _call_row(c, "❌")
    if yes_calls:
        rows += "<tr><td colspan='4' style='background:#e8f5e9;font-weight:bold;padding:8px'>✅ ПОДТВЕРДИЛИ</td></tr>"
        for c in yes_calls:
            rows += _call_row(c, "✅")
    if unclear_calls:
        rows += "<tr><td colspan='4' style='background:#fff3e0;font-weight:bold;padding:8px'>❓ НЕ РАСПОЗНАНО</td></tr>"
        for c in unclear_calls:
            rows += _call_row(c, "❓")

    return f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'></head><body style='font-family:sans-serif;padding:20px'>
<h2>📊 Сводка автообзвона</h2>
<p>Время: {s['started_at'][:16]} | Всего: <b>{total}</b></p>
<table style='border-collapse:collapse;width:100%'>
<tr style='background:#f5f5f5'><th>Статус</th><th>Телефон</th><th>Источник</th><th>Время</th></tr>
{rows}
</table>
<p style='color:#666;font-size:12px;margin-top:20px'>CSV: {CSV_RESULTS_PATH.name}</p>
</body></html>"""


def log_dtmf_event(call_id: str, digit: str, phone: str = "", deal_id: str = ""):
    """Записать DTMF событие в JSONL лог."""
    event = {
        "timestamp": datetime.now().isoformat(),
        "call_id": call_id,
        "digit": digit,
        "phone": phone,
        "deal_id": deal_id,
        "action": "confirmed" if digit == "1" else "cancelled" if digit == "0" else "unknown",
    }
    with open(DTMF_LOG, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    log.info(f"📝 DTMF лог: {event}")
    return event


def bx_update_deal_stage(deal_id: str, stage: str):
    """Перевести сделку в Bitrix24 на новую стадию."""
    if not BITRIX_URL or not deal_id:
        log.warning("⚠️ Bitrix URL или deal_id не задан — пропускаю")
        return False
    try:
        resp = requests.post(
            f"{BITRIX_URL}/crm.deal.update",
            json={"id": deal_id, "fields": {"STAGE_ID": stage}},
            timeout=10,
        )
        result = resp.json()
        log.info(f"✅ Bitrix deal {deal_id} → stage {stage}: {result}")
        return result.get("result", False)
    except Exception as e:
        log.error(f"❌ Bitrix error: {e}")
        return False


def bx_add_comment(deal_id: str, comment: str):
    """Добавить комментарий к сделке в Bitrix24."""
    if not BITRIX_URL or not deal_id:
        return
    try:
        requests.post(
            f"{BITRIX_URL}/crm.timeline.comment.add",
            json={
                "fields": {
                    "ENTITY_ID": deal_id,
                    "ENTITY_TYPE": "deal",
                    "COMMENT": comment,
                }
            },
            timeout=10,
        )
    except Exception:
        pass


def tg_notify(message: str):
    """Отправить уведомление в Telegram."""
    if not TG_BOT_TOKEN or not TG_ADMIN_CHAT:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_ADMIN_CHAT, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def handle_dtmf(call_id: str, digit: str, source: str = "dtmf", text: str = ""):
    """Главный обработчик DTMF нажатия."""
    log.info(f"🔢 DTMF: call_id={call_id}, digit={digit}, source={source}")
    
    # Ищем информацию о звонке
    call_info = active_calls.get(call_id, {})
    phone = call_info.get("phone", "неизвестен")
    deal_id = call_info.get("deal_id", "")
    
    # Логируем в JSONL
    event = log_dtmf_event(call_id, digit, phone, deal_id)
    
    # Записать в CSV и сессионную статистику
    _write_csv_row(phone, digit, source, deal_id, text)
    _session_stats["total"] += 1
    if digit == "1":
        _session_stats["confirmed"] += 1
    elif digit == "0":
        _session_stats["cancelled"] += 1
    else:
        _session_stats["unclear"] += 1
    _session_stats["calls"].append({
        "phone": phone, "digit": digit, "deal_id": deal_id,
        "source": source, "time": datetime.now().strftime("%H:%M:%S"),
    })
    
    if digit == "1":
        # ✅ Подтверждение
        log.info(f"✅ ПОДТВЕРЖДЕНО: {phone} (deal={deal_id})")
        
        if deal_id:
            bx_update_deal_stage(deal_id, STAGE_CONFIRMED)
            bx_add_comment(deal_id, (
                f"✅ Клиент ПОДТВЕРДИЛ доставку ({source}={digit})\n"
                f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"Телефон: {phone}"
                + (f"\nSTT: «{text}»" if text else "")
            ))
        
        tg_notify(f"✅ <b>Подтверждение доставки</b>\n📞 {phone}\n🔑 Сделка: {deal_id or 'N/A'}")
        
    elif digit == "0":
        # ❌ Отмена/перенос
        log.info(f"❌ ОТМЕНЕНО/ПЕРЕНЕСЕНО: {phone} (deal={deal_id})")
        
        if deal_id:
            bx_update_deal_stage(deal_id, STAGE_CANCELLED)
            bx_add_comment(deal_id, (
                f"❌ Клиент ПЕРЕНЁС/ОТМЕНИЛ доставку ({source}={digit})\n"
                f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"Телефон: {phone}"
                + (f"\nSTT: «{text}»" if text else "")
            ))
        
        tg_notify(f"❌ <b>Отмена/перенос доставки</b>\n📞 {phone}\n🔑 Сделка: {deal_id or 'N/A'}")
    
    else:
        log.info(f"❓ Неизвестное нажатие: {digit} от {phone}")
    
    return event


class DTMFWebhookHandler(BaseHTTPRequestHandler):
    """HTTP-сервер для приёма DTMF событий от baresip."""
    
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        
        # Поддерживаем JSON и form-encoded
        try:
            data = json.loads(body)
        except:
            data = {k: v[0] for k, v in parse_qs(body).items()}
        
        call_id = data.get("call_id", data.get("entry_id", "unknown"))
        digit = data.get("digit", data.get("dtmf", ""))
        phone = data.get("phone", "")
        deal_id = data.get("deal_id", "")
        source = data.get("source", "dtmf")
        text = data.get("text", "")
        
        # Регистрируем звонок если есть данные
        if call_id != "unknown" and (phone or deal_id):
            active_calls[call_id] = {"phone": phone, "deal_id": deal_id}
        
        if digit:
            result = handle_dtmf(call_id, digit, source=source, text=text)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode())
        else:
            # Регистрация звонка (без DTMF)
            if call_id != "unknown":
                active_calls[call_id] = {"phone": phone, "deal_id": deal_id}
                log.info(f"📞 Зарегистрирован звонок: {call_id} → {phone} (deal={deal_id})")
            
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status": "registered"}')
    
    def do_GET(self):
        """Статус сервера + /summary для Telegram-сводки."""
        path = self.path.rstrip("/")
        
        if path == "/summary":
            summary = _build_summary()
            tg_notify(summary)

            if SMTP_ENABLED:
                email_html = _build_email_report()
                _send_email("📊 Сводка автообзвона", email_html)
            else:
                log.info("📧 Email отключён (SMTP_ENABLED=0)")

            log.info(f"📊 Сводка отправлена — {_session_stats['total']} звонков")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "sent", "total": _session_stats["total"], "summary": summary}
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode())
            return
        
        # Статус сервера (по умолчанию)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {
            "service": "DTMF Handler",
            "active_calls": len(active_calls),
            "session_stats": {
                "started_at": _session_stats["started_at"],
                "total": _session_stats["total"],
                "confirmed": _session_stats["confirmed"],
                "cancelled": _session_stats["cancelled"],
                "unclear": _session_stats["unclear"],
            },
        }
        self.wfile.write(json.dumps(response, ensure_ascii=False, indent=2).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress default HTTP logs


def monitor_baresip_screen():
    """Мониторинг baresip screen-сессии на предмет DTMF."""
    log.info("👁️ Мониторинг baresip screen на DTMF...")
    
    # Регулярка для DTMF в логах baresip
    dtmf_pattern = re.compile(r"DTMF.*?digit[=:]?\s*['\"]?(\d)['\"]?", re.IGNORECASE)
    incoming_pattern = re.compile(r"incoming.*?from.*?(\d+)", re.IGNORECASE)
    
    last_check = ""
    while True:
        try:
            # Снимаем скриншот screen-сессии
            subprocess.run(
                ["screen", "-S", "sip_bot", "-X", "hardcopy", "/tmp/baresip_dtmf.txt"],
                capture_output=True, timeout=5,
            )
            
            with open("/tmp/baresip_dtmf.txt", "r") as f:
                content = f.read()
            
            if content != last_check:
                # Ищем новые DTMF
                new_lines = content[len(last_check):] if last_check else content
                
                for match in dtmf_pattern.finditer(new_lines):
                    digit = match.group(1)
                    log.info(f"🔢 DTMF обнаружен в screen: {digit}")
                    handle_dtmf("screen_call", digit)
                
                last_check = content
            
            time.sleep(0.5)  # Проверяем каждые 500мс
            
        except Exception as e:
            log.error(f"Monitor error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="DTMF Handler")
    parser.add_argument("--mode", choices=["http", "monitor"], default="http",
                       help="Режим: http (webhook сервер) или monitor (мониторинг screen)")
    parser.add_argument("--port", type=int, default=8086, help="Порт HTTP сервера")
    args = parser.parse_args()
    
    if args.mode == "http":
        server = HTTPServer(("0.0.0.0", args.port), DTMFWebhookHandler)
        log.info(f"🚀 DTMF Handler запущен на порту {args.port}")
        log.info(f"   POST http://localhost:{args.port}/ — отправить DTMF")
        log.info(f"   GET  http://localhost:{args.port}/ — статус")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log.info("🛑 Stopped")
            server.server_close()
    
    elif args.mode == "monitor":
        monitor_baresip_screen()
