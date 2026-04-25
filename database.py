"""
SQLite хранилище для inplay-скринера.

Таблицы:
  ticker_snapshots   — снапшоты тикеров каждую минуту
  volume_baselines   — базелайны объёма (обновляются раз в час)
  alerts_sent        — история отправленных алертов (cooldown)
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = "inplay_screener.db"


# ── Подключение ────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


# ── Инициализация ──────────────────────────────────────────────────

def init_db():
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS ticker_snapshots (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ts               DATETIME DEFAULT (datetime('now')),
                symbol           TEXT NOT NULL,
                quote_volume_24h REAL,
                price            REAL,
                price_change_pct REAL,
                high_24h         REAL,
                low_24h          REAL
            );

            CREATE INDEX IF NOT EXISTS idx_snap_sym_ts
                ON ticker_snapshots(symbol, ts);

            CREATE TABLE IF NOT EXISTS volume_baselines (
                symbol           TEXT PRIMARY KEY,
                avg_daily_vol    REAL,
                avg_hourly_vol   REAL,
                updated_at       DATETIME DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alerts_sent (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                score       REAL,
                volume_spike REAL,
                rsi         REAL,
                details_json TEXT,
                sent_at     DATETIME DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_sym_ts
                ON alerts_sent(symbol, sent_at);
        """)
    logger.info("БД инициализирована: %s", DB_PATH)


# ── Снапшоты тикеров ───────────────────────────────────────────────

def save_snapshots(rows: List[Dict]):
    if not rows:
        return
    with _conn() as c:
        c.executemany(
            """
            INSERT INTO ticker_snapshots
                (symbol, quote_volume_24h, price, price_change_pct, high_24h, low_24h)
            VALUES
                (:symbol, :quote_volume_24h, :price, :price_change_pct, :high_24h, :low_24h)
            """,
            rows,
        )


def get_snapshot_minutes_ago(symbol: str, minutes: int) -> Optional[Dict]:
    """Ближайший снапшот ~N минут назад."""
    with _conn() as c:
        row = c.execute(
            """
            SELECT * FROM ticker_snapshots
            WHERE symbol = ?
              AND ts <= datetime('now', ? || ' minutes')
            ORDER BY ts DESC
            LIMIT 1
            """,
            (symbol, f"-{minutes}"),
        ).fetchone()
    return dict(row) if row else None


def get_recent_snapshots(symbol: str, hours: int = 4) -> List[Dict]:
    """Все снапшоты за последние N часов."""
    with _conn() as c:
        rows = c.execute(
            """
            SELECT * FROM ticker_snapshots
            WHERE symbol = ?
              AND ts >= datetime('now', ? || ' hours')
            ORDER BY ts ASC
            """,
            (symbol, f"-{hours}"),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Базелайны объёма ───────────────────────────────────────────────

def upsert_baseline(symbol: str, avg_daily: float, avg_hourly: float):
    with _conn() as c:
        c.execute(
            """
            INSERT OR REPLACE INTO volume_baselines
                (symbol, avg_daily_vol, avg_hourly_vol, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (symbol, avg_daily, avg_hourly),
        )


def get_baseline(symbol: str) -> Optional[Dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM volume_baselines WHERE symbol = ?", (symbol,)
        ).fetchone()
    return dict(row) if row else None


def count_baselines() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM volume_baselines").fetchone()[0]


# ── История алертов ────────────────────────────────────────────────

def was_recently_alerted(symbol: str, cooldown_minutes: int) -> bool:
    with _conn() as c:
        row = c.execute(
            """
            SELECT id FROM alerts_sent
            WHERE symbol = ?
              AND sent_at >= datetime('now', ? || ' minutes')
            LIMIT 1
            """,
            (symbol, f"-{cooldown_minutes}"),
        ).fetchone()
    return row is not None


def save_alert(symbol: str, score: float, volume_spike: float, rsi: Optional[float], details: Dict):
    with _conn() as c:
        c.execute(
            """
            INSERT INTO alerts_sent (symbol, score, volume_spike, rsi, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (symbol, score, volume_spike, rsi, json.dumps(details, default=str)),
        )


def get_recent_alerts(hours: int = 24) -> List[Dict]:
    with _conn() as c:
        rows = c.execute(
            """
            SELECT symbol, score, volume_spike, rsi, sent_at
            FROM alerts_sent
            WHERE sent_at >= datetime('now', ? || ' hours')
            ORDER BY sent_at DESC
            """,
            (f"-{hours}",),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Обслуживание ───────────────────────────────────────────────────

def cleanup_old_data(keep_days: int = 7):
    with _conn() as c:
        c.execute(
            "DELETE FROM ticker_snapshots WHERE ts < datetime('now', ? || ' days')",
            (f"-{keep_days}",),
        )
        c.execute(
            "DELETE FROM alerts_sent WHERE sent_at < datetime('now', '-30 days')"
        )
    logger.info("Очистка БД выполнена (оставляем последние %d дней снапшотов)", keep_days)
