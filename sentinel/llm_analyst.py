"""
llm_analyst.py — LLM analysis layer.

Primary model   : Gemini 2.0 Flash-Lite  ($0.075/$0.30 per 1M tokens)
Fallback model  : DeepSeek V3.2          ($0.28/$0.42  per 1M tokens)

At 500 calls/month × ~2,000 tokens avg → ~$0.12/month total.

Hard monthly call budget enforced to prevent surprise bills.
"""

import os
import json
from datetime import date
from .config import (
    GEMINI_API_KEY, DEEPSEEK_API_KEY,
    MONTHLY_LLM_CALL_BUDGET, LLM_CALL_COUNT_FILE,
    PRIMARY_LLM_MODEL, FALLBACK_LLM_MODEL,
    LLM_MAX_OUTPUT_TOKENS, LLM_TEMPERATURE,
)

# ─── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a quantitative trading analyst specializing in sentiment-driven short-term stock movements for mega-cap US companies.

You analyze real-time sentiment data and identify potential short-term trading opportunities based on three primary patterns:
1. Overreaction patterns: Strong companies drop sharply on sentiment/news that does not change fundamentals
2. Post-earnings drift: Earnings beats/misses set up directional trades lasting 2-8 weeks
3. Social media momentum: Unusual attention spikes indicating potential price movement

Your output must be a JSON object with EXACTLY these fields and no others:
{
  "action": "BUY" | "SELL" | "HOLD" | "WATCH",
  "confidence": <integer 0-100>,
  "time_horizon": "1-2 days" | "3-7 days" | "2-4 weeks",
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "reasoning": "<2-3 sentences describing what the data shows and why this matters>",
  "entry_note": "<brief note on timing or conditions to wait for before entering>",
  "stop_loss_note": "<brief mental stop-loss note based on the data>"
}

Strict rules:
- Only suggest BUY/SELL for S&P 500 companies with clear, multi-source signals
- Default to WATCH when signal is present but ambiguous
- Default to HOLD when there is no meaningful signal
- Flag HIGH risk whenever earnings are within 14 days
- Never suggest specific dollar amounts or position sizes
- A large z-score alone (without supporting price/volume) should result in WATCH not BUY/SELL"""


# ─── Monthly call budget ──────────────────────────────────────────────────────

def _get_monthly_calls() -> int:
    try:
        with open(LLM_CALL_COUNT_FILE) as f:
            data = json.load(f)
        if data.get("month") == date.today().strftime("%Y-%m"):
            return data.get("count", 0)
    except Exception:
        pass
    return 0


def _increment_call_count() -> int:
    count = _get_monthly_calls() + 1
    with open(LLM_CALL_COUNT_FILE, "w") as f:
        json.dump({"month": date.today().strftime("%Y-%m"), "count": count}, f)
    return count


# ─── Context packet builder ───────────────────────────────────────────────────

def build_context_packet(
    ticker: str,
    sentiment: dict,
    price: dict,
    stocktwits: dict,
    fear_greed: dict,
) -> str:
    """
    Assemble the compact context string sent to the LLM.
    Deliberately minimal to keep token count (and cost) low.
    """
    headlines = "\n".join(
        f"  - {h}" for h in sentiment.get("top_headlines", [])[:5]
    ) or "  - (no recent headlines)"

    return f"""TICKER: {ticker}
PRICE: ${price.get('price', 'N/A')} | 1D: {price.get('price_change_1d_pct', 0):+.1f}% | 5D: {price.get('ret_5d_pct', 0):+.1f}%
VOLUME: {price.get('volume_ratio_vs_30d_avg', 1):.1f}x 30d avg{' [SPIKE]' if price.get('is_volume_spike') else ''}

SENTIMENT (last 4h):
  Score:    {sentiment.get('avg_sentiment', 0):+.3f}  (-1=very bearish, +1=very bullish)
  Velocity: {sentiment.get('velocity', 0):+.3f}  (rate of change last hour)
  Z-Score:  {sentiment.get('z_score', 0):+.1f}sigma from 7-day baseline
  Items:    {sentiment.get('item_count', 0)} news/social pieces analyzed

SOCIAL (StockTwits):
  Bull ratio: {stocktwits.get('bull_ratio', 0.5):.0%}  Score: {stocktwits.get('stocktwits_score', 0):+.2f}

MARKET MOOD (Fear & Greed): {fear_greed.get('score', 50):.0f}/100 — {fear_greed.get('rating', 'Neutral')}

TOP HEADLINES (last 4h):
{headlines}

ANOMALY: {sentiment.get('anomaly_direction', 'none').upper()} at {abs(sentiment.get('z_score', 0)):.1f}sigma"""


# ─── LLM call with failover ───────────────────────────────────────────────────

def analyze_with_llm(context_packet: str, ticker: str) -> dict:
    """
    Send the context packet to the LLM and return a structured analysis dict.

    Primary:  Gemini 2.0 Flash-Lite (cheapest viable model)
    Fallback: DeepSeek V3.2 (OpenAI-compatible API)

    Returns dict with keys: action, confidence, time_horizon, risk_level,
                             reasoning, entry_note, stop_loss_note, model_used
    """
    # Cost guardrail — hard stop
    monthly_calls = _get_monthly_calls()
    if monthly_calls >= MONTHLY_LLM_CALL_BUDGET:
        print(f"[LLM] Monthly budget reached ({MONTHLY_LLM_CALL_BUDGET} calls). Skipping.")
        return _budget_exceeded_result()

    prompt = f"Analyze this trading signal and respond with valid JSON only:\n\n{context_packet}"

    # ── Try Gemini first ──────────────────────────────────────────────────────
    if GEMINI_API_KEY:
        result = _call_gemini(prompt)
        if result:
            _increment_call_count()
            result["model_used"] = PRIMARY_LLM_MODEL
            return result

    # ── Fallback to DeepSeek ──────────────────────────────────────────────────
    if DEEPSEEK_API_KEY:
        result = _call_deepseek(prompt)
        if result:
            _increment_call_count()
            result["model_used"] = FALLBACK_LLM_MODEL
            return result

    print(f"[LLM] Both models failed for {ticker}")
    return _error_result("Both primary and fallback LLM calls failed")


def _call_gemini(prompt: str) -> dict | None:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=PRIMARY_LLM_MODEL,
            system_instruction=SYSTEM_PROMPT,
        )
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=LLM_TEMPERATURE,
                max_output_tokens=LLM_MAX_OUTPUT_TOKENS,
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[LLM] Gemini error: {e}")
        return None


def _call_deepseek(prompt: str) -> dict | None:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[LLM] DeepSeek error: {e}")
        return None


def _budget_exceeded_result() -> dict:
    return {
        "action": "HOLD", "confidence": 0,
        "time_horizon": "N/A", "risk_level": "HIGH",
        "reasoning": f"Monthly LLM budget of {MONTHLY_LLM_CALL_BUDGET} calls reached.",
        "entry_note": "", "stop_loss_note": "",
        "model_used": "budget_exceeded",
    }


def _error_result(msg: str) -> dict:
    return {
        "action": "HOLD", "confidence": 0,
        "time_horizon": "N/A", "risk_level": "HIGH",
        "reasoning": msg, "entry_note": "", "stop_loss_note": "",
        "model_used": "error",
    }
