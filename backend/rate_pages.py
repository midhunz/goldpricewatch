"""Server-rendered gold rate pages: templates, registry and HTML generation.

Why this module exists
----------------------
The Search Console data for Jan-Sep 2026 says the site ranks and is not clicked:
87 non-brand queries sit at positions 4-10 across 27,510 impressions and return
158 clicks, a 0.57% CTR against a ~3.5% positional norm. The diagnosis is the
snippet - for "gold rate today <city>" the searcher wants one number, and if it
is not in the title or description they take it from a competitor. That is
SEO_TASKS T4.8, and it is the highest-value fix on the site.

It cannot be made on the pages themselves: the Next.js source for those routes is
not in this repository (docs/BLOCKED.md). So the rate pages are rendered here
instead and routed to this backend by Caddy, ahead of the catch-all proxy - the
same precedence trick the Caddyfile already uses for /gold-rates/*.

Rendering server-side is the whole point. The price has to be in the HTML for
Google to build a snippet out of it, and the trend chart is inline SVG rather
than a JS chart so it costs no layout shift.

Kept free of FastAPI and SQLAlchemy imports on purpose, exactly as rate_utils.py
is: the guardrail tests in tests/ run on stdlib unittest with no dependencies
installed (see .github/workflows/ci.yml), so everything worth asserting on lives
in pure functions that take plain dataclasses. The database queries that feed
them live in main.py.

Tasks closed here, per page moved onto the renderer:
  T1.2  no permanent 0.00% - a missing prior close renders as nothing
  T1.3  a real "last updated" timestamp, from the feed fetch time
  T2.1  city pages no longer present the national rate as a distinct local rate
  T3.1  title <= 60 chars      T3.2  description <= 155 chars
  T4.3  per-gram, per-tola, per-sovereign and per-ounce rows
  T4.8  live price and today's date in the title
  T5.1  Dataset structured data
"""

import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

SITE = "https://goldpricewatch.com"
BRAND = "GoldPriceWatch"
OG_IMAGE = f"{SITE}/og-image.png"
GA_MEASUREMENT_ID = "G-ELK0VFT5L7"

TITLE_MAX = 60
DESCRIPTION_MAX = 155

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
#
# Stored prices are per gram. Confirmed three ways: the production Oman page
# renders the stored figure unchanged (OMR 52.80 for 22K on 9 Sep 2026), the
# India rows carry their own per-10g figure alongside the per-gram one
# ("14,240<rupee>142,400/ 10g"), and the cross-market ratios implied by treating
# every stored figure as per-gram line up with published FX.
#
# The gram is not how people buy, though, which is the T4.3 gap: Gulf shops quote
# per tola, Kerala and Tamil Nadu quote per sovereign (pavan). Those queries rank
# and convert at zero today.
GRAMS_PER_TOLA = 11.6638
GRAMS_PER_SOVEREIGN = 8.0
GRAMS_PER_OUNCE = 31.1034768

GULF_UNITS: Tuple[Tuple[str, float], ...] = (
    ("1 gram", 1.0),
    ("8 grams", GRAMS_PER_SOVEREIGN),
    ("1 tola (11.66 g)", GRAMS_PER_TOLA),
    ("1 ounce (31.10 g)", GRAMS_PER_OUNCE),
)

INDIA_UNITS: Tuple[Tuple[str, float], ...] = (
    ("1 gram", 1.0),
    ("8 grams (1 sovereign / pavan)", GRAMS_PER_SOVEREIGN),
    ("10 grams", 10.0),
    ("1 tola (11.66 g)", GRAMS_PER_TOLA),
)

# Purities are rendered in this order where present. The feed carries 14 Carat
# for the UAE only.
PURITY_ORDER = ("24K", "22K", "21K", "18K", "14K")

# The karat a snippet leads with. 22K is what jewellery is sold in across both
# the Gulf and India, and it is what the ranking queries ask for ("gold rate
# today ajman 22k", "sharjah gold rate today 22 carat").
HEADLINE_PURITY = "22K"


@dataclass(frozen=True)
class PageSpec:
    """One rendered page: which market it reads from, and how it presents it."""

    path: str
    region: str          # the gold_rates.region key this page reads
    place: str           # display name - "Muscat", "Oman"
    kind: str            # "country" or "city"
    locale: str          # og:locale, e.g. "en_OM"
    country: str         # display name of the country, for city pages
    blurb: str           # place-specific prose; never place-specific numbers
    units: Tuple[Tuple[str, float], ...] = GULF_UNITS
    parent: Optional[str] = None       # hub path, for city pages
    cities: Sequence[str] = field(default_factory=tuple)  # child paths, for hubs
    keywords: str = ""
    # Local time zone used for the "Updated" stamp and the date token in the
    # title. Both Gulf markets and India are whole- or half-hour offsets with no
    # daylight saving, so a fixed offset is exact rather than an approximation.
    tz_offset_hours: float = 4.0
    tz_label: str = "GST"


@dataclass
class RateSnapshot:
    """Everything one market's page needs from the database.

    `by_purity` holds per-gram floats keyed on canonical purity ("22K"). A purity
    whose price failed the rate_utils guardrails is absent rather than zero.
    `changes` holds the day-over-day delta, or None where there is no prior close
    to compare against - which is what stops T1.2's permanent 0.00%.
    """

    region: str
    currency: str
    by_purity: Dict[str, float]
    changes: Dict[str, Optional[float]]
    updated_at: Optional[datetime]
    stale: bool

    @property
    def has_prices(self) -> bool:
        return bool(self.by_purity)

    @property
    def usable(self) -> bool:
        """True when this page may publish figures and be indexed.

        Ground rule 1 of SEO_TASKS: never invent price data. A stale feed or an
        empty snapshot renders an explicit empty state and noindex, rather than
        carrying yesterday's number forward as today's.
        """
        return self.has_prices and not self.stale


# ---------------------------------------------------------------------------
# Page registry
# ---------------------------------------------------------------------------
#
# Oman leads this list, deliberately. It is the one market the site has won -
# cluster average position 8.3, against 26.7 for the UAE and 59.2 for India -
# and it is where the state of the site was doing the most damage: /gold-rates/salalah.html (9.24), muscat.html (9.09),
# sohar.html (9.08) and nizwa.html (9.02) are among the best-ranking URLs on the
# domain and all four are being deindexed right now by the T1.1 emergency fix,
# which was the correct response to their publishing rupee prices for Omani
# cities but is not a resting place.
#
# The city pages keep their existing .html URLs. Preserving a position-9 ranking
# is the entire point; a new URL restarts from zero.
#
# On city pages and the national rate
# -----------------------------------
# The feed carries one row per country per purity - there is no per-city or
# per-state rate anywhere in it. Gold in Oman is priced nationally, so showing
# the same OMR figure on the Muscat and Salalah pages is correct. Presenting it
# as a distinct *Muscat rate* would not be, and that is precisely the bug that
# put 11 India state pages 10.22% out and got all 15 static pages deindexed.
# So every city page says plainly which rate it is showing, and differentiates
# on content - geography, souqs, making charges - never on invented numbers.

