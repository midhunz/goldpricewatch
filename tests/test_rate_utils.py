"""Guardrail tests for backend/rate_utils.py — SEO_TASKS T1.2, T1.3, T7.1.

Run: python -m unittest discover -s tests -v
"""

import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from rate_utils import (  # noqa: E402
    FEED_REFRESH_CADENCE,
    FEED_STALE_AFTER,
    PURITY_RATIO_BOUNDS,
    STATE_TOLERANCE_PCT,
    canonical_purity,
    check_purity_ratio,
    check_state_divergence,
    feed_age,
    is_feed_stale,
    parse_price,
    state_divergence_pct,
)


class TestCanonicalPurity(unittest.TestCase):
    """The join key that T1.2's permanent 0.00% came from."""

    def test_carat_and_k_forms_collapse_to_one_key(self):
        # This is the whole bug: the current-rate table says "22 Carat" and the
        # history table header says "22K". They must produce the same key.
        self.assertEqual(canonical_purity("22 Carat"), canonical_purity("22K"))
        self.assertEqual(canonical_purity("24 Carat"), canonical_purity("24K"))
        self.assertEqual(canonical_purity("18 Carat"), canonical_purity("18K"))

    def test_known_label_variants(self):
        cases = {
            "22 Carat": "22K",
            "22K": "22K",
            "22k": "22K",
            "22 karat": "22K",
            "24 Carat (999 Gold)": "24K",
            "22 Carat (916 KDM)": "22K",
            "18ct": "18K",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonical_purity(raw), expected)

    def test_distinct_purities_do_not_collide(self):
        keys = {canonical_purity(p) for p in ("14 Carat", "18K", "21 Carat", "22K", "24K")}
        self.assertEqual(len(keys), 5)

    def test_empty_and_none(self):
        self.assertEqual(canonical_purity(""), "")
        self.assertEqual(canonical_purity(None), "")

    def test_unrecognised_label_joins_against_itself(self):
        self.assertEqual(canonical_purity(" 916 "), canonical_purity("916"))


class TestParsePrice(unittest.TestCase):
    """T7.1: a price is either a usable positive number or it is None."""

    def test_plain_and_grouped_numbers(self):
        self.assertEqual(parse_price("14190"), 14190.0)
        self.assertEqual(parse_price("14,190"), 14190.0)
        self.assertEqual(parse_price("1,70,620"), 170620.0)

    def test_india_composite_format(self):
        """India stores per-gram and per-10g in one string; take the per-gram.

        Regression test for a real near-miss: stripping the currency symbol and
        parsing the whole string turns "14,190₹141,900/ 10g" into the nonsense
        "14190141900/ 10g", which fails to parse and drops the row — silently
        removing every India price from /api/rates.
        """
        self.assertEqual(parse_price("14,190₹141,900/ 10g"), 14190.0)
        self.assertEqual(parse_price("15,480₹154,800/ 10g"), 15480.0)
        self.assertEqual(parse_price("11,610₹116,100/ 10g"), 11610.0)

    def test_leading_currency_symbol(self):
        self.assertEqual(parse_price("₹14,190"), 14190.0)

    def test_trailing_currency_code(self):
        self.assertEqual(parse_price("494.25 AED"), 494.25)
        self.assertEqual(parse_price("533.75 AED"), 533.75)

    def test_all_real_stored_formats(self):
        """Every price format observed in the production database."""
        observed = {
            "494.25": 494.25,          # UAE / AED
            "317.00": 317.0,           # UAE 14K
            "40.61": 40.61,            # Kuwait / KWD
            "480.00": 480.0,           # Saudi / SAR
            "54.40": 54.40,            # Bahrain / BHD
            "14,190₹141,900/ 10g": 14190.0,   # India / INR composite
        }
        for raw, expected in observed.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_price(raw), expected)

    def test_zero_and_negative_are_not_data(self):
        # T7.1: any rendered price of 0.00 must block render, not display.
        for bad in ("0", "0.00", "-1", "-5.5"):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_price(bad))

    def test_missing_and_garbage(self):
        for bad in (None, "", "   ", "n/a", "N/A", "--"):
            with self.subTest(bad=bad):
                self.assertIsNone(parse_price(bad))

    def test_never_returns_zero(self):
        """No input may yield 0.0 — that is the value T1.2 forbids publishing."""
        for value in (None, "", "0", "0.00", "n/a", "-3", "₹0"):
            self.assertNotEqual(parse_price(value), 0.0)


