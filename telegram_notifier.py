"""
Telegram-нотификатор для inplay-скринера.

Форматирует и отправляет алерты через Bot API.
Не требует библиотеки python-telegram-bot — работает на чистом requests.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.token   = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{token}"

    # ── низкоуровневая отправка ────────────────────────────────────

    def _send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.token or not self.chat_id:
            logger.warning("Telegram не настроен — токен или chat_id отсутствуют")
            return False

        try:
            resp = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    "chat_id":                  self.chat_id,
                    "text":                     text,
                    "parse_mode":               parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                logger.error("Telegram error: %s", result)
                return False
            return True

        except requests.exceptions.RequestException as e:
            logger.error("Ошибка отправки в Telegram: %s", e)
            return False

    # ── публичные методы ───────────────────────────────────────────

    def send_inplay_alert(self, coin: Dict) -> bool:
        """Форматирует и отправляет inplay-алерт."""
        symbol      = coin["symbol"]
        base        = symbol.replace("USDT", "")
        score       = coin["score"]
        rvol        = coin.get("rvol", 0)
        rvol_peak   = coin.get("rvol_peak", 0)
        n_candles   = coin.get("candles_sustained", 0)
        rsi         = coin.get("rsi")
        price       = coin["price"]
        change_5m   = coin.get("change_5m", 0)
        change_15m  = coin.get("change_15m", 0)
        change_1h   = coin.get("change_1h", 0)
        change_24h  = coin.get("price_change_24h", 0)
        cons        = coin.get("consolidation_pct", 0)
        label       = coin.get("signal_label", "")

        if score >= 75:   fire = "🔥🔥🔥"
        elif score >= 60: fire = "🔥🔥"
        else:             fire = "🔥"

        filled = round(score / 10)
        bar    = "█" * filled + "░" * (10 - filled)

        # Ссылки на фьючерсный график — 1m для входа, 5m для контекста
        tv_1m = f"https://www.tradingview.com/chart/?symbol=BINANCE:{base}USDTPERP&interval=1"
        tv_5m = f"https://www.tradingview.com/chart/?symbol=BINANCE:{base}USDTPERP&interval=5"

        if price >= 1:         price_str = f"${price:.4f}"
        elif price >= 0.001:   price_str = f"${price:.6f}"
        else:                  price_str = f"${price:.8f}"

        rsi_text     = f"{rsi:.1f}" if rsi is not None else "—"
        minutes_held = n_candles * 5
        now_utc      = datetime.now(timezone.utc).strftime("%H:%M UTC")

        text = (
            f"{fire} <b>INPLAY — {base}/USDT</b>\n"
            f"\n"
            f"📊 RVOL: <b>{rvol:.0f}x</b>  (держится {minutes_held}+ мин)\n"
            f"💰 Цена: <b>{price_str}</b>\n"
            f"⚡ 5m: <b>{change_5m:+.2f}%</b>  ·  15m: <b>{change_15m:+.2f}%</b>\n"
            f"\n"
            f"🕐 {now_utc}\n"
            f"<a href=\"{tv_1m}\">1m</a>  ·  <a href=\"{tv_5m}\">5m</a>"
        )

        return self._send(text)

    def send_status(self, message: str) -> bool:
        return self._send(f"ℹ️ {message}")

    def send_error(self, error: str) -> bool:
        return self._send(f"⚠️ <b>Ошибка скринера:</b>\n<code>{error}</code>")

    def send_startup(self, coin_count: int) -> bool:
        return self._send(
            f"🚀 <b>Inplay скринер запущен</b>\n"
            f"🔍 Мониторю <b>{coin_count}</b> монет (≥$20M объём/сутки)\n"
            f"⏱ Сканирование каждые <b>60 секунд</b>\n"
            f"📊 Критерий: RVOL ≥ 10x в течение 5+ минут"
        )

    def send_scan_summary(self, total: int, candidates: int, alerted: int) -> bool:
        """Краткая сводка — отправляется редко (каждые N сканов)."""
        return self._send(
            f"📋 <b>Итог скана</b>\n"
            f"Монет отсканировано: {total}\n"
            f"Кандидатов с спайком: {candidates}\n"
            f"Алертов отправлено: {alerted}"
        )

    def test_connection(self) -> bool:
        """Проверяет соединение с Telegram, возвращает True/False."""
        return self._send("✅ Тест соединения — скринер готов к работе")
