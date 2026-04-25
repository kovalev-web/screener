"""
Точка входа inplay-скринера.

Запуск:
  python main.py

Режимы:
  python main.py          — нормальный запуск (бесконечный цикл)
  python main.py --test   — один тестовый скан без алертов
  python main.py --ping   — проверить Telegram-соединение
"""

import argparse
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import database as db
from config import (
    SCAN_INTERVAL_SECONDS,
)
from screener import InplayScreener

# ── Логирование ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("screener.log", encoding="utf-8"),
    ],
)
# Убираем лишние логи от requests
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

logger = logging.getLogger("main")


# ── Сигналы завершения ─────────────────────────────────────────────
_shutdown = threading.Event()


def _handle_signal(sig, frame):
    logger.info("Получен сигнал завершения — останавливаемся...")
    _shutdown.set()


signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Основной цикл ──────────────────────────────────────────────────

def run():
    logger.info("=" * 55)
    logger.info("  🚀  Inplay Screener v1.0  — Binance USDT пары")
    logger.info("=" * 55)

    db.init_db()
    screener = InplayScreener()

    # Считаем сколько монет будем мониторить
    logger.info("Получаем список монет с Binance...")
    all_tickers = screener.binance.get_all_tickers()
    coin_count  = sum(1 for t in all_tickers if screener._is_valid_altcoin(t))
    logger.info(f"Монет для мониторинга: {coin_count}")

    # Стартовый тест Telegram
    logger.info("Проверяем Telegram...")
    screener.notifier.test_connection()

    scan_count   = 0
    last_cleanup = time.time()

    # Сообщаем в Telegram о запуске
    screener.notifier.send_startup(coin_count)

    logger.info(f"Сканирую каждые {SCAN_INTERVAL_SECONDS}с. Нажми Ctrl+C для остановки.")

    while not _shutdown.is_set():
        loop_start = time.time()
        scan_count += 1

        try:
            inplay = screener.scan()
            alerted = screener.process_alerts(inplay)

            # Ежедневная очистка БД
            if time.time() - last_cleanup > 86_400:
                db.cleanup_old_data()
                last_cleanup = time.time()

            # Краткая статистика каждые 60 сканов (раз в час)
            if scan_count % 60 == 0:
                logger.info(
                    f"[Итог] Сканов: {scan_count}  "
                    f"Всего алертов: {screener._total_alerted}"
                )

        except Exception as e:
            logger.error(f"Ошибка в цикле сканирования: {e}", exc_info=True)
            screener.notifier.send_error(str(e)[:300])

        # Ждём до следующего скана
        elapsed   = time.time() - loop_start
        sleep_for = max(0, SCAN_INTERVAL_SECONDS - elapsed)
        logger.debug(f"Скан занял {elapsed:.1f}с, спим {sleep_for:.1f}с")
        _shutdown.wait(timeout=sleep_for)

    # Завершение
    logger.info("Скринер остановлен.")
    screener.notifier.send_status("⛔ Inplay скринер остановлен.")


# ── Тестовые режимы ────────────────────────────────────────────────

def run_test():
    """Один скан — показывает топ кандидатов без отправки алертов."""
    print("🧪 ТЕСТОВЫЙ РЕЖИМ — алерты НЕ отправляются\n")
    db.init_db()
    screener = InplayScreener()

    print("Загружаем базелайны (это займёт 1–2 мин)...")
    screener.load_baselines()

    print("\nЗапускаем скан...\n")
    inplay = screener.scan()

    if not inplay:
        print("Inplay монет не найдено (порог не достигнут).")
    else:
        print(f"\n{'─'*55}")
        print(f"  🔥 INPLAY монеты (топ-{len(inplay)}):")
        print(f"{'─'*55}")
        for c in inplay:
            rsi_str = f"{c['rsi']:.1f}" if c.get("rsi") else "—"
            print(
                f"  {c['symbol']:<14} score={c['score']:3d}  "
                f"spike={c['volume_spike']:.1f}x  RSI={rsi_str}  "
                f"cons={c.get('consolidation_pct', 0):.1f}%  "
                f"24h={c['price_change_24h']:+.1f}%"
            )
        print(f"{'─'*55}")


def run_ping():
    """Проверяет Telegram-соединение."""
    from telegram_notifier import TelegramNotifier
    notifier = TelegramNotifier()
    ok = notifier.test_connection()
    if ok:
        print("✅ Telegram работает!")
    else:
        print("❌ Ошибка Telegram — проверь токен и chat_id в .env")


# ── Точка входа ────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inplay Crypto Screener")
    parser.add_argument("--test", action="store_true", help="Один скан без алертов")
    parser.add_argument("--ping", action="store_true", help="Тест Telegram-соединения")
    args = parser.parse_args()

    if args.ping:
        run_ping()
    elif args.test:
        run_test()
    else:
        run()
