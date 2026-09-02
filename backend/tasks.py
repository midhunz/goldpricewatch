from sqlalchemy.orm import Session
from models import GoldRate
from scraper import get_all_rates
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def scrape_news_task():
    """
    Task to fetch gold news from multiple sources.
    Runs every hour.
    """
    from multi_news_scraper import fetch_all_gold_news, cleanup_old_news
    
    start_time = datetime.now()
    logger.info(f"Starting news scrape job at {start_time.strftime('%Y-%m-%d %H:%M:%S')}...")
    
    try:
        # Fetch news from all sources
        new_count = fetch_all_gold_news()
        
        # Cleanup old news (keep 30 days)
        cleanup_old_news(days=30)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"✅ News scrape completed in {duration:.2f} seconds. Added {new_count} articles.")
        logger.info(f"Next news scrape scheduled in 1 hour")
        
    except Exception as e:
        logger.error(f"❌ Error in news scrape: {e}")

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


def run_ai_calculations_task():
    """
    Task to calculate and store all AI results.
    Runs every 6 hours.
    """
    from ai_scheduler import run_ai_calculations, cleanup_old_results
    
    start_time = datetime.now()
    logger.info(f"Starting AI calculations job at {start_time.strftime('%Y-%m-%d %H:%M:%S')}...")
    
    try:
        # Run all AI calculations
        run_ai_calculations()
        
        # Cleanup old results (keep 30 days)
        cleanup_old_results(days_to_keep=30)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"✅ AI calculations completed in {duration:.2f} seconds")
        logger.info(f"Next AI calculation scheduled in 6 hours")
        
    except Exception as e:
        logger.error(f"❌ Error in AI calculations: {e}")
