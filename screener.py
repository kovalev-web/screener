"""
Inplay-скринер. Одно правило:

  RVOL ≥ 10x на 1m свечах, держится 5+ минут подряд → ALERT

Всё остальное неинтересно.

Алгоритм:
  1. GET /api/v3/ticker/24hr — все USDT пары (1 запрос)
  2. Фильтр: убираем BTC/ETH/BNB, стейблы, < $500k объёма
  3. Сканируем ВСЕ оставшиеся монеты (~250-350 штук)
     Для каждой: GET klines 1m × 100 свечей
  4. RVOL = объём свечи / средний объём первых 70 свечей
  5. Если 5+ подряд завершённых 1m свечей с RVOL ≥ 10x → ALERT

Время скана: ~30-40 секунд (250 монет × ~120ms на запрос)
Интервал:    60 секунд
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List

import database as db
from binance_client import BinanceClient
from config import (
    ALERT_COOLDOWN_MINUTES,
    BASELINE_CANDLES,
    EXCLUDED_BASE,
    KLINE_INTERVAL,
    KLINE_INTERVAL_SEC,
    KLINE_LIMIT,
    MIN_CHANGE_MOVING,
    MIN_PRICE_USDT,
    MIN_RVOL,
    MIN_SCORE_TO_ALERT,
    MIN_VOLUME_ALWAYS,
    MIN_VOLUME_MOVING,
    RSI_PERIOD,
    STABLECOIN_KEYWORDS,
    SUSTAINED_CANDLES,
)
from metrics import (
    calculate_consolidation,
    calculate_rsi,
    check_sustained_rvol,
    extract_kline_data,
    peak_rvol,
    price_change_pct,
    rvol_series,
    scaled_current_vol,
)
from scorer import calculate_score, classify_signal
from telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class InplayScreener:
    def __init__(self):
        self.binance  = BinanceClient()
        self.notifier = TelegramNotifier()

        self._scan_count    = 0
        self._total_alerted = 0

    # ── Фильтр монет ───────────────────────────────────────────────

    def _is_valid_altcoin(self, ticker: Dict) -> bool:
        symbol = ticker.get("symbol", "")
        if not symbol.endswith("USDT"):
            return False

        base = symbol[:-4]

        if base in EXCLUDED_BASE:
            return False

        if any(kw in base for kw in STABLECOIN_KEYWORDS):
            return False

        # Leveraged tokens
        if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
            return False

        if float(ticker.get("lastPrice", 0)) < MIN_PRICE_USDT:
            return False

        # Двухуровневый фильтр объёма:
        # Уровень 1: крупные ликвидные монеты — всегда мониторим
        # Уровень 2: небольшие монеты — мониторим если уже движутся (≥5% за 24ч)
        vol    = float(ticker.get("quoteVolume", 0))
        change = abs(float(ticker.get("priceChangePercent", 0)))

        if vol >= MIN_VOLUME_ALWAYS:
            return True
        if vol >= MIN_VOLUME_MOVING and change >= MIN_CHANGE_MOVING:
            return True

        return False

    # ── Совместимость ──────────────────────────────────────────────

    def load_baselines(self):
        logger.info("Базелайн встроен в 1m klines. Начинаем сканирование.")

    # ── Основной скан ──────────────────────────────────────────────

    def scan(self) -> List[Dict]:
        self._scan_count += 1
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        logger.info(f"── Скан #{self._scan_count} — {ts} ──")

        # 1. Все тикеры одним запросом
        all_tickers = self.binance.get_all_tickers()
        if not all_tickers:
            logger.error("Нет данных от Binance")
            return []

        # 2. Фильтруем: оставляем все валидные альткоины
        valid = [t for t in all_tickers if self._is_valid_altcoin(t)]
        logger.info(f"Сканирую {len(valid)} монет...")

        # 3. Сохраняем снапшоты в БД
        db.save_snapshots([{
            "symbol":           t["symbol"],
            "quote_volume_24h": float(t.get("quoteVolume", 0)),
            "price":            float(t.get("lastPrice", 0)),
            "price_change_pct": float(t.get("priceChangePercent", 0)),
            "high_24h":         float(t.get("highPrice", 0)),
            "low_24h":          float(t.get("lowPrice", 0)),
        } for t in valid])

        # 4. Полный RVOL-скан всех монет
        inplay_coins = []
        checked = 0
        skipped_data = 0

        for ticker in valid:
            symbol = ticker["symbol"]

            # Получаем 1m klines
            klines = self.binance.get_klines(
                symbol, interval=KLINE_INTERVAL, limit=KLINE_LIMIT
            )
            kd = extract_kline_data(klines)

            if not kd or len(kd.get("closes", [])) < BASELINE_CANDLES + 10:
                skipped_data += 1
                continue

            checked += 1
            closes     = kd["closes"]
            highs      = kd["highs"]
            lows       = kd["lows"]
            quote_vols = kd["quote_vols"]
            open_times = kd["open_times"]

            # ── RVOL ─────────────────────────────────────────────
            # Нормализуем текущую (формирующуюся) свечу по времени
            cur_scaled = scaled_current_vol(
                quote_vols, open_times, interval_sec=KLINE_INTERVAL_SEC
            )
            vols = quote_vols[:-1] + [cur_scaled]
            rvols = rvol_series(vols, baseline_n=BASELINE_CANDLES)

            # Главная проверка: 5+ минут с RVOL ≥ 10x
            is_sustained, avg_rvol, n_candles = check_sustained_rvol(
                rvols,
                min_rvol          = MIN_RVOL,
                sustained_candles = SUSTAINED_CANDLES,
            )

            if not is_sustained:
                continue  # ← Большинство монет отсеивается здесь

            # ── Дополнительные метрики (только для прошедших) ────
            rsi        = calculate_rsi(closes, period=RSI_PERIOD)
            change_5m  = price_change_pct(closes, candles_back=5)
            change_15m = price_change_pct(closes, candles_back=15)
            change_1h  = price_change_pct(closes, candles_back=min(60, len(closes) - 1))
            change_24h = float(ticker.get("priceChangePercent", 0))
            cons_pct   = calculate_consolidation(highs[-10:], lows[-10:])
            peak       = peak_rvol(rvols, window=15)
            price      = float(ticker.get("lastPrice", 0))

            breakdown = calculate_score(
                rvol          = avg_rvol,
                candles_count = n_candles,
                rsi           = rsi,
                change_5m     = change_5m,
                change_15m    = change_15m,
            )
            total_score = breakdown["total"]
            signal_label = classify_signal(total_score, avg_rvol, change_5m, n_candles)

            logger.info(
                f"  🔥 {symbol:<14} "
                f"RVOL={avg_rvol:.0f}x ({n_candles}мин)  "
                f"peak={peak:.0f}x  "
                f"5m={change_5m:+.1f}%  15m={change_15m:+.1f}%  "
                f"RSI={rsi}  score={total_score}"
            )

            inplay_coins.append({
                "symbol":            symbol,
                "price":             price,
                "price_change_24h":  change_24h,
                "change_5m":         change_5m,
                "change_15m":        change_15m,
                "change_1h":         change_1h,
                "rvol":              avg_rvol,
                "rvol_peak":         peak,
                "candles_sustained": n_candles,
                "rsi":               rsi,
                "consolidation_pct": cons_pct,
                "score":             total_score,
                "score_breakdown":   breakdown,
                "signal_label":      signal_label,
            })

        logger.info(
            f"Проверено: {checked}  |  "
            f"Пропущено (мало данных): {skipped_data}  |  "
            f"INPLAY (RVOL≥{MIN_RVOL:.0f}x, {SUSTAINED_CANDLES}мин): {len(inplay_coins)}"
        )

        inplay_coins.sort(key=lambda x: x["rvol"], reverse=True)
        return inplay_coins

    # ── Отправка алертов ───────────────────────────────────────────

    def process_alerts(self, inplay_coins: List[Dict]) -> int:
        sent = 0
        for coin in inplay_coins:
            symbol = coin["symbol"]

            if db.was_recently_alerted(symbol, ALERT_COOLDOWN_MINUTES):
                logger.debug(f"{symbol}: кулдаун {ALERT_COOLDOWN_MINUTES} мин")
                continue

            ok = self.notifier.send_inplay_alert(coin)
            if ok:
                db.save_alert(
                    symbol       = symbol,
                    score        = coin["score"],
                    volume_spike = coin["rvol"],
                    rsi          = coin.get("rsi"),
                    details      = coin,
                )
                self._total_alerted += 1
                sent += 1
                logger.info(
                    f"✅ АЛЕРТ: {symbol}  "
                    f"RVOL={coin['rvol']:.0f}x  "
                    f"5m={coin['change_5m']:+.1f}%"
                )
            else:
                logger.error(f"Ошибка отправки: {symbol}")

        return sent
