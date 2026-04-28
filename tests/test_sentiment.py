"""
tests/test_sentiment.py — Unit tests for the sentiment engine.
Run with: pytest tests/ -v
"""

import pytest


def test_score_text_positive():
    from sentinel.sentiment import score_text
    result = score_text("Apple beats earnings expectations with record iPhone sales")
    assert result["label"]           == "positive"
    assert result["sentiment_value"]  > 0
    assert 0 <= result["confidence"] <= 1


def test_score_text_negative():
    from sentinel.sentiment import score_text
    result = score_text("Tesla warns of slowing demand amid increasing competition and missed guidance")
    assert result["label"]           == "negative"
    assert result["sentiment_value"]  < 0


def test_score_batch_returns_same_length():
    from sentinel.sentiment import score_batch
    texts  = ["Market rallies on strong jobs data", "Fed raises rates unexpectedly", "Stock unchanged"]
    scores = score_batch(texts)
    assert len(scores) == len(texts)
    for s in scores:
        assert "label"           in s
        assert "sentiment_value" in s
        assert "confidence"      in s


def test_attach_scores_mutates_in_place():
    from sentinel.sentiment import attach_scores
    items = [
        {"text": "NVDA surges on record data center revenue", "ticker": "NVDA"},
        {"text": "AAPL faces regulatory headwinds in Europe",  "ticker": "AAPL"},
    ]
    result = attach_scores(items)
    assert result is items  # same list
    for item in items:
        assert "sentiment_label"      in item
        assert "sentiment_value"      in item
        assert "sentiment_confidence" in item


def test_score_empty_batch():
    from sentinel.sentiment import score_batch
    assert score_batch([]) == []
