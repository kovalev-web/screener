"""
Дневной inplay-скан — топ монет по активности за сутки.

Запуск:
  python3 daily_scan.py          — вывод в консоль
  python3 daily_scan.py --tg     — вывод в консоль + отправить в Telegram

Логика отбора — монета проходит если выполняется хотя бы одно:
  1. Объёмный взрыв:  дневной RVOL ≥ 1.3x (объём аномальный — главный сигнал)
  2. Ценовой тренд:   текущий рост ≥ +7% от открытия дня (стабильный рост)

  Фильтр качества: цена не ниже 65% от дневного хая (убирает быстрые вики)
  Минимальный объём: $5M/сутки
"""

import argparse
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from binance_client import BinanceClient
from config import EXCLUDED_BASE, STABLECOIN_KEYWORDS
from telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("daily_scan")

# ── Настройки ──────────────────────────────────────────────────────
MIN_VOLUME_24H    = 10_000_000  # минимум $10M оборота за сутки
DAILY_RVOL_MIN    = 1.2         # объём сегодня в 1.2x+ раза выше нормы (главный сигнал)
MIN_CHANGE_PCT    = 5.0         # текущий рост ≥ +5% от открытия дня
MAX_REVERSAL_PCT  = 65.0        # цена не ниже 65% от дневного хая
HISTORY_DAYS      = 17          # нужно 17 чтобы после пропуска 2 дней осталось 15 для базелайна
TOP_N             = 6           # сколько монет показывать


def is_valid(ticker: Dict) -> bool:
    symbol = ticker.get("symbol", "")
    if not symbol.endswith("USDT"):
        return False
    base = symbol[:-4]
    if base in EXCLUDED_BASE:
        return False
    if any(kw in base for kw in STABLECOIN_KEYWORDS):
        return False
    if base.endswith(("UP", "DOWN", "BULL", "BEAR")):
        return False
    if float(ticker.get("quoteVolume", 0)) < MIN_VOLUME_24H:
        return False
    return True


def calc_metrics(client: BinanceClient, symbol: str, ticker: Dict) -> Optional[Dict]:
    klines = client.get_klines(symbol, interval="1d", limit=HISTORY_DAYS)
    if not klines or len(klines) < 4:
        return None

    today        = klines[-1]   # текущий день (неполный)
    # Пропускаем сегодня И вчера из базелайна:
    # если вчера был большой день (pump), он не должен раздувать среднее.
    # Rolling 24h из тикера включает вчера → сравниваем с нормой до вчера.
    baseline     = klines[:-2]  # дни от -17 до -2 (не включая вчера и сегодня)
    history_vols = [float(k[7]) for k in baseline]
    avg_vol      = sum(history_vols) / len(history_vols) if history_vols else 0

    # Rolling 24h из тикера — всегда полные 24ч, не зависит от времени суток
    today_vol  = float(ticker.get("quoteVolume", 0))
    daily_rvol = today_vol / avg_vol if avg_vol > 0 else 0

    # Берём open/high из дневной свечи (от полуночи UTC) — точнее чем тикер
    # Тикер считает скользящие 24ч и может показывать -1% на монете которая
    # выросла сегодня с 4.7 до 5.5 (если 24ч назад была уже 5.4)
    price      = float(ticker.get("lastPrice", today[4]))
    open_price = float(today[1])   # открытие дневной свечи (полночь UTC)
    high_price = float(today[2])   # хай дневной свечи

    # change_pct считаем от открытия дневной свечи, не от тикера
    change_pct = ((price / open_price) - 1) * 100 if open_price > 0 else 0

    # Фильтр качества: цена не ниже 65% от дневного хая (убирает быстрые вики)
    reversal_pct = (price / high_price * 100) if high_price > 0 else 100
    if reversal_pct < MAX_REVERSAL_PCT:
        return None

    # Два критерия — достаточно одного:
    # 1. Объём аномальный (RVOL) — неважно куда цена, это главный сигнал
    # 2. Цена стабильно растёт от открытия дня
    passes_rvol   = daily_rvol >= DAILY_RVOL_MIN
    passes_change = change_pct >= MIN_CHANGE_PCT

    if not passes_rvol and not passes_change:
        return None

    # Скор: только по RVOL — монета с большим объёмом всегда выше
    score = daily_rvol

    return {
        "symbol":        symbol,
        "daily_rvol":    daily_rvol,
        "vol_today":     today_vol,
        "vol_avg7d":     avg_vol,
        "price":         price,
        "open_price":    open_price,
        "high_price":    high_price,
        "change_pct":    change_pct,
        "reversal_pct":  reversal_pct,
        "score":         score,
        "passes_rvol":   passes_rvol,
        "passes_change": passes_change,
    }


