"""
INPLAY Scan API — Vercel serverless function.
"""

import sys
import os
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class handler(BaseHTTPRequestHandler):

    def _send_telegram(self, text: str) -> bool:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.warning("Telegram не настроен")
            return False
        import requests
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
            return r.json().get("ok", False)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    def _run_scan(self):
        import requests
        from daily_scan import build_message, run_scan
        from binance_client import BinanceClient

        client = BinanceClient()
        top = run_scan(client)
        message = build_message(top)
        self._send_telegram(message)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_POST(self):
        try:
            self._run_scan()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"status":"error"}')