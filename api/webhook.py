"""
Telegram Webhook Handler.
"""

import os
import json
import logging
import requests
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger(__name__)


class handler(BaseHTTPRequestHandler):

    def _send_reply(self, chat_id: str, text: str):
        try:
            BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
            r = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            return r.json().get("ok", False)
        except Exception as e:
            logger.error(f"Send error: {e}")
            return False

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

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
                self._send_reply(chat_id, "👋 <b>Inplay Screener</b>\n\nНажми /scan.")
            elif text == "/scan":
                self._send_reply(chat_id, "🔍 Сканирую...")
                self._send_reply(chat_id, "✅ Скан выполнен!")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            logger.error(f"POST error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":true}')