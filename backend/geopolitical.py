"""
Geopolitical Risk Analysis Module

Detects geopolitical events from news, scores their potential gold impact,
calculates a Geopolitical Risk Index, and provides backtesting against
historical gold price data.
"""

import json
import logging
import os
import csv
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# ============== Geopolitical Event Categories ==============

GEO_CATEGORIES = {
    "war_conflict": {
        "keywords": [
            "war", "military", "missile", "bombing", "invasion",
            "troops", "airstrike", "conflict", "escalation", "attack",
            "defense", "nato", "nuclear", "ceasefire", "drone strike",
            "army", "navy", "combat", "artillery", "casualties",
            "frontline", "occupation", "siege", "militia", "insurgent",
            "ukraine", "russia", "gaza", "hamas", "hezbollah",
            "iran", "strait of hormuz", "taiwan", "south china sea",
            "red sea", "houthi", "proxy war", "weapons", "warship",
        ],
        "gold_direction": "bullish",
        "base_impact": 0.6,
        "label": "War & Military Conflict",
        "icon": "Swords",
    },
    "sanctions_trade": {
        "keywords": [
            "sanctions", "tariff", "trade war", "embargo", "ban",
            "trade dispute", "export ban", "import duty", "retaliation",
            "trade restriction", "blacklist", "trade deal", "trade tension",
            "customs", "protectionism", "dumping", "countervailing",
            "reciprocal tariff", "baseline tariff", "trade deficit",
            "supply chain", "decoupling", "reshoring", "nearshoring",
            "semiconductor ban", "chip war", "export control",
            "swift", "frozen assets", "asset seizure",
        ],
        "gold_direction": "bullish",
        "base_impact": 0.4,
        "label": "Sanctions & Trade Wars",
        "icon": "Ban",
    },
    "election_political": {
        "keywords": [
            "election", "vote", "coup", "protest", "impeach",
            "resign", "political crisis", "government collapse",
            "referendum", "parliament", "constitutional", "regime",
            "opposition", "martial law", "political unrest", "riot",
            "brics", "g7", "g20", "geopolitical shift",
            "populism", "nationalism", "executive order",
            "government shutdown", "debt ceiling",
        ],
        "gold_direction": "bullish",
        "base_impact": 0.3,
        "label": "Elections & Political Instability",
        "icon": "Vote",
    },
    "central_bank": {
        "keywords": [
            "fed", "rate cut", "rate hike", "interest rate", "rbi",
            "monetary policy", "quantitative easing", "taper",
            "central bank", "gold reserves", "gold buying", "ecb",
            "bank of england", "bank of japan", "stimulus", "dovish",
            "hawkish", "yield curve", "treasury", "bond",
            "pboc", "gold reserves", "reserve diversification",
            "de-dollarization", "dollar alternative", "gold standard",
            "gold-backed", "reserve currency", "forex reserves",
            "inflation target", "rate pause", "rate hold",
        ],
        "gold_direction": "context_dependent",
        "base_impact": 0.5,
        "label": "Central Bank Policy",
        "icon": "Landmark",
    },
    "financial_crisis": {
        "keywords": [
            "bank collapse", "bank failure", "credit crisis",
            "recession", "depression", "market crash", "stock crash",
            "liquidity crisis", "contagion", "bailout", "default",
            "bankruptcy", "insolvency", "systemic risk", "panic",
            "bubble burst", "debt spiral", "credit crunch",
            "shadow banking", "commercial real estate crisis",
            "bond market turmoil", "yield spike", "bank run",
            "market correction", "flash crash", "selloff",
        ],
        "gold_direction": "bullish",
        "base_impact": 0.7,
        "label": "Financial Crisis",
        "icon": "TrendingDown",
    },
    "currency_crisis": {
        "keywords": [
            "currency crash", "devaluation", "hyperinflation",
            "dollar collapse", "debt crisis", "sovereign default",
            "capital controls", "currency peg", "forex crisis",
            "de-dollarization", "dedollarization", "dollar weaponization",
            "brics currency", "gold-backed currency", "yuan",
            "rupee internationalization", "local currency trade",
            "dollar dominance", "reserve currency shift",
        ],
        "gold_direction": "bullish",
        "base_impact": 0.5,
        "label": "Currency & De-dollarization",
        "icon": "DollarSign",
    },
    "peace_resolution": {
        "keywords": [
            "peace deal", "ceasefire agreement", "treaty signed",
            "diplomatic breakthrough", "de-escalation", "resolution",
            "normalize relations", "peace talks succeed", "armistice",
            "peace talks", "peace negotiations", "diplomatic talks",
            "truce", "reconciliation", "withdrawal",
        ],
        "gold_direction": "bearish",
        "base_impact": -0.3,
        "label": "Peace & Diplomatic Resolution",
        "icon": "Handshake",
    },
}

