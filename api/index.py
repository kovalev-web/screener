"""
Vercel serverless API — endpoint для ручного запуска INPLAY-скана.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from daily_scan import build_message, run_scan
from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier


class handler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            client = BinanceClient()
            top = run_scan(client)
            message = build_message(top)

            notifier = TelegramNotifier()
            notifier._send(message)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write('{"status": "ok"}'.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write('{"status": "error"}'.encode("utf-8"))

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write('{"status": "ok"}'.encode("utf-8"))