class TestFeedStaleness(unittest.TestCase):
    """T1.3 / T7.1: the published timestamp is the feed's, and stale feeds are known."""

    def test_naive_timestamp_treated_as_utc(self):
        naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
        age = feed_age(naive)
        self.assertIsNotNone(age)
        self.assertGreater(age, timedelta(hours=2))

    def test_aware_timestamp(self):
        aware = datetime.now(timezone.utc) - timedelta(hours=3)
        self.assertGreater(feed_age(aware), timedelta(hours=2))

    def test_naive_and_aware_agree(self):
        """Mixing the two forms must not raise, and must give the same answer."""
        now = datetime.now(timezone.utc)
        aware = now - timedelta(hours=5)
        naive = aware.replace(tzinfo=None)
        self.assertAlmostEqual(
            feed_age(aware).total_seconds(),
            feed_age(naive).total_seconds(),
            delta=2,
        )

    def test_none_timestamp(self):
        self.assertIsNone(feed_age(None))
        self.assertFalse(is_feed_stale(None))

    def test_fresh_feed_is_not_stale(self):
        self.assertFalse(is_feed_stale(datetime.now(timezone.utc) - timedelta(minutes=10)))

    def test_stale_feed_detected(self):
        old = datetime.now(timezone.utc) - (FEED_STALE_AFTER + timedelta(minutes=5))
        self.assertTrue(is_feed_stale(old))

    def test_stale_threshold_is_twice_the_cadence(self):
        """Assert the relationship, not the value: the cadence is env-configurable
        because the real scrape schedule lives in an external Prefect flow."""
        self.assertEqual(FEED_STALE_AFTER, FEED_REFRESH_CADENCE * 2)


class TestPurityRatioGuardrail(unittest.TestCase):
    """T7.1: 22K/24K ratio must sit in the 0.90-0.93 band."""

    def test_real_india_rates_pass(self):
        # Observed 5 Sep 2026: 22K 14,190 / 24K 15,480 -> 0.9167
        self.assertEqual(
            check_purity_ratio({"India": {"22K": 14190.0, "24K": 15480.0}}),
            [],
        )

    def test_every_real_market_passes(self):
        """All 7 markets, as stored in the production DB on 5 Sep 2026.

        The band in SEO_TASKS T7.1 (0.90-0.93) would have flagged Bahrain and Oman
        on healthy data. These are the measured values the widened band must clear.
        """
        live = {
            "Saudi Arabia": {"22K": 503.00, "24K": 550.00},   # 0.9145
            "India": {"22K": 14190.0, "24K": 15480.0},        # 0.9167
            "Kuwait": {"22K": 40.61, "24K": 44.18},           # 0.9192
            "Qatar": {"22K": 491.50, "24K": 533.50},          # 0.9213
            "UAE": {"22K": 494.25, "24K": 533.75},            # 0.9260
            "Bahrain": {"22K": 50.70, "24K": 54.40},          # 0.9320
            "Oman": {"22K": 53.15, "24K": 56.70},             # 0.9374
        }
        self.assertEqual(check_purity_ratio(live), [])

    def test_theoretical_ratio_is_inside_the_band(self):
        low, high = PURITY_RATIO_BOUNDS
        self.assertLess(low, 916 / 999)
        self.assertGreater(high, 916 / 999)

    def test_ratio_above_band_flagged(self):
        # The Kerala figure (15,640) against the national 24K (15,480).
        anomalies = check_purity_ratio({"Kerala": {"22K": 15640.0, "24K": 15480.0}})
        self.assertEqual(len(anomalies), 1)
        self.assertIn("Kerala", anomalies[0])

    def test_ratio_below_band_flagged(self):
        anomalies = check_purity_ratio({"Test": {"22K": 100.0, "24K": 200.0}})
        self.assertEqual(len(anomalies), 1)

    def test_mixed_currency_pairing_flagged(self):
        # An AED 22K against an INR 24K is exactly what this guardrail is for.
        anomalies = check_purity_ratio({"Muddle": {"22K": 494.25, "24K": 15480.0}})
        self.assertEqual(len(anomalies), 1)

    def test_incomplete_pair_is_skipped_not_flagged(self):
        self.assertEqual(check_purity_ratio({"India": {"22K": 14190.0}}), [])
        self.assertEqual(check_purity_ratio({"India": {"24K": 15480.0}}), [])
        self.assertEqual(check_purity_ratio({}), [])

    def test_band_bounds(self):
        """Deliberately wider than T7.1's 0.90-0.93 — see rate_utils for the data."""
        self.assertEqual(PURITY_RATIO_BOUNDS, (0.89, 0.95))


class TestStateDivergenceGuardrail(unittest.TestCase):
    """T1.1 acceptance: a state 22K must be within 2% of the national 22K."""

    NATIONAL_22K = 14190.0

    def test_kerala_bug_is_caught(self):
        """The exact defect from T1.1: Kerala published +10.22% over national."""
        divergence = state_divergence_pct(15640.0, self.NATIONAL_22K)
        self.assertAlmostEqual(divergence, 10.22, places=2)
        self.assertGreater(abs(divergence), STATE_TOLERANCE_PCT)

        anomalies = check_state_divergence(self.NATIONAL_22K, {"Kerala": 15640.0})
        self.assertEqual(len(anomalies), 1)
        self.assertIn("Kerala", anomalies[0])

    def test_all_eleven_state_pages_would_have_failed(self):
        """Every state page shipped the same wrong figure, so every one must fail."""
        states = [
            "Kerala", "Tamil Nadu", "Karnataka", "Maharashtra", "Delhi",
            "West Bengal", "Gujarat", "Rajasthan", "Andhra Pradesh",
            "Punjab", "Uttar Pradesh",
        ]
        anomalies = check_state_divergence(
            self.NATIONAL_22K, {s: 15640.0 for s in states}
        )
        self.assertEqual(len(anomalies), len(states))

    def test_genuine_regional_premium_passes(self):
        """Chennai's real rate (14,361) is a 1.2% premium — inside tolerance."""
        divergence = state_divergence_pct(14361.0, self.NATIONAL_22K)
        self.assertLess(abs(divergence), STATE_TOLERANCE_PCT)
        self.assertEqual(
            check_state_divergence(self.NATIONAL_22K, {"Chennai": 14361.0}), []
        )

    def test_exact_national_rate_passes(self):
        self.assertEqual(
            check_state_divergence(self.NATIONAL_22K, {"Anywhere": self.NATIONAL_22K}), []
        )

    def test_boundary_just_inside_and_just_outside(self):
        inside = self.NATIONAL_22K * (1 + (STATE_TOLERANCE_PCT - 0.01) / 100)
        outside = self.NATIONAL_22K * (1 + (STATE_TOLERANCE_PCT + 0.01) / 100)
        self.assertEqual(check_state_divergence(self.NATIONAL_22K, {"A": inside}), [])
        self.assertEqual(len(check_state_divergence(self.NATIONAL_22K, {"B": outside})), 1)

    def test_negative_divergence_also_flagged(self):
        self.assertEqual(
            len(check_state_divergence(self.NATIONAL_22K, {"Low": 12000.0})), 1
        )

    def test_missing_values_are_skipped(self):
        self.assertEqual(check_state_divergence(None, {"Kerala": 15640.0}), [])
        self.assertEqual(check_state_divergence(self.NATIONAL_22K, {"Kerala": None}), [])

    def test_zero_national_raises_rather_than_dividing(self):
        with self.assertRaises(ValueError):
            state_divergence_pct(14190.0, 0)


if __name__ == "__main__":
    unittest.main()
