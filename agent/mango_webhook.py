#!/usr/bin/env python3
"""
Mango Office Webhook Server

Сервер для приёма уведомлений от Mango Office API.
Запускается на VPS или локально с ngrok.

Использование:
    python3 mango_webhook.py --port 8080
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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "")


class MangoWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        # Логируем запрос
        timestamp = datetime.now().isoformat()
        print(f"\n[{timestamp}] POST {self.path}")
        print(f"Body: {body.decode('utf-8')}")
        
        # Проверяем подпись (опционально)
        # sign = self.headers.get('Sign', '')
        
        # Отвечаем OK
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
        
        # Обрабатываем событие
        try:
            data = json.loads(body)
            event_type = self.path.split('/')[-1]
            print(f"📞 Событие: {event_type}")
            print(f"   Данные: {json.dumps(data, indent=2)}")
        except Exception as e:
            print(f"Ошибка парсинга: {e}")
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status":"Mango Webhook Online"}')
    
    def log_message(self, format, *args):
        print(f"[{datetime.now().isoformat()}] {args[0]}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Mango Office Webhook Server')
    parser.add_argument('--port', type=int, default=8085, help='Port to listen on')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to')
    args = parser.parse_args()
    
    server = HTTPServer((args.host, args.port), MangoWebhookHandler)
    print("🤖 Mango Webhook Server")
    print(f"   Listening on {args.host}:{args.port}")
    print(f"   Webhook URL: http://{args.host}:{args.port}/vpbx/result/callback")
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
