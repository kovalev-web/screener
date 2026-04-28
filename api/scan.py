"""
Vercel serverless API — endpoint для ручного запуска INPLAY-скана.

Вызывается:
  1. По кнопке из Telegram (POST)
  2. По HTTP запросу извне
  3. По Vercel Cron (опционально)
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from daily_scan import build_message, run_scan
from binance_client import BinanceClient
from telegram_notifier import TelegramNotifier


def main(http_trigger: bool = False):
    try:
        client = BinanceClient()
        top = run_scan(client)
        message = build_message(top)

        if http_trigger and TELEGRAM_BOT_TOKEN:
            notifier = TelegramNotifier()
            notifier._send(message)
            return {"status": "ok", "coins": len(top)}

        return {"status": "ok", "message": message, "coins": len(top)}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def handler(request):
    if request.method == "POST":
        result = main(http_trigger=True)
        return {"statusCode": 200, "body": str(result)}
    elif request.method == "GET":
        result = main(http_trigger=False)
        return {"statusCode": 200, "body": str(result)}
    else:
        return {"statusCode": 405, "body": '{"status": "method not allowed"}'}