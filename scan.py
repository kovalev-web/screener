"""
INPLAY Scan API.
"""

import sys
import os
import logging
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            from daily_scan import run_scan
            from binance_client import BinanceClient
            from telegram_notifier import TelegramNotifier

            client = BinanceClient()
            top = run_scan(client)

            notifier = TelegramNotifier()
            notifier._send(f"Скан выполнен! Inplay: {len(top)} монет")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"status":"ok","count":{len(top)}}}'.encode())
        except Exception as e:
            logger.error(f"Error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f'{{"status":"error"}}'.encode())