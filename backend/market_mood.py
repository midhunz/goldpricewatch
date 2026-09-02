"""
Market Mood Index Calculator (v2 — Multi-Signal Fear & Greed)

Calculates a 0-100 mood score for gold markets by blending:
  1. Price Momentum  (15%)  — 7d MA vs 30d MA of gold prices
  2. Volatility      (10%)  — 14-day std-dev as % of avg price (inverted)
  3. Recent Change   (15%)  — 7-day price % change
  4. USD Strength    (15%)  — USD index impact (-1 to 1)
  5. Interest Rate   (15%)  — Treasury yield impact (-1 to 1)
  6. News Sentiment  (10%)  — VADER compound score (-1 to 1)
  7. Geopolitical    (10%)  — Geo risk score (0 to 100)
  8. Central Bank    (10%)  — CB buying/selling impact (-1 to 1)

Each sub-score maps to 0-100.  The weighted average gives the final mood.
"""

import math
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# ─── Weights ────────────────────────────────────────────────────────
WEIGHTS = {
    "momentum":       0.15,
    "volatility":     0.10,
    "recent_change":  0.15,
    "usd_strength":   0.15,
    "interest_rate":  0.15,
    "news_sentiment": 0.10,
    "geopolitical":   0.10,
    "central_bank":   0.10,
}

# ─── Helpers ────────────────────────────────────────────────────────

def _clamp(value: float, lo: float = 0, hi: float = 100) -> float:
    return max(lo, min(hi, value))


def _moving_average(prices: List[float], period: int) -> float:
    if not prices or len(prices) < period:
        return 0.0
    return sum(prices[-period:]) / period


def _std_dev(prices: List[float]) -> float:
    if not prices or len(prices) < 2:
        return 0.0
    mean = sum(prices) / len(prices)
    variance = sum((p - mean) ** 2 for p in prices) / len(prices)
    return math.sqrt(variance)


def _pct_change(prices: List[float], days: int) -> float:
    if not prices or len(prices) < days + 1:
        return 0.0
    old = prices[-(days + 1)]
    return ((prices[-1] - old) / old) * 100 if old else 0.0


# ─── Sub-score functions ────────────────────────────────────────────

def _score_momentum(prices: List[float]) -> float:
    """7-day MA vs 30-day MA.  ±5 % spread → 0-100."""
    ma_7 = _moving_average(prices, 7)
    ma_30 = _moving_average(prices, min(30, len(prices)))
    if ma_30 <= 0:
        return 50.0
    ratio = (ma_7 - ma_30) / ma_30 * 100          # e.g. +2 %
    return _clamp(50 + (ratio / 5) * 50)


def _score_volatility(prices: List[float]) -> float:
    """14-day std-dev as % of avg.  0-5 % → 100-0 (inverted: low vol = greed)."""
    recent = prices[-14:] if len(prices) >= 14 else prices
    sd = _std_dev(recent)
    avg = sum(recent) / len(recent) if recent else 1
    vol_pct = (sd / avg) * 100 if avg > 0 else 0
    return _clamp(100 - (vol_pct / 5) * 100)


def _score_recent_change(prices: List[float]) -> float:
    """7-day price change.  ±5 % → 0-100."""
    change = _pct_change(prices, 7)
    return _clamp(50 + (change / 5) * 50)


def _score_usd_strength(usd_impact: float) -> float:
    """
    usd_impact is -1 (strong USD, bearish for gold) to +1 (weak USD, bullish).
    Map to 0-100:  -1 → 0 (fear), +1 → 100 (greed).
    """
    return _clamp(50 + usd_impact * 50)


def _score_interest_rate(ir_impact: float) -> float:
    """
    ir_impact is -1 (high yields, bearish) to +1 (low yields, bullish).
    Map to 0-100.
    """
    return _clamp(50 + ir_impact * 50)


def _score_news_sentiment(sentiment: float) -> float:
    """
    VADER compound score -1 to +1.  Map to 0-100.
    """
    return _clamp(50 + sentiment * 50)


def _score_geopolitical(geo_risk_score: float) -> float:
    """
    geo_risk_score is 0-100 (higher = more risk).
    Higher geopolitical risk is generally *bullish* for gold (safe haven).
    So higher risk → higher mood score.
    """
    return _clamp(geo_risk_score)


def _score_central_bank(cb_impact: float) -> float:
    """
    cb_impact is -1 (selling) to +1 (buying).  Buying = bullish → greed.
    """
    return _clamp(50 + cb_impact * 50)


# ─── Main calculator ────────────────────────────────────────────────

def calculate_market_mood(
    history_data: List[Dict],
    slope: float = 0,
    *,
    usd_impact: float = 0.0,
    interest_rate_impact: float = 0.0,
    news_sentiment: float = 0.0,
    geo_risk_score: float = 0.0,
    central_bank_impact: float = 0.0,
) -> Dict:
    """
    Calculate the Market Mood Index (0-100).

    Args:
        history_data:        List of {'timestamp', 'price'} dicts
        slope:               Regression slope (kept for compat, unused in v2)
        usd_impact:          -1 to +1
        interest_rate_impact:-1 to +1
        news_sentiment:      -1 to +1  (VADER compound)
        geo_risk_score:      0 to 100
        central_bank_impact: -1 to +1
    """
    if not history_data or len(history_data) < 7:
        return {
            "mood_score": 50,
            "mood_label": "Insufficient Data",
            "factors": {k: 50 for k in WEIGHTS},
        }

    sorted_data = sorted(history_data, key=lambda x: x["timestamp"])
    prices = [float(d["price"]) for d in sorted_data]

    # Compute each sub-score
    scores = {
        "momentum":       round(_score_momentum(prices)),
        "volatility":     round(_score_volatility(prices)),
        "recent_change":  round(_score_recent_change(prices)),
        "usd_strength":   round(_score_usd_strength(usd_impact)),
        "interest_rate":  round(_score_interest_rate(interest_rate_impact)),
        "news_sentiment": round(_score_news_sentiment(news_sentiment)),
        "geopolitical":   round(_score_geopolitical(geo_risk_score)),
        "central_bank":   round(_score_central_bank(central_bank_impact)),
    }

    # Weighted average
    mood_score = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)
    mood_score = round(mood_score)

    # Label
    if mood_score >= 80:
        mood_label = "Extreme Greed"
    elif mood_score >= 60:
        mood_label = "Greed"
    elif mood_score >= 40:
        mood_label = "Neutral"
    elif mood_score >= 20:
        mood_label = "Fear"
    else:
        mood_label = "Extreme Fear"

    # Details (for debugging / transparency)
    ma_7 = _moving_average(prices, 7)
    ma_30 = _moving_average(prices, min(30, len(prices)))
    recent = prices[-14:] if len(prices) >= 14 else prices
    avg_price = sum(recent) / len(recent) if recent else 1
    vol_pct = (_std_dev(recent) / avg_price) * 100 if avg_price > 0 else 0

    return {
        "mood_score": mood_score,
        "mood_label": mood_label,
        "factors": scores,
        "details": {
            "ma_7": round(ma_7, 2),
            "ma_30": round(ma_30, 2),
            "volatility_percent": round(vol_pct, 2),
            "change_7d_percent": round(_pct_change(prices, 7), 2),
            "slope": round(slope, 2),
            "usd_impact": round(usd_impact, 2),
            "interest_rate_impact": round(interest_rate_impact, 2),
            "news_sentiment": round(news_sentiment, 2),
            "geo_risk_score": round(geo_risk_score, 2),
            "central_bank_impact": round(central_bank_impact, 2),
        },
    }