# Category display order
CATEGORY_ORDER = [
    "war_conflict", "financial_crisis", "sanctions_trade",
    "central_bank", "election_political", "currency_crisis",
    "peace_resolution",
]


def classify_news_article(title: str, summary: str = "") -> Optional[Dict]:
    """
    Classify a news article into a geopolitical event category.

    Returns None if the article is not geopolitical, or a dict with:
    - category, severity_score, gold_impact_direction, gold_impact_magnitude,
      keywords_matched
    """
    text = f"{title} {summary}".lower()

    best_match = None
    best_score = 0
    best_keywords = []

    for cat_id, cat_info in GEO_CATEGORIES.items():
        matched = [kw for kw in cat_info["keywords"] if kw in text]
        score = len(matched)

        if score > best_score:
            best_score = score
            best_match = cat_id
            best_keywords = matched

    if best_score < 2:
        # Need at least 2 keyword matches to classify
        return None

    cat_info = GEO_CATEGORIES[best_match]

    # Severity: more keywords = higher severity, capped at 10
    severity = min(10, best_score + 3)

    # Determine direction
    direction = cat_info["gold_direction"]
    if direction == "context_dependent":
        # Check for dovish vs hawkish language
        dovish = ["rate cut", "stimulus", "easing", "dovish", "gold buying"]
        hawkish = ["rate hike", "tightening", "hawkish", "taper"]
        dovish_count = sum(1 for kw in dovish if kw in text)
        hawkish_count = sum(1 for kw in hawkish if kw in text)
        if dovish_count > hawkish_count:
            direction = "bullish"
        elif hawkish_count > dovish_count:
            direction = "bearish"
        else:
            direction = "neutral"

    # Magnitude based on base impact scaled by severity
    magnitude = cat_info["base_impact"] * (severity / 10)
    if direction == "bearish" and magnitude > 0:
        magnitude = -magnitude

    return {
        "category": best_match,
        "severity_score": severity,
        "gold_impact_direction": direction,
        "gold_impact_magnitude": round(magnitude, 3),
        "keywords_matched": best_keywords,
    }


