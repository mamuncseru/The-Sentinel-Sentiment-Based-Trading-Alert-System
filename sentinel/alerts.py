"""
alerts.py — Telegram alert system (free).

Setup (5 minutes):
  1. Open Telegram → search @BotFather → /newbot → copy the API token
  2. Send any message to your new bot
  3. Visit: https://api.telegram.org/bot{TOKEN}/getUpdates → copy "chat_id"
  4. Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to your .env file
"""

import requests
from datetime import datetime
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALERT_ACTIONS, MIN_ALERT_CONFIDENCE


def _post(text: str) -> bool:
    """Low-level Telegram send. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Bot token or chat ID not configured.")
        return False
    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram] send error: {e}")
        return False


def should_alert(llm_result: dict) -> bool:
    """Return True if this signal is worth sending an alert for."""
    action     = llm_result.get("action", "HOLD")
    confidence = llm_result.get("confidence", 0)
    return action in ALERT_ACTIONS and confidence >= MIN_ALERT_CONFIDENCE


def send_signal_alert(
    ticker:      str,
    llm_result:  dict,
    sentiment:   dict,
    price:       dict,
    fear_greed:  dict,
) -> bool:
    """
    Send a formatted trading signal alert to Telegram.
    Returns True if successfully sent.
    """
    if not should_alert(llm_result):
        return False

    action     = llm_result.get("action", "HOLD")
    confidence = llm_result.get("confidence", 0)
    risk       = llm_result.get("risk_level", "MEDIUM")
    horizon    = llm_result.get("time_horizon", "N/A")
    reasoning  = llm_result.get("reasoning", "N/A")
    entry_note = llm_result.get("entry_note", "N/A")
    sl_note    = llm_result.get("stop_loss_note", "N/A")
    model      = llm_result.get("model_used", "N/A")

    risk_tag = {"LOW": "[LOW RISK]", "MEDIUM": "[MED RISK]", "HIGH": "[HIGH RISK]"}.get(risk, risk)
    now      = datetime.now().strftime("%Y-%m-%d %H:%M ET")

    msg = f"""
SENTINEL ALERT — {ticker}
{'='*34}
  Action     : {action}
  Confidence : {confidence}%
  Horizon    : {horizon}
  Risk       : {risk_tag}

MARKET DATA
  Price      : ${price.get('price', 'N/A')}  ({price.get('price_change_1d_pct', 0):+.1f}% today)
  Volume     : {price.get('volume_ratio_vs_30d_avg', 1):.1f}x 30d avg{' SPIKE' if price.get('is_volume_spike') else ''}
  Sentiment  : {sentiment.get('avg_sentiment', 0):+.3f}  (z={sentiment.get('z_score', 0):+.1f}sigma)
  Fear/Greed : {fear_greed.get('score', 50):.0f}/100 — {fear_greed.get('rating', 'Neutral')}

REASONING
{reasoning}

ENTRY NOTE
{entry_note}

STOP-LOSS
{sl_note}

Model: {model}  |  {now}
""".strip()

    return _post(msg)


def send_daily_summary(watchlist: list[str], summary: dict) -> bool:
    """
    Send end-of-day digest with sentiment snapshot for every ticker.
    Called at 4:05 PM ET (market close).
    """
    lines = [
        "SENTINEL — DAILY SUMMARY",
        "=" * 34,
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        f"{'TICKER':<7} {'SENT':>6} {'Z':>5} {'1D%':>6} {'VOL':>5}",
        "-" * 34,
    ]
    for ticker in watchlist:
        d   = summary.get(ticker, {})
        s   = d.get("avg_sentiment", 0.0)
        z   = d.get("z_score", 0.0)
        pct = d.get("price_change_1d_pct", 0.0)
        vol = d.get("volume_ratio_vs_30d_avg", 1.0)
        bar = "+" if s > 0.1 else "-" if s < -0.1 else "~"
        lines.append(f"{ticker:<7} {bar}{s:>+5.2f}  {z:>+4.1f}s  {pct:>+5.1f}%  {vol:>4.1f}x")

    return _post("\n".join(lines))


def send_startup_message(watchlist: list[str]) -> bool:
    """Notify that the bot started successfully."""
    tickers = ", ".join(watchlist)
    msg = (
        f"Sentinel started successfully.\n"
        f"Monitoring: {tickers}\n"
        f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}"
    )
    return _post(msg)


def send_error_alert(context: str, error: str) -> bool:
    """Send an error notification (used for critical failures)."""
    msg = f"[SENTINEL ERROR]\nContext: {context}\nError: {str(error)[:300]}"
    return _post(msg)
