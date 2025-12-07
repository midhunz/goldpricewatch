from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
import logging
from datetime import datetime, timedelta

from database import engine, Base, get_db, SessionLocal
from models import GoldRate, GoldNews
from tasks import scrape_and_store_rates

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

# Scheduler setup
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting scheduler...")
    # Run immediately on startup
    db = SessionLocal()
    scrape_and_store_rates(db)
    db.close()
    
    # Schedule to run every 1 hour
    scheduler.add_job(lambda: run_scrape_job(), 'interval', hours=1)
    scheduler.start()
    yield
    # Shutdown
    logger.info("Shutting down scheduler...")
    scheduler.shutdown()

def run_scrape_job():
    db = SessionLocal()
    try:
        scrape_and_store_rates(db)
    finally:
        db.close()

app = FastAPI(title="GoldPriceWatch API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Gold Rate API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/rates")
def read_rates(db: Session = Depends(get_db)):
    # 1. Get Latest Rates
    # Fetch recent rates (last 500) and deduplicate by region/purity to get the absolute latest for each
    recent_rates = db.query(GoldRate).order_by(GoldRate.created_at.desc()).limit(500).all()
    
    latest_rates_map = {}
    for rate in recent_rates:
        key = (rate.region, rate.purity)
        if key not in latest_rates_map:
            latest_rates_map[key] = rate
            
    latest_rates = list(latest_rates_map.values())
    
    if not latest_rates:
        return []
        
    # Use the timestamp of the most recent rate as the reference point
    latest_time = latest_rates[0].created_at

    # 2. Get Reference Rates (Yesterday or Oldest)
    # Target: 24 hours ago
    target_time = latest_time - timedelta(days=1)
    
    # Find the entry closest to target_time, or just use oldest if not enough history
    # We'll look for a batch created before (latest_time - 20 hours) to be safe "yesterday"
    # If not found, we fallback to the oldest available batch that is NOT the latest batch.
    
    cutoff_time = latest_time - timedelta(hours=20)
    
    reference_entry = db.query(GoldRate).filter(GoldRate.created_at <= cutoff_time).order_by(GoldRate.created_at.desc()).first()
    
    if not reference_entry:
        # Fallback: Get the absolute oldest entry that is NOT from the latest batch
        # (This handles the case where we just started and have maybe 2 scrapes 1 hour apart)
        # We want to show *some* change if possible.
        reference_entry = db.query(GoldRate).filter(GoldRate.created_at < latest_time).order_by(GoldRate.created_at.asc()).first()

    reference_rates_map = {}
    if reference_entry:
        ref_time = reference_entry.created_at
        # Fetch that entire batch
        # Assuming batch items are within a few seconds/minutes
        # We can filter by a small window around ref_time or just >= ref_time if we are careful.
        # Better: filter by created_at between ref_time and ref_time + 1 min
        # Or simpler: just match by region/purity from the query if we fetched all history? No, too heavy.
        
        # Let's fetch rates with created_at == ref_time (exact match might fail due to ms)
        # So we use a small range.
        ref_rates_list = db.query(GoldRate).filter(
            GoldRate.created_at >= ref_time, 
            GoldRate.created_at < ref_time + timedelta(minutes=5)
        ).all()
        
        for r in ref_rates_list:
            key = f"{r.region}-{r.purity}"
            reference_rates_map[key] = r.price

    # 3. Helper to parse price
    def parse_price(price_str):
        if not price_str: return 0.0
        clean = price_str
        if "₹" in price_str:
            clean = price_str.split("₹")[0]
        clean = clean.replace(",", "").strip()
        try:
            return float(clean)
        except ValueError:
            return 0.0

    # 4. Build Response
    response = []
    for rate in latest_rates:
        key = f"{rate.region}-{rate.purity}"
        current_price = parse_price(rate.price)
        
        change = 0.0
        change_percent = 0.0
        
        if key in reference_rates_map:
            prev_price = parse_price(reference_rates_map[key])
            if prev_price > 0:
                change = current_price - prev_price
                change_percent = (change / prev_price) * 100
        
        response.append({
            "region": rate.region,
            "purity": rate.purity,
            "price": rate.price,
            "currency": rate.currency,
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "updated_at": rate.created_at.isoformat() if rate.created_at else None
        })
        
    return response

@app.get("/api/rates/history")
def read_rates_history(
    region: str, 
    purity: str, 
    days: int = 7, 
    db: Session = Depends(get_db)
):
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # Query rates
    rates = db.query(GoldRate).filter(
        GoldRate.region == region,
        GoldRate.purity == purity,
        GoldRate.created_at >= cutoff_date
    ).order_by(GoldRate.created_at.asc()).all()
    
    # Parse prices and format response
    history = []
    for rate in rates:
        # Parse price string to float
        price_val = 0.0
        if rate.price:
            clean = rate.price
            if "₹" in clean:
                clean = clean.split("₹")[0]
            clean = clean.replace(",", "").strip()
            try:
                price_val = float(clean)
            except ValueError:
                pass
        
        history.append({
            "timestamp": rate.created_at.isoformat(),
            "price": price_val,
            "currency": rate.currency
        })
        
    return history

@app.get("/api/news")
def get_news(limit: int = 20, db: Session = Depends(get_db)):
    """Get latest gold news articles"""
    news = db.query(GoldNews).order_by(GoldNews.published_at.desc()).limit(limit).all()
    
    return [{
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "source": article.source,
        "url": article.url,
        "image_url": article.image_url,
        "slug": article.slug,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "created_at": article.created_at.isoformat() if article.created_at else None
    } for article in news]

@app.get("/api/news/{slug}")
def get_news_by_slug(slug: str, db: Session = Depends(get_db)):
    """Get a single news article by slug"""
    article = db.query(GoldNews).filter(GoldNews.slug == slug).first()
    
    if not article:
        return {"error": "Article not found"}
    
    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "source": article.source,
        "url": article.url,
        "image_url": article.image_url,
        "slug": article.slug,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "created_at": article.created_at.isoformat() if article.created_at else None
    }
