"""
dashboard.py — Streamlit web dashboard.

Run locally:  streamlit run dashboard.py
Access:       http://localhost:8501

On Oracle Cloud: open port 8501 in the Security List, then access
                 http://YOUR_INSTANCE_IP:8501
"""

import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="The Sentinel",
    layout="wide",
    page_icon="",
    initial_sidebar_state="expanded",
)

from sentinel.config   import WATCHLIST
from sentinel.database import get_recent_analyses, get_sentiment_history
from sentinel.paper_trader import get_portfolio_summary

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("The Sentinel")
    st.caption("Sentiment-Driven Trading Alerts")
    st.divider()
    lookback_hours = st.slider("Lookback (hours)", 6, 168, 48)
    selected_ticker = st.selectbox("Sentiment chart ticker", WATCHLIST)
    st.divider()
    if st.button("Refresh", use_container_width=True):
        st.rerun()

# ─── Header ───────────────────────────────────────────────────────────────────
st.title("Sentinel Dashboard")
st.caption(f"Last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ─── Top metrics row ──────────────────────────────────────────────────────────
analyses = get_recent_analyses(hours=lookback_hours)
df       = pd.DataFrame(analyses)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Alerts", len(df))
col2.metric("BUY signals",  len(df[df["action"] == "BUY"])  if not df.empty else 0)
col3.metric("SELL signals", len(df[df["action"] == "SELL"]) if not df.empty else 0)
col4.metric("WATCH signals",len(df[df["action"] == "WATCH"])if not df.empty else 0)
avg_conf = int(df["confidence"].mean()) if not df.empty else 0
col5.metric("Avg Confidence", f"{avg_conf}%")

st.divider()

# ─── Recent alerts table ──────────────────────────────────────────────────────
st.subheader(f"Recent Alerts ({lookback_hours}h)")
if df.empty:
    st.info("No alerts in the selected time window. The system may be warming up (needs 7 days of data for z-score baseline).")
else:
    action_colors = {"BUY": "green", "SELL": "red", "WATCH": "orange", "HOLD": "gray"}

    display_cols = ["timestamp", "ticker", "action", "confidence", "risk_level", "time_horizon", "reasoning"]
    available    = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[available].rename(columns={
            "timestamp":   "Time",
            "ticker":      "Ticker",
            "action":      "Action",
            "confidence":  "Confidence %",
            "risk_level":  "Risk",
            "time_horizon":"Horizon",
            "reasoning":   "Reasoning",
        }),
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ─── Sentiment chart ──────────────────────────────────────────────────────────
st.subheader(f"Sentiment History — {selected_ticker}")
hist = get_sentiment_history(selected_ticker, hours=lookback_hours)
if hist:
    hist_df = pd.DataFrame(hist)
    hist_df["time"] = pd.to_datetime(hist_df["time"])
    hist_df = hist_df.set_index("time")

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.line_chart(hist_df["sentiment_value"], height=250)
    with col_b:
        st.metric("Data points", len(hist_df))
        if len(hist_df) > 0:
            st.metric("Avg sentiment", f"{hist_df['sentiment_value'].mean():+.3f}")
            st.metric("Min", f"{hist_df['sentiment_value'].min():+.3f}")
            st.metric("Max", f"{hist_df['sentiment_value'].max():+.3f}")

    with st.expander("Recent headlines"):
        for _, row in hist_df.tail(10).iterrows():
            st.write(f"`{row['source']}` — {row['headline'][:120]}")
else:
    st.info(f"No sentiment data for {selected_ticker} in the selected window yet.")

st.divider()

# ─── Paper portfolio ──────────────────────────────────────────────────────────
st.subheader("Paper Portfolio (Alpaca)")
portfolio = get_portfolio_summary()
if portfolio.get("status") in ("not_configured", "error"):
    st.info("Alpaca paper trading not configured or unavailable.")
else:
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Portfolio Value", f"${portfolio.get('portfolio_value', 0):,.2f}")
    p2.metric("Cash",            f"${portfolio.get('cash', 0):,.2f}")
    p3.metric("Buying Power",    f"${portfolio.get('buying_power', 0):,.2f}")
    p4.metric("Unrealized P/L",  f"${portfolio.get('unrealized_pl', 0):+,.2f}")

    positions = portfolio.get("positions", [])
    if positions:
        pos_df = pd.DataFrame(positions)
        st.dataframe(pos_df, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")
