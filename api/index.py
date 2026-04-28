"""
Vercel serverless API — endpoint для ручного запуска INPLAY-скана.
"""

import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            from binance_client import BinanceClient
            client = BinanceClient()
            tickers = client.get_all_tickers()
            count = len(tickers) if tickers else 0

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"status": "ok", "tickers": {count}}}'.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write('{"status": "error"}'.encode("utf-8"))

    def do_POST(self):
        try:
            from daily_scan import build_message, run_scan
            from binance_client import BinanceClient
            from telegram_notifier import TelegramNotifier

            client = BinanceClient()
            top = run_scan(client)
            message = build_message(top)

            notifier = TelegramNotifier()
            notifier._send(message)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(f'{{"status": "ok", "count": {len(top)}}}'.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write('{"status": "error"}'.encode("utf-8"))