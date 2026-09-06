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
