"""
scheduler.py — Main orchestrator. Runs all jobs on their schedules.

Jobs:
  job_fetch_and_score   : Every 5 min (news from Finnhub + Google RSS)
  job_social_media      : Every 15 min (Reddit + StockTwits)
  job_anomaly_check     : Every 10 min (detect anomalies → LLM → alert)
  job_daily_summary     : 4:05 PM ET Monday-Friday

All jobs respect market hours to avoid burning API quota overnight.
"""

import logging
from datetime import datetime, timedelta
import pytz

from apscheduler.schedulers.blocking import BlockingScheduler

from .config       import (
    WATCHLIST,
    NEWS_FETCH_INTERVAL_MIN, SOCIAL_FETCH_INTERVAL_MIN,
    ANOMALY_CHECK_INTERVAL_MIN, DAILY_SUMMARY_HOUR, DAILY_SUMMARY_MINUTE,
    PRICE_SHOCK_THRESHOLD_PCT, LLM_TRIGGER_VOLUME_RATIO,
    ANOMALY_Z_SCORE_THRESHOLD, ALERT_ACTIONS, MIN_ALERT_CONFIDENCE,
    PAPER_TRADING_ENABLED,
)
from .database     import init_database, save_news_batch, compute_rolling_sentiment, save_analysis
from .collectors   import (
    get_company_news, get_google_news, get_reddit_mentions,
    get_stocktwits_sentiment, get_price_data, get_fear_and_greed,
)
from .sentiment    import attach_scores
from .llm_analyst  import build_context_packet, analyze_with_llm
from .alerts       import send_signal_alert, send_daily_summary, send_startup_message, send_error_alert
from .paper_trader import submit_paper_trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sentinel")

ET_TZ = pytz.timezone("America/New_York")


# ─── Market hours helpers ─────────────────────────────────────────────────────

def _is_market_hours() -> bool:
    now = datetime.now(ET_TZ)
    if now.weekday() >= 5:
        return False
    open_  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_ = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_ <= now <= close_


def _is_pre_market() -> bool:
    now = datetime.now(ET_TZ)
    if now.weekday() >= 5:
        return False
    pre_start = now.replace(hour=4,  minute=0,  second=0, microsecond=0)
    open_     = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    return pre_start <= now < open_


def _is_active_period() -> bool:
    """True during both pre-market and regular market hours."""
    return _is_market_hours() or _is_pre_market()


# ─── Jobs ─────────────────────────────────────────────────────────────────────

def job_fetch_and_score() -> None:
    """Fetch news from Finnhub + Google RSS, score with FinBERT, store to DB."""
    if not _is_active_period():
        return

    logger.info(f"[fetch] Running for {len(WATCHLIST)} tickers")
    for ticker in WATCHLIST:
        try:
            items = []
            items.extend(get_company_news(ticker))
            items.extend(get_google_news(ticker))

            if items:
                attach_scores(items)
                new_rows = save_news_batch(items)
                if new_rows:
                    logger.info(f"[fetch] {ticker}: +{new_rows} new items")
        except Exception as e:
            logger.error(f"[fetch] {ticker}: {e}")


def job_social_media() -> None:
    """Fetch Reddit posts and StockTwits sentiment, score, store."""
    if not _is_market_hours():
        return

    logger.info("[social] Running Reddit + StockTwits sweep")
    for ticker in WATCHLIST:
        try:
            posts = get_reddit_mentions(ticker)
            if posts:
                attach_scores(posts)
                new_rows = save_news_batch(posts)
                logger.debug(f"[social] {ticker}: +{new_rows} Reddit items")
        except Exception as e:
            logger.error(f"[social] {ticker}: {e}")