@dataclass(frozen=True)
class Market:
    """A country in the feed, and how its pages present it."""

    region: str          # the gold_rates.region key
    place: str           # display name
    hub_path: str
    locale: str
    tz_offset_hours: float
    tz_label: str
    blurb: str
    units: Tuple[Tuple[str, float], ...] = GULF_UNITS


MARKETS: Tuple[Market, ...] = (
    Market(
        region="Oman",
        place="Oman",
        hub_path="/oman-gold-prices",
        locale="en_OM",
        tz_offset_hours=4.0,
        tz_label="GST",
        blurb=(
            "Gold in Oman is quoted in Omani rials per gram and the rate is set "
            "nationally, so the same figure applies in Muscat, Salalah, Sohar "
            "and every other city. What differs between shops is the making "
            "charge on a finished piece, not the price of the gold itself."
        ),
    ),
    Market(
        region="UAE",
        place="the UAE",
        hub_path="/uae-gold-prices",
        locale="en_AE",
        tz_offset_hours=4.0,
        tz_label="GST",
        blurb=(
            "Gold in the UAE is quoted in dirhams per gram and the rate is set "
            "federally, so Dubai, Abu Dhabi, Sharjah and Ajman all trade at the "
            "same figure. The UAE is the only market here that also quotes 14K."
        ),
    ),
    Market(
        region="Qatar",
        place="Qatar",
        hub_path="/qatar-gold-prices",
        locale="en_QA",
        tz_offset_hours=3.0,
        tz_label="AST",
        blurb=(
            "Gold in Qatar is quoted in Qatari riyals per gram, with Doha's Gold "
            "Souq in Souq Waqif the best-known place to buy."
        ),
    ),
    Market(
        region="Saudi Arabia",
        place="Saudi Arabia",
        hub_path="/saudi-arabia-gold-prices",
        locale="en_SA",
        tz_offset_hours=3.0,
        tz_label="AST",
        blurb=(
            "Gold in Saudi Arabia is quoted in riyals per gram and priced "
            "nationally, from Riyadh and Jeddah to the smaller souqs."
        ),
    ),
    Market(
        region="Bahrain",
        place="Bahrain",
        hub_path="/bahrain-gold-prices",
        locale="en_BH",
        tz_offset_hours=3.0,
        tz_label="AST",
        blurb=(
            "Gold in Bahrain is quoted in Bahraini dinars per gram. The dinar is "
            "one of the highest-valued currencies in the world, so the per-gram "
            "figure looks small next to its neighbours - it is the same metal at "
            "the same world price."
        ),
    ),
    Market(
        region="Kuwait",
        place="Kuwait",
        hub_path="/kuwait-gold-prices",
        locale="en_KW",
        tz_offset_hours=3.0,
        tz_label="AST",
        blurb=(
            "Gold in Kuwait is quoted in Kuwaiti dinars per gram, with the Gold "
            "Souq in Kuwait City the main retail market."
        ),
    ),
    Market(
        region="India",
        place="India",
        hub_path="/india-gold-prices",
        locale="en_IN",
        tz_offset_hours=5.5,
        tz_label="IST",
        units=INDIA_UNITS,
        blurb=(
            "Gold in India is quoted in rupees per gram, and jewellery is usually "
            "priced per sovereign (pavan) of 8 grams or per 10 grams. The rate "
            "below is the national figure; state and city totals differ by local "
            "taxes and making charges rather than by the price of the metal."
        ),
    ),
)

MARKETS_BY_REGION: Dict[str, Market] = {market.region: market for market in MARKETS}


# Cities and states, as (path, display name, blurb). Every one of them reads its
# country's rate: see the note above on why that is correct and how it is said.
#
# The four Oman .html paths and the eleven India state .html paths are kept
# exactly as they are. Those URLs already rank - Salalah at 9.24, Muscat at
# 9.09 - and a new URL would restart from zero.
_CITIES: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "Oman": (
        ("/gold-rates/muscat.html", "Muscat",
         "Muscat is Oman's capital and its largest gold market, with the Mutrah "
         "souq in the old port district the best-known place to buy."),
        ("/gold-rates/salalah.html", "Salalah",
         "Salalah is the capital of Dhofar in Oman's far south, and the main "
         "gold-buying centre outside the Muscat area."),
        ("/gold-rates/sohar.html", "Sohar",
         "Sohar is the principal city of Al Batinah North, on the coast between "
         "Muscat and the UAE border."),
        ("/gold-rates/nizwa.html", "Nizwa",
         "Nizwa sits inland in Ad Dakhiliyah and is known for its historic souq, "
         "long a centre for Omani silver and gold craftsmanship."),
        ("/gold-rates/sur.html", "Sur",
         "Sur is the coastal capital of Ash Sharqiyah South, east of Muscat."),
        ("/gold-rates/ibri.html", "Ibri",
         "Ibri is the main town of Ad Dhahirah, in Oman's north-west interior."),
        ("/gold-rates/barka.html", "Barka",
         "Barka lies in Al Batinah South, on the coast a short drive north-west "
         "of Muscat."),
    ),
    "UAE": (
        ("/dubai-gold-prices", "Dubai",
         "Dubai is the largest gold market in the region, and the Gold Souq in "
         "Deira is its best-known retail centre."),
        ("/abu-dhabi-gold-prices", "Abu Dhabi",
         "Abu Dhabi is the UAE capital, with Madinat Zayed a long-established "
         "gold shopping destination."),
        ("/sharjah-gold-prices", "Sharjah",
         "Sharjah borders Dubai and has its own Central Souq gold trade."),
        ("/ajman-gold-prices", "Ajman",
         "Ajman is the smallest emirate, immediately north of Sharjah."),
    ),
    "India": (
        ("/mumbai-gold-prices", "Mumbai",
         "Mumbai is India's bullion trading centre, with Zaveri Bazaar its "
         "historic jewellery market."),
        ("/bangalore-gold-prices", "Bangalore",
         "Bangalore is the largest gold market in Karnataka."),
        ("/chennai-gold-prices", "Chennai",
         "Chennai is a major South Indian gold market, where jewellery is "
         "commonly priced per sovereign."),
        ("/hyderabad-gold-prices", "Hyderabad",
         "Hyderabad has a long jewellery tradition centred on Charminar."),
        ("/pune-gold-prices", "Pune",
         "Pune is one of Maharashtra's largest gold retail markets."),
        ("/gold-rates/kerala.html", "Kerala",
         "Kerala buys gold by the pavan of 8 grams, and per-pavan pricing is how "
         "rates are usually quoted in the state."),
        ("/gold-rates/tamil-nadu.html", "Tamil Nadu",
         "Tamil Nadu, like neighbouring Kerala, prices jewellery by the sovereign."),
        ("/gold-rates/karnataka.html", "Karnataka",
         "Karnataka's gold trade centres on Bangalore."),
        ("/gold-rates/maharashtra.html", "Maharashtra",
         "Maharashtra contains Mumbai, India's bullion trading hub."),
        ("/gold-rates/delhi.html", "Delhi",
         "Delhi's jewellery trade centres on Karol Bagh and Chandni Chowk."),
        ("/gold-rates/west-bengal.html", "West Bengal",
         "West Bengal's gold trade centres on Kolkata's Bowbazar."),
        ("/gold-rates/gujarat.html", "Gujarat",
         "Gujarat has major jewellery markets in Ahmedabad, Surat and Rajkot."),
        ("/gold-rates/rajasthan.html", "Rajasthan",
         "Rajasthan's jewellery trade centres on Jaipur, long known for "
         "gemstone and gold work."),
        ("/gold-rates/andhra-pradesh.html", "Andhra Pradesh",
         "Andhra Pradesh, like the rest of South India, commonly prices "
         "jewellery per sovereign."),
        ("/gold-rates/punjab.html", "Punjab",
         "Punjab's gold retail centres on Ludhiana and Amritsar."),
        ("/gold-rates/uttar-pradesh.html", "Uttar Pradesh",
         "Uttar Pradesh is India's most populous state, with major gold markets "
         "in Lucknow, Kanpur and Varanasi."),
    ),
}


