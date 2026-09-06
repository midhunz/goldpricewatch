"""SEO regression tests for the static rate pages — SEO_TASKS T7.2 (+ T1.1, T3.x).

Covers every file in frontend/public/gold-rates/. These are plain static HTML, so
they are checkable without a build. The equivalent checks for the Next.js routes
cannot live here yet: that source is not in this repository (see docs/BLOCKED.md).

Run: python -m unittest discover -s tests -v
"""

import html
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
RATE_PAGES_DIR = REPO / "frontend" / "public" / "gold-rates"
PUBLIC_DIR = REPO / "frontend" / "public"

TITLE_MAX = 60
DESC_MAX = 155
BASE = "https://goldpricewatch.com"

PAGES = sorted(RATE_PAGES_DIR.glob("*.html"))


def head_of(markup: str) -> str:
    return markup.split("</head>")[0]


def meta(markup: str, name: str, attr: str = "name") -> str | None:
    m = re.search(
        rf'<meta\s+{attr}="{re.escape(name)}"\s+content="(.*?)"\s*/?>',
        markup,
        re.I | re.S,
    )
    return html.unescape(m.group(1)) if m else None


def headings(markup: str) -> list[tuple[int, str]]:
    body = markup.split("</head>", 1)[-1]
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    out = []
    for m in re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", body, re.S | re.I):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        out.append((int(m.group(1)), text))
    return out


class TestRatePagesExist(unittest.TestCase):
    def test_pages_are_present(self):
        self.assertTrue(PAGES, f"no HTML files under {RATE_PAGES_DIR}")

    def test_expected_page_count(self):
        """15 files: 11 India states + 4 Oman cities. The audit counted only 11."""
        self.assertEqual(len(PAGES), 15, [p.name for p in PAGES])


