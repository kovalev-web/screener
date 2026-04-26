"""
Bybit USDT Linear Futures REST API client.

Drop-in замена Binance клиента — те же методы, тот же формат данных.
Bybit не блокирует облачные провайдеры (Railway, Render, Fly.io и т.д.).
Цены USDT perpetual практически идентичны Binance благодаря арбитражу.

Rate limits Bybit (без API-ключа):
  - /v5/market/tickers  →  10 req/s
  - /v5/market/kline    →  10 req/s
"""

import time
import logging
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BYBIT_BASE_URL = "https://api.bybit.com"

# Маппинг интервалов Binance → Bybit
INTERVAL_MAP = {
    "1m":  "1",
    "3m":  "3",
    "5m":  "5",
    "15m": "15",
    "30m": "30",
    "1h":  "60",
    "2h":  "120",
    "4h":  "240",
    "6h":  "360",
    "12h": "720",
    "1d":  "D",
    "1w":  "W",
    "1M":  "M",
}

# Длительность интервала в миллисекундах (для close_time)
INTERVAL_MS = {
    "1":   60_000,
    "3":   180_000,
    "5":   300_000,
    "15":  900_000,
    "30":  1_800_000,
    "60":  3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "360": 21_600_000,
    "720": 43_200_000,
    "D":   86_400_000,
    "W":   604_800_000,
}


class BinanceClient:
    """
    Bybit-клиент с интерфейсом Binance.
    Все методы возвращают данные в формате Binance для полной совместимости.
    """

    def __init__(self):
        self.base_url = BYBIT_BASE_URL

        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist={429, 500, 502, 503, 504},
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.headers.update({"Accept": "application/json"})

        # Простой rate limiter: не более 8 запросов в секунду
        self._last_request_time = 0.0
        self._min_interval = 0.125  # 1/8 секунды между запросами

    # ── внутренние методы ──────────────────────────────────────────

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        """HTTP GET с throttle и обработкой ошибок Bybit."""
        # Throttle
        now = time.time()
        since_last = now - self._last_request_time
        if since_last < self._min_interval:
            time.sleep(self._min_interval - since_last)
        self._last_request_time = time.time()

        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=10)

            if resp.status_code == 429:
                logger.warning("429 Too Many Requests — ждём 5с")
                time.sleep(5)
                return None

            resp.raise_for_status()
            data = resp.json()

            # Bybit всегда возвращает {"retCode": 0, "result": {...}}
            if data.get("retCode") != 0:
                logger.error(
                    f"Bybit error {data.get('retCode')}: "
                    f"{data.get('retMsg')} | {endpoint}"
                )
                return None

            return data.get("result")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout: {endpoint}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {resp.status_code}: {endpoint}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        return None

    # ── публичные методы ───────────────────────────────────────────

    def get_all_tickers(self) -> List[Dict]:
        """
        GET /v5/market/tickers?category=linear
        Возвращает тикеры в формате Binance Futures:
          symbol, lastPrice, quoteVolume, priceChangePercent, highPrice, lowPrice
        """
        result = self._get("/v5/market/tickers", params={"category": "linear"})
        if not result or "list" not in result:
            return []

        tickers = []
        for item in result["list"]:
            symbol = item.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue

            try:
                # Bybit price24hPcnt — десятичная дробь (0.05 = 5%)
                price_change_pct = float(item.get("price24hPcnt", 0)) * 100

                tickers.append({
                    "symbol":             symbol,
                    "lastPrice":          item.get("lastPrice", "0"),
                    "quoteVolume":        item.get("turnover24h", "0"),    # USDT оборот за 24ч
                    "priceChangePercent": str(round(price_change_pct, 4)),
                    "highPrice":          item.get("highPrice24h", "0"),
                    "lowPrice":           item.get("lowPrice24h", "0"),
                    "volume":             item.get("volume24h", "0"),      # base volume
                    "openPrice":          item.get("prevPrice24h", "0"),   # цена 24ч назад
                })
            except (ValueError, TypeError):
                continue

        return tickers

    def get_klines(
        self,
        symbol:   str,
        interval: str = "1m",
        limit:    int = 100,
    ) -> List[List]:
        """
        GET /v5/market/kline?category=linear
        Конвертирует ответ Bybit в формат Binance:
          [open_time, open, high, low, close, base_vol, close_time, quote_vol, ...]

        Важно: Bybit возвращает свечи от новых к старым — реверсируем.
        """
        bybit_interval = INTERVAL_MAP.get(interval, interval)
        result = self._get("/v5/market/kline", params={
            "category": "linear",
            "symbol":   symbol,
            "interval": bybit_interval,
            "limit":    limit,
        })
        if not result or "list" not in result:
            return []

        # Bybit: [startTime, open, high, low, close, volume, turnover]
        # отсортирован от новых к старым → разворачиваем
        raw = list(reversed(result["list"]))

        interval_ms = INTERVAL_MS.get(bybit_interval, 60_000)

        klines = []
        for row in raw:
            try:
                start_ms = int(row[0])
                klines.append([
                    start_ms,                    # [0] open_time (ms)
                    row[1],                      # [1] open
                    row[2],                      # [2] high
                    row[3],                      # [3] low
                    row[4],                      # [4] close
                    row[5],                      # [5] base volume
                    start_ms + interval_ms - 1,  # [6] close_time (ms)
                    row[6],                      # [7] quote_volume (USDT) ← главное
                    "0",                         # [8] trades (нет без ключа)
                    "0", "0", "0",               # [9-11] игнорируемые поля
                ])
            except (IndexError, ValueError):
                continue

        return klines

    def get_price(self, symbol: str) -> Optional[float]:
        """GET /v5/market/tickers — текущая цена символа."""
        result = self._get("/v5/market/tickers", params={
            "category": "linear",
            "symbol":   symbol,
        })
        if result and "list" in result and result["list"]:
            try:
                return float(result["list"][0]["lastPrice"])
            except (KeyError, ValueError):
                pass
        return None