def _keywords(place: str, country: str) -> str:
    low = place.lower()
    return (
        f"gold rate {low}, {low} gold price today, 22k gold rate {low}, "
        f"24k gold price {low}, gold rate {country.lower()}"
    )


def _build_pages() -> List[PageSpec]:
    pages: List[PageSpec] = []
    for market in MARKETS:
        cities = _CITIES.get(market.region, ())
        pages.append(PageSpec(
            path=market.hub_path,
            region=market.region,
            place=market.place,
            kind="country",
            locale=market.locale,
            country=market.place,
            blurb=market.blurb,
            units=market.units,
            cities=tuple(path for path, _, _ in cities),
            keywords=_keywords(market.place, market.place),
            tz_offset_hours=market.tz_offset_hours,
            tz_label=market.tz_label,
        ))
        for path, name, blurb in cities:
            pages.append(PageSpec(
                path=path,
                region=market.region,
                place=name,
                kind="city",
                locale=market.locale,
                country=market.place,
                blurb=blurb,
                units=market.units,
                parent=market.hub_path,
                keywords=_keywords(name, market.place),
                tz_offset_hours=market.tz_offset_hours,
                tz_label=market.tz_label,
            ))
    return pages


PAGES: Dict[str, PageSpec] = {spec.path: spec for spec in _build_pages()}


def get_page(path: str) -> Optional[PageSpec]:
    """Look up a page spec by request path, tolerating a trailing slash.

    The site canonicalises to the no-slash form (T0.4), and Caddy forwards the
    path as requested, so accept both here rather than 404ing a slashed URL.
    """
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return PAGES.get(path)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def local_now(spec: PageSpec, reference: Optional[datetime] = None) -> datetime:
    """`reference` (assumed UTC) expressed in the page's local time zone."""
    from datetime import timedelta, timezone

    moment = reference or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone(timedelta(hours=spec.tz_offset_hours)))


def format_money(value: float, currency: str) -> str:
    """Format a price the way its market quotes it.

    The Gulf currencies are quoted to two decimals on a two-figure per-gram
    price; the rupee is quoted in whole units with thousands separators. Showing
    "14240.00" to an Indian reader looks like a machine wrote it.
    """
    if currency == "INR":
        return f"{value:,.0f}"
    if value >= 1000:
        return f"{value:,.2f}"
    return f"{value:.2f}"


def format_date(moment: datetime) -> str:
    """'9 Sep 2026' - no leading zero, which %-d cannot do portably."""
    return f"{moment.day} {moment:%b %Y}"


def format_short_date(moment: datetime) -> str:
    """'9 Sep' - the compact form used inside the 60-character title."""
    return f"{moment.day} {moment:%b}"


def format_stamp(moment: datetime, tz_label: str) -> str:
    """'9 Sep 2026, 14:20 GST' - the visible freshness signal required by T1.3."""
    return f"{format_date(moment)}, {moment:%H:%M} {tz_label}"


# ---------------------------------------------------------------------------
# Title and description (T3.1, T3.2, T4.8)
# ---------------------------------------------------------------------------
#
# The report's finding in one line: a title reading "Gold Rate in Muscat |
# GoldPriceWatch" loses to "Gold Rate in Muscat Today - 22K OMR 53.25 (9 Sep)",
# because the competing snippet answers the query and ours only promises to.
#
# Both builders are fallback chains rather than a single f-string with a hard
# truncation, because a title cut mid-number is worse than a shorter title that
# ends cleanly. Each candidate is tried in order and the first one inside the
# cap wins; the last candidate in every chain is short enough to always fit.

def build_title(spec: PageSpec, snapshot: RateSnapshot, now: datetime) -> str:
    """Page title, <= 60 characters, carrying the live rate and today's date."""
    place = spec.place
    if not snapshot.usable:
        # No verified price to advertise, so make no claim about one.
        candidates = [
            f"Gold Rate in {place} Today - 22K, 24K & 18K",
            f"{place} Gold Rate Today - 22K, 24K & 18K",
            f"{place} Gold Rate Today",
        ]
        return _first_within(candidates, TITLE_MAX)

    price = snapshot.by_purity.get(HEADLINE_PURITY)
    if price is None:
        return _first_within([f"{place} Gold Rate Today - Live Rates"], TITLE_MAX)

    money = f"{snapshot.currency} {format_money(price, snapshot.currency)}"
    day = format_short_date(now)
    candidates = [
        f"Gold Rate in {place} Today - 22K {money}/g · {day}",
        f"{place} Gold Rate Today - 22K {money}/g · {day}",
        f"{place} Gold Rate Today - 22K {money}/g",
        f"{place} Gold Rate Today - {money}/g",
        f"{place} Gold Rate Today",
    ]
    return _first_within(candidates, TITLE_MAX)


def build_description(spec: PageSpec, snapshot: RateSnapshot, now: datetime) -> str:
    """Meta description, <= 155 characters, leading with the live figures."""
    place = spec.place
    if not snapshot.usable:
        candidates = [
            (
                f"Live 22K, 24K, 21K and 18K gold rates for {place}, per gram, "
                f"tola and 8 grams, updated through the day."
            ),
            f"Live gold rates for {place}, per gram and per tola.",
        ]
        return _first_within(candidates, DESCRIPTION_MAX)

    cur = snapshot.currency
    p22 = snapshot.by_purity.get("22K")
    p24 = snapshot.by_purity.get("24K")
    day = format_date(now)

    candidates = []
    if p22 is not None and p24 is not None:
        candidates.append(
            f"22K gold rate in {place} today is {cur} "
            f"{format_money(p22, cur)}/g and 24K is {cur} "
            f"{format_money(p24, cur)}/g. Updated {day}. Per gram, tola and 8 g."
        )
        candidates.append(
            f"22K gold rate in {place} today: {cur} {format_money(p22, cur)}/g. "
            f"24K: {cur} {format_money(p24, cur)}/g. Updated {day}."
        )
    if p22 is not None:
        candidates.append(
            f"22K gold rate in {place} today is {cur} "
            f"{format_money(p22, cur)} per gram. Updated {day}."
        )
    candidates.append(f"Live gold rates for {place}, updated {day}.")
    return _first_within(candidates, DESCRIPTION_MAX)