def run_scan(client: BinanceClient, progress_callback=None) -> List[Dict]:
    logger.info("Получаем список фьючерсных пар...")
    tickers = client.get_all_tickers()
    valid   = [t for t in tickers if is_valid(t)]
    total   = len(valid)
    logger.info(f"Сканируем {total} пар...")

    results = []
    for i, ticker in enumerate(valid):
        symbol  = ticker["symbol"]
        metrics = calc_metrics(client, symbol, ticker)
        if metrics:
            results.append(metrics)
        time.sleep(0.05)

        # Обновляем прогресс каждые 20 монет
        if progress_callback and (i + 1) % 20 == 0:
            progress_callback(i + 1, total)

        if (i + 1) % 50 == 0:
            logger.info(f"  {i + 1}/{total} обработано, кандидатов: {len(results)}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:TOP_N]


def fmt_vol(v: float) -> str:
    if v >= 1_000_000_000: return f"${v/1_000_000_000:.1f}B"
    if v >= 1_000_000:     return f"${v/1_000_000:.1f}M"
    if v >= 1_000:         return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def build_message(top: List[Dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%d %b %H:%M UTC")

    if not top:
        return (
            f"📊 <b>Дневной скан — {now}</b>\n\n"
            f"Inplay монет не найдено."
        )

    lines = [f"📊 <b>Дневной скан — {now}</b>\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for i, coin in enumerate(top):
        base   = coin["symbol"][:-4]
        rvol   = coin["daily_rvol"]
        vol    = fmt_vol(coin["vol_today"])
        avg    = fmt_vol(coin["vol_avg7d"])
        chg    = coin["change_pct"]
        price  = coin["price"]
        medal  = medals[i] if i < len(medals) else f"{i+1}."

        # Теги почему попал
        tags = []
        if coin["passes_rvol"]:   tags.append(f"Vol {rvol:.1f}x")
        if coin["passes_change"]: tags.append(f"+{chg:.1f}% от открытия")
        tag_str = "  ·  ".join(tags)

        chg_emoji = "📈" if chg >= 0 else "📉"

        if price >= 1:       price_str = f"${price:.4f}"
        elif price >= 0.001: price_str = f"${price:.6f}"
        else:                price_str = f"${price:.8f}"

        tv = f"https://www.tradingview.com/chart/?symbol=BINANCE:{base}USDTPERP&interval=5"

        lines.append(
            f"{medal} <b>{base}/USDT</b>  —  {tag_str}\n"
            f"   {chg_emoji} {chg:+.1f}%  ·  Vol: {rvol:.1f}x нормы  ·  {price_str}\n"
            f"   Объём: {vol}  (норма: {avg})\n"
            f"   <a href=\"{tv}\">График →</a>"
        )

    return "\n\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="Только консоль, без Telegram")
    args = parser.parse_args()

    client = BinanceClient()
    top    = run_scan(client)

    message = build_message(top)

    # Всегда выводим в консоль
    clean = re.sub(r"<[^>]+>", "", message)
    print("\n" + clean)

    # По умолчанию отправляем в Telegram (если не передан --print)
    if not args.print:
        notifier = TelegramNotifier()
        notifier._send(message)
        logger.info("Отправлено в Telegram.")


if __name__ == "__main__":
    main()
