"""Pure helpers for gold-rate parsing, normalisation and sanity guardrails.

Kept free of FastAPI and SQLAlchemy imports on purpose: main.py runs
`Base.metadata.create_all(bind=engine)` at import time, so anything importable
from main.py needs a live database. These functions are the part worth unit
testing, so they live here instead.

Implements the data-correctness guardrails from SEO_TASKS.md:
  T1.2  a missing prior close yields None, never 0.00
  T1.3  feed staleness is measurable, so a stale delta can be suppressed
  T7.1  price sanity: no zero/negative prices, 22K/24K ratio band,
        state-vs-national divergence, feed age
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Purity normalisation
# ---------------------------------------------------------------------------
#
# In the supabase_scraper.py copy in this repo, purity labels reach the database
# from two different places:
#   - current rates take the label from the rate table's first column ("22 Carat")
#   - the 30-day history table takes it from the <thead> ("22K")
# The day-over-day join in /api/rates keyed on the raw label, so those two never
# matched and every row fell through to change=0.0 — which reproduces exactly the
# symptom T1.2 describes: a permanent "0.00%" on every karat of every page.
#
# Caveat: the scrape that actually feeds production runs outside this repo (Prefect
# Cloud, github.com/midhunz/gold-price-scraper), so that mechanism is a confirmed
# explanation of the symptom rather than a verified reading of the live writer.
# Normalising here is robust either way: it makes the join succeed for whatever
# label variants are already stored, with no backfill and no dependency on which
# writer produced them.

_PURITY_RE = re.compile(r"(\d{1,2})\s*(?:K|Karat|Carat|ct)\b", re.IGNORECASE)


def canonical_purity(purity: Optional[str]) -> str:
    """Normalise any purity label to a canonical '22K' form.

    '22 Carat' / '22K' / '22 karat' / '22 Carat (916 KDM)' -> '22K'

    An unrecognised label is returned stripped and lowercased, so it still joins
    against itself rather than silently colliding with another purity.
    """
    if not purity:
        return ""
    match = _PURITY_RE.search(purity)
    if match:
        return f"{int(match.group(1))}K"
    return purity.strip().lower()


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

# Two price formats are actually stored, and they are not interchangeable:
#
#   GCC    "494.25"                 a plain per-gram figure
#   India  "14,190₹141,900/ 10g"    per-gram, then per-10g, in one string
#
# The per-gram figure comes first in both, so take the first numeric token and
# ignore the rest. The optional leading minus is matched deliberately so that a
# negative value is read as negative and rejected, rather than having the sign
# silently dropped.
_FIRST_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_price(price_str) -> Optional[float]:
    """Parse a stored price string to its per-gram float, or None if unusable.

    Returns None — never 0.0 — so callers can distinguish "no data" from "zero".
    A non-positive price is treated as no data: gold is never free, so a 0 or a
    negative in the feed means the scrape failed (T7.1).

    >>> parse_price("494.25")                # GCC
    494.25
    >>> parse_price("14,190₹141,900/ 10g")   # India composite
    14190.0
    """
    if price_str is None:
        return None
    match = _FIRST_NUMBER.search(str(price_str))
    if not match:
        return None
    try:
        value = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


# ---------------------------------------------------------------------------
# Guardrail thresholds (T7.1)
# ---------------------------------------------------------------------------

# 22K is 916/999 of pure gold, so the theoretical ratio is 0.9169.
#
# SEO_TASKS T7.1 proposes a 0.90-0.93 band. That is too tight for live data and
# would fire on legitimate rates. Measured across all 7 markets in the production
# database on 5 Sep 2026:
#
#   Saudi Arabia 0.9145   India  0.9167   Kuwait 0.9192   Qatar 0.9213
#   UAE          0.9260   Bahrain 0.9320  Oman   0.9374
#
# India sits on the theoretical ratio because it quotes bullion purity directly;
# the GCC quotes carry retail premia that push 22K relatively higher. A 0.93 ceiling
# would flag Bahrain and Oman every single run, and a guardrail that cries wolf on
# healthy data gets muted and then ignored.
#
# 0.89-0.95 clears the observed range with headroom while still catching what this
# check is actually for: the Kerala defect (ratio 1.0103), an inverted pair, or a
# 22K in one currency against a 24K in another (ratio ~0.03).
PURITY_RATIO_BOUNDS = (0.89, 0.95)

# Suppress movement indicators once the feed is more than 2x its refresh cadence
# stale, rather than presenting an old delta as today's (T7.1).
#
# ASSUMPTION, and it needs confirming: the gold rate scrape does not run in this
# repo. main.py's lifespan comment says it runs on Prefect Cloud from
# github.com/midhunz/gold-price-scraper and writes straight to Supabase, so the
# real cadence is defined there and is not discoverable from this codebase. One
# hour is the assumed default because the site's own copy claims hourly updates
# (which T1.4 flags as unverified). Override without a code change once the true
# Prefect schedule is known.
FEED_REFRESH_CADENCE = timedelta(
    minutes=int(os.getenv("FEED_REFRESH_CADENCE_MINUTES", "60"))
)
FEED_STALE_AFTER = FEED_REFRESH_CADENCE * 2

# A state/city 22K rate more than this far from the national 22K rate is not a
# regional premium, it is a bug. Kerala was published 10.2% high.
STATE_TOLERANCE_PCT = 2.0


def feed_age(latest_time: Optional[datetime]) -> Optional[timedelta]:
    """Age of the newest feed row, tolerating naive or tz-aware timestamps.

    supabase_scraper.py writes tz-aware UTC values, but GoldRate.created_at is a
    plain DateTime column, so what comes back may be naive depending on the driver.
    Subtracting one form from the other raises TypeError, which would 500 the whole
    rates endpoint — so normalise to UTC first.
    """
    if latest_time is None:
        return None
    if latest_time.tzinfo is None:
        # Stored values are UTC: the scraper writes datetime.now(timezone.utc).
        latest_time = latest_time.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - latest_time


def is_feed_stale(latest_time: Optional[datetime]) -> bool:
    """True when the feed is more than 2x the stated refresh cadence old."""
    age = feed_age(latest_time)
    return age is not None and age > FEED_STALE_AFTER


def check_purity_ratio(rates_by_region: Dict[str, Dict[str, float]]) -> List[str]:
    """Return human-readable 22K/24K ratio anomalies, logging each at ERROR."""
    anomalies: List[str] = []
    low, high = PURITY_RATIO_BOUNDS
    for region, by_purity in rates_by_region.items():
        p22, p24 = by_purity.get("22K"), by_purity.get("24K")
        if not p22 or not p24:
            continue
        ratio = p22 / p24
        if not low <= ratio <= high:
            message = (
                f"{region}: 22K/24K ratio {ratio:.4f} outside [{low}, {high}] "
                f"(22K={p22}, 24K={p24})"
            )
            logger.error("RATE GUARDRAIL: %s", message)
            anomalies.append(message)
    return anomalies


def state_divergence_pct(state_price: float, national_price: float) -> float:
    """Signed percentage by which a regional rate diverges from the national rate."""
    if not national_price:
        raise ValueError("national_price must be non-zero")
    return (state_price - national_price) / national_price * 100.0


def check_state_divergence(
    national_22k: Optional[float],
    state_22k_by_region: Dict[str, Optional[float]],
    tolerance_pct: float = STATE_TOLERANCE_PCT,
) -> List[str]:
    """Return regions whose 22K rate diverges from national by more than tolerance.

    This is the check that would have caught T1.1: Kerala published ₹15,640/g
    against a national ₹14,190/g, a +10.22% divergence.
    """
    anomalies: List[str] = []
    if not national_22k:
        return anomalies
    for region, price in state_22k_by_region.items():
        if not price:
            continue
        divergence = state_divergence_pct(price, national_22k)
        if abs(divergence) > tolerance_pct:
            message = (
                f"{region}: 22K {price} diverges {divergence:+.2f}% from national "
                f"{national_22k} (tolerance +/-{tolerance_pct}%)"
            )
            logger.error("RATE GUARDRAIL: %s", message)
            anomalies.append(message)
    return anomalies