def _first_within(candidates: Sequence[str], limit: int) -> str:
    for candidate in candidates:
        if len(candidate) <= limit:
            return candidate
    # Every candidate overflowed. Trim the shortest at a word boundary rather
    # than mid-token, so the result still reads as a phrase.
    shortest = min(candidates, key=len)
    trimmed = shortest[:limit].rsplit(" ", 1)[0]
    return trimmed or shortest[:limit]


# ---------------------------------------------------------------------------
# Trend chart (inline SVG)
# ---------------------------------------------------------------------------
#
# Rendered as SVG in the initial HTML rather than drawn by a chart library after
# hydration. Two reasons beyond the obvious one that a crawler can read it: it
# reserves its own space so it cannot shift the layout (the report flags reflow
# on desktop, and T6.1 flags the ticker for the same reason), and it costs no
# JavaScript on a page whose whole job is to answer a question in one screen.

_SVG_W = 720
_SVG_H = 220
_PAD_L = 8
_PAD_R = 8
_PAD_T = 16
_PAD_B = 26


def trend_svg(points: Sequence[Tuple[datetime, float]], currency: str) -> str:
    """An inline SVG line chart, or "" when there is not enough data to draw one.

    Returning "" rather than an empty axis matters: a chart frame with no line
    reads as a broken feature, where showing nothing reads as a page that simply
    does not have that section.
    """
    if len(points) < 2:
        return ""

    values = [value for _, value in points]
    lowest, highest = min(values), max(values)
    span = highest - lowest
    if span <= 0:
        # A dead-flat series still tells a true story; give it a band to sit in
        # so the line lands mid-chart instead of dividing by zero.
        span = max(highest * 0.01, 0.01)
        lowest, highest = highest - span / 2, highest + span / 2

    plot_w = _SVG_W - _PAD_L - _PAD_R
    plot_h = _SVG_H - _PAD_T - _PAD_B
    last = len(points) - 1

    coords = []
    for index, (_, value) in enumerate(points):
        x = _PAD_L + (index / last) * plot_w
        y = _PAD_T + (1 - (value - lowest) / (highest - lowest)) * plot_h
        coords.append((x, y))

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = (
        f"{coords[0][0]:.1f},{_PAD_T + plot_h:.1f} "
        + line
        + f" {coords[-1][0]:.1f},{_PAD_T + plot_h:.1f}"
    )

    first_date, last_date = points[0][0], points[-1][0]
    high_text = f"{currency} {format_money(highest, currency)}"
    low_text = f"{currency} {format_money(lowest, currency)}"
    label = (
        f"22K gold rate from {format_date(first_date)} to {format_date(last_date)}: "
        f"low {low_text}, high {high_text}"
    )

    return f"""<svg class="trend" viewBox="0 0 {_SVG_W} {_SVG_H}" role="img"
     aria-label="{html.escape(label, quote=True)}" preserveAspectRatio="none">
  <polygon class="trend-area" points="{area}"/>
  <polyline class="trend-line" points="{line}"/>
  <circle class="trend-dot" cx="{coords[-1][0]:.1f}" cy="{coords[-1][1]:.1f}" r="4"/>
</svg>
<div class="trend-scale">
  <span>{html.escape(format_date(first_date))}</span>
  <span>Low {html.escape(low_text)} · High {html.escape(high_text)}</span>
  <span>{html.escape(format_date(last_date))}</span>
</div>"""


def trend_summary(
    points: Sequence[Tuple[datetime, float]], currency: str, place: str, days: int
) -> str:
    """One sentence stating what the chart shows, in text a crawler can read."""
    if len(points) < 2:
        return ""
    opening, closing = points[0][1], points[-1][1]
    delta = closing - opening
    pct = (delta / opening * 100) if opening else 0.0
    if abs(pct) < 0.05:
        movement = "is effectively unchanged"
    else:
        direction = "risen" if delta > 0 else "fallen"
        movement = (
            f"has {direction} {format_money(abs(delta), currency)} "
            f"{currency} ({abs(pct):.1f}%)"
        )
    return (
        f"Over the last {days} days the 22K gold rate in {place} {movement}, "
        f"from {currency} {format_money(opening, currency)} to "
        f"{currency} {format_money(closing, currency)} per gram."
    )


def downsample(
    points: Sequence[Tuple[datetime, float]], target: int = 90
) -> List[Tuple[datetime, float]]:
    """Thin a dense series to about `target` points, always keeping the last one.

    The feed writes hourly, so a 365-day series is ~8,700 points - far more than
    a 720px-wide chart can show and a needless few hundred KB of path data.
    """
    if len(points) <= target:
        return list(points)
    step = len(points) / target
    thinned = [points[int(index * step)] for index in range(target)]
    if thinned[-1] != points[-1]:
        thinned.append(points[-1])
    return thinned


# ---------------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------------
#
# The nav and footer link sets are copied from the live site so navigation is
# continuous with the Next app either side of these pages. The styling is not:
# production's CSS lives at a content-hashed /_next/static/chunks/*.css path
# that changes on every frontend build, and pointing at it from here would mean
# these pages lose their stylesheet the next time the frontend is deployed. The
# whole reason this renderer exists is to not depend on that build, so the CSS
# is inline and self-contained.

