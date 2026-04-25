"""
Диагностика: почему одни монеты inplay, другие нет.

Запуск:
  python3 diagnose.py

Что делает:
  1. Тянет 1m klines для inplay-монет и "обычных" монет
  2. Считает RVOL для каждой
  3. Выводит сравнительную таблицу
  4. Объясняет почему наш скринер их ловит или нет
"""

import sys
import time
sys.path.insert(0, ".")

from binance_client import BinanceClient
from metrics import rvol_series, check_sustained_rvol, price_change_pct, peak_rvol
from config import BASELINE_CANDLES, MIN_RVOL, SUSTAINED_CANDLES, KLINE_INTERVAL_SEC

binance = BinanceClient()

# ── Монеты для сравнения ───────────────────────────────────────────
INPLAY   = ["BSBUSDT", "ORCAUSDT", "ENSOUSDT", "MOVRUSDT", "ZBTUSDT", "BUSDT"]
ORDINARY = ["SOLUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "ADAUSDT", "MATICUSDT"]

def analyze(symbol: str) -> dict:
    klines = binance.get_klines(symbol, interval="1m", limit=100)
    if not klines or len(klines) < 80:
        return {"symbol": symbol, "error": "нет данных"}

    from metrics import extract_kline_data, scaled_current_vol
    kd = extract_kline_data(klines)
    closes     = kd["closes"]
    quote_vols = kd["quote_vols"]
    open_times = kd["open_times"]

    # Нормализуем текущую свечу
    cur_scaled = scaled_current_vol(quote_vols, open_times, interval_sec=60)
    vols = quote_vols[:-1] + [cur_scaled]

    rvols = rvol_series(vols, baseline_n=BASELINE_CANDLES)

    is_ok, avg_rvol, n_candles = check_sustained_rvol(
        rvols, min_rvol=MIN_RVOL, sustained_candles=SUSTAINED_CANDLES
    )

    avg_baseline = sum(quote_vols[:BASELINE_CANDLES]) / BASELINE_CANDLES
    peak         = peak_rvol(rvols, window=15)
    ch5m         = price_change_pct(closes, 5)
    ch15m        = price_change_pct(closes, 15)

    # Последние 10 RVOL значений (минуты)
    last10 = [f"{r:.1f}x" for r in rvols[-10:]]

    return {
        "symbol":       symbol,
        "inplay":       is_ok,
        "avg_rvol":     avg_rvol,
        "peak_rvol":    peak,
        "n_minutes":    n_candles,
        "baseline_vol": avg_baseline,
        "cur_vol":      cur_scaled,
        "ch5m":         ch5m,
        "ch15m":        ch15m,
        "last10_rvol":  last10,
        "error":        None,
    }


def fmt_vol(v: float) -> str:
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000:     return f"${v/1_000:.1f}K"
    return f"${v:.0f}"


print()
print("=" * 70)
print("  RVOL ДИАГНОСТИКА — 1m свечи, базелайн 70 минут")
print(f"  Критерий алерта: RVOL ≥ {MIN_RVOL}x в течение {SUSTAINED_CANDLES}+ минут подряд")
print("=" * 70)

all_symbols = [("INPLAY (должны алертиться)", INPLAY),
               ("ОБЫЧНЫЕ (не должны алертиться)", ORDINARY)]

for group_name, symbols in all_symbols:
    print(f"\n{'─' * 70}")
    print(f"  {group_name}")
    print(f"{'─' * 70}")
    print(f"  {'Монета':<14} {'RVOL':<8} {'Пик':<8} {'Мин':<6} {'Базелайн':<12} {'Сейчас':<12} {'5m':>7} {'15m':>7}  {'ALERT'}")
    print(f"  {'-'*14} {'-'*7} {'-'*7} {'-'*5} {'-'*11} {'-'*11} {'-'*7} {'-'*7}  {'-'*5}")

    for sym in symbols:
        r = analyze(sym)
        time.sleep(0.15)  # rate limit

        if r.get("error"):
            print(f"  {sym:<14} ERROR: {r['error']}")
            continue

        alert_str = "✅ ДА" if r["inplay"] else "❌ нет"
        print(
            f"  {r['symbol']:<14} "
            f"{r['avg_rvol']:>5.1f}x  "
            f"{r['peak_rvol']:>5.1f}x  "
            f"{r['n_minutes']:>4}  "
            f"{fmt_vol(r['baseline_vol']):<12} "
            f"{fmt_vol(r['cur_vol']):<12} "
            f"{r['ch5m']:>+6.1f}%  "
            f"{r['ch15m']:>+6.1f}%  "
            f"{alert_str}"
        )

        # Последние 10 минут RVOL
        print(f"  {'':14} Последние 10 мин: {' | '.join(r['last10_rvol'])}")
        print()

print()
print("=" * 70)
print("  ВЫВОД")
print("=" * 70)
print("""
  RVOL (Relative Volume) = объём текущей 1m свечи / средний объём за 70 мин

  Inplay монета:  несколько минут подряд торгует в 10x+ раз выше нормы
  Обычная монета: RVOL близко к 1x — торгует как всегда

  Скринер ловит ТОЛЬКО события типа ORCA: тихо-тихо → ВЗРЫВ 10x+
  Таких событий на рынке 1-5 в час среди всех 300 монет.
""")