def calculate_geo_risk_index(recent_events: List[Dict]) -> Dict:
    """
    Calculate the Geopolitical Risk Index (0-100) from recent events.

    Args:
        recent_events: List of event dicts with category, severity_score, event_date

    Returns:
        Dict with risk_score, risk_label, category_breakdown, etc.
    """
    if not recent_events:
        return {
            "risk_score": 10,
            "risk_label": "Low",
            "active_events_count": 0,
            "top_events": [],
            "category_breakdown": {},
            "gold_impact_estimate": 0.0,
            "trend": "Stable",
        }

    now = datetime.now()

    # Weight events by recency (newer = more weight)
    weighted_severities = []
    category_scores = {}
    for event in recent_events:
        event_date = event.get("event_date")
        if isinstance(event_date, str):
            event_date = datetime.fromisoformat(event_date)

        days_ago = max(1, (now - event_date).days) if event_date else 7
        recency_weight = max(0.1, 1.0 - (days_ago / 14))  # Decay over 14 days
        severity = event.get("severity_score", 5)
        weighted = severity * recency_weight

        weighted_severities.append(weighted)

        cat = event.get("category", "unknown")
        category_scores[cat] = category_scores.get(cat, 0) + weighted

    # Components of the risk score
    event_count_score = min(40, len(recent_events) * 5)  # 40% weight, max at 8 events
    avg_severity_score = (sum(weighted_severities) / len(weighted_severities)) * 3  # 30% weight
    avg_severity_score = min(30, avg_severity_score)

    # Trend: compare last 3 days vs prior 4 days
    recent_3d = [e for e in recent_events if _days_ago(e.get("event_date")) <= 3]
    prior_4d = [e for e in recent_events if 3 < _days_ago(e.get("event_date")) <= 7]
    if len(recent_3d) > len(prior_4d) * 1.5:
        trend = "Escalating"
        trend_score = 20
    elif len(recent_3d) < len(prior_4d) * 0.5:
        trend = "De-escalating"
        trend_score = 5
    else:
        trend = "Stable"
        trend_score = 12

    risk_score = int(event_count_score + avg_severity_score + trend_score)
    risk_score = max(0, min(100, risk_score))

    # Label
    if risk_score <= 20:
        risk_label = "Low"
    elif risk_score <= 40:
        risk_label = "Moderate"
    elif risk_score <= 60:
        risk_label = "Elevated"
    elif risk_score <= 80:
        risk_label = "High"
    else:
        risk_label = "Extreme"

    # Gold impact estimate based on risk level
    impact_map = {
        "Low": 0.2, "Moderate": 0.8, "Elevated": 1.5,
        "High": 3.0, "Extreme": 5.0,
    }
    gold_impact_estimate = impact_map.get(risk_label, 0.5)

    # Top events (sorted by weighted severity)
    sorted_events = sorted(
        recent_events,
        key=lambda e: e.get("severity_score", 0),
        reverse=True,
    )[:5]
    top_events = [
        {
            "title": e.get("title", ""),
            "category": e.get("category", ""),
            "severity": e.get("severity_score", 0),
            "direction": e.get("gold_impact_direction", "neutral"),
        }
        for e in sorted_events
    ]

    return {
        "risk_score": risk_score,
        "risk_label": risk_label,
        "active_events_count": len(recent_events),
        "top_events": top_events,
        "category_breakdown": category_scores,
        "gold_impact_estimate": round(gold_impact_estimate, 2),
        "trend": trend,
    }


def _days_ago(event_date) -> int:
    """Get days since event date."""
    if event_date is None:
        return 7
    if isinstance(event_date, str):
        event_date = datetime.fromisoformat(event_date)
    return max(0, (datetime.now() - event_date).days)


# ============== Backtesting Engine ==============

