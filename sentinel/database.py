"""
database.py — SQLite schema, initialization, and all read/write helpers.
Uses a single sentinel.db file — no server required.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from statistics import mean, stdev
from typing import Optional
from .config import DB_PATH, BASELINE_WINDOW_DAYS, DEFAULT_BASELINE_STD


# ─── Schema initialization ────────────────────────────────────────────────────

def init_database(db_path: str = DB_PATH) -> None:
    """Create all tables on first run. Safe to call on every startup (IF NOT EXISTS)."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # News and social media items with FinBERT scores
    c.execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            source          TEXT    NOT NULL,
            headline        TEXT    NOT NULL,
            text            TEXT,
            url             TEXT    UNIQUE,
            sentiment_label TEXT,
            sentiment_value REAL,
            sentiment_confidence REAL,
            published_at    INTEGER,
            fetched_at      INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_news_ticker_time ON news_items(ticker, published_at)")

    # LLM analysis results
    c.execute("""
        CREATE TABLE IF NOT EXISTS llm_analyses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            action          TEXT    NOT NULL,
            confidence      INTEGER,
            time_horizon    TEXT,
            risk_level      TEXT,
            reasoning       TEXT,
            entry_note      TEXT,
            stop_loss_note  TEXT,
            model_used      TEXT,
            context_snapshot TEXT,
            created_at      INTEGER DEFAULT (strftime('%s','now'))
        )
    """)

    # Paper and real trade log
    c.execute("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL,
            action      TEXT    NOT NULL,
            price       REAL,
            quantity    REAL,
            analysis_id INTEGER REFERENCES llm_analyses(id),
            paper_trade INTEGER DEFAULT 1,
            outcome_pct REAL,
            exit_price  REAL,
            entry_at    INTEGER DEFAULT (strftime('%s','now')),
            exit_at     INTEGER,
            notes       TEXT
        )
    """)

    # Daily sentiment snapshots (for baseline drift tracking)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_sentiment (
            ticker      TEXT,
            date        TEXT,
            avg_sentiment REAL,
            item_count  INTEGER,
            PRIMARY KEY (ticker, date)
        )
    """)

    conn.commit()
    conn.close()


# ─── News item persistence ────────────────────────────────────────────────────

def save_news_item(item: dict, db_path: str = DB_PATH) -> bool:
    """
    Insert one news/social item.  IGNORE on duplicate URL.
    Returns True if a new row was inserted, False if already existed.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO news_items
                (ticker, source, headline, text, url,
                 sentiment_label, sentiment_value, sentiment_confidence, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("ticker"),
            item.get("source"),
            item.get("headline", ""),
            item.get("text", ""),
            item.get("url", ""),
            item.get("sentiment_label"),
            item.get("sentiment_value"),
            item.get("sentiment_confidence"),
            item.get("published_at"),
        ))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[DB] save_news_item error: {e}")
        return False
    finally:
        conn.close()


def save_news_batch(items: list[dict], db_path: str = DB_PATH) -> int:
    """Bulk insert news items. Returns count of newly inserted rows."""
    inserted = 0
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        for item in items:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO news_items
                    (ticker, source, headline, text, url,
                     sentiment_label, sentiment_value, sentiment_confidence, published_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("ticker"), item.get("source"),
                item.get("headline", ""), item.get("text", ""),
                item.get("url", ""),
                item.get("sentiment_label"), item.get("sentiment_value"),
                item.get("sentiment_confidence"), item.get("published_at"),
            ))
            inserted += cursor.rowcount
        conn.commit()
    finally:
        conn.close()
    return inserted


# ─── Sentiment aggregation ────────────────────────────────────────────────────

def get_7day_baseline(ticker: str, db_path: str = DB_PATH) -> float:
    cutoff = int((datetime.now() - timedelta(days=BASELINE_WINDOW_DAYS)).timestamp())
    conn = sqlite3.connect(db_path)
    row = conn.execute("""
        SELECT AVG(sentiment_value) FROM news_items
        WHERE ticker = ? AND published_at >= ? AND sentiment_value IS NOT NULL
    """, (ticker, cutoff)).fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else 0.0


def get_7day_std(ticker: str, db_path: str = DB_PATH) -> float:
    cutoff = int((datetime.now() - timedelta(days=BASELINE_WINDOW_DAYS)).timestamp())
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT sentiment_value FROM news_items
        WHERE ticker = ? AND published_at >= ? AND sentiment_value IS NOT NULL
    """, (ticker, cutoff)).fetchall()
    conn.close()
    values = [r[0] for r in rows]
    return stdev(values) if len(values) >= 2 else DEFAULT_BASELINE_STD


