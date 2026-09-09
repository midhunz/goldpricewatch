"""SEO regression tests for the server-rendered rate pages — SEO_TASKS T7.2.

Covers backend/rate_pages.py, which serves the Oman country and city pages with
live prices (see that module's docstring for why it exists). The rendering is
pure, so every page in the registry can be rendered here from a synthetic
snapshot with no database and no dependencies — which is what lets these run in
the same stdlib-only CI job as the static-page checks.

The rule these exist to protect, above all the metadata ones: a page that cannot
publish a verified price must publish none, and must not ask to be indexed.

Run: python -m unittest discover -s tests -v
"""

import json
import math
import pathlib
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

import rate_pages  # noqa: E402

BASE = "https://goldpricewatch.com"
NOW = datetime(2026, 9, 9, 10, 20, tzinfo=timezone.utc)

LIVE = rate_pages.RateSnapshot(
    region="Oman",
    currency="OMR",
    by_purity={"24K": 56.75, "22K": 53.25, "21K": 48.65, "18K": 42.30},
    # 22K deliberately has no prior close: that is the T1.2 case, and it must
    # render as absence rather than as 0.00%.
    changes={"24K": 0.45, "22K": None, "21K": -0.30, "18K": 0.0},
    updated_at=NOW,
    stale=False,
)

STALE = rate_pages.RateSnapshot(
    region="Oman",
    currency="OMR",
    by_purity={"24K": 56.75, "22K": 53.25},
    changes={"24K": None, "22K": None},
    updated_at=NOW - timedelta(hours=9),
    stale=True,
)

EMPTY = rate_pages.RateSnapshot(
    region="Oman", currency="OMR", by_purity={}, changes={}, updated_at=None, stale=False
)

def _series(base, days=30, start=datetime(2026, 8, 10)):
    """A daily series with a little shape to it, as the feed would produce."""
    return [(start + timedelta(days=i), base + math.sin(i / 3.0) * 1.2)
            for i in range(days)]


HISTORY = {"22K": _series(52.0), "24K": _series(55.5)}
TREND = HISTORY["22K"]

SPECS = list(rate_pages.PAGES.values())


def render(spec, snapshot=LIVE, history=HISTORY):
    return rate_pages.render_page(spec, snapshot, history, NOW)


def head_of(markup: str) -> str:
    return markup.split("</head>")[0]


def meta(markup: str, name: str, attr: str = "name"):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="(.*?)">', markup, re.S)
    return m.group(1) if m else None


def headings(markup: str):
    body = markup.split("</head>", 1)[-1]
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    return [
        (int(m.group(1)), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip())
        for m in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", body, re.S | re.I)
    ]


def ld_blocks(markup: str):
    return [
        json.loads(m)
        for m in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', markup, re.S
        )
    ]


class TestRegistry(unittest.TestCase):
    def test_registry_is_not_empty(self):
        self.assertTrue(SPECS)

    def test_every_path_is_absolute_and_unique(self):
        paths = [spec.path for spec in SPECS]
        self.assertEqual(len(paths), len(set(paths)))
        for path in paths:
            self.assertTrue(path.startswith("/"), path)

    def test_city_pages_point_at_a_hub_that_lists_them(self):
        for spec in SPECS:
            if spec.kind != "city":
                continue
            with self.subTest(page=spec.path):
                self.assertIn(spec.parent, rate_pages.PAGES, spec.path)
                self.assertIn(spec.path, rate_pages.PAGES[spec.parent].cities)

    def test_lookup_tolerates_a_trailing_slash(self):
        self.assertIsNotNone(rate_pages.get_page("/oman-gold-prices/"))
        self.assertIsNone(rate_pages.get_page("/not-a-page"))


