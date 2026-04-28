"""
Vercel serverless API — endpoint для ручного запуска INPLAY-скана.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from daily_scan import build_message, run_scan
from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier


def handler(request):
    if request.method == "POST":
        try:
            client = BinanceClient()
            top = run_scan(client)
            message = build_message(top)

            notifier = TelegramNotifier()
            notifier._send(message)

            return {"statusCode": 200, "body": '{"status": "ok"}'}
        except Exception as e:
            return {"statusCode": 500, "body": f'{{"status": "error", "error": "{e}"}}'}
    else:
        return {"statusCode": 405, "body": '{"status": "method not allowed"}'}