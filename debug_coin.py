"""
Диагностика конкретной монеты — почему она в списке или нет.
Запуск: python3 debug_coin.py ILVUSDT
"""
import sys
from binance_client import BinanceClient
from daily_scan import (
    DAILY_RVOL_MIN, MIN_CHANGE_PCT, MIN_INTRADAY_PCT,
    MIN_VOLUME_24H, MAX_REVERSAL_PCT, HISTORY_DAYS, TOP_N
)

symbol = sys.argv[1].upper() if len(sys.argv) > 1 else "ILVUSDT"
client = BinanceClient()

tickers = client.get_all_tickers()
ticker  = next((t for t in tickers if t["symbol"] == symbol), None)

if not ticker:
    print(f"❌ {symbol} не найден на Binance Futures")
    sys.exit(1)

price   = float(ticker.get("lastPrice", 0))
vol_24h = float(ticker.get("quoteVolume", 0))

# Дневные свечи (от полуночи UTC)
klines       = client.get_klines(symbol, interval="1d", limit=HISTORY_DAYS)
history      = klines[:-1]
today        = klines[-1]
history_vols = [float(k[7]) for k in history]
today_vol    = float(today[7])
avg_vol      = sum(history_vols) / len(history_vols) if history_vols else 0
daily_rvol   = today_vol / avg_vol if avg_vol > 0 else 0

open_price   = float(today[1])
high_price   = float(today[2])
change_pct   = ((price / open_price) - 1) * 100 if open_price > 0 else 0
intraday_pct = ((high_price / open_price) - 1) * 100 if open_price > 0 else 0
reversal_pct = (price / high_price * 100) if high_price > 0 else 100

passes_vol      = daily_rvol >= DAILY_RVOL_MIN
passes_intraday = intraday_pct >= MIN_INTRADAY_PCT
passes_change   = change_pct >= MIN_CHANGE_PCT
passes_volume   = vol_24h >= MIN_VOLUME_24H
passes_reversal = reversal_pct >= MAX_REVERSAL_PCT

score = (
    daily_rvol          * 0.4 +
    (intraday_pct / 8)  * 0.4 +
    (max(change_pct, 0) / 10) * 0.2
)

print(f"\n{'='*52}")
print(f"  Диагностика: {symbol}")
print(f"{'='*52}")
print(f"  Цена сейчас:      ${price:.6f}")
print(f"  Открытие дня:     ${open_price:.6f}  (полночь UTC)")
print(f"  Хай дня:          ${high_price:.6f}")
print(f"  Изм. от открытия: {change_pct:+.2f}%")
print(f"  Хай от открытия:  {intraday_pct:+.2f}%")
print(f"  Объём сегодня:    ${today_vol:,.0f}")
print(f"  Средний 7д:       ${avg_vol:,.0f}")
print(f"  Объём 24ч:        ${vol_24h:,.0f}")
print(f"{'─'*52}")
print(f"  Объём ≥ $5M:      {'✅' if passes_volume else '❌'}  (${vol_24h/1e6:.1f}M)")
print(f"  Нет разворота:    {'✅' if passes_reversal else '❌'}  (цена = {reversal_pct:.0f}% от хая, порог ≥ {MAX_REVERSAL_PCT:.0f}%)")
print(f"{'─'*52}")
print(f"  Критерии (достаточно одного):")
print(f"  RVOL ≥ {DAILY_RVOL_MIN}x:       {'✅' if passes_vol else '❌'}  ({daily_rvol:.2f}x)")
print(f"  Хай дня ≥ +{MIN_INTRADAY_PCT:.0f}%:   {'✅' if passes_intraday else '❌'}  ({intraday_pct:+.2f}%)")
print(f"  Сейчас ≥ +{MIN_CHANGE_PCT:.0f}%:   {'✅' if passes_change else '❌'}  ({change_pct:+.2f}%)")
print(f"{'─'*52}")

passes_any = passes_vol or passes_intraday or passes_change
in_list    = passes_volume and passes_reversal and passes_any

print(f"  ИТОГ: {'✅ ПОПАДЁТ в список' if in_list else '❌ НЕ ПОПАДЁТ'}")
if in_list:
    print(f"  Скор: {score:.2f}  (топ-{TOP_N} по скору попадут в отчёт)")
else:
    reasons = []
    if not passes_volume:   reasons.append(f"объём ${vol_24h/1e6:.1f}M < ${MIN_VOLUME_24H/1e6:.0f}M")
    if not passes_reversal: reasons.append(f"разворот {reversal_pct:.0f}% < {MAX_REVERSAL_PCT:.0f}% от хая")
    if not passes_any:      reasons.append(f"RVOL {daily_rvol:.1f}x, хай {intraday_pct:+.1f}%, сейчас {change_pct:+.1f}% — все ниже порогов")
    print(f"  Причина: {',  '.join(reasons)}")
print()