class TestTitles(unittest.TestCase):
    """T3.1 and T4.8: within 60 characters, and carrying the live rate."""

    def test_title_within_cap_in_every_state(self):
        for spec in SPECS:
            for label, snapshot in (("live", LIVE), ("stale", STALE), ("empty", EMPTY)):
                with self.subTest(page=spec.path, state=label):
                    title = re.search(
                        r"<title>(.*?)</title>", render(spec, snapshot).html
                    ).group(1)
                    self.assertLessEqual(len(title), rate_pages.TITLE_MAX, title)
                    self.assertTrue(title.strip())

    def test_live_title_carries_the_price_and_the_date(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                title = re.search(r"<title>(.*?)</title>", render(spec).html).group(1)
                self.assertIn("53.25", title, title)
                self.assertIn("OMR", title, title)
                self.assertIn("9 Sep", title, title)

    def test_brand_is_not_repeated_into_the_title(self):
        """T3.1: the domain is already in the SERP; spending 16 chars on it again
        is what pushed 8 of 9 live titles over the cap."""
        for spec in SPECS:
            with self.subTest(page=spec.path):
                title = re.search(r"<title>(.*?)</title>", render(spec).html).group(1)
                self.assertNotIn("GoldPriceWatch", title)

    def test_title_uses_gold_rate_not_gold_price(self):
        """T4.1: 'rate' is the term these markets search with."""
        for spec in SPECS:
            with self.subTest(page=spec.path):
                title = re.search(r"<title>(.*?)</title>", render(spec).html).group(1)
                self.assertIn("Gold Rate", title, title)


class TestDescriptions(unittest.TestCase):
    def test_description_within_cap_in_every_state(self):
        for spec in SPECS:
            for label, snapshot in (("live", LIVE), ("stale", STALE), ("empty", EMPTY)):
                with self.subTest(page=spec.path, state=label):
                    desc = meta(head_of(render(spec, snapshot).html), "description")
                    self.assertIsNotNone(desc)
                    self.assertLessEqual(len(desc), rate_pages.DESCRIPTION_MAX, desc)

    def test_live_description_leads_with_the_figure(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                desc = meta(head_of(render(spec).html), "description")
                self.assertIn("53.25", desc, desc)


class TestNeverPublishesUnverifiedPrices(unittest.TestCase):
    """The rule that must not bend: ground rule 1 of SEO_TASKS.

    A stale feed or an empty snapshot renders an empty state and noindex. It does
    not carry yesterday's number forward, and it does not emit Dataset markup
    asserting a measurement it does not have.
    """

    def test_stale_and_empty_pages_are_noindex(self):
        for spec in SPECS:
            for label, snapshot in (("stale", STALE), ("empty", EMPTY)):
                with self.subTest(page=spec.path, state=label):
                    page = render(spec, snapshot)
                    self.assertFalse(page.indexable)
                    self.assertEqual(
                        meta(head_of(page.html), "robots"), "noindex, follow"
                    )

    def test_no_figure_leaks_into_a_stale_page(self):
        for spec in SPECS:
            for label, snapshot in (("stale", STALE), ("empty", EMPTY)):
                with self.subTest(page=spec.path, state=label):
                    markup = render(spec, snapshot).html
                    body = markup.split("</head>", 1)[-1]
                    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
                    self.assertNotIn("53.25", markup)
                    self.assertNotIn("56.75", markup)
                    self.assertIsNone(
                        re.search(r"OMR\s*\d", body), "a currency figure reached the page"
                    )

    def test_stale_page_emits_no_dataset_markup(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                types = {b.get("@type") for b in ld_blocks(render(spec, STALE).html)}
                self.assertNotIn("Dataset", types)

    def test_stale_page_says_so(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                self.assertIn("not available", render(spec, STALE).html)

    def test_live_page_is_indexable(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                page = render(spec)
                self.assertTrue(page.indexable)
                self.assertEqual(meta(head_of(page.html), "robots"), "index, follow")


class TestNoPermanentZeroChange(unittest.TestCase):
    """T1.2: the live site prints 0.00% on every karat of every page."""

    def test_missing_prior_close_renders_as_absence_not_zero(self):
        markup = render(rate_pages.PAGES["/gold-rates/muscat.html"]).html
        self.assertIn("No prior close to compare", markup)

    def test_no_zero_percent_change_anywhere(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                markup = render(spec).html
                self.assertNotIn("0.00%", markup)
                self.assertNotIn("0.00 %", markup)

    def test_a_genuinely_flat_price_says_unchanged(self):
        markup = render(rate_pages.PAGES["/gold-rates/muscat.html"]).html
        self.assertIn("Unchanged vs yesterday", markup)


class TestCanonicalAndSocial(unittest.TestCase):
    def test_canonical_is_absolute_and_self_referencing(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                markup = render(spec).html
                m = re.search(r'<link rel="canonical" href="([^"]+)">', markup)
                self.assertIsNotNone(m)
                self.assertEqual(m.group(1), f"{BASE}{spec.path}")

    def test_open_graph_and_twitter_are_complete(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                head = head_of(render(spec).html)
                for prop in ("og:title", "og:description", "og:url", "og:image",
                             "og:type", "og:site_name", "og:locale"):
                    self.assertIsNotNone(meta(head, prop, attr="property"), prop)
                for name in ("twitter:card", "twitter:title", "twitter:description",
                             "twitter:image"):
                    self.assertIsNotNone(meta(head, name), name)

    def test_og_image_is_absolute_and_exists_in_the_repo(self):
        """T3.3: a relative og:image never renders a preview, and the previous
        static pages pointed at hero images that 404'd."""
        head = head_of(render(SPECS[0]).html)
        image = meta(head, "og:image", attr="property")
        self.assertTrue(image.startswith("https://"), image)
        self.assertTrue(
            (REPO / "frontend" / "public" / image[len(BASE) + 1:]).is_file(), image
        )


class TestHeadings(unittest.TestCase):
    def test_exactly_one_h1(self):
        for spec in SPECS:
            for label, snapshot in (("live", LIVE), ("stale", STALE)):
                with self.subTest(page=spec.path, state=label):
                    levels = [lv for lv, _ in headings(render(spec, snapshot).html)]
                    self.assertEqual(levels.count(1), 1, levels)

    def test_no_skipped_heading_level(self):
        for spec in SPECS:
            for label, snapshot in (("live", LIVE), ("stale", STALE)):
                with self.subTest(page=spec.path, state=label):
                    levels = [lv for lv, _ in headings(render(spec, snapshot).html)]
                    self.assertEqual(levels[0], 1, levels)
                    for previous, current in zip(levels, levels[1:]):
                        self.assertLessEqual(current - previous, 1, levels)


class TestCityPagesAreHonestAboutTheNationalRate(unittest.TestCase):
    """T2.1 / T1.5, and the defect behind T1.1.

    The feed has one rate per country. Repeating it on seven city pages is fine;
    presenting it as seven distinct city rates is what put eleven India state
    pages 10.22% out and got all fifteen static pages deindexed.
    """

    def test_every_city_page_states_the_rate_is_national(self):
        for spec in SPECS:
            if spec.kind != "city":
                continue
            with self.subTest(page=spec.path):
                markup = render(spec).html
                self.assertIn("national gold rate", markup)
                self.assertIn(
                    f"There is no separate\n{spec.place} rate".replace("\n", " "),
                    re.sub(r"\s+", " ", markup),
                )

    def test_hub_city_table_states_it_too(self):
        hub = rate_pages.PAGES["/oman-gold-prices"]
        markup = re.sub(r"\s+", " ", render(hub).html)
        self.assertIn("is set nationally, so it is the same in every city", markup)

    def test_city_pages_do_not_claim_a_distinct_local_rate(self):
        banned = re.compile(r"(?:the\s+)?%s\s+gold\s+rate\s+is\s+(?:currently\s+)?OMR", re.I)
        for spec in SPECS:
            if spec.kind != "city":
                continue
            with self.subTest(page=spec.path):
                self.assertIsNone(banned.search(render(spec).html))


class TestInternalLinking(unittest.TestCase):
    """Report finding 7: 1.61 pages per session."""

    def test_city_pages_link_to_their_hub_and_their_siblings(self):
        for spec in SPECS:
            if spec.kind != "city":
                continue
            with self.subTest(page=spec.path):
                markup = render(spec).html
                self.assertIn(f'href="{spec.parent}"', markup)
                siblings = [
                    p for p in rate_pages.PAGES[spec.parent].cities if p != spec.path
                ]
                for sibling in siblings:
                    self.assertIn(f'href="{sibling}"', markup)

    def test_every_page_links_to_the_prediction_page_and_calculator(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                markup = render(spec).html
                self.assertIn('href="/gold-prediction"', markup)
                self.assertIn('href="/calculator"', markup)

    def test_hub_links_to_every_city(self):
        hub = rate_pages.PAGES["/oman-gold-prices"]
        markup = render(hub).html
        for path in hub.cities:
            self.assertIn(f'href="{path}"', markup)


class TestUnits(unittest.TestCase):
    """T4.3 and report finding 5: karat and unit queries rank and convert at zero."""

    def test_unit_rows_are_the_per_gram_rate_multiplied_out(self):
        markup = render(rate_pages.PAGES["/gold-rates/muscat.html"]).html
        self.assertIn(rate_pages.format_money(53.25 * 8, "OMR"), markup)
        self.assertIn(
            rate_pages.format_money(53.25 * rate_pages.GRAMS_PER_TOLA, "OMR"), markup
        )

    def test_every_karat_in_the_feed_is_shown(self):
        markup = render(rate_pages.PAGES["/gold-rates/muscat.html"]).html
        for purity in ("24K", "22K", "21K", "18K"):
            self.assertIn(purity, markup)


class TestStructuredData(unittest.TestCase):
    """T5.1. Dataset, not Product: this is a published measurement, not a sale."""

    def test_live_pages_emit_valid_dataset_json(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                blocks = ld_blocks(render(spec).html)
                datasets = [b for b in blocks if b.get("@type") == "Dataset"]
                self.assertEqual(len(datasets), 1)
                dataset = datasets[0]
                self.assertEqual(dataset["url"], f"{BASE}{spec.path}")
                self.assertTrue(dataset["dateModified"])
                values = {v["name"]: v["value"] for v in dataset["variableMeasured"]}
                self.assertEqual(values["22K gold rate"], 53.25)
                for measured in dataset["variableMeasured"]:
                    self.assertEqual(measured["unitText"], "OMR per gram")

    def test_city_pages_emit_a_breadcrumb_trail(self):
        for spec in SPECS:
            if spec.kind != "city":
                continue
            with self.subTest(page=spec.path):
                blocks = ld_blocks(render(spec).html)
                crumbs = [b for b in blocks if b.get("@type") == "BreadcrumbList"]
                self.assertEqual(len(crumbs), 1)
                items = crumbs[0]["itemListElement"]
                self.assertEqual(items[-1]["item"], f"{BASE}{spec.path}")
                self.assertEqual(items[1]["item"], f"{BASE}{spec.parent}")

    def test_no_product_or_offer_markup(self):
        markup = render(SPECS[0]).html
        self.assertNotIn('"Product"', markup)
        self.assertNotIn('"Offer"', markup)


class TestTrend(unittest.TestCase):
    """Every country page carries a historical trend, rendered server-side."""

    def test_live_page_renders_an_svg_and_a_text_summary(self):
        markup = render(rate_pages.PAGES["/oman-gold-prices"]).html
        self.assertIn("<svg", markup)
        self.assertIn("<polyline", markup)
        self.assertIn("Over the last 30 days", markup)

    def test_chart_is_omitted_rather_than_drawn_empty(self):
        for history in ({}, {"22K": TREND[:1]}):
            with self.subTest(points=len(history)):
                markup = render(SPECS[0], LIVE, history).html
                self.assertNotIn("<polyline", markup)

    def test_a_zero_point_would_visibly_wreck_the_chart(self):
        """Why the history endpoint must drop unparseable rows, not zero them.

        It used to fall back to price_val = 0.0 on any parse failure. This pins
        what that does to the drawing: one bad row rescales the whole series into
        the top sliver of the plot and drags a line to the floor. The fix is in
        main.read_rates_history, which now drops those rows; this is the evidence
        for why the fix is not cosmetic.
        """
        clean = rate_pages.trend_svg(TREND, "OMR")
        poisoned = rate_pages.trend_svg(
            list(TREND[:15]) + [(TREND[15][0], 0.0)] + list(TREND[16:]), "OMR"
        )

        def y_span(svg):
            pts = re.search(
                r'<polyline class="trend-line" points="([^"]+)"', svg
            ).group(1)
            ys = [float(pair.split(",")[1]) for pair in pts.split()]
            return max(ys) - min(ys)

        # Both use the full plot height, but the poisoned one spends nearly all
        # of it on a single spike to zero, so the real variation collapses.
        real_variation = [
            float(p.split(",")[1])
            for p in re.search(
                r'<polyline class="trend-line" points="([^"]+)"', poisoned
            ).group(1).split()
        ]
        real_variation.remove(max(real_variation))
        self.assertGreater(y_span(clean), 100)
        self.assertLess(max(real_variation) - min(real_variation), 10)

    def test_downsample_keeps_the_latest_point(self):
        dense = TREND * 40
        thinned = rate_pages.downsample(dense, target=50)
        self.assertLessEqual(len(thinned), 51)
        self.assertEqual(thinned[-1], dense[-1])

    def test_flat_series_does_not_divide_by_zero(self):
        flat = [(datetime(2026, 9, 1) + timedelta(days=i), 50.0) for i in range(10)]
        self.assertIn("<polyline", rate_pages.trend_svg(flat, "OMR"))


class TestHistoryTables(unittest.TestCase):
    """The dated history tables: last 7 days daily, last 30 days by week.

    The chart shows the shape; these show the numbers, and they are the part
    that answers "gold rate last 10 days" style queries in text a crawler reads.
    """

    def rows(self, markup, heading):
        section = markup.split(heading, 1)[-1].split("</table>", 1)[0]
        return re.findall(r"<tr><td>([^<]+)</td>(.*?)</tr>", section, re.S)

    def test_both_tables_render_on_a_live_page(self):
        markup = render(rate_pages.PAGES["/gold-rates/muscat.html"]).html
        self.assertIn("Gold rate history in Muscat", markup)
        self.assertIn("Last 7 days", markup)
        self.assertIn("Last 30 days", markup)

    def test_week_table_is_seven_days_newest_first(self):
        markup = render(SPECS[0]).html
        rows = self.rows(markup, "Last 7 days")
        self.assertEqual(len(rows), 7, [r[0] for r in rows])
        dates = [datetime.strptime(r[0], "%d %b %Y") for r in rows]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(dates[0], TREND[-1][0])

    def test_week_table_shows_both_karats(self):
        markup = render(SPECS[0]).html
        rows = self.rows(markup, "Last 7 days")
        latest = rows[0][1]
        self.assertIn(rate_pages.format_money(TREND[-1][1], "OMR"), latest)
        self.assertIn(rate_pages.format_money(HISTORY["24K"][-1][1], "OMR"), latest)

    def test_oldest_row_has_no_fabricated_change(self):
        """Same rule as the rate cards: nothing to compare against renders as a
        dash, never as 0.00 (T1.2)."""
        markup = render(SPECS[0]).html
        rows = self.rows(markup, "Last 7 days")
        self.assertIn("—", rows[-1][1])
        self.assertNotIn("0.00%", markup)

    def test_month_table_counts_full_weeks_back_from_today(self):
        """Chunking forwards leaves a two-day stub at the top of the table."""
        markup = render(SPECS[0]).html
        rows = self.rows(markup, "Last 30 days")
        spans = [r[0] for r in rows]
        first_start, first_end = spans[0].split(" – ")
        start = datetime.strptime(first_start, "%d %b %Y")
        end = datetime.strptime(first_end, "%d %b %Y")
        self.assertEqual(end, TREND[-1][0])
        self.assertEqual((end - start).days, 6, spans)

    def test_month_table_high_and_low_are_real_readings(self):
        markup = render(SPECS[0]).html
        rows = self.rows(markup, "Last 30 days")
        prices = {round(p, 2) for _, p in rate_pages.daily_closes(TREND)}
        for _, cells in rows:
            for value in re.findall(r"<td>([0-9][0-9.,]*)</td>", cells):
                with self.subTest(value=value):
                    self.assertIn(round(float(value.replace(",", "")), 2), prices)

    def test_tables_are_withheld_when_there_is_no_live_rate(self):
        """A page that will not price today does not publish a price history."""
        for label, snapshot in (("stale", STALE), ("empty", EMPTY)):
            with self.subTest(state=label):
                markup = render(SPECS[0], snapshot).html
                self.assertNotIn("Gold rate history", markup)

    def test_tables_are_omitted_rather_than_drawn_empty(self):
        markup = render(SPECS[0], LIVE, {"22K": TREND[:1]}).html
        self.assertNotIn("Last 7 days", markup)

    def test_daily_closes_keeps_the_last_reading_of_each_day(self):
        """The feed writes hourly. A day's closing rate is its last reading -
        averaging would publish a number that was never quoted."""
        day = datetime(2026, 9, 1)
        points = [
            (day.replace(hour=9), 50.0),
            (day.replace(hour=13), 51.0),
            (day.replace(hour=17), 52.0),
            (day.replace(day=2, hour=10), 53.0),
        ]
        self.assertEqual(
            rate_pages.daily_closes(points),
            [(day.replace(hour=17), 52.0), (day.replace(day=2, hour=10), 53.0)],
        )

    def test_history_currency_matches_the_market(self):
        """The renderer takes the currency from the snapshot, so an India page
        fed India rows must not inherit the Gulf currency or its formatting."""
        rupees = rate_pages.RateSnapshot(
            region="India",
            currency="INR",
            by_purity={"24K": 15535.0, "22K": 14240.0, "18K": 11651.0},
            changes={"24K": 35.0, "22K": None, "18K": -12.0},
            updated_at=NOW,
            stale=False,
        )
        history = {"22K": _series(14240.0), "24K": _series(15535.0)}
        markup = rate_pages.render_page(
            rate_pages.PAGES["/gold-rates/kerala.html"], rupees, history, NOW
        ).html
        self.assertIn("Gold rate history in Kerala", markup)
        section = markup.split("Gold rate history", 1)[-1].split("</table>")[1]
        self.assertIn("INR per gram", section)
        self.assertNotIn("OMR", section)
        # Rupees are quoted in whole units with separators, not to two decimals.
        self.assertIn("14,240", markup)

class TestSitemap(unittest.TestCase):
    """T2.7 and T2.8."""

    def setUp(self):
        self.updated = datetime(2026, 9, 9, 9, 1, tzinfo=timezone.utc)
        self.xml = rate_pages.render_sitemap(
            self.updated,
            articles=[("gold-hits-record", datetime(2026, 9, 1, 12, 0))],
            now=NOW,
        )

    def test_it_parses(self):
        import xml.etree.ElementTree as ET

        ET.fromstring(self.xml)

    def test_lastmod_is_not_hardcoded_to_a_build_date(self):
        """Production stamps all 42 entries with one of two build dates, the
        newer of which is six months stale."""
        self.assertNotIn("2026-02-28", self.xml)
        self.assertNotIn("2026-01-24", self.xml)
        self.assertIn("2026-09-09T09:01:00Z", self.xml)

    def test_every_rendered_page_is_listed(self):
        for spec in SPECS:
            with self.subTest(page=spec.path):
                self.assertIn(f"<loc>{BASE}{spec.path}</loc>", self.xml)

    def test_nothing_production_publishes_is_dropped(self):
        """This change deindexes nothing. Every URL in the live sitemap stays."""
        for path in ("/", "/india-gold-prices", "/uae-gold-prices",
                     "/dubai-gold-prices", "/saudi-arabia-gold-prices",
                     "/why-gold-price-is-increasing-2026", "/about", "/terms"):
            with self.subTest(path=path):
                self.assertIn(f"<loc>{BASE}{path}</loc>", self.xml)
        # The 11 India state URLs, which used to be static files and are now
        # rendered. Listed literally so this test still fails if they fall out
        # of the registry rather than quietly following it.
        for state in ("kerala", "tamil-nadu", "karnataka", "maharashtra", "delhi",
                      "west-bengal", "gujarat", "rajasthan", "andhra-pradesh",
                      "punjab", "uttar-pradesh"):
            with self.subTest(state=state):
                self.assertIn(f"<loc>{BASE}/gold-rates/{state}.html</loc>", self.xml)

    def test_news_articles_are_included(self):
        """T2.8: no article URL appears in the live sitemap at all."""
        self.assertIn(f"<loc>{BASE}/gold-news-today/gold-hits-record</loc>", self.xml)

    def test_no_url_is_listed_twice(self):
        locs = re.findall(r"<loc>([^<]+)</loc>", self.xml)
        duplicates = {loc for loc in locs if locs.count(loc) > 1}
        self.assertFalse(duplicates, duplicates)

    def test_falls_back_to_now_when_the_feed_is_empty(self):
        xml = rate_pages.render_sitemap(None, now=NOW)
        self.assertIn("2026-09-09T10:20:00Z", xml)


class TestNoStaticRatePagesRemain(unittest.TestCase):
    """What is left of tests/test_seo_static.py, which this suite replaced.

    All 15 files under frontend/public/gold-rates/ were hardcoded-price pages;
    T1.1 stripped their figures and noindexed them, and every one of those URLs
    is now rendered live instead. A file reappearing there would be shadowed by
    the Caddy @rendered matcher and diverge silently from the page users get -
    so the guard is that the directory stays empty of them.
    """

    RATE_PAGES_DIR = REPO / "frontend" / "public" / "gold-rates"

    def test_no_static_rate_page_shadows_a_rendered_one(self):
        rendered = set(rate_pages.PAGES)
        for path in self.RATE_PAGES_DIR.glob("*.html"):
            with self.subTest(file=path.name):
                self.assertNotIn(
                    f"/gold-rates/{path.name}",
                    rendered,
                    f"{path.name} exists as a file and as a rendered route; "
                    f"Caddy serves the rendered one, so the file is dead code",
                )

    def test_no_static_rate_page_ships_a_hardcoded_price(self):
        """T1.1 acceptance, kept alive: eleven of these once published an
        identical rupee figure that was 10.22% above the national rate."""
        for path in self.RATE_PAGES_DIR.glob("*.html"):
            with self.subTest(file=path.name):
                markup = path.read_text(encoding="utf-8")
                self.assertIsNone(
                    re.search(r"[₹$]\s?[0-9][0-9,]{2,}", markup),
                    f"{path.name} contains a hardcoded price figure",
                )


class TestNoAnalyticsRegression(unittest.TestCase):
    def test_pages_still_report_into_ga4(self):
        """These URLs already exist and already send pageviews; losing the tag
        would look like a traffic drop rather than a rendering change."""
        markup = render(SPECS[0]).html
        self.assertIn(rate_pages.GA_MEASUREMENT_ID, markup)


if __name__ == "__main__":
    unittest.main()