def compute_rolling_sentiment(ticker: str, hours: int = 4, db_path: str = DB_PATH) -> dict:
    """
    Compute rolling sentiment statistics and z-score anomaly detection for a ticker.
    This is the primary trigger function — called every 10 minutes per ticker.
    """
    cutoff_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT sentiment_value, published_at, source, headline
        FROM news_items
        WHERE ticker = ? AND published_at >= ? AND sentiment_value IS NOT NULL
        ORDER BY published_at DESC
    """, (ticker, cutoff_ts)).fetchall()
    conn.close()

    if not rows:
        return {"ticker": ticker, "has_data": False}

    sentiments = [r[0] for r in rows]
    avg_sentiment = mean(sentiments)

    baseline_avg = get_7day_baseline(ticker, db_path)
    baseline_std = get_7day_std(ticker, db_path)

    recent_cutoff = int((datetime.now() - timedelta(hours=1)).timestamp())
    recent  = [r[0] for r in rows if r[1] >= recent_cutoff]
    older   = [r[0] for r in rows if r[1] <  recent_cutoff]
    recent_avg = mean(recent) if recent else avg_sentiment
    older_avg  = mean(older)  if older  else avg_sentiment
    velocity   = recent_avg - older_avg

    z_score = (avg_sentiment - baseline_avg) / baseline_std if baseline_std > 0 else 0.0

    return {
        "ticker":           ticker,
        "has_data":         True,
        "avg_sentiment":    round(avg_sentiment, 4),
        "item_count":       len(rows),
        "recent_avg_1h":    round(recent_avg, 4),
        "older_avg_3h":     round(older_avg, 4),
        "velocity":         round(velocity, 4),
        "z_score":          round(z_score, 2),
        "is_anomaly":       abs(z_score) >= 2.0,
        "anomaly_direction": "negative" if z_score < -2.0 else "positive" if z_score > 2.0 else "none",
        "top_headlines":    [r[3] for r in rows[:5]],
    }


# ─── LLM analysis persistence ─────────────────────────────────────────────────

def save_analysis(ticker: str, result: dict, context: str, db_path: str = DB_PATH) -> int:
    """Save LLM analysis result. Returns the new row id."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.execute("""
        INSERT INTO llm_analyses
            (ticker, action, confidence, time_horizon, risk_level,
             reasoning, entry_note, stop_loss_note, model_used, context_snapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker,
        result.get("action", "HOLD"),
        result.get("confidence", 0),
        result.get("time_horizon", ""),
        result.get("risk_level", "HIGH"),
        result.get("reasoning", ""),
        result.get("entry_note", ""),
        result.get("stop_loss_note", ""),
        result.get("model_used", ""),
        context,
    ))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


# ─── Trade log ────────────────────────────────────────────────────────────────

def save_trade(ticker: str, action: str, price: float, quantity: int,
               analysis_id: Optional[int] = None, paper: bool = True,
               db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.execute("""
        INSERT INTO trade_log (ticker, action, price, quantity, analysis_id, paper_trade)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (ticker, action, price, quantity, analysis_id, 1 if paper else 0))
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


# ─── Dashboard queries ────────────────────────────────────────────────────────

def get_recent_analyses(hours: int = 48, db_path: str = DB_PATH) -> list[dict]:
    cutoff = int((datetime.now() - timedelta(hours=hours)).timestamp())
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT ticker, action, confidence, time_horizon, risk_level, reasoning,
               datetime(created_at,'unixepoch','localtime') as ts
        FROM llm_analyses
        WHERE created_at >= ?
        ORDER BY created_at DESC
    """, (cutoff,)).fetchall()
    conn.close()
    keys = ["ticker","action","confidence","time_horizon","risk_level","reasoning","timestamp"]
    return [dict(zip(keys, r)) for r in rows]


def get_sentiment_history(ticker: str, hours: int = 72, db_path: str = DB_PATH) -> list[dict]:
    cutoff = int((datetime.now() - timedelta(hours=hours)).timestamp())
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT datetime(published_at,'unixepoch','localtime') as time,
               sentiment_value, source, headline
        FROM news_items
        WHERE ticker = ? AND published_at >= ?
        ORDER BY published_at
    """, (ticker, cutoff)).fetchall()
    conn.close()
    return [{"time": r[0], "sentiment_value": r[1], "source": r[2], "headline": r[3]} for r in rows]
