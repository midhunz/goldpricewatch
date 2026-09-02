import os
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supabase connection. Never hardcode credentials here - this repo is public.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUBA_BASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL (or SUBA_BASE_URL) before running this script.")

API_KEY = os.getenv("API_KEY_TO_CHECK")
if not API_KEY:
    raise SystemExit("Set API_KEY_TO_CHECK before running this script.")

def check_key():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM api_keys WHERE key = :key"), {"key": API_KEY}).fetchone()
        if result:
            logger.info(f"✅ Key found: {result}")
        else:
            logger.warning("❌ Key NOT found!")
            # Insert it if missing
            logger.info("Inserting key...")
            conn.execute(text("INSERT INTO api_keys (key, owner, is_active, tier, created_at) VALUES (:key, 'admin', true, 'free', now())"), {"key": API_KEY})
            conn.commit()
            logger.info("✅ Key inserted.")

if __name__ == "__main__":
    check_key()