STYLES = """
:root{
  --bg:#0f1115; --card:#1a1d23; --line:#272b33;
  --text:#f8fafc; --muted:#94a3b8;
  --gold:#E2BC3E; --gold-dim:#B8860B;
  --up:#4ade80; --down:#f87171;
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--bg); color:var(--text);
  font-family:Outfit,-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;
  line-height:1.6; -webkit-font-smoothing:antialiased;
  font-variant-numeric:tabular-nums;
}
a{color:var(--gold);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px}
header.site{border-bottom:1px solid var(--line)}
footer.site{border-top:1px solid var(--line);margin-top:64px}
header.site .wrap{display:flex;align-items:center;gap:22px;flex-wrap:wrap;padding-top:16px;padding-bottom:16px}
.brand{font-weight:700;font-size:1.15rem;color:var(--text)}
.brand span{color:var(--gold)}
header.site nav ul{display:flex;gap:18px;list-style:none;flex-wrap:wrap;font-size:.92rem}
header.site nav a{color:var(--muted)}
h1{font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.15;margin:34px 0 8px;font-weight:700}
h2{font-size:1.32rem;margin:42px 0 14px;font-weight:600}
h3{font-size:1.05rem;margin:22px 0 8px;font-weight:600}
p{margin:0 0 14px;color:var(--muted);max-width:70ch}
.lede{color:var(--text);font-size:1.05rem}
.stamp{display:inline-block;font-size:.86rem;color:var(--muted);
  border:1px solid var(--line);border-radius:999px;padding:5px 14px;margin-bottom:8px}
.stamp b{color:var(--gold);font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin:22px 0 8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.card .k{font-size:.82rem;color:var(--muted);letter-spacing:.04em;text-transform:uppercase}
.card .v{font-size:1.75rem;font-weight:700;margin-top:6px;line-height:1.1}
.card .u{font-size:.8rem;color:var(--muted)}
.card .d{font-size:.85rem;margin-top:6px}
.d.up{color:var(--up)} .d.down{color:var(--down)} .d.flat{color:var(--muted)}
.scroll{overflow-x:auto;margin:16px 0 8px}
table{border-collapse:collapse;width:100%;min-width:420px;font-size:.95rem}
caption{caption-side:bottom;text-align:left;color:var(--muted);font-size:.82rem;padding-top:10px}
th,td{text-align:right;padding:11px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}
thead th{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em;font-weight:600}
tbody tr:hover{background:#1e222a}
.trend{width:100%;height:220px;display:block;margin-top:8px}
.trend-area{fill:rgba(226,188,62,.12);stroke:none}
.trend-line{fill:none;stroke:var(--gold);stroke-width:2;vector-effect:non-scaling-stroke}
.trend-dot{fill:var(--gold)}
.trend-scale{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
  font-size:.8rem;color:var(--muted);margin-top:6px}
.notice{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--gold);
  border-radius:8px;padding:16px 18px;margin:22px 0}
.notice p:last-child{margin-bottom:0}
.chips{display:flex;flex-wrap:wrap;gap:10px;list-style:none;margin:14px 0 0}
.chips a{display:inline-block;background:var(--card);border:1px solid var(--line);
  border-radius:999px;padding:7px 15px;font-size:.9rem;color:var(--text)}
.chips a:hover{border-color:var(--gold);text-decoration:none}
.next{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin-top:16px}
.next a{display:block;background:var(--card);border:1px solid var(--line);
  border-radius:12px;padding:16px 18px;color:var(--text)}
.next a:hover{border-color:var(--gold);text-decoration:none}
.next b{display:block;color:var(--gold);margin-bottom:4px}
.next span{font-size:.88rem;color:var(--muted)}
footer.site .cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:26px;padding:34px 0 10px}
footer.site h3{font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;
  color:var(--muted);margin:0 0 12px}
footer.site ul{list-style:none;font-size:.9rem}
footer.site li{margin-bottom:8px}
footer.site a{color:var(--muted)}
.legal{border-top:1px solid var(--line);padding:18px 0 34px;font-size:.82rem;color:var(--muted)}
@media (max-width:620px){
  header.site nav ul{gap:13px;font-size:.86rem}
  .card .v{font-size:1.5rem}
}
"""

NAV_LINKS: Tuple[Tuple[str, str], ...] = (
    ("/", "Dashboard"),
    ("/trends", "Trends"),
    ("/gold-prediction", "Price Forecast"),
    ("/geopolitical-gold-impact", "Geo Impact"),
    ("/calculator", "Calculator"),
    ("/gold-news-today", "News"),
)

FOOTER_GROUPS: Tuple[Tuple[str, Tuple[Tuple[str, str], ...]], ...] = (
    ("Tools", (
        ("/", "Live Gold Rates"),
        ("/trends", "Price Trends & Charts"),
        ("/calculator", "Gold Calculator"),
        ("/gold-news-today", "Gold News"),
    )),
    ("Gold prices by country", (
        ("/india-gold-prices", "Gold Rate in India"),
        ("/uae-gold-prices", "Gold Rate in UAE"),
        ("/saudi-arabia-gold-prices", "Gold Rate in Saudi Arabia"),
        ("/qatar-gold-prices", "Gold Rate in Qatar"),
        ("/kuwait-gold-prices", "Gold Rate in Kuwait"),
    )),
    ("Gulf gold prices", (
        ("/oman-gold-prices", "Oman Gold Rate"),
        ("/bahrain-gold-prices", "Bahrain Gold Rate"),
        ("/dubai-gold-prices", "Dubai Gold Rate"),
        ("/abu-dhabi-gold-prices", "Abu Dhabi Gold Rate"),
        ("/sharjah-gold-prices", "Sharjah Gold Rate"),
        ("/ajman-gold-prices", "Ajman Gold Rate"),
    )),
    ("Company", (
        ("/about", "About Us"),
        ("/contact", "Contact Us"),
        ("/privacy", "Privacy Policy"),
        ("/terms", "Terms of Service"),
    )),
)


def _nav() -> str:
    items = "".join(
        f'<li><a href="{href}">{html.escape(label)}</a></li>'
        for href, label in NAV_LINKS
    )
    return f"""<header class="site">
  <div class="wrap">
    <a class="brand" href="/">GoldPrice<span>Watch</span></a>
    <nav aria-label="Main"><ul>{items}</ul></nav>
  </div>
</header>"""


def _footer() -> str:
    cols = []
    for heading, links in FOOTER_GROUPS:
        items = "".join(
            f'<li><a href="{href}">{html.escape(label)}</a></li>' for href, label in links
        )
        cols.append(
            f'<nav aria-label="{html.escape(heading, quote=True)}">'
            f"<h3>{html.escape(heading)}</h3><ul>{items}</ul></nav>"
        )
    return f"""<footer class="site">
  <div class="wrap">
    <div class="cols">{"".join(cols)}</div>
    <div class="legal">
      &copy; 2026 {BRAND}. Gold rates are indicative, published per gram in the
      local currency, and sourced from public market data. Always confirm the
      price with your jeweller before buying.
    </div>
  </div>
</footer>"""


# ---------------------------------------------------------------------------
# Page sections
# ---------------------------------------------------------------------------

@dataclass
class RenderedPage:
    """A rendered page and whether it may be indexed.

    `indexable` is False whenever the page could not publish verified figures, so
    the caller emits noindex. Deciding it here keeps the rule in one place: a
    page that shows an empty state must never also invite Google to index it.
    """

    html: str
    indexable: bool


def _ordered_purities(snapshot: RateSnapshot) -> List[str]:
    known = [p for p in PURITY_ORDER if p in snapshot.by_purity]
    extra = sorted(p for p in snapshot.by_purity if p not in PURITY_ORDER)
    return known + extra


def _change_markup(price: float, change: Optional[float], currency: str) -> str:
    """Day-over-day movement, or nothing at all when there is no prior close.

    T1.2: the site currently prints a permanent "0.00%" on every karat of every
    page, because the day-over-day join never matched. A delta that cannot be
    computed is rendered as absence, not as zero - a zero is a claim that the
    price did not move, which is a different and false statement.
    """
    if change is None:
        return '<div class="d flat">No prior close to compare</div>'
    pct = (change / (price - change) * 100) if price != change else 0.0
    if abs(change) < 0.005:
        return '<div class="d flat">Unchanged vs yesterday</div>'
    direction = "up" if change > 0 else "down"
    arrow = "▲" if change > 0 else "▼"
    return (
        f'<div class="d {direction}">{arrow} {format_money(abs(change), currency)} '
        f"{html.escape(currency)} ({abs(pct):.2f}%) vs yesterday</div>"
    )


