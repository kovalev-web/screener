"""
Telegram Webhook Handler — Vercel serverless function.
"""

import os
import json
import logging
import requests
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
VERCEL_URL = os.getenv("VERCEL_URL", "https://screener-l716.vercel.app/api/scan")


class handler(BaseHTTPRequestHandler):

    def _send_reply(self, chat_id: str, text: str):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            r = requests.post(
                f"{TELEGRAM_API}/bot{BOT_TOKEN}/sendMessage",
                json=payload,
                timeout=10,
            )
            return r.json().get("ok", False)
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    def _call_scan(self, chat_id: str):
        try:
            r = requests.post(VERCEL_URL, timeout=55)
            if r.status_code == 200:
                return "✅ Скан выполнен!"
            return f"⚠️ Ошибка: {r.status_code}"
        except Exception as e:
            return f"⚠️ Ошибка: {e}"

    def do_POST(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len > 0 else b"{}"
            data = json.loads(body) if body else {}

            message = data.get("message", {})
            text = message.get("text", "").strip()
            chat_id = str(message.get("chat", {}).get("id", ""))

            if not chat_id:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok":false}')
                return

            if text == "/start":
                reply = "👋 <b>Inplay Screener</b>\n\nНажми /scan для проверки монет."
                self._send_reply(chat_id, reply)
            elif text == "/scan":
                self._send_reply(chat_id, "🔍 Сканирую...")
                result = self._call_scan(chat_id)
                self._send_reply(chat_id, result)
            else:
                self._send_reply(chat_id, "Используй /scan для проверки inplay монет.")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":true}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')