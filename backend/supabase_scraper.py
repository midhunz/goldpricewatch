"""
Gulf News gold rate scraper (current + historical) -> Supabase `gold_rates` table.

Replaces a lost ingestion job that used to keep the public site's Supabase
`gold_rates` table fresh (it stopped updating around 2026-05-12).

For each country subpage on gulfnews.com/gold-forex, this pulls BOTH:
  - the current live rate table
  - the "historical-gold-rate-table" (30-day date/purity/price table that's
    server-rendered into the page HTML)

UAE has no working historical subpage (connection resets, and the main
/gold-forex page doesn't carry the historical table either) so it's
current-only, same as the existing SQLite scraper.py.

Requires a direct Postgres connection string with INSERT permission on
`gold_rates` (SUBA_BASE_URL env var, read from .env).

Usage:
    python supabase_scraper.py
"""

import os
import re
import sys
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

POSTGRES_URL = os.environ.get("SUBA_BASE_URL")

BASE_URL = "https://gulfnews.com/gold-forex"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def get_soup(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return BeautifulSoup(response.content, "lxml")


def parse_gulfnews_date(date_str: str):
    """Parse '2nd Sept 2026' / '31st Aug 2026' -> datetime (UTC noon)."""
    m = re.match(r"(\d{1,2})[a-zA-Z]*\s+([A-Za-z]+)\.?\s+(\d{4})", date_str.strip())
    if not m:
        return None
    day, mon_str, year = m.groups()
    mon = MONTHS.get(mon_str.lower())
    if not mon:
        return None
    return datetime(int(year), mon, int(day), 12, 0, 0, tzinfo=timezone.utc)


def clean_price(text: str) -> str:
    return text.replace(",", "").replace("₹", "").strip()


# ---------------------------------------------------------------------------
# Current rates (same logic as scraper.py)
# ---------------------------------------------------------------------------

def scrape_uae_rates():
    soup = get_soup(BASE_URL)
    rates = []
    section = soup.find("h3", string=lambda t: t and "UAE Gold Rates" in t)
    if section:
        table = section.find_next("table")
        if table:
            for row in table.find_all("tr")[1:]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    rates.append({
                        "region": "UAE",
                        "purity": cols[0].get_text(strip=True),
                        "price": clean_price(cols[1].get_text(strip=True)),
                        "currency": "AED",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
    return rates


def scrape_country_current_and_history(country, url_suffix, currency):
    """Scrape both current rate and the 30-day historical table for one country."""
    soup = get_soup(f"{BASE_URL}/{url_suffix}")
    records = []

    # --- current rate: first plain rate table (not the historical one) ---
    for table in soup.find_all("table"):
        if table.find_parent(id="historical-gold-rate-table"):
            continue
        rows = table.find_all("tr")
        found = []
        for row in rows[1:]:
            cols = row.find_all("td")
            if len(cols) >= 2:
                purity = cols[0].get_text(strip=True)
                price = cols[1].get_text(strip=True)
                if "K" in purity or "Carat" in purity:
                    found.append({
                        "region": country,
                        "purity": purity,
                        "price": clean_price(price),
                        "currency": currency,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
        if found:
            records.extend(found)
            break

    # --- historical 30-day table ---
    hist_div = soup.find(id="historical-gold-rate-table")
    if hist_div:
        table = hist_div.find("table")
        if table:
            headers = [th.get_text(strip=True) for th in table.find("thead").find_all("th")]
            purity_cols = headers[1:]  # skip "Date"
            for row in table.find("tbody").find_all("tr"):
                cols = row.find_all("td")
                if len(cols) != len(headers):
                    continue
                dt = parse_gulfnews_date(cols[0].get_text(strip=True))
                if not dt:
                    continue
                for i, purity in enumerate(purity_cols):
                    price = cols[i + 1].get_text(strip=True)
                    if not price:
                        continue
                    records.append({
                        "region": country,
                        "purity": purity,
                        "price": clean_price(price),
                        "currency": currency,
                        "created_at": dt.isoformat(),
                    })
    return records


COUNTRIES = [
    ("India", "india-gold-prices", "INR"),
    ("Oman", "oman-gold-prices", "OMR"),
    ("Qatar", "qatar-gold-prices", "QAR"),
    ("Saudi Arabia", "saudi-gold-prices", "SAR"),
    ("Bahrain", "bahrain-gold-prices", "BHD"),
    ("Kuwait", "kuwait-gold-prices", "KWD"),
]


def get_all_records():
    all_records = []

    try:
        uae = scrape_uae_rates()
        logger.info(f"UAE: {len(uae)} current rates (no historical source available)")
        all_records.extend(uae)
    except Exception as e:
        logger.error(f"Failed to scrape UAE: {e}")

    for country, suffix, currency in COUNTRIES:
        try:
            recs = scrape_country_current_and_history(country, suffix, currency)
            logger.info(f"{country}: {len(recs)} records (current + historical)")
            all_records.extend(recs)
        except Exception as e:
            logger.error(f"Failed to scrape {country}: {e}")

    return all_records


# ---------------------------------------------------------------------------
# Insert into Supabase (direct Postgres connection)
# ---------------------------------------------------------------------------

def insert_records(records):
    if not POSTGRES_URL:
        logger.error("SUBA_BASE_URL is not set in the environment")
        sys.exit(1)

    import psycopg2
    from psycopg2.extras import execute_values

    conn = psycopg2.connect(POSTGRES_URL, connect_timeout=15)
    cur = conn.cursor()
    execute_values(
        cur,
        "INSERT INTO gold_rates (region, purity, price, currency, created_at) VALUES %s",
        [(r["region"], r["purity"], r["price"], r["currency"], r["created_at"]) for r in records],
    )
    conn.commit()
    cur.close()
    conn.close()


if __name__ == "__main__":
    records = get_all_records()
    logger.info(f"Total scraped records (current + historical): {len(records)}")
    if not records:
        logger.warning("Nothing scraped, exiting")
        sys.exit(0)

    insert_records(records)
    logger.info(f"Inserted {len(records)} rows into Supabase gold_rates")
