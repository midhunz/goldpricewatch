import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
from models import GoldRate, GoldNews, APIKey
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Connection Strings
SQLITE_URL = "sqlite:///./data/goldrate.db"
# Direct Postgres URL for schema changes.
# Never hardcode credentials here - this repo is public.
POSTGRES_URL = os.getenv("SUBA_BASE_URL") or os.getenv("SUPABASE_POSTGRES_URL")
if not POSTGRES_URL:
    raise SystemExit("Set SUBA_BASE_URL before running this migration.")

def migrate_data():
    logger.info("Starting migration from SQLite to Supabase...")

    # 1. Connect to SQLite (Source)
    sqlite_engine = create_engine(SQLITE_URL)
    SQLiteSession = sessionmaker(bind=sqlite_engine)
    sqlite_session = SQLiteSession()
    
    try:
        rates = sqlite_session.query(GoldRate).all()
        news = sqlite_session.query(GoldNews).all()
        api_keys = sqlite_session.query(APIKey).all()
        logger.info(f"Fetched {len(rates)} rates, {len(news)} news articles, {len(api_keys)} API keys from SQLite.")
    except Exception as e:
        logger.error(f"Error reading from SQLite: {e}")
        return
    finally:
        sqlite_session.close()

    # 2. Connect to Postgres (Destination)
    pg_engine = create_engine(POSTGRES_URL)
    PgSession = sessionmaker(bind=pg_engine)
    pg_session = PgSession()

    try:
        # Create tables if they don't exist
        logger.info("Creating tables in Supabase...")
        Base.metadata.create_all(pg_engine)
        
        # Check if data already exists to avoid duplicates (simple check)
        existing_rates_count = pg_session.query(GoldRate).count()
        if existing_rates_count > 0:
            logger.warning(f"Supabase already has {existing_rates_count} rates. Skipping migration to avoid duplicates.")
            # For a real migration, we might want to truncate or upsert. 
            # For now, let's assume if it's empty we fill it.
            if existing_rates_count > 100: # Arbitrary threshold
                 return

        # Bulk Insert Rates
        logger.info("Migrating Gold Rates...")
        for r in rates:
            pg_session.merge(GoldRate(
                region=r.region,
                purity=r.purity,
                price=r.price,
                currency=r.currency,
                created_at=r.created_at
            ))
        
        # Bulk Insert News
        logger.info("Migrating News...")
        for n in news:
            pg_session.merge(GoldNews(
                title=n.title,
                summary=n.summary,
                source=n.source,
                url=n.url,
                image_url=n.image_url,
                slug=n.slug,
                published_at=n.published_at,
                created_at=n.created_at
            ))
            
        # Bulk Insert API Keys
        logger.info("Migrating API Keys...")
        for k in api_keys:
            pg_session.merge(APIKey(
                key=k.key,
                owner=k.owner,
                is_active=k.is_active,
                tier=k.tier,
                created_at=k.created_at
            ))

        pg_session.commit()
        logger.info("Migration completed successfully!")

    except Exception as e:
        logger.error(f"Error writing to Supabase: {e}")
        pg_session.rollback()
    finally:
        pg_session.close()

if __name__ == "__main__":
    migrate_data()
