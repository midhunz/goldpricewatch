from sqlalchemy.orm import Session
from models import GoldRate
from scraper import get_all_rates
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def scrape_and_store_rates(db: Session):
    start_time = datetime.now()
    logger.info(f"Starting scheduled scrape job at {start_time.strftime('%Y-%m-%d %H:%M:%S')}...")
    try:
        rates_data = get_all_rates()
        if not rates_data:
            logger.warning("No rates fetched.")
            return

        # Optional: Clear old rates for "latest" view or just append for history.
        # For this requirement, we want "latest data stored". 
        # If we want history, we just append. 
        # But the API needs to fetch the *latest*.
        # Let's just append everything. The API will query the latest entries.
        
        # To make "latest" query easy, we could delete old "current" rates or just insert new ones.
        # Let's insert new ones.
        
        for rate in rates_data:
            db_rate = GoldRate(
                region=rate["region"],
                purity=rate["purity"],
                price=rate["price"],
                currency=rate["currency"]
            )
            db.add(db_rate)
        
        db.commit()
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"✅ Successfully stored {len(rates_data)} rates in {duration:.2f} seconds")
        logger.info(f"Next scrape scheduled in 1 hour")
        
    except Exception as e:
        logger.error(f"❌ Error in scrape_and_store_rates: {e}")
        db.rollback()
    finally:
        db.close()
