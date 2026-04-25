"""
Метрики для inplay-скринера.
Ядро: RVOL (Relative Volume) на 5m свечах.

Что такое RVOL:
  RVOL = объём текущей свечи / средний объём свечи за базовый период.
  RVOL 10x = сейчас торгуется в 10 раз больше обычного.
  Базелайн = первые 72 свечи из 100 (6 часов "нормы" до возможного спайка).
"""

from typing import Dict, List, Optional, Tuple
import time


# ── RSI ────────────────────────────────────────────────────────────

def calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """Wilder RSI."""
    if len(closes) < period + 1:
        return None

    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)


# ── RVOL ───────────────────────────────────────────────────────────

def calc_baseline_avg(quote_vols: List[float], baseline_n: int = 72) -> float:
    """Среднее значение объёма по первым baseline_n свечам."""
    if len(quote_vols) < baseline_n:
        baseline_n = len(quote_vols) // 2
    if baseline_n == 0:
        return 0.0
    return sum(quote_vols[:baseline_n]) / baseline_n


def rvol_series(quote_vols: List[float], baseline_n: int = 72) -> List[float]:
    """
    Возвращает RVOL для каждой свечи.
    RVOL[i] = quote_vols[i] / avg_baseline
    """
    avg_bl = calc_baseline_avg(quote_vols, baseline_n)
    if avg_bl <= 0:
        return [0.0] * len(quote_vols)
    return [round(v / avg_bl, 2) for v in quote_vols]


def check_sustained_rvol(
    rvols:             List[float],
    min_rvol:          float = 10.0,
    sustained_candles: int   = 2,
) -> Tuple[bool, float, int]:
    """
    Проверяет: держится ли RVOL ≥ min_rvol минимум sustained_candles свечей подряд.

    Важно: последняя свеча (-1) обычно ещё формируется → смотрим на завершённые.
    Завершённые свечи: все кроме последней.

    Возвращает:
      (is_sustained, avg_rvol_recent, candles_sustained)
    """
    # Исключаем последнюю (формирующуюся) свечу
    completed = rvols[:-1]
    if len(completed) < sustained_candles:
        return False, 0.0, 0

    # Считаем сколько подряд последних свечей имеют RVOL ≥ порога
    count = 0
    for r in reversed(completed):
        if r >= min_rvol:
            count += 1
        else:
            break

    is_ok    = count >= sustained_candles
    recent_n = min(count, 5) if count > 0 else sustained_candles
    avg_rvol = sum(completed[-recent_n:]) / recent_n if recent_n > 0 else 0.0

    return is_ok, round(avg_rvol, 1), count


def current_rvol(rvols: List[float]) -> float:
    """RVOL последней (возможно формирующейся) свечи."""
    return rvols[-1] if rvols else 0.0


def peak_rvol(rvols: List[float], window: int = 12) -> float:
    """Максимальный RVOL за последние window свечей (1 час на 5m)."""
    if not rvols:
        return 0.0
    recent = rvols[-window:]
    return round(max(recent), 1)


# ── Ценовые метрики ────────────────────────────────────────────────

def price_change_pct(closes: List[float], candles_back: int) -> float:
    """Изменение цены за последние N свечей (%)."""
    if len(closes) < candles_back + 1:
        return 0.0
    old = closes[-(candles_back + 1)]
    now = closes[-1]
    if old == 0:
        return 0.0
    return round(((now - old) / old) * 100, 2)


def calculate_consolidation(highs: List[float], lows: List[float]) -> float:
    """Диапазон (high-low)/low × 100%. Меньше = теснее боковик."""
    if not highs or not lows:
        return 100.0
    max_h = max(h for h in highs if h > 0)
    min_l = min(l for l in lows  if l > 0)
    if min_l <= 0:
        return 100.0
    return round(((max_h - min_l) / min_l) * 100, 2)


# ── Парсинг Klines ─────────────────────────────────────────────────

def extract_kline_data(klines: List[List]) -> Dict:
    """
    Binance klines формат:
    [open_time, open, high, low, close, base_vol, close_time, quote_vol, trades, ...]
    """
    if not klines:
        return {}

    open_times = [int(k[0]) for k in klines]

    return {
        "open_times":  open_times,
        "closes":      [float(k[4]) for k in klines],
        "highs":       [float(k[2]) for k in klines],
        "lows":        [float(k[3]) for k in klines],
        "base_vols":   [float(k[5]) for k in klines],
        "quote_vols":  [float(k[7]) for k in klines],
    }


def candle_age_seconds(open_time_ms: int, interval_seconds: int = 300) -> float:
    """
    Сколько секунд прошло с начала текущей свечи.
    Используется для нормализации объёма незавершённой свечи.
    """
    now_ms = time.time() * 1000
    elapsed = (now_ms - open_time_ms) / 1000
    return min(max(elapsed, 1), interval_seconds)


def scaled_current_vol(quote_vols: List[float], open_times: List[int], interval_sec: int = 300) -> float:
    """
    Нормализованный объём текущей (формирующейся) свечи.
    Если свеча прошла 2.5 из 5 минут с объёмом 500 → экстраполируем до 1000.
    Это даёт точный RVOL даже для незавершённой свечи.
    """
    if not quote_vols or not open_times:
        return 0.0
    age = candle_age_seconds(open_times[-1], interval_sec)
    raw_vol = quote_vols[-1]
    return raw_vol * (interval_sec / age)
