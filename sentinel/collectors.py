"""
collectors.py — All data source adapters.
Each function returns a list of normalized dicts ready for FinBERT scoring.

Data sources (all free):
  - Finnhub       : Company & market news (60 req/min free)
  - Google News   : RSS feed, no key needed
  - Reddit PRAW   : r/wallstreetbets, r/stocks (100 req/min free)
  - StockTwits    : Bull/bear ratio (200 req/hr, no key)
  - yfinance      : Price, volume, returns (unofficial Yahoo, free)
"""

import os
import time
import hashlib
import requests
import feedparser
import yfinance as yf
import finnhub
import praw
from datetime import datetime, timedelta

from .config import (
    FINNHUB_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT, REDDIT_SUBREDDITS, REDDIT_POST_LIMIT,
    REDDIT_LOOKBACK_HOURS, TICKER_NAMES, VOLUME_SPIKE_THRESHOLD,
)

# ─── Finnhub client (singleton) ──────────────────────────────────────────────
_finnhub_client = None

def _get_finnhub():
    global _finnhub_client
    if _finnhub_client is None and FINNHUB_API_KEY:
        _finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _finnhub_client


# ─── Reddit client (singleton) ───────────────────────────────────────────────
_reddit_client = None

def _get_reddit():
    global _reddit_client
    if _reddit_client is None and REDDIT_CLIENT_ID:
        _reddit_client = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
    return _reddit_client


# ─── Finnhub ─────────────────────────────────────────────────────────────────

def get_company_news(ticker: str) -> list[dict]:
    """Fetch last 24h of company-specific news from Finnhub."""
    client = _get_finnhub()
    if not client:
        return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        news = client.company_news(ticker, _from=yesterday, to=today)
        return [
            {
                "source":       "finnhub",
                "ticker":       ticker,
                "headline":     item["headline"],
                "text":         item["headline"] + ". " + item.get("summary", ""),
                "url":          item.get("url", ""),
                "published_at": item.get("datetime", int(time.time())),
            }
            for item in news[:20]
        ]
    except Exception as e:
        print(f"[Finnhub] company_news error for {ticker}: {e}")
        return []


def get_market_news() -> list[dict]:
    """Fetch general market news from Finnhub (tagged as MARKET ticker)."""
    client = _get_finnhub()
    if not client:
        return []
    try:
        news = client.general_news("general", min_id=0)
        return [
            {
                "source":       "finnhub_market",
                "ticker":       "MARKET",
                "headline":     item["headline"],
                "text":         item["headline"] + ". " + item.get("summary", ""),
                "url":          item.get("url", ""),
                "published_at": item.get("datetime", int(time.time())),
            }
            for item in news[:10]
        ]
    except Exception as e:
        print(f"[Finnhub] market_news error: {e}")
        return []


# ─── Google News RSS ──────────────────────────────────────────────────────────

def get_google_news(ticker: str) -> list[dict]:
    """
    Fetch news from Google News RSS — completely free, no API key.
    Queries using the ticker symbol (e.g. $NVDA stock).
    """
    company = TICKER_NAMES.get(ticker, ticker)
    query   = f"${ticker} stock"
    url     = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en"
    cutoff  = datetime.now() - timedelta(hours=24)

    try:
        feed    = feedparser.parse(url)
        results = []
        seen    = set()

        for entry in feed.entries[:15]:
            if entry.link in seen:
                continue
            seen.add(entry.link)

            try:
                pub_date = datetime(*entry.published_parsed[:6])
            except Exception:
                pub_date = datetime.now()

            if pub_date < cutoff:
                continue

            results.append({
                "source":       "google_news",
                "ticker":       ticker,
                "headline":     entry.title,
                "text":         entry.title,
                "url":          entry.link,
                "published_at": int(pub_date.timestamp()),
            })

        return results
    except Exception as e:
        print(f"[GoogleNews] error for {ticker}: {e}")
        return []


# ─── Reddit PRAW ─────────────────────────────────────────────────────────────

def get_reddit_mentions(ticker: str) -> list[dict]:
    """Search recent Reddit posts mentioning a ticker across financial subreddits."""
    reddit = _get_reddit()
    if not reddit:
        return []

    cutoff  = datetime.utcnow() - timedelta(hours=REDDIT_LOOKBACK_HOURS)
    results = []

    for sub_name in REDDIT_SUBREDDITS[:2]:   # cap at 2 subs to stay in free tier
        try:
            subreddit = reddit.subreddit(sub_name)
            for post in subreddit.search(
                f"${ticker} OR {ticker}",
                sort="new", time_filter="day",
                limit=REDDIT_POST_LIMIT,
            ):
                if datetime.utcfromtimestamp(post.created_utc) < cutoff:
                    continue
                results.append({
                    "source":       f"reddit_{sub_name}",
                    "ticker":       ticker,
                    "headline":     post.title,
                    "text":         post.title + " " + (post.selftext[:200] if post.selftext else ""),
                    "url":          f"https://reddit.com{post.permalink}",
                    "published_at": int(post.created_utc),
                    "upvotes":      post.score,
                    "comments":     post.num_comments,
                })
        except Exception as e:
            print(f"[Reddit] error in r/{sub_name} for {ticker}: {e}")

    return results


# ─── StockTwits ───────────────────────────────────────────────────────────────

def get_stocktwits_sentiment(ticker: str) -> dict:
    """
    Pull bull/bear ratio from StockTwits public stream.
    No API key required.
    """
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        msgs = data.get("messages", [])

        bull  = sum(1 for m in msgs if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish")
        bear  = sum(1 for m in msgs if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish")
        total = bull + bear

        return {
            "ticker":           ticker,
            "bull_count":       bull,
            "bear_count":       bear,
            "bull_ratio":       bull / total if total > 0 else 0.5,
            "total_messages":   len(msgs),
            "stocktwits_score": (bull - bear) / total if total > 0 else 0.0,
        }
    except Exception as e:
        print(f"[StockTwits] error for {ticker}: {e}")
        return {"ticker": ticker, "bull_ratio": 0.5, "stocktwits_score": 0.0}


# ─── yfinance price data ─────────────────────────────────────────────────────

def get_price_data(ticker: str) -> dict:
    """
    Return current price, 1-day change %, 5-day return, and volume spike indicator.
    Uses yfinance (unofficial Yahoo Finance API — free, no key needed).
    """
    try:
        hist = yf.Ticker(ticker).history(period="35d")
        if hist.empty or len(hist) < 2:
            return {"ticker": ticker}

        price        = hist["Close"].iloc[-1]
        prev_close   = hist["Close"].iloc[-2]
        change_1d    = (price / prev_close - 1) * 100
        ret_5d       = (price / hist["Close"].iloc[-6] - 1) * 100 if len(hist) >= 6 else 0.0
        avg_vol_30d  = hist["Volume"].iloc[:-1].mean()
        today_vol    = hist["Volume"].iloc[-1]
        vol_ratio    = today_vol / avg_vol_30d if avg_vol_30d > 0 else 1.0

        return {
            "ticker":                  ticker,
            "price":                   round(float(price), 2),
            "price_change_1d_pct":     round(float(change_1d), 2),
            "ret_5d_pct":              round(float(ret_5d), 2),
            "volume_ratio_vs_30d_avg": round(float(vol_ratio), 2),
            "is_volume_spike":         vol_ratio >= VOLUME_SPIKE_THRESHOLD,
        }
    except Exception as e:
        print(f"[yfinance] error for {ticker}: {e}")
        return {"ticker": ticker}


# ─── Fear & Greed (CNN) ───────────────────────────────────────────────────────

def get_fear_and_greed() -> dict:
    """
    Fetch the CNN Fear & Greed Index via their unofficial JSON endpoint.
    Returns a score 0-100 (0=extreme fear, 100=extreme greed).
    """
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp    = requests.get(url, headers=headers, timeout=10)
        data    = resp.json()
        score   = data["fear_and_greed"]["score"]
        rating  = data["fear_and_greed"]["rating"]
        return {"score": round(score, 1), "rating": rating}
    except Exception as e:
        print(f"[FearGreed] error: {e}")
        return {"score": 50.0, "rating": "Neutral"}
