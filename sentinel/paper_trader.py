"""
paper_trader.py — Alpaca paper trading integration (free).

Paper trading = real market data, fake money.
Use this to track the signal performance for 3-6 months before considering real money.

Setup:
  1. Create a free account at https://alpaca.markets
  2. Go to Paper Trading → Generate API Keys
  3. Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .env
"""

from .config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    PAPER_TRADING_ENABLED, PAPER_PORTFOLIO_VALUE,
    PAPER_MIN_POSITION_PCT, PAPER_MAX_POSITION_PCT,
)
from .database import save_trade


def _get_client():
    """Return Alpaca TradingClient (paper mode) or None if not configured."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return None
    try:
        from alpaca.trading.client import TradingClient
        return TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
    except Exception as e:
        print(f"[Alpaca] client init error: {e}")
        return None


def submit_paper_trade(
    ticker:     str,
    action:     str,
    confidence: int,
    price:      float,
    analysis_id: int | None = None,
) -> dict:
    """
    Submit a paper trade sized by confidence (1%-3% of portfolio).

    Args:
        ticker      : stock symbol
        action      : "BUY" or "SELL"
        confidence  : LLM confidence 0-100
        price       : current market price
        analysis_id : FK to llm_analyses table

    Returns:
        dict with status and order details
    """
    if not PAPER_TRADING_ENABLED:
        return {"status": "disabled"}

    if action not in ("BUY", "SELL"):
        return {"status": "skipped", "reason": f"action={action}"}

    client = _get_client()
    if not client:
        return {"status": "skipped", "reason": "Alpaca not configured"}

    # Confidence-scaled position sizing
    conf_factor   = min(confidence / 100.0, 1.0)
    position_pct  = PAPER_MIN_POSITION_PCT + (PAPER_MAX_POSITION_PCT - PAPER_MIN_POSITION_PCT) * conf_factor
    position_val  = PAPER_PORTFOLIO_VALUE * position_pct
    qty           = max(1, int(position_val / price))

    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums    import OrderSide, TimeInForce

        order = MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.BUY if action == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        result = client.submit_order(order)

        # Persist to local DB
        save_trade(
            ticker=ticker, action=action,
            price=price, quantity=qty,
            analysis_id=analysis_id, paper=True,
        )

        return {
            "status":          "submitted",
            "order_id":        str(result.id),
            "ticker":          ticker,
            "action":          action,
            "qty":             qty,
            "estimated_value": round(qty * price, 2),
            "position_pct":    round(position_pct * 100, 1),
        }
    except Exception as e:
        print(f"[Alpaca] order error for {ticker}: {e}")
        return {"status": "error", "error": str(e)}


def get_portfolio_summary() -> dict:
    """Return current paper portfolio state."""
    client = _get_client()
    if not client:
        return {"status": "not_configured"}
    try:
        account   = client.get_account()
        positions = client.get_all_positions()
        return {
            "portfolio_value": float(account.portfolio_value),
            "cash":            float(account.cash),
            "buying_power":    float(account.buying_power),
            "unrealized_pl":   sum(float(p.unrealized_pl) for p in positions),
            "positions": [
                {
                    "ticker":             p.symbol,
                    "qty":                float(p.qty),
                    "avg_entry":          float(p.avg_entry_price),
                    "current_price":      float(p.current_price),
                    "unrealized_pl_pct":  float(p.unrealized_plpc) * 100,
                }
                for p in positions
            ],
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
