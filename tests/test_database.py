"""
tests/test_database.py — Unit tests for DB layer using a temp DB.
Run with: pytest tests/ -v
"""

import pytest
import tempfile
import os
from datetime import datetime


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite DB for each test."""
    db = str(tmp_path / "test_sentinel.db")
    from sentinel.database import init_database
    init_database(db)
    return db


def test_init_creates_tables(tmp_db):
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "news_items"     in tables
    assert "llm_analyses"   in tables
    assert "trade_log"      in tables
    assert "daily_sentiment" in tables


def test_save_and_retrieve_news_item(tmp_db):
    from sentinel.database import save_news_item, get_sentiment_history
    item = {
        "ticker":              "NVDA",
        "source":              "test",
        "headline":            "NVIDIA beats Q4 earnings",
        "text":                "NVIDIA beats Q4 earnings handily.",
        "url":                 "https://example.com/nvda-q4",
        "sentiment_label":     "positive",
        "sentiment_value":     0.85,
        "sentiment_confidence":0.92,
        "published_at":        int(datetime.now().timestamp()),
    }
    inserted = save_news_item(item, db_path=tmp_db)
    assert inserted is True

    # Duplicate should be ignored
    inserted_again = save_news_item(item, db_path=tmp_db)
    assert inserted_again is False


def test_save_news_batch(tmp_db):
    from sentinel.database import save_news_batch
    items = [
        {"ticker": "AAPL", "source": "test", "headline": f"Headline {i}",
         "url": f"https://ex.com/{i}", "sentiment_value": 0.5,
         "sentiment_label": "positive", "sentiment_confidence": 0.8,
         "published_at": int(datetime.now().timestamp())}
        for i in range(5)
    ]
    count = save_news_batch(items, db_path=tmp_db)
    assert count == 5


def test_compute_rolling_sentiment_no_data(tmp_db):
    from sentinel.database import compute_rolling_sentiment
    result = compute_rolling_sentiment("TSLA", db_path=tmp_db)
    assert result["has_data"] is False


def test_compute_rolling_sentiment_with_data(tmp_db):
    from sentinel.database import save_news_batch, compute_rolling_sentiment
    import time
    now = int(time.time())
    items = [
        {"ticker": "TSLA", "source": "test", "headline": f"h{i}",
         "url": f"https://ex.com/t{i}", "sentiment_value": -0.6,
         "sentiment_label": "negative", "sentiment_confidence": 0.9,
         "published_at": now - i * 300}  # spaced 5 mins apart
        for i in range(10)
    ]
    save_news_batch(items, db_path=tmp_db)
    result = compute_rolling_sentiment("TSLA", db_path=tmp_db)
    assert result["has_data"] is True
    assert result["avg_sentiment"] < 0


def test_save_analysis(tmp_db):
    from sentinel.database import save_analysis, get_recent_analyses
    analysis = {
        "action":         "BUY",
        "confidence":     75,
        "time_horizon":   "3-7 days",
        "risk_level":     "MEDIUM",
        "reasoning":      "Strong sentiment reversal on high volume.",
        "entry_note":     "Wait for morning confirmation.",
        "stop_loss_note": "Close below -5% from entry.",
        "model_used":     "gemini-2.5-flash",
    }
    row_id = save_analysis("NVDA", analysis, "context text", db_path=tmp_db)
    assert row_id > 0

    recent = get_recent_analyses(hours=24, db_path=tmp_db)
    assert len(recent) == 1
    assert recent[0]["action"] == "BUY"
