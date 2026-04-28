"""
test_connections.py — Verify all API connections before going live.
Run: python scripts/test_connections.py

Checks each data source independently and prints PASS/FAIL.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def check(name: str, fn):
    try:
        result = fn()
        print(f"  [PASS] {name}: {result}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False


def main():
    results = {}
    print("\n=== Sentinel Connection Tests ===\n")

    # ── Finnhub ───────────────────────────────────────────────────────────────
    print("Finnhub (company news):")
    results["finnhub"] = check(
        "NVDA news",
        lambda: f"{len(__import__('finnhub').Client(api_key=os.environ.get('FINNHUB_API_KEY','')).company_news('NVDA', _from='2026-01-01', to='2026-12-31'))} items"
    )

    # ── Google News RSS ───────────────────────────────────────────────────────
    print("\nGoogle News RSS (no key needed):")
    from sentinel.collectors import get_google_news
    results["google_rss"] = check(
        "$NVDA headlines",
        lambda: f"{len(get_google_news('NVDA'))} items"
    )

    # ── yfinance ─────────────────────────────────────────────────────────────
    print("\nyfinance (price data):")
    from sentinel.collectors import get_price_data
    results["yfinance"] = check(
        "AAPL price",
        lambda: f"${get_price_data('AAPL').get('price', 'N/A')}"
    )

    # ── StockTwits ────────────────────────────────────────────────────────────
    print("\nStockTwits (no key needed):")
    from sentinel.collectors import get_stocktwits_sentiment
    results["stocktwits"] = check(
        "TSLA bull/bear",
        lambda: f"bull={get_stocktwits_sentiment('TSLA').get('bull_ratio',0):.0%}"
    )

    # ── Fear & Greed ──────────────────────────────────────────────────────────
    print("\nFear & Greed Index (no key needed):")
    from sentinel.collectors import get_fear_and_greed
    results["fear_greed"] = check(
        "CNN F&G",
        lambda: f"{get_fear_and_greed().get('score', 'N/A')}/100"
    )

    # ── Reddit ────────────────────────────────────────────────────────────────
    if os.environ.get("REDDIT_CLIENT_ID"):
        print("\nReddit PRAW:")
        from sentinel.collectors import get_reddit_mentions
        results["reddit"] = check(
            "NVDA mentions",
            lambda: f"{len(get_reddit_mentions('NVDA'))} posts"
        )
    else:
        print("\nReddit: SKIPPED (REDDIT_CLIENT_ID not set)")

    # ── FinBERT ───────────────────────────────────────────────────────────────
    print("\nFinBERT (loads model — takes ~10 seconds first time):")
    from sentinel.sentiment import score_text
    results["finbert"] = check(
        "Positive headline",
        lambda: score_text("Apple beats earnings with record revenue")["label"]
    )

    # ── Gemini ────────────────────────────────────────────────────────────────
    if os.environ.get("GEMINI_API_KEY"):
        print("\nGemini 2.0 Flash-Lite (LLM):")
        import google.generativeai as genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        results["gemini"] = check(
            "Simple prompt",
            lambda: model.generate_content("Reply with: OK").text.strip()[:20]
        )
    else:
        print("\nGemini: SKIPPED (GEMINI_API_KEY not set)")

    # ── Telegram ─────────────────────────────────────────────────────────────
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        print("\nTelegram Bot:")
        import requests as req
        token   = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
        results["telegram"] = check(
            "Send test message",
            lambda: req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": "Sentinel connection test OK"},
                timeout=10,
            ).status_code
        )
    else:
        print("\nTelegram: SKIPPED (tokens not set)")

    # ── Alpaca ────────────────────────────────────────────────────────────────
    if os.environ.get("ALPACA_API_KEY"):
        print("\nAlpaca Paper Trading:")
        from sentinel.paper_trader import get_portfolio_summary
        results["alpaca"] = check(
            "Portfolio summary",
            lambda: f"${get_portfolio_summary().get('portfolio_value', 'N/A')}"
        )
    else:
        print("\nAlpaca: SKIPPED (ALPACA_API_KEY not set)")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 38)
    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    print(f"Results: {passed}/{total} passed\n")
    if passed == total:
        print("All connections OK. Ready to run: python main.py")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"Failed: {', '.join(failed)}")
        print("Check your .env file and API keys.")


if __name__ == "__main__":
    main()
