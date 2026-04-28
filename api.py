"""
INPLAY Scan API — Vercel serverless function.
"""

import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from daily_scan import build_message, run_scan
from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            client = BinanceClient()
            top = run_scan(client)
            message = build_message(top)

            notifier = TelegramNotifier()
            notifier._send(message)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"status":"ok","count":{len(top)}}}'.encode())
        except Exception as e:
            logger.error(f"Scan error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"status":"error"}')

    def do_POST(self):
        self.do_GET()