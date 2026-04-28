"""
config.py — Central configuration for The Sentinel
All user-tunable settings in one place.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── Watchlist ────────────────────────────────────────────────────────────────
WATCHLIST = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META",
    "AMZN", "TSLA", "JPM", "NFLX", "AMD"
]

# Company names mapped to tickers (used for Google News search)
TICKER_NAMES = {
    "NVDA":  "NVIDIA",
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "GOOGL": "Google Alphabet",
    "META":  "Meta Platforms",
    "AMZN":  "Amazon",
    "TSLA":  "Tesla",
    "JPM":   "JPMorgan Chase",
    "NFLX":  "Netflix",
    "AMD":   "Advanced Micro Devices",
}

# ─── API Keys (loaded from .env) ─────────────────────────────────────────────
FINNHUB_API_KEY     = os.environ.get("FINNHUB_API_KEY", "")
GEMINI_API_KEY      = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY    = os.environ.get("DEEPSEEK_API_KEY", "")
REDDIT_CLIENT_ID    = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET= os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT   = os.environ.get("REDDIT_USER_AGENT", "SentinelBot/1.0")
TELEGRAM_BOT_TOKEN  = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID    = os.environ.get("TELEGRAM_CHAT_ID", "")
ALPACA_API_KEY      = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY   = os.environ.get("ALPACA_SECRET_KEY", "")

# ─── Paths ────────────────────────────────────────────────────────────────────
DB_PATH             = os.environ.get("DB_PATH", "sentinel.db")
LLM_CALL_COUNT_FILE = "llm_call_count.json"

# ─── Sentiment thresholds ─────────────────────────────────────────────────────
ANOMALY_Z_SCORE_THRESHOLD   = 2.0   # std devs from baseline to trigger LLM
PRICE_SHOCK_THRESHOLD_PCT   = 4.0   # % intraday move to trigger LLM
VOLUME_SPIKE_THRESHOLD      = 2.5   # x average volume to flag spike
LLM_TRIGGER_VOLUME_RATIO    = 3.0   # x volume to trigger LLM independently

# ─── Sentiment rolling windows ────────────────────────────────────────────────
ROLLING_WINDOW_HOURS        = 4     # primary sentiment window
BASELINE_WINDOW_DAYS        = 7     # days back for baseline std dev
DEFAULT_BASELINE_STD        = 0.15  # default std when insufficient history

# ─── LLM cost guardrails ─────────────────────────────────────────────────────
MONTHLY_LLM_CALL_BUDGET     = 600   # max calls per calendar month
MIN_ALERT_CONFIDENCE        = 55    # minimum confidence % to send Telegram alert
SKIP_HOLD_BELOW_CONFIDENCE  = 50    # skip HOLD signals below this confidence

# ─── Alert filtering ─────────────────────────────────────────────────────────
ALERT_ACTIONS               = ["BUY", "SELL", "WATCH"]  # actions that generate alerts

# ─── Scheduler settings ──────────────────────────────────────────────────────
NEWS_FETCH_INTERVAL_MIN     = 5     # minutes between news fetches
SOCIAL_FETCH_INTERVAL_MIN   = 15    # minutes between Reddit/StockTwits fetches
ANOMALY_CHECK_INTERVAL_MIN  = 10    # minutes between anomaly scans
DAILY_SUMMARY_HOUR          = 16    # hour (ET) for daily summary (4 PM = market close)
DAILY_SUMMARY_MINUTE        = 5

# ─── Market hours (ET) ───────────────────────────────────────────────────────
MARKET_OPEN_HOUR    = 9
MARKET_OPEN_MIN     = 30
MARKET_CLOSE_HOUR   = 16
MARKET_CLOSE_MIN    = 0
PRE_MARKET_HOUR     = 4   # pre-market starts at 4 AM ET

# ─── Paper trading ───────────────────────────────────────────────────────────
PAPER_TRADING_ENABLED       = True
PAPER_PORTFOLIO_VALUE       = 10_000  # simulated portfolio size $
PAPER_MIN_POSITION_PCT      = 0.01    # 1% minimum position
PAPER_MAX_POSITION_PCT      = 0.03    # 3% maximum position

# ─── Reddit subreddits to monitor ────────────────────────────────────────────
REDDIT_SUBREDDITS   = ["wallstreetbets", "stocks", "investing", "StockMarket"]
REDDIT_POST_LIMIT   = 25    # posts per search per subreddit
REDDIT_LOOKBACK_HOURS = 6   # only fetch posts from last N hours

# ─── FinBERT settings ─────────────────────────────────────────────────────────
FINBERT_MODEL       = "ProsusAI/finbert"
FINBERT_BATCH_SIZE  = 16
FINBERT_MAX_CHARS   = 1000  # truncate input text to this length

# ─── LLM models ──────────────────────────────────────────────────────────────
PRIMARY_LLM_MODEL   = "gemini-2.5-flash"   # cheapest viable option
FALLBACK_LLM_MODEL  = "deepseek-chat"            # DeepSeek V3.2 fallback
LLM_MAX_OUTPUT_TOKENS = 300
LLM_TEMPERATURE     = 0.1   # low = more deterministic output
