"""
OKX USDT Perpetual Swap REST API client.

Drop-in замена Binance/Bybit клиента — те же методы, тот же формат данных.
OKX не блокирует облачные провайдеры.
Цены USDT perpetual практически идентичны Binance благодаря арбитражу.

Rate limits OKX (без API-ключа):
  - /api/v5/market/tickers  →  20 req/2s
  - /api/v5/market/candles  →  40 req/2s

instId формат OKX: SOL-USDT-SWAP, BTC-USDT-SWAP, ...
"""

import time
import logging
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

OKX_BASE_URL = "https://www.okx.com"

# Маппинг интервалов Binance → OKX
INTERVAL_MAP = {
    "1m":  "1m",
    "3m":  "3m",
    "5m":  "5m",
    "15m": "15m",
    "30m": "30m",
    "1h":  "1H",
    "2h":  "2H",
    "4h":  "4H",
    "6h":  "6H",
    "12h": "12H",
    "1d":  "1D",
    "1w":  "1W",
    "1M":  "1M",
}

# Длительность интервала в миллисекундах (для close_time)
INTERVAL_MS = {
    "1m":  60_000,
    "3m":  180_000,
    "5m":  300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h":  3_600_000,
    "2h":  7_200_000,
    "4h":  14_400_000,
    "6h":  21_600_000,
    "12h": 43_200_000,
    "1d":  86_400_000,
    "1w":  604_800_000,
}


def _binance_symbol_to_okx(symbol: str) -> str:
    """SOLUSDT → SOL-USDT-SWAP"""
    base = symbol[:-4]  # убираем USDT
    return f"{base}-USDT-SWAP"


def _okx_instid_to_binance(inst_id: str) -> str:
    """SOL-USDT-SWAP → SOLUSDT"""
    base = inst_id.split("-")[0]
    return f"{base}USDT"


class BinanceClient:
    """
    OKX-клиент с интерфейсом Binance.
    Все методы возвращают данные в формате Binance для полной совместимости.
    """

    def __init__(self):
        self.base_url = OKX_BASE_URL

        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist={429, 500, 502, 503, 504},
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        })

        # Rate limiter: не более 8 запросов в секунду
        self._last_request_time = 0.0
        self._min_interval = 0.125  # 125ms между запросами

    # ── внутренние методы ──────────────────────────────────────────

    def _get(self, endpoint: str, params: Dict = None) -> Optional[Any]:
        """HTTP GET с throttle и обработкой ошибок OKX."""
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

            # OKX возвращает {"code": "0", "data": [...]}
            if data.get("code") != "0":
                logger.error(
                    f"OKX error {data.get('code')}: "
                    f"{data.get('msg')} | {endpoint}"
                )
                return None

            return data.get("data")

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
        GET /api/v5/market/tickers?instType=SWAP
        Возвращает тикеры в формате Binance Futures:
          symbol, lastPrice, quoteVolume, priceChangePercent, highPrice, lowPrice
        """
        data = self._get("/api/v5/market/tickers", params={"instType": "SWAP"})
        if not data:
            return []

        tickers = []
        for item in data:
            inst_id = item.get("instId", "")
            # Берём только USDT-SWAP пары
            if not inst_id.endswith("-USDT-SWAP"):
                continue

            symbol = _okx_instid_to_binance(inst_id)

            try:
                last_price = float(item.get("last", 0))
                open_price = float(item.get("open24h", last_price))  # цена 24ч назад
                vol_usdt   = float(item.get("volCcy24h", 0))         # оборот в USDT

                # Считаем priceChangePercent вручную (OKX не даёт напрямую)
                if open_price > 0:
                    price_change_pct = ((last_price - open_price) / open_price) * 100
                else:
                    price_change_pct = 0.0

                tickers.append({
                    "symbol":             symbol,
                    "lastPrice":          str(last_price),
                    "quoteVolume":        str(vol_usdt),
                    "priceChangePercent": str(round(price_change_pct, 4)),
                    "highPrice":          item.get("high24h", "0"),
                    "lowPrice":           item.get("low24h", "0"),
                    "volume":             item.get("vol24h", "0"),    # base volume
                    "openPrice":          str(open_price),
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
        GET /api/v5/market/candles
        Конвертирует ответ OKX в формат Binance:
          [open_time, open, high, low, close, base_vol, close_time, quote_vol, ...]

        OKX candle формат: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        Важно: OKX возвращает свечи от новых к старым — реверсируем.
        """
        inst_id        = _binance_symbol_to_okx(symbol)
        okx_interval   = INTERVAL_MAP.get(interval, interval)
        interval_ms    = INTERVAL_MS.get(interval, 60_000)

        data = self._get("/api/v5/market/candles", params={
            "instId": inst_id,
            "bar":    okx_interval,
            "limit":  limit,
        })
        if not data:
            return []

        # OKX: список от новых к старым → разворачиваем
        raw = list(reversed(data))

        klines = []
        for row in raw:
            try:
                start_ms = int(row[0])
                # OKX candle: [ts, o, h, l, c, vol(contracts), volCcy(base), volCcyQuote(USDT), confirm]
                # Для RVOL нужен USDT-объём: row[7]=volCcyQuote, fallback на row[6]
                quote_vol = row[7] if len(row) > 7 else row[6]
                klines.append([
                    start_ms,                    # [0] open_time (ms)
                    row[1],                      # [1] open
                    row[2],                      # [2] high
                    row[3],                      # [3] low
                    row[4],                      # [4] close
                    row[5],                      # [5] base volume (contracts)
                    start_ms + interval_ms - 1,  # [6] close_time (ms)
                    quote_vol,                   # [7] quote_volume (USDT) ← для RVOL
                    "0",                         # [8] trades
                    "0", "0", "0",               # [9-11] ignored
                ])
            except (IndexError, ValueError):
                continue

        return klines

    def get_price(self, symbol: str) -> Optional[float]:
        """GET /api/v5/market/ticker — текущая цена символа."""
        inst_id = _binance_symbol_to_okx(symbol)
        data = self._get("/api/v5/market/ticker", params={"instId": inst_id})
        if data and len(data) > 0:
            try:
                return float(data[0]["last"])
            except (KeyError, ValueError, IndexError):
                pass
        return None