def _rate_cards(snapshot: RateSnapshot) -> str:
    cards = []
    for purity in _ordered_purities(snapshot):
        price = snapshot.by_purity[purity]
        cards.append(
            '<div class="card">'
            f'<div class="k">{html.escape(purity)} gold</div>'
            f'<div class="v">{html.escape(snapshot.currency)} '
            f"{format_money(price, snapshot.currency)}</div>"
            '<div class="u">per gram</div>'
            f"{_change_markup(price, snapshot.changes.get(purity), snapshot.currency)}"
            "</div>"
        )
    return f'<div class="cards">{"".join(cards)}</div>'


def _units_table(spec: PageSpec, snapshot: RateSnapshot) -> str:
    """Per-unit prices - the T4.3 gap, and report finding 5.

    225 of the site's top 1,000 queries specify a purity or a unit and together
    they returned 15 clicks from 12,023 impressions. They are also the highest
    intent queries in the set: someone searching "gold rate today ajman 22k" is
    standing in a shop. Every figure here is the per-gram rate multiplied out, so
    nothing is invented.
    """
    purities = [p for p in _ordered_purities(snapshot) if p in ("24K", "22K", "21K", "18K")]
    if not purities:
        return ""
    head = "".join(f"<th>{html.escape(p)}</th>" for p in purities)
    rows = []
    for label, grams in spec.units:
        cells = "".join(
            f"<td>{format_money(snapshot.by_purity[p] * grams, snapshot.currency)}</td>"
            for p in purities
        )
        rows.append(f"<tr><td>{html.escape(label)}</td>{cells}</tr>")
    return f"""<div class="scroll">
  <table>
    <thead><tr><th>Quantity</th>{head}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
    <caption>All figures in {html.escape(snapshot.currency)}, calculated from the
    per-gram rate above. Making charges and any local taxes are additional.</caption>
  </table>
</div>"""


def _city_table(spec: PageSpec, snapshot: RateSnapshot) -> str:
    """The city breakdown on a country hub.

    Every row carries the same figure, because the feed holds one national rate
    and gold is priced nationally in this market. That is stated in the caption
    rather than hidden: eleven India state pages once carried an identical
    fabricated number presented as eleven local rates, which is what got all 15
    static pages deindexed (T1.1). The honest version of the same table is still
    useful - it is how someone searching for their own city finds their page.
    """
    if not spec.cities or not snapshot.usable:
        return ""
    p22 = snapshot.by_purity.get("22K")
    p24 = snapshot.by_purity.get("24K")
    if p22 is None and p24 is None:
        return ""
    rows = []
    for path in spec.cities:
        city = PAGES.get(path)
        if city is None:
            continue
        cells = ""
        if p22 is not None:
            cells += f"<td>{format_money(p22, snapshot.currency)}</td>"
        if p24 is not None:
            cells += f"<td>{format_money(p24, snapshot.currency)}</td>"
        rows.append(
            f'<tr><td><a href="{path}">Gold rate in {html.escape(city.place)}</a></td>'
            f"{cells}</tr>"
        )
    head = "<th>City</th>"
    if p22 is not None:
        head += "<th>22K per gram</th>"
    if p24 is not None:
        head += "<th>24K per gram</th>"
    return f"""<div class="scroll">
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
    <caption>Figures in {html.escape(snapshot.currency)} per gram. The gold rate in
    {html.escape(spec.country)} is set nationally, so it is the same in every city
    listed - what varies between shops is the making charge, not the metal.</caption>
  </table>
</div>"""


def _city_switcher(spec: PageSpec) -> str:
    """Sibling-city links on every page in the cluster.

    Report finding 7: 1.61 pages per session, which means internal linking is
    doing almost no work. The four Oman city pages were reachable only from the
    country page and not from each other.
    """
    if spec.kind == "city" and spec.parent:
        hub = PAGES.get(spec.parent)
        siblings = hub.cities if hub else ()
    else:
        siblings = spec.cities
    links = []
    for path in siblings:
        page = PAGES.get(path)
        if page is None or path == spec.path:
            continue
        links.append(f'<li><a href="{path}">{html.escape(page.place)}</a></li>')
    if not links:
        return ""
    if spec.parent:
        hub = PAGES.get(spec.parent)
        if hub is not None:
            links.insert(
                0, f'<li><a href="{hub.path}">All {html.escape(hub.place)}</a></li>'
            )
    return f"""<h2>Gold rates in other {html.escape(spec.country)} cities</h2>
<ul class="chips">{"".join(links)}</ul>"""


def _next_steps(spec: PageSpec) -> str:
    """Links to the two pages a rate-checker plausibly wants next.

    /gold-prediction is the site's best-performing content by CTR (1.17%, triple
    the site average) and /calculator is the natural second action after reading
    a rate. Neither was reachable from a city page.
    """
    return f"""<h2>Next</h2>
<div class="next">
  <a href="/gold-prediction"><b>Where is gold heading?</b>
    <span>Our 7-day forecast for the gold price, updated daily.</span></a>
  <a href="/calculator"><b>Gold calculator</b>
    <span>Price a piece by weight and karat, including making charges.</span></a>
  <a href="/trends"><b>Historical charts</b>
    <span>Compare {html.escape(spec.country)} against other markets over time.</span></a>
</div>"""


def _structured_data(
    spec: PageSpec, snapshot: RateSnapshot, canonical: str, now: datetime
) -> str:
    """Dataset (+ BreadcrumbList on city pages) - T5.1.

    Dataset, not Product/Offer: this is a published measurement, not something
    the site sells. Emitted only when there are verified figures behind it, for
    the same reason the FAQPage markup already on the site is a liability - the
    existing FAQPage blocks sit on the three pages whose answers do not render.
    """
    blocks: List[Dict] = []
    if snapshot.usable:
        measured = [
            {
                "@type": "PropertyValue",
                "name": f"{purity} gold rate",
                "value": round(snapshot.by_purity[purity], 4),
                "unitText": f"{snapshot.currency} per gram",
            }
            for purity in _ordered_purities(snapshot)
        ]
        blocks.append({
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": f"Gold rate in {spec.place}",
            "description": (
                f"Live 24K, 22K, 21K and 18K gold rates for {spec.place}, "
                f"quoted in {snapshot.currency} per gram."
            ),
            "url": canonical,
            "isAccessibleForFree": True,
            "dateModified": (
                snapshot.updated_at.isoformat() if snapshot.updated_at else now.isoformat()
            ),
            "creator": {"@type": "Organization", "name": BRAND, "url": SITE},
            "variableMeasured": measured,
        })
    if spec.kind == "city" and spec.parent and spec.parent in PAGES:
        hub = PAGES[spec.parent]
        blocks.append({
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
                {
                    "@type": "ListItem",
                    "position": 2,
                    "name": f"Gold rate in {hub.place}",
                    "item": f"{SITE}{hub.path}",
                },
                {
                    "@type": "ListItem",
                    "position": 3,
                    "name": f"Gold rate in {spec.place}",
                    "item": canonical,
                },
            ],
        })
    return "".join(
        '<script type="application/ld+json">'
        + json.dumps(block, ensure_ascii=False, separators=(",", ":"))
        + "</script>"
        for block in blocks
    )


