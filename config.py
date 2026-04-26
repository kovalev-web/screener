import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Binance ───────────────────────────────────────────────
# USDT-M Futures (Perpetual) — fapi.binance.com
BINANCE_BASE_URL = "https://fapi.binance.com"

# ── Интервалы сканирования ────────────────────────────────
SCAN_INTERVAL_SECONDS = 60   # Сканировать каждые 60 секунд

# ── Таймфрейм анализа (скальпинг 1m) ────────────────────
KLINE_INTERVAL    = "1m"   # 1-минутные свечи — ловим спайк сразу
KLINE_LIMIT       = 100    # 100 свечей = 1 час 40 мин истории
KLINE_INTERVAL_SEC = 60    # секунд в одной свече

# Базелайн: первые N свечей как "норма" (до возможного спайка)
BASELINE_CANDLES  = 70     # 70 свечей × 1m = 70 минут "тихой" нормы

# ── RVOL (Relative Volume) ────────────────────────────────
MIN_RVOL          = 10.0   # Минимальный RVOL для попадания в алерт (10x)
SUSTAINED_CANDLES = 5      # Минимум 5 завершённых 1m свечей с RVOL ≥ 10x
                           # 5 × 1m = 5 минут непрерывного спайка

# ── Фильтр монет (двухуровневый) ─────────────────────────
# Уровень 1: всегда мониторим — крупные ликвидные монеты
MIN_VOLUME_ALWAYS   = 20_000_000   # ≥ $20M/сутки → всегда в списке

# Уровень 2: добавляем если монета уже движется
# (небольшие монеты, но с аномальным ростом цены сегодня)
MIN_VOLUME_MOVING   = 1_000_000    # ≥ $1M/сутки
MIN_CHANGE_MOVING   = 5.0          # И цена выросла ≥ 5% за 24ч
MIN_PRICE_USDT            = 0.000001

# ── Алерты ────────────────────────────────────────────────
MIN_SCORE_TO_ALERT     = 50   # Порог алерта
ALERT_COOLDOWN_MINUTES = 360  # Не повторять алерт по одной монете 6 часов

# ── RSI ───────────────────────────────────────────────────
RSI_PERIOD = 14

# ── Исключения ────────────────────────────────────────────
EXCLUDED_BASE = {"BTC", "ETH", "BNB"}

STABLECOIN_KEYWORDS = {
    "USDT", "USDC", "BUSD", "TUSD", "DAI",
    "FDUSD", "USDP", "USDD", "FRAX", "LUSD",
    "EUR", "GBP", "AUD", "TRY", "BRL",
}
