# The Sentinel — Sentiment-Based Trading Alert System

A Python bot that monitors news, Reddit, and social media 24/7 for your stock watchlist,
detects sudden sentiment shifts, and sends you Telegram alerts with LLM-powered trading analysis.

**Monthly cost: ~$0.12–$2** (Scenario A, near-free)

---

## How It Works

1. Every 5–15 min: pulls news (Finnhub, Google RSS), Reddit posts, StockTwits data
2. FinBERT scores every piece of text (87% accuracy, runs locally, zero cost)
3. Z-score anomaly detection: if sentiment shifts >2σ from 7-day baseline → triggers LLM
4. Gemini 2.0 Flash-Lite analyzes the signal → returns BUY/SELL/HOLD/WATCH + reasoning
5. Telegram alert sent to your phone instantly
6. Everything logged to SQLite; optional paper trades on Alpaca

---

## Quick Start

### 1. Clone and install
```bash
git clone https://github.com/YOURUSERNAME/sentinel-bot.git
cd sentinel-bot
python3.11 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

### 2. Configure API keys
```bash
cp .env.example .env
# Edit .env and fill in your keys (all free to obtain — see .env.example for links)
```

**Required keys:**
| Key | Get From | Cost |
|-----|----------|------|
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) | Free |
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | Free (low usage) |
| `TELEGRAM_BOT_TOKEN` | Telegram → @BotFather → /newbot | Free |
| `TELEGRAM_CHAT_ID` | See .env.example instructions | Free |

**Optional (recommended):**
| Key | Get From | Cost |
|-----|----------|------|
| `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com) | ~$0.29/month |
| `REDDIT_CLIENT_ID/SECRET` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) | Free |
| `ALPACA_API_KEY/SECRET` | [alpaca.markets](https://alpaca.markets) | Free (paper) |

### 3. Test all connections
```bash
python scripts/test_connections.py
```

### 4. Run
```bash
python main.py              # start full scheduler (runs forever)
python main.py --test       # run one anomaly check cycle and exit
python main.py --summary    # send daily summary now and exit
```

### 5. View dashboard
```bash
streamlit run dashboard.py
# Open http://localhost:8501
```

---

## Project Structure

```
sentinel-bot/
├── main.py                   # Entry point
├── dashboard.py              # Streamlit web dashboard
├── requirements.txt          # Python dependencies
├── .env.example              # Template for API keys
│
├── sentinel/
│   ├── config.py             # All settings in one place
│   ├── collectors.py         # Data sources (Finnhub, RSS, Reddit, etc.)
│   ├── sentiment.py          # FinBERT scoring engine
│   ├── llm_analyst.py        # LLM analysis (Gemini + DeepSeek failover)
│   ├── alerts.py             # Telegram alert sender
│   ├── paper_trader.py       # Alpaca paper trading
│   ├── database.py           # SQLite schema and queries
│   └── scheduler.py          # APScheduler orchestrator
│
├── tests/
│   ├── test_sentiment.py     # Unit tests for FinBERT engine
│   └── test_database.py      # Unit tests for DB layer
│
└── scripts/
    ├── deploy_oracle.sh      # Oracle Cloud free tier deployment
    └── test_connections.py   # Verify all APIs before going live
```

---

## Customization

### Change your watchlist
Edit `sentinel/config.py`:
```python
WATCHLIST = ["NVDA", "AAPL", "MSFT", ...]
```

### Adjust alert sensitivity
In `sentinel/config.py`:
```python
ANOMALY_Z_SCORE_THRESHOLD = 2.0   # lower = more alerts, higher = fewer
PRICE_SHOCK_THRESHOLD_PCT = 4.0   # % price move to trigger LLM
MIN_ALERT_CONFIDENCE      = 55    # minimum LLM confidence to send Telegram
```

### Switch LLM model
```python
PRIMARY_LLM_MODEL  = "gemini-2.0-flash-lite"   # cheapest
# PRIMARY_LLM_MODEL = "gemini-2.5-flash-lite"  # better quality, slightly more
# PRIMARY_LLM_MODEL = "deepseek-chat"          # excellent reasoning, cheap
```

---

## Deploy to Oracle Cloud (Free, Always-On)

```bash
# SSH into your Oracle ARM instance, then:
chmod +x scripts/deploy_oracle.sh
./scripts/deploy_oracle.sh
```

This creates systemd services that auto-start on reboot and restart on crash.

---

## Monthly Cost

| Component | Scenario A | Scenario B |
|-----------|-----------|-----------|
| Hosting   | $0 (Oracle Free) | $5 (Hetzner) |
| LLM API   | ~$0.12 (Gemini Flash-Lite) | ~$3 (DeepSeek) |
| All data  | $0 (free tiers) | $0 |
| **Total** | **~$0.12/month** | **~$8/month** |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Important Disclaimers

- This system generates trading **alerts**, not financial advice
- Always paper trade for at least 3–6 months before using real money
- Past signal accuracy does not guarantee future performance
- The LLM can be wrong — always apply your own judgment
- Never risk more than you can afford to lose
# The-Sentinel-Sentiment-Based-Trading-Alert-System