def job_anomaly_check() -> None:
    """
    Core detection loop:
    1. Compute rolling sentiment + z-score for every ticker
    2. If anomaly OR price shock → call LLM
    3. If actionable signal → send Telegram alert + optional paper trade
    """
    if not _is_active_period():
        return

    logger.info("[anomaly] Scanning watchlist")
    fear_greed = get_fear_and_greed()

    for ticker in WATCHLIST:
        try:
            sentiment = compute_rolling_sentiment(ticker)
            price     = get_price_data(ticker)
            stocktwits= get_stocktwits_sentiment(ticker)

            if not sentiment.get("has_data"):
                continue

            # Decide whether to call LLM
            price_shock   = abs(price.get("price_change_1d_pct", 0)) >= PRICE_SHOCK_THRESHOLD_PCT
            volume_spike  = price.get("volume_ratio_vs_30d_avg", 1) >= LLM_TRIGGER_VOLUME_RATIO
            sent_anomaly  = sentiment.get("is_anomaly", False)

            if not (sent_anomaly or price_shock or volume_spike):
                continue

            trigger = (
                f"anomaly z={sentiment['z_score']:.1f}" if sent_anomaly else
                f"price shock {price.get('price_change_1d_pct',0):+.1f}%" if price_shock else
                f"volume spike {price.get('volume_ratio_vs_30d_avg',1):.1f}x"
            )
            logger.info(f"[anomaly] {ticker}: {trigger} → calling LLM")

            context    = build_context_packet(ticker, sentiment, price, stocktwits, fear_greed)
            llm_result = analyze_with_llm(context, ticker)
            analysis_id= save_analysis(ticker, llm_result, context)

            logger.info(
                f"[LLM] {ticker}: {llm_result.get('action')} "
                f"@ {llm_result.get('confidence')}% ({llm_result.get('model_used')})"
            )

            # Alert
            sent = send_signal_alert(ticker, llm_result, sentiment, price, fear_greed)
            if sent:
                logger.info(f"[alert] Telegram alert sent for {ticker}")

            # Paper trade (BUY/SELL only, not WATCH/HOLD)
            if (PAPER_TRADING_ENABLED
                    and llm_result.get("action") in ("BUY", "SELL")
                    and llm_result.get("confidence", 0) >= MIN_ALERT_CONFIDENCE):
                trade = submit_paper_trade(
                    ticker=ticker,
                    action=llm_result["action"],
                    confidence=llm_result["confidence"],
                    price=price.get("price", 0),
                    analysis_id=analysis_id,
                )
                logger.info(f"[paper] {ticker}: {trade.get('status')}")

        except Exception as e:
            logger.error(f"[anomaly] {ticker}: {e}")


def job_daily_summary() -> None:
    """Compile and send end-of-day digest at 4:05 PM ET."""
    logger.info("[summary] Generating daily digest")
    summary = {}
    for ticker in WATCHLIST:
        sent  = compute_rolling_sentiment(ticker, hours=8)
        price = get_price_data(ticker)
        summary[ticker] = {**sent, **price}
    send_daily_summary(WATCHLIST, summary)
    logger.info("[summary] Daily digest sent")


# ─── Main entry point ─────────────────────────────────────────────────────────

def run() -> None:
    """Initialize database, start all scheduled jobs, block forever."""
    logger.info("Initializing database...")
    init_database()

    logger.info(f"Monitoring watchlist: {', '.join(WATCHLIST)}")
    send_startup_message(WATCHLIST)

    scheduler = BlockingScheduler(timezone=ET_TZ)

    # News fetch: every 5 min, Mon-Fri, 4 AM – 5 PM ET
    scheduler.add_job(
        job_fetch_and_score, "cron",
        day_of_week="mon-fri", hour="4-17",
        minute=f"*/{NEWS_FETCH_INTERVAL_MIN}",
        id="fetch_news",
        max_instances=1, coalesce=True,
    )

    # Social media: every 15 min, Mon-Fri, 9:30 AM – 4 PM ET
    scheduler.add_job(
        job_social_media, "cron",
        day_of_week="mon-fri", hour="9-16",
        minute=f"*/{SOCIAL_FETCH_INTERVAL_MIN}",
        id="social_media",
        max_instances=1, coalesce=True,
    )

    # Anomaly check: every 10 min, Mon-Fri, 4 AM – 5 PM ET
    scheduler.add_job(
        job_anomaly_check, "cron",
        day_of_week="mon-fri", hour="4-17",
        minute=f"*/{ANOMALY_CHECK_INTERVAL_MIN}",
        id="anomaly_check",
        max_instances=1, coalesce=True,
    )

    # Daily summary: 4:05 PM ET, Mon-Fri
    scheduler.add_job(
        job_daily_summary, "cron",
        day_of_week="mon-fri",
        hour=DAILY_SUMMARY_HOUR,
        minute=DAILY_SUMMARY_MINUTE,
        id="daily_summary",
    )

    logger.info("Sentinel is running. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Sentinel stopped.")