def load_seed_events() -> List[Dict]:
    """Load curated historical events from the seed JSON file."""
    seed_path = os.path.join(DATA_DIR, "geo_events_seed.json")
    try:
        with open(seed_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Seed file not found: {seed_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in seed file: {e}")
        return []


def load_gold_price_csv() -> Dict[str, float]:
    """
    Load historical gold prices.
    Returns a dict mapping date string (YYYY-MM-DD) to price (USD).

    Priority:
    1. Database table (historical_gold_prices) -- populated by ingest script
    2. CSV file (gold_prices_historical.csv) -- legacy fallback
    3. Seed event data -- last resort
    """
    prices = {}

    # 1. Try database table first (best source)
    try:
        from database import SessionLocal
        from models import HistoricalGoldPrice
        db = SessionLocal()
        try:
            rows = db.query(
                HistoricalGoldPrice.date, HistoricalGoldPrice.price_usd
            ).all()
            if rows:
                for row in rows:
                    prices[row.date.isoformat()] = float(row.price_usd)
                logger.info(f"Loaded {len(prices)} gold prices from database")
                return prices
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"Could not load from database: {e}")

    # 2. Fall back to CSV file
    csv_path = os.path.join(DATA_DIR, "gold_prices_historical.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    date_str = row.get("date") or row.get("Date") or ""
                    price_str = row.get("price_usd") or row.get("Price") or row.get("price") or ""
                    if date_str and price_str:
                        try:
                            prices[date_str[:10]] = float(price_str.replace(",", ""))
                        except ValueError:
                            continue
            logger.info(f"Loaded {len(prices)} gold prices from CSV")
        except Exception as e:
            logger.warning(f"Error loading gold price CSV: {e}")

    # 3. Last resort: build prices from seed event data
    if not prices:
        logger.info("No historical data found, using seed event prices for backtesting")
        for event in load_seed_events():
            date = event.get("date", "")
            price = event.get("price_at_event")
            if date and price:
                prices[date] = float(price)

    return prices


def _find_nearest_price(prices: Dict[str, float], target_date: str, direction: int = 0, max_days: int = 5) -> Optional[float]:
    """
    Find the nearest price to a target date.
    direction: 0=any, 1=forward, -1=backward
    """
    from datetime import date as date_type

    try:
        target = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

    # Try exact date first
    if target_date[:10] in prices:
        return prices[target_date[:10]]

    # Search nearby dates
    for offset in range(1, max_days + 1):
        if direction >= 0:
            forward = (target + timedelta(days=offset)).isoformat()
            if forward in prices:
                return prices[forward]
        if direction <= 0:
            backward = (target - timedelta(days=offset)).isoformat()
            if backward in prices:
                return prices[backward]

    return None


def run_backtest_for_event(event: Dict, prices: Dict[str, float]) -> Optional[Dict]:
    """
    Run a backtest for a single historical event.

    Calculates the actual gold price impact across multiple time windows.
    """
    event_date = event.get("date", "")
    event_name = event.get("name", "Unknown Event")

    # Get price at event (use seed data if available, else CSV)
    price_at_event = event.get("price_at_event")
    if not price_at_event:
        price_at_event = _find_nearest_price(prices, event_date)
    if not price_at_event:
        logger.warning(f"No price data for {event_name} on {event_date}")
        return None

    price_at_event = float(price_at_event)

    # Calculate date offsets
    try:
        base_date = datetime.strptime(event_date[:10], "%Y-%m-%d")
    except ValueError:
        return None

    # Look up prices at different windows
    price_before_7d = _find_nearest_price(
        prices, (base_date - timedelta(days=7)).strftime("%Y-%m-%d"),
        direction=-1,
    )
    price_after_1d = _find_nearest_price(
        prices, (base_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        direction=1,
    )
    price_after_7d = event.get("price_after_7d") or _find_nearest_price(
        prices, (base_date + timedelta(days=7)).strftime("%Y-%m-%d"),
        direction=1,
    )
    price_after_30d = _find_nearest_price(
        prices, (base_date + timedelta(days=30)).strftime("%Y-%m-%d"),
        direction=1,
    )
    price_after_90d = _find_nearest_price(
        prices, (base_date + timedelta(days=90)).strftime("%Y-%m-%d"),
        direction=1,
    )

    def pct(before, after):
        if before and after and before > 0:
            return round(((after - before) / before) * 100, 2)
        return None

    # Use the seed-provided impact if we don't have CSV data for this window
    impact_7d = event.get("impact_7d_pct") or pct(price_at_event, price_after_7d)

    # Build price chart data (daily prices from -30d to +90d)
    chart_data = []
    for day_offset in range(-30, 91):
        check_date = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        price = _find_nearest_price(prices, check_date, max_days=2)
        if price:
            chart_data.append({"date": check_date, "price": price, "day": day_offset})

    return {
        "event_name": event_name,
        "event_date": event_date,
        "category": event.get("category", "unknown"),
        "severity_score": event.get("severity", 5),
        "description": event.get("description", ""),
        "region_affected": event.get("region_affected", "Global"),
        "price_at_event": price_at_event,
        "price_before_7d": price_before_7d,
        "price_after_1d": price_after_1d,
        "price_after_7d": float(price_after_7d) if price_after_7d else None,
        "price_after_30d": float(price_after_30d) if price_after_30d else None,
        "price_after_90d": float(price_after_90d) if price_after_90d else None,
        "impact_1d_pct": pct(price_at_event, price_after_1d),
        "impact_7d_pct": impact_7d,
        "impact_30d_pct": pct(price_at_event, price_after_30d),
        "impact_90d_pct": pct(price_at_event, price_after_90d),
        "price_chart_data": chart_data,
    }


def run_full_backtest() -> List[Dict]:
    """
    Run backtest for all seed events.
    Returns list of backtest results.
    """
    events = load_seed_events()
    prices = load_gold_price_csv()

    if not events:
        logger.warning("No seed events to backtest")
        return []

    results = []
    for event in events:
        result = run_backtest_for_event(event, prices)
        if result:
            results.append(result)
            logger.info(
                f"Backtested: {result['event_name']} "
                f"(7d impact: {result.get('impact_7d_pct', 'N/A')}%)"
            )

    logger.info(f"Backtest complete: {len(results)}/{len(events)} events processed")
    return results


def get_category_statistics(backtest_results: List[Dict]) -> List[Dict]:
    """
    Aggregate backtest results by event category.
    Returns list of category stats sorted by average 30d impact.
    """
    category_data = {}

    for result in backtest_results:
        cat = result.get("category", "unknown")
        if cat not in category_data:
            category_data[cat] = {
                "category": cat,
                "label": GEO_CATEGORIES.get(cat, {}).get("label", cat),
                "icon": GEO_CATEGORIES.get(cat, {}).get("icon", "AlertTriangle"),
                "direction": GEO_CATEGORIES.get(cat, {}).get("gold_direction", "neutral"),
                "events": [],
                "impacts_1d": [],
                "impacts_7d": [],
                "impacts_30d": [],
                "impacts_90d": [],
            }

        category_data[cat]["events"].append({
            "name": result["event_name"],
            "date": result["event_date"],
            "impact_7d_pct": result.get("impact_7d_pct"),
        })

        for window in ["1d", "7d", "30d", "90d"]:
            val = result.get(f"impact_{window}_pct")
            if val is not None:
                category_data[cat][f"impacts_{window}"].append(val)

    # Calculate averages
    stats = []
    for cat_id in CATEGORY_ORDER:
        if cat_id not in category_data:
            continue
        data = category_data[cat_id]
        stat = {
            "category": data["category"],
            "label": data["label"],
            "icon": data["icon"],
            "direction": data["direction"],
            "event_count": len(data["events"]),
            "events": data["events"],
        }
        for window in ["1d", "7d", "30d", "90d"]:
            impacts = data[f"impacts_{window}"]
            if impacts:
                stat[f"avg_impact_{window}_pct"] = round(sum(impacts) / len(impacts), 2)
                stat[f"max_impact_{window}_pct"] = round(max(impacts), 2)
                stat[f"min_impact_{window}_pct"] = round(min(impacts), 2)
            else:
                stat[f"avg_impact_{window}_pct"] = None
                stat[f"max_impact_{window}_pct"] = None
                stat[f"min_impact_{window}_pct"] = None

        stats.append(stat)

    return stats


def get_backtest_summary(backtest_results: List[Dict]) -> Dict:
    """Get summary statistics across all backtest results."""
    if not backtest_results:
        return {"total_events": 0}

    impacts_7d = [r["impact_7d_pct"] for r in backtest_results if r.get("impact_7d_pct") is not None]
    impacts_30d = [r["impact_30d_pct"] for r in backtest_results if r.get("impact_30d_pct") is not None]

    # Find strongest event
    strongest = max(backtest_results, key=lambda r: abs(r.get("impact_7d_pct") or 0))

    return {
        "total_events": len(backtest_results),
        "avg_impact_7d_pct": round(sum(impacts_7d) / len(impacts_7d), 2) if impacts_7d else 0,
        "avg_impact_30d_pct": round(sum(impacts_30d) / len(impacts_30d), 2) if impacts_30d else 0,
        "strongest_event": strongest["event_name"],
        "strongest_impact_7d": strongest.get("impact_7d_pct", 0),
        "bullish_events": sum(1 for r in backtest_results if (r.get("impact_7d_pct") or 0) > 0),
        "bearish_events": sum(1 for r in backtest_results if (r.get("impact_7d_pct") or 0) < 0),
    }