# ---------------------------------------------------------------------------
# Historical price tables
# ---------------------------------------------------------------------------
#
# The chart shows the shape; these show the numbers. Both are wanted, and the
# table is the part that ranks: "gold rate last 10 days", "gold rate in kerala
# last 30 days" and their variants are a real slice of this query space, and
# competitors answer them with exactly this - a dated table a crawler can read.
#
# Two spans, because they answer different questions. A week is what someone
# deciding whether to buy today looks at. A month is what someone deciding
# whether this is a good time to buy looks at, and it is summarised by week
# rather than listed day by day so it stays scannable next to the daily table.

WEEK_DAYS = 7
MONTH_DAYS = 30


def daily_closes(
    points: Sequence[Tuple[datetime, float]]
) -> List[Tuple[datetime, float]]:
    """Collapse an hourly series to one reading per day - the day's last.

    The feed writes hourly, so a month is ~720 rows. The last reading of each
    day is the day's closing rate, which is what a dated table should show;
    averaging the day's readings would publish a number that was never quoted.
    """
    by_day: Dict[str, Tuple[datetime, float]] = {}
    for moment, price in points:
        key = moment.strftime("%Y-%m-%d")
        if key not in by_day or moment >= by_day[key][0]:
            by_day[key] = (moment, price)
    return [by_day[key] for key in sorted(by_day)]


def _delta_cell(current: float, previous: Optional[float], currency: str) -> str:
    """A day-over-day change cell, empty where there is nothing to compare to.

    Same rule as the rate cards: no prior reading renders as a dash, never as
    0.00, because a zero asserts the price held steady (T1.2).
    """
    if previous is None:
        return '<td class="flat">—</td>'
    change = current - previous
    if abs(change) < 0.005:
        return '<td class="flat">no change</td>'
    pct = (change / previous * 100) if previous else 0.0
    cls = "up" if change > 0 else "down"
    sign = "+" if change > 0 else "−"
    return (
        f'<td class="{cls}">{sign}{format_money(abs(change), currency)} '
        f"({abs(pct):.2f}%)</td>"
    )


def week_table(
    spec: PageSpec,
    snapshot: RateSnapshot,
    history: Dict[str, Sequence[Tuple[datetime, float]]],
) -> str:
    """Daily closing rates for the last 7 days, per karat, with movement."""
    purities = [p for p in ("22K", "24K") if history.get(p)]
    if not purities:
        return ""

    series = {p: daily_closes(history[p])[-WEEK_DAYS:] for p in purities}
    days = sorted({moment.strftime("%Y-%m-%d") for p in purities for moment, _ in series[p]})
    if len(days) < 2:
        return ""

    lookup = {
        p: {moment.strftime("%Y-%m-%d"): (moment, price) for moment, price in series[p]}
        for p in purities
    }

    head = "".join(f"<th>{html.escape(p)} per gram</th>" for p in purities)
    lead = purities[0]
    rows = []
    for index, day in enumerate(days):
        cells = ""
        for purity in purities:
            entry = lookup[purity].get(day)
            cells += (
                f"<td>{format_money(entry[1], snapshot.currency)}</td>"
                if entry else "<td>—</td>"
            )
        current = lookup[lead].get(day)
        previous = lookup[lead].get(days[index - 1]) if index else None
        delta = (
            _delta_cell(current[1], previous[1] if previous else None, snapshot.currency)
            if current else '<td class="flat">—</td>'
        )
        label = datetime.strptime(day, "%Y-%m-%d")
        rows.append(
            f"<tr><td>{html.escape(format_date(label))}</td>{cells}{delta}</tr>"
        )

    return f"""<h3>Last {WEEK_DAYS} days</h3>
<div class="scroll">
  <table>
    <thead><tr><th>Date</th>{head}<th>{html.escape(lead)} change</th></tr></thead>
    <tbody>{"".join(reversed(rows))}</tbody>
    <caption>Closing rate for each day in {html.escape(snapshot.currency)} per gram.
    A day with no reading is shown as a dash rather than filled in.</caption>
  </table>
</div>"""


def month_table(
    spec: PageSpec,
    snapshot: RateSnapshot,
    history: Dict[str, Sequence[Tuple[datetime, float]]],
) -> str:
    """Weekly high, low and close for the last 30 days.

    By week rather than by day: 30 more rows directly under a 7-row daily table
    is a wall, and the question a month answers is about the trend, not about
    any one day. High and low are real readings from the feed, not derived.
    """
    points = daily_closes(history.get("22K") or [])[-MONTH_DAYS:]
    if len(points) < WEEK_DAYS + 1:
        return ""

    # Bucket backwards from the newest day, so the current week is a full week
    # and any short bucket is the oldest one. Chunking forwards leaves a two-day
    # stub at the top of the table, next to six full weeks.
    buckets: List[List[Tuple[datetime, float]]] = []
    end = len(points)
    while end > 0:
        start = max(0, end - WEEK_DAYS)
        buckets.append(points[start:end])
        end = start

    rows = []
    for chunk in buckets:
        prices = [price for _, price in chunk]
        rows.append(
            "<tr>"
            f"<td>{html.escape(format_date(chunk[0][0]))} – "
            f"{html.escape(format_date(chunk[-1][0]))}</td>"
            f"<td>{format_money(min(prices), snapshot.currency)}</td>"
            f"<td>{format_money(max(prices), snapshot.currency)}</td>"
            f"<td>{format_money(chunk[-1][1], snapshot.currency)}</td>"
            "</tr>"
        )

    all_prices = [price for _, price in points]
    return f"""<h3>Last {MONTH_DAYS} days</h3>
<div class="scroll">
  <table>
    <thead><tr><th>Week</th><th>Low</th><th>High</th><th>Closing rate</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
    <caption>22K gold in {html.escape(snapshot.currency)} per gram. Over the whole
    period the rate ranged from {format_money(min(all_prices), snapshot.currency)}
    to {format_money(max(all_prices), snapshot.currency)}.</caption>
  </table>
</div>"""


def history_tables(
    spec: PageSpec,
    snapshot: RateSnapshot,
    history: Dict[str, Sequence[Tuple[datetime, float]]],
) -> str:
    week = week_table(spec, snapshot, history)
    month = month_table(spec, snapshot, history)
    if not week and not month:
        return ""
    return (
        f"<h2>Gold rate history in {html.escape(spec.place)}</h2>"
        f"{week}{month}"
    )

# ---------------------------------------------------------------------------
# Whole page
# ---------------------------------------------------------------------------

TREND_DAYS = 30


