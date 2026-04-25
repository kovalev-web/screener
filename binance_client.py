"""
Binance REST API client.

Использует только публичные endpoints — API-ключ не нужен.
Rate limits Binance:
  - GET /api/v3/ticker/24hr  →  weight 40 (все символы)
  - GET /api/v3/klines        →  weight 2 за запрос
  - Лимит: 1200 weight/min
"""

import time
import logging
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import BINANCE_BASE_URL

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self):
        self.base_url = BINANCE_BASE_URL
        self._used_weight   = 0
        self._weight_reset  = time.time() + 60  # скользящее окно
        self._max_weight    = 1100               # оставляем запас

        # HTTP-сессия с автоматическим retry
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist={429, 500, 502, 503, 504},
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.headers.update({"Accept": "application/json"})

    # ── внутренние методы ──────────────────────────────────────────

    def _check_rate_limit(self, weight: int):
        """Приостанавливает выполнение если приближаемся к лимиту."""
        now = time.time()
        if now >= self._weight_reset:
            self._used_weight = 0
            self._weight_reset = now + 60

        if self._used_weight + weight >= self._max_weight:
            sleep_secs = self._weight_reset - now + 0.5
            logger.warning(f"Rate limit: спим {sleep_secs:.1f}с")
            time.sleep(max(sleep_secs, 1))
            self._used_weight = 0
            self._weight_reset = time.time() + 60

    def _get(self, endpoint: str, params: Dict = None, weight: int = 1) -> Optional[Any]:
        self._check_rate_limit(weight)
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.get(url, params=params, timeout=10)

            # Обновляем счётчик по заголовку биржи
            used = resp.headers.get("X-MBX-USED-WEIGHT-1M")
            if used:
                self._used_weight = int(used)
            else:
                self._used_weight += weight

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 30))
                logger.warning(f"429 Too Many Requests — ждём {retry_after}с")
                time.sleep(retry_after)
                return None

            resp.raise_for_status()
            return resp.json()

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
        GET /api/v3/ticker/24hr
        Возвращает 24ч статистику по всем торговым парам.
        Weight: 40
        """
        data = self._get("/api/v3/ticker/24hr", weight=40)
        return data if isinstance(data, list) else []

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 20,
    ) -> List[List]:
        """
        GET /api/v3/klines
        Формат свечи: [open_time, open, high, low, close, volume,
                        close_time, quote_volume, trades, ...]
        Weight: 2
        """
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        data = self._get("/api/v3/klines", params=params, weight=2)
        return data if isinstance(data, list) else []

    def get_price(self, symbol: str) -> Optional[float]:
        """GET /api/v3/ticker/price — текущая цена. Weight: 2"""
        data = self._get("/api/v3/ticker/price", params={"symbol": symbol}, weight=2)
        if data and "price" in data:
            return float(data["price"])
        return None