class TestNoFabricatedPrices(unittest.TestCase):
    """T1.1 acceptance: no static rate page may contain a literal price figure.

    A file in public/ cannot reach /api/rates (it requires an X-API-KEY header),
    so any number baked into these pages is by definition a stale hardcoded
    snapshot. Kerala shipped 22K at Rs 15,640/g against a national Rs 14,190/g —
    10.22% wrong — for as long as the file sat there unedited.
    """

    RUPEE_FIGURE = re.compile(r"[₹]\s*[\d,]{3,}")
    CURRENCY_FIGURE = re.compile(
        r"\b(?:AED|SAR|QAR|OMR|BHD|KWD|INR|USD)\s*[\d,]+(?:\.\d+)?\b"
        r"|\b[\d,]+(?:\.\d+)?\s*(?:AED|SAR|QAR|OMR|BHD|KWD|INR|USD)\b",
        re.I,
    )

    def test_no_rupee_figures(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                found = self.RUPEE_FIGURE.findall(page.read_text(encoding="utf-8"))
                self.assertEqual(found, [], f"{page.name} contains hardcoded rupee figures")

    def test_no_other_currency_figures(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                found = self.CURRENCY_FIGURE.findall(page.read_text(encoding="utf-8"))
                self.assertEqual(found, [], f"{page.name} contains hardcoded prices")

    def test_no_stale_loading_placeholder(self):
        """The 'Loading latest rates...' badge sat above a static table forever."""
        for page in PAGES:
            with self.subTest(page=page.name):
                self.assertNotIn("Loading latest rates", page.read_text(encoding="utf-8"))

    def test_no_client_side_timestamp_fabrication(self):
        """The old script stamped browser time as 'Last Updated' over stale prices.

        T1.3 requires the feed fetch time, not the render time. Rendering
        `new Date()` next to a hardcoded price manufactures a freshness signal.
        """
        for page in PAGES:
            with self.subTest(page=page.name):
                markup = page.read_text(encoding="utf-8")
                body = markup.split("</head>", 1)[-1]
                self.assertNotIn("fetchLiveRates", body)
                self.assertNotIn("toLocaleDateString", body)


class TestIndexability(unittest.TestCase):
    """T1.1 step 1: these pages must not be indexable while they carry no feed."""

    def test_all_pages_noindex(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                robots = meta(head_of(page.read_text(encoding="utf-8")), "robots")
                self.assertIsNotNone(robots, f"{page.name} has no robots meta")
                self.assertIn("noindex", robots.replace(" ", "").lower())


class TestTitles(unittest.TestCase):
    """T3.1: hard cap 60 characters, brand not duplicated."""

    def test_title_present_and_within_cap(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                m = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.S)
                self.assertIsNotNone(m, f"{page.name} has no <title>")
                title = html.unescape(m.group(1)).strip()
                self.assertLessEqual(
                    len(title), TITLE_MAX,
                    f"{page.name}: title is {len(title)} chars: {title!r}",
                )

    def test_brand_appears_at_most_once(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                m = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.S)
                title = html.unescape(m.group(1))
                self.assertLessEqual(title.lower().count("goldpricewatch"), 1, title)

    def test_uses_gold_rate_not_gold_price(self):
        """T4.1: 'gold rate' is the dominant query form in India and the GCC."""
        for page in PAGES:
            with self.subTest(page=page.name):
                m = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.S)
                title = html.unescape(m.group(1)).lower()
                self.assertIn("gold rate", title)
                self.assertNotIn("gold price", title)


class TestDescriptions(unittest.TestCase):
    """T3.2: meta description at most 155 characters."""

    def test_description_present_and_within_cap(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                desc = meta(head_of(page.read_text(encoding="utf-8")), "description")
                self.assertIsNotNone(desc, f"{page.name} has no meta description")
                self.assertLessEqual(
                    len(desc), DESC_MAX,
                    f"{page.name}: description is {len(desc)} chars",
                )

    def test_no_unsubstantiated_freshness_claim(self):
        """T1.4: no page may claim a refresh cadence the implementation cannot back."""
        for page in PAGES:
            with self.subTest(page=page.name):
                text = page.read_text(encoding="utf-8").lower()
                for claim in ("updated every hour", "updated hourly", "real-time updates"):
                    self.assertNotIn(claim, text, f"{page.name} claims {claim!r}")


class TestCanonical(unittest.TestCase):
    """T7.2: canonical present, absolute, self-referencing."""

    def test_canonical_is_absolute_and_self_referencing(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                markup = page.read_text(encoding="utf-8")
                m = re.search(r'<link rel="canonical" href="(.*?)"', markup, re.I)
                self.assertIsNotNone(m, f"{page.name} has no canonical")
                href = m.group(1)
                self.assertTrue(href.startswith("https://"), href)
                self.assertEqual(href, f"{BASE}/gold-rates/{page.name}")


class TestOpenGraph(unittest.TestCase):
    """T3.3: absolute og:image, page-specific og:title/description, full card set."""

    def test_og_image_absolute(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                og = meta(head_of(page.read_text(encoding="utf-8")), "og:image", "property")
                self.assertIsNotNone(og, f"{page.name} has no og:image")
                self.assertTrue(
                    og.startswith("http://") or og.startswith("https://"),
                    f"{page.name}: og:image is relative: {og!r}",
                )

    def test_og_image_target_exists(self):
        """A relative og:image will not render; neither will an absolute 404."""
        for page in PAGES:
            with self.subTest(page=page.name):
                og = meta(head_of(page.read_text(encoding="utf-8")), "og:image", "property")
                local = PUBLIC_DIR / og.replace(BASE + "/", "")
                self.assertTrue(local.is_file(), f"{page.name}: og:image 404s ({og})")

    def test_site_name_type_and_locale_present(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                head = head_of(page.read_text(encoding="utf-8"))
                for prop in ("og:site_name", "og:type", "og:locale", "og:url"):
                    self.assertIsNotNone(
                        meta(head, prop, "property"), f"{page.name} missing {prop}"
                    )

    def test_twitter_card_complete(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                head = head_of(page.read_text(encoding="utf-8"))
                for name in ("twitter:card", "twitter:title", "twitter:description",
                             "twitter:image"):
                    self.assertIsNotNone(head and meta(head, name), f"{page.name} missing {name}")

    def test_og_title_matches_page_title(self):
        """T3.3.2: pages must not inherit a generic homepage og:title."""
        for page in PAGES:
            with self.subTest(page=page.name):
                markup = page.read_text(encoding="utf-8")
                title = html.unescape(
                    re.search(r"<title>(.*?)</title>", markup, re.S).group(1)
                ).strip()
                self.assertEqual(meta(head_of(markup), "og:title", "property"), title)


class TestHeadings(unittest.TestCase):
    """T3.6: exactly one H1 and no skipped heading level."""

    def test_exactly_one_h1(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                levels = [lvl for lvl, _ in headings(page.read_text(encoding="utf-8"))]
                self.assertEqual(levels.count(1), 1, f"{page.name}: H1 count {levels.count(1)}")

    def test_no_skipped_heading_level(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                found = headings(page.read_text(encoding="utf-8"))
                seen = 0
                for level, text in found:
                    self.assertLessEqual(
                        level, seen + 1,
                        f"{page.name}: jumped H{seen} -> H{level} at {text!r}",
                    )
                    seen = max(seen, level)

    def test_h1_is_first_heading(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                found = headings(page.read_text(encoding="utf-8"))
                self.assertTrue(found, f"{page.name} has no headings")
                self.assertEqual(found[0][0], 1, f"{page.name} starts at H{found[0][0]}")


class TestReferencedAssets(unittest.TestCase):
    """Every locally-referenced image must exist. 14 of 15 pages used to 404."""

    LOCAL_ASSET = re.compile(r"""url\(['"]?(/images/[^)'"]+)['"]?\)""")

    def test_css_background_images_exist(self):
        for page in PAGES:
            with self.subTest(page=page.name):
                for ref in self.LOCAL_ASSET.findall(page.read_text(encoding="utf-8")):
                    self.assertTrue(
                        (PUBLIC_DIR / ref.lstrip("/")).is_file(),
                        f"{page.name} references missing asset {ref}",
                    )


class TestInternalLinks(unittest.TestCase):
    """The empty state must route users to a page that actually has rates."""

    def test_every_page_links_to_a_live_rate_page(self):
        oman = {"muscat", "salalah", "sohar", "nizwa"}
        for page in PAGES:
            with self.subTest(page=page.name):
                markup = page.read_text(encoding="utf-8")
                expected = "/oman-gold-prices" if page.stem in oman else "/india-gold-prices"
                self.assertIn(
                    f'href="{expected}"', markup,
                    f"{page.name} should link to {expected}",
                )

    def test_no_india_specific_claims_on_oman_pages(self):
        """Omani cities were served the India template: GST and BIS hallmarking."""
        for page in PAGES:
            if page.stem not in {"muscat", "salalah", "sohar", "nizwa"}:
                continue
            with self.subTest(page=page.name):
                text = page.read_text(encoding="utf-8")
                self.assertNotIn("GST", text, f"{page.name} cites Indian GST")
                self.assertNotIn("BIS Hallmark", text, f"{page.name} cites Indian BIS")


if __name__ == "__main__":
    unittest.main()