def render_page(
    spec: PageSpec,
    snapshot: RateSnapshot,
    history: Optional[Dict[str, Sequence[Tuple[datetime, float]]]] = None,
    now: Optional[datetime] = None,
) -> RenderedPage:
    """Render one rate page.

    Pure: everything it needs arrives in the arguments, so the guardrail tests
    can render every page in the registry without a database.
    """
    local = local_now(spec, now)
    canonical = f"{SITE}{spec.path}"
    title = build_title(spec, snapshot, local)
    description = build_description(spec, snapshot, local)
    indexable = snapshot.usable

    if snapshot.usable:
        stamp_time = local_now(spec, snapshot.updated_at) if snapshot.updated_at else local
        stamp = (
            f'<p class="stamp">Updated: <b>'
            f"{html.escape(format_stamp(stamp_time, spec.tz_label))}</b></p>"
        )
        rates_block = _rate_cards(snapshot)
        units_block = (
            f"<h2>Gold rate in {html.escape(spec.place)} by weight</h2>"
            + _units_table(spec, snapshot)
        )
    else:
        # No verified figures. Say so, publish nothing, and do not ask to be
        # indexed - ground rule 1 of SEO_TASKS.
        stamp = ""
        rates_block = """<div class="notice">
  <h2 style="margin-top:0">Today's rate is not available</h2>
  <p>The rate feed has not reported recently enough for us to publish a figure we
  can stand behind, so we are showing none rather than yesterday's price as if it
  were today's. Please check back shortly.</p>
</div>"""
        units_block = ""

    history = history or {}
    series = downsample(list(history.get("22K") or []))
    if series and snapshot.usable:
        summary = trend_summary(series, snapshot.currency, spec.place, TREND_DAYS)
        trend_block = (
            f"<h2>{TREND_DAYS}-day trend</h2>"
            + (f"<p>{html.escape(summary)}</p>" if summary else "")
            + trend_svg(series, snapshot.currency)
        )
    else:
        trend_block = ""

    # The chart shows the shape, the tables show the numbers. Only published
    # when there is a live rate to head them, so a page in its empty state does
    # not present a history it is not also willing to price today.
    tables_block = history_tables(spec, snapshot, history) if snapshot.usable else ""

    city_block = ""
    if spec.cities and snapshot.usable:
        city_block = (
            f"<h2>Gold rate by city in {html.escape(spec.country)}</h2>"
            + _city_table(spec, snapshot)
        )

    if spec.kind == "city":
        heading = f"Gold Rate in {spec.place} Today"
        context = f"""<h2>How the {html.escape(spec.place)} rate is set</h2>
<p>{html.escape(spec.blurb)}</p>
<p>The figures above are the {html.escape(spec.country)} national gold rate, which
is what jewellers in {html.escape(spec.place)} price against. There is no separate
{html.escape(spec.place)} rate for the metal itself - two shops in the same street
will quote different totals for the same chain because their making charges
differ, not because their gold costs a different amount.</p>"""
    else:
        heading = f"Gold Rate in {spec.place} Today"
        context = f"""<h2>How the {html.escape(spec.country)} rate is set</h2>
<p>{html.escape(spec.blurb)}</p>"""

    robots = "index, follow" if indexable else "noindex, follow"
    structured = _structured_data(spec, snapshot, canonical, local)

    body = f"""{_nav()}
<main class="wrap">
  <h1>{html.escape(heading)}</h1>
  {stamp}
  {rates_block}
  {units_block}
  {trend_block}
  {tables_block}
  {city_block}
  {context}
  {_city_switcher(spec)}
  {_next_steps(spec)}
</main>
{_footer()}
{structured}"""

    return RenderedPage(
        html=f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<meta name="keywords" content="{html.escape(spec.keywords, quote=True)}">
<meta name="robots" content="{robots}">
<meta name="googlebot" content="{robots}, max-image-preview:large, max-snippet:-1">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{BRAND}">
<meta property="og:locale" content="{spec.locale}">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{OG_IMAGE}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title, quote=True)}">
<meta name="twitter:description" content="{html.escape(description, quote=True)}">
<meta name="twitter:image" content="{OG_IMAGE}">
<link rel="icon" href="/favicon.ico">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
<script>
window.dataLayer = window.dataLayer || [];
function gtag(){{dataLayer.push(arguments);}}
gtag('js', new Date());
gtag('config', '{GA_MEASUREMENT_ID}');
</script>
<style>{STYLES}</style>
</head>
<body>
{body}
</body>
</html>
""",
        indexable=indexable,
    )


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
#
# Production's sitemap.ts stamps every one of its 42 entries with the build date
# - only two distinct values exist across the whole file, the newer of which is
# six months stale (T2.7). On a site whose entire proposition is "today's rate",
# a lastmod claiming February is an active anti-freshness signal, and it works
# directly against the date-stamped titles this module exists to produce.
#
# Like the pages, this is served ahead of the Next route handler by Caddy. Every
# URL production already publishes is kept: nothing is dropped from the index by
# this change.

# Everything production publishes that the renderer does NOT own. The rate pages
# come from PAGES below, so listing them here too would duplicate all 34.
SITEMAP_STATIC: Tuple[Tuple[str, str, str], ...] = (
    ("/", "hourly", "1.0"),
    ("/gold-prediction", "daily", "0.9"),
    ("/trends", "daily", "0.8"),
    ("/calculator", "weekly", "0.7"),
    ("/geopolitical-gold-impact", "weekly", "0.8"),
    ("/gold-news-today", "daily", "0.9"),
    ("/why-gold-price-is-increasing-2026", "monthly", "0.8"),
    ("/about", "monthly", "0.5"),
    ("/contact", "monthly", "0.5"),
    ("/privacy", "monthly", "0.5"),
    ("/terms", "monthly", "0.5"),
)


def _sitemap_entry(path: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (
        "<url>"
        f"<loc>{SITE}{path}</loc>"
        f"<lastmod>{lastmod}</lastmod>"
        f"<changefreq>{changefreq}</changefreq>"
        f"<priority>{priority}</priority>"
        "</url>"
    )


def render_sitemap(
    rates_updated_at: Optional[datetime],
    articles: Sequence[Tuple[str, datetime]] = (),
    now: Optional[datetime] = None,
) -> str:
    """Build sitemap.xml with a lastmod that reflects reality.

    `rates_updated_at` is the newest row in gold_rates, so every rate page claims
    the moment its data actually changed. `articles` is (slug, published_at) for
    the news pieces, which appear in no sitemap at all today (T2.8).
    """
    from datetime import timezone

    moment = now or datetime.now(timezone.utc)
    fallback = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    if rates_updated_at is not None:
        stamp = rates_updated_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        rate_lastmod = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        rate_lastmod = fallback

    entries = []
    for path, changefreq, priority in SITEMAP_STATIC:
        lastmod = rate_lastmod if changefreq in ("hourly", "daily") else fallback
        entries.append(_sitemap_entry(path, lastmod, changefreq, priority))

    for spec in PAGES.values():
        priority = "0.9" if spec.kind == "country" else "0.8"
        entries.append(_sitemap_entry(spec.path, rate_lastmod, "daily", priority))

    for slug, published in articles:
        stamp = published
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        entries.append(
            _sitemap_entry(
                f"/gold-news-today/{slug}",
                stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "monthly",
                "0.6",
            )
        )

    body = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )
