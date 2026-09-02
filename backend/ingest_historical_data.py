"""
Historical Data Ingestion Script

Downloads and stores historical data for backtesting and model validation:
1. Gold prices (USD) from FreeGoldAPI.com -- no API key needed
2. 10-Year Treasury yields from FRED DGS10.txt -- no API key needed
3. USD trade-weighted index from FRED DTWEXBGS.txt -- no API key needed

Safe to re-run: skips dates that already exist in the database.

Usage:
    python ingest_historical_data.py          # all 3 datasets
    python ingest_historical_data.py gold     # gold prices only
    python ingest_historical_data.py yields   # treasury yields only
    python ingest_historical_data.py usd      # usd index only
"""

import csv
import io
import logging
import ssl
import sys
import urllib.request
from datetime import datetime, date

from database import engine, Base, SessionLocal
from models import HistoricalGoldPrice, HistoricalTreasuryYield, HistoricalUsdIndex

# Build SSL context using certifi if available (fixes macOS cert issues)
try:
    import certifi
    _ssl_context = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _ssl_context = ssl.create_default_context()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ============== Data Source URLs ==============
GOLD_PRICE_URL = "https://freegoldapi.com/data/latest.csv"
TREASURY_YIELD_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
USD_INDEX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS"

USER_AGENT = "Mozilla/5.0 (GoldPriceWatch/1.0)"


def _download(url: str) -> str:
    """Download a URL and return the text content."""
    logger.info(f"Downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=_ssl_context) as response:
        data = response.read().decode("utf-8")
    logger.info(f"Downloaded {len(data):,} bytes")
    return data


def _get_existing_dates(db, model) -> set:
    """Get all dates already in a table to avoid duplicates."""
    rows = db.query(model.date).all()
    return {row[0] for row in rows}


# ============== Gold Prices ==============

def ingest_gold_prices(db):
    """
    Download daily gold prices from FreeGoldAPI.com and insert into DB.

    CSV format: date,price,source
    Example:    2025-02-07,2860.56,"London Bullion Market"
    """
    logger.info("=== Ingesting historical gold prices ===")
    raw = _download(GOLD_PRICE_URL)

    existing_dates = _get_existing_dates(db, HistoricalGoldPrice)
    logger.info(f"Found {len(existing_dates)} existing gold price records")

    reader = csv.DictReader(io.StringIO(raw))
    records = []

    for row in reader:
        date_str = row.get("date", "").strip()
        price_str = row.get("price", "").strip()

        if not date_str or not price_str:
            continue

        try:
            price = float(price_str)
        except ValueError:
            continue

        if price <= 0:
            continue

        try:
            d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        if d in existing_dates:
            continue

        records.append(HistoricalGoldPrice(
            date=d,
            price_usd=round(price, 2),
            source="freegoldapi"
        ))
        existing_dates.add(d)

    if records:
        db.bulk_save_objects(records)
        db.commit()

    logger.info(f"Inserted {len(records)} new gold price records")
    return len(records)


# ============== FRED CSV Parser ==============

def _parse_fred_csv(raw: str):
    """
    Parse a FRED graph CSV download.

    Format (CSV):
        observation_date,SERIES_ID
        1962-01-02,4.06
        1962-01-03,.          <-- missing value (market holiday)
        ...

    Yields (date, float_value) tuples, skipping missing values ('.').
    """
    reader = csv.reader(io.StringIO(raw))
    header = next(reader, None)  # Skip header row
    if not header:
        return

    for row in reader:
        if len(row) < 2:
            continue

        date_str = row[0].strip()
        value_str = row[1].strip()

        if value_str == "." or not value_str:
            continue

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            val = float(value_str)
            yield d, val
        except (ValueError, TypeError):
            continue


# ============== Treasury Yields ==============

def ingest_treasury_yields(db):
    """
    Download daily 10-Year Treasury yields from FRED and insert into DB.
    Series: DGS10 (daily, 1962-present).
    """
    logger.info("=== Ingesting historical Treasury yields ===")
    raw = _download(TREASURY_YIELD_URL)

    existing_dates = _get_existing_dates(db, HistoricalTreasuryYield)
    logger.info(f"Found {len(existing_dates)} existing yield records")

    records = []
    for d, val in _parse_fred_csv(raw):
        if d in existing_dates:
            continue
        records.append(HistoricalTreasuryYield(
            date=d,
            yield_10y=round(val, 2),
            source="fred_dgs10"
        ))
        existing_dates.add(d)

    if records:
        db.bulk_save_objects(records)
        db.commit()

    logger.info(f"Inserted {len(records)} new Treasury yield records")
    return len(records)


# ============== USD Index ==============

def ingest_usd_index(db):
    """
    Download daily USD trade-weighted broad index from FRED and insert into DB.
    Series: DTWEXBGS (daily, 2006-present, indexed Jan 2006=100).
    """
    logger.info("=== Ingesting historical USD index ===")
    raw = _download(USD_INDEX_URL)

    existing_dates = _get_existing_dates(db, HistoricalUsdIndex)
    logger.info(f"Found {len(existing_dates)} existing USD index records")

    records = []
    for d, val in _parse_fred_csv(raw):
        if d in existing_dates:
            continue
        records.append(HistoricalUsdIndex(
            date=d,
            usd_index=round(val, 2),
            source="fred_dtwexbgs"
        ))
        existing_dates.add(d)

    if records:
        db.bulk_save_objects(records)
        db.commit()

    logger.info(f"Inserted {len(records)} new USD index records")
    return len(records)


# ============== Main ==============

def run_all():
    """Run all 3 ingestions."""
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        total = 0
        total += ingest_gold_prices(db)
        total += ingest_treasury_yields(db)
        total += ingest_usd_index(db)
        logger.info(f"=== Done. Total new records inserted: {total} ===")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def run_single(dataset: str):
    """Run ingestion for a single dataset."""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if dataset == "gold":
            ingest_gold_prices(db)
        elif dataset == "yields":
            ingest_treasury_yields(db)
        elif dataset == "usd":
            ingest_usd_index(db)
        else:
            logger.error(f"Unknown dataset: {dataset}. Use: gold, yields, usd")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_single(sys.argv[1])
    else:
        run_all()
