"""
Скоринг inplay-монет.
Главный критерий: RVOL ≥ 10x, держится ≥ 5 минут.

Итого 0–100:
  RVOL сила         0–40  (основной сигнал)
  Устойчивость      0–20  (сколько свечей держится)
  RSI зона          0–20  (не перегрет)
  Ценовое действие  0–20  (флэт=накопление, небольшой рост=моментум)
"""

from typing import Optional


def score_rvol(rvol: float) -> int:
    """0–40. Сила относительного объёма."""
    if rvol >= 50: return 40
    if rvol >= 30: return 36
    if rvol >= 20: return 32
    if rvol >= 15: return 28
    if rvol >= 12: return 24
    if rvol >= 10: return 20
    if rvol >= 7:  return 12
    if rvol >= 5:  return 6
    return 0


def score_sustained(candles_count: int) -> int:
    """0–20. Сколько подряд завершённых 5m свечей с RVOL ≥ 10x."""
    if candles_count >= 6: return 20   # 30+ минут
    if candles_count >= 4: return 16   # 20+ минут
    if candles_count >= 3: return 12   # 15 минут
    if candles_count >= 2: return 8    # 10 минут (минимум для алерта)
    if candles_count >= 1: return 4    # 5 минут (одна завершённая)
    return 0


def score_rsi(rsi: Optional[float]) -> int:
    """0–20. Лучше всего RSI 45–65 на 5m."""
    if rsi is None:         return 8
    if 45 <= rsi <= 65:     return 20
    if 38 <= rsi < 45:      return 14
    if 65 < rsi <= 72:      return 12
    if 30 <= rsi < 38:      return 7
    if 72 < rsi <= 80:      return 4
    return 0


def score_price_action(change_5m: float, change_15m: float) -> int:
    """
    0–20. Оцениваем ценовое действие на 5m/15m.

    Идеальный сигнал для скальпера:
      - Объём взлетел, цена ещё не сильно двинулась (вход до движения)
      - Или небольшой рост (подтверждение импульса)

    Плохо: цена уже улетела (FOMO) или сильно падает.
    """
    # change_5m: изменение за последние 5 минут (1 свеча)
    # change_15m: изменение за последние 15 минут (3 свечи)

    if abs(change_5m) <= 0.5 and abs(change_15m) <= 1.5:
        return 20   # Цена стоит — объём копится → лучший вход

    if 0 < change_5m <= 1.0 and change_15m <= 3.0:
        return 17   # Небольшой рост + объём → подтверждение

    if 1.0 < change_5m <= 2.5:
        return 12   # Движение началось, ещё не поздно

    if -1.0 <= change_5m < 0 and change_15m >= -2.0:
        return 12   # Откат с объёмом → возможен разворот

    if 2.5 < change_5m <= 5.0:
        return 6    # Уже хорошо выросло

    if -3.0 <= change_5m < -1.0:
        return 4    # Заметное падение

    return 0        # Улетело > 5% за 5m или обвал


def calculate_score(
    rvol:          float,
    candles_count: int,
    rsi:           Optional[float],
    change_5m:     float,
    change_15m:    float,
) -> dict:
    v = score_rvol(rvol)
    s = score_sustained(candles_count)
    r = score_rsi(rsi)
    p = score_price_action(change_5m, change_15m)

    total = min(v + s + r + p, 100)

    return {
        "total":     total,
        "rvol":      v,
        "sustained": s,
        "rsi":       r,
        "price":     p,
    }


def classify_signal(score: int, rvol: float, change_5m: float, candles_count: int) -> str:
    """Короткое описание сигнала для алерта."""
    if abs(change_5m) <= 1.0:
        pattern = "Объём без движения цены 🎯"  # Лучший вход
    elif change_5m > 1.0:
        pattern = "Объём + рост 📈"
    else:
        pattern = "Объём + откат 🔄"

    minutes = candles_count * 5
    duration = f"{minutes}+ мин"

    if score >= 75:   strength = "🔥🔥🔥 СИЛЬНЫЙ"
    elif score >= 60: strength = "🔥🔥 Хороший"
    else:             strength = "🔥 Слабый"

    return f"{strength} · {pattern} · держится {duration}"
