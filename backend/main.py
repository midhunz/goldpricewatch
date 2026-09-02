from fastapi import FastAPI, Depends, HTTPException, Security, status, Response
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any, Optional, Dict
import hashlib
import json
import os
import secrets

from database import engine, Base, get_db, SessionLocal
from models import (
    GoldRate, GoldNews, APIKey,
    MarketMoodResult, NewsSentimentResult, PredictionResult, PredictionAccuracy,
    ExternalFactorsResult,
    GeopoliticalEvent, GeoRiskResult, GeoBacktestResult, TrainedModel
)
from tasks import scrape_and_store_rates, run_ai_calculations_task, scrape_news_task
from prediction import predict_future_prices
from export import export_rates_to_csv, export_news_to_csv
from model_trainer import (
    get_model_metrics_history,
    get_model_drift_status,
    compute_feature_drift,
)
from drift import get_concept_drift_status

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============== In-Memory Cache for AI Endpoints ==============
class AICache:
    """
    Simple in-memory cache with TTL for AI endpoints.
    Reduces database queries for frequently accessed AI results.
    """
    
    def __init__(self, default_ttl_seconds: int = 3600):  # 1 hour default
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl_seconds
    
    def _make_key(self, endpoint: str, **params) -> str:
        """Create a unique cache key from endpoint and parameters."""
        param_str = json.dumps(params, sort_keys=True) if params else ""
        key_data = f"{endpoint}:{param_str}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, endpoint: str, **params) -> Optional[Any]:
        """Get cached value if exists and not expired."""
        key = self._make_key(endpoint, **params)
        
        if key in self._cache:
            entry = self._cache[key]
            if time.time() < entry['expires_at']:
                logger.debug(f"Cache HIT: {endpoint}")
                return entry['data']
            else:
                # Expired, remove from cache
                del self._cache[key]
                logger.debug(f"Cache EXPIRED: {endpoint}")
        
        logger.debug(f"Cache MISS: {endpoint}")
        return None
    
    def set(self, endpoint: str, data: Any, ttl_seconds: int = None, **params):
        """Store value in cache with TTL."""
        key = self._make_key(endpoint, **params)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        
        self._cache[key] = {
            'data': data,
            'expires_at': time.time() + ttl,
            'created_at': time.time()
        }
        logger.debug(f"Cache SET: {endpoint} (TTL: {ttl}s)")
    
    def invalidate(self, endpoint: str = None, **params):
        """Invalidate cache entries. If endpoint is None, clear all."""
        if endpoint is None:
            self._cache.clear()
            logger.info("Cache CLEARED: All entries")
        else:
            key = self._make_key(endpoint, **params)
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache INVALIDATED: {endpoint}")
    
    def stats(self) -> Dict:
        """Get cache statistics."""
        now = time.time()
        valid_entries = sum(1 for e in self._cache.values() if now < e['expires_at'])
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._cache) - valid_entries
        }


# Initialize cache with 30 minute TTL
ai_cache = AICache(default_ttl_seconds=1800)  # 30 minutes


# Security & Rate Limiting
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Admin authentication.
#
# The regular X-API-KEY is shipped to the browser in the frontend bundle
# (NEXT_PUBLIC_API_KEY), so it is public by design and can never gate admin
# actions. Admin endpoints therefore require a separate secret that is only
# ever held server-side, supplied via the ADMIN_API_KEY environment variable.
# If it is not configured, admin endpoints stay closed rather than open.
ADMIN_KEY_NAME = "X-ADMIN-KEY"
admin_key_header = APIKeyHeader(name=ADMIN_KEY_NAME, auto_error=False)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def require_admin(admin_key: str = Security(admin_key_header)):
    """Gate admin-only endpoints on a server-side-only shared secret."""
    if not ADMIN_API_KEY:
        logger.warning("Admin endpoint called but ADMIN_API_KEY is not configured; denying.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API is not configured"
        )

    # Compare as bytes: compare_digest rejects non-ASCII str and would 500 otherwise.
    if not admin_key or not secrets.compare_digest(
        admin_key.encode("utf-8"), ADMIN_API_KEY.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return True

# In-memory API key cache — avoids DB round-trip on every request
# key_string -> {"record": APIKey-like dict, "expires_at": float}
_api_key_cache: Dict[str, Dict] = {}
_API_KEY_CACHE_TTL = 300  # 5 minutes

# Simple in-memory rate limiter (for demonstration/low volume)
# In production, this should use Redis
rate_limit_store = defaultdict(list)

def check_rate_limit(key_id: int, tier: str):
    now = time.time()
    # 1 minute window
    window = 60
    # Clean up old timestamps
    rate_limit_store[key_id] = [ts for ts in rate_limit_store[key_id] if now - ts < window]
    
    # Define limits
    limit = 60 if tier == "free" else 1000 # 60 req/min for free, 1000 for paid
    
    if len(rate_limit_store[key_id]) >= limit:
        return False
    
    rate_limit_store[key_id].append(now)
    return True


class _CachedKey:
    """Lightweight stand-in for the APIKey ORM object in cached responses."""
    def __init__(self, id: int, key: str, owner: str, tier: str):
        self.id = id
        self.key = key
        self.owner = owner
        self.tier = tier
        self.is_active = 1


async def get_api_key(
    api_key_header: str = Security(api_key_header),
    db: Session = Depends(get_db)
):
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key missing"
        )

    # Check in-memory cache first (avoids DB round-trip)
    now = time.time()
    cached = _api_key_cache.get(api_key_header)
    if cached and now < cached["expires_at"]:
        key_obj = cached["record"]
        if not check_rate_limit(key_obj.id, key_obj.tier):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Upgrade your tier for more requests."
            )
        return key_obj

    # Cache miss — query DB
    key_record = db.query(APIKey).filter(
        APIKey.key == api_key_header,
        APIKey.is_active == 1
    ).first()

    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key"
        )

    # Store in cache
    cached_obj = _CachedKey(
        id=key_record.id,
        key=key_record.key,
        owner=key_record.owner,
        tier=key_record.tier,
    )
    _api_key_cache[api_key_header] = {
        "record": cached_obj,
        "expires_at": now + _API_KEY_CACHE_TTL,
    }

    # Rate Limiting Check
    if not check_rate_limit(key_record.id, key_record.tier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Upgrade your tier for more requests."
        )

    return key_record

# Create tables
Base.metadata.create_all(bind=engine)

# Add new columns if they don't exist (for existing databases)
def _migrate_external_factors_columns():
    """Add new factor columns to external_factors_results if missing."""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    if 'external_factors_results' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('external_factors_results')}
        new_cols = {
            'treasury_yield_10y': 'FLOAT',
            'interest_rate_impact': 'FLOAT',
            'central_bank_net_change': 'FLOAT',
            'central_bank_impact': 'FLOAT',
        }
        with engine.begin() as conn:
            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f'ALTER TABLE external_factors_results ADD COLUMN {col_name} {col_type}'))
                        logger.info(f"Added column {col_name} to external_factors_results")
                    except Exception as e:
                        logger.debug(f"Column {col_name} may already exist: {e}")

_migrate_external_factors_columns()

# Scheduler setup
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting scheduler...")
    # Run scraper immediately on startup (in background to avoid blocking API)
    scheduler.add_job(run_scrape_job, 'date', run_date=datetime.now() + timedelta(seconds=5))
    
    # Run news scraper on startup (after 10 seconds)
    scheduler.add_job(run_news_scrape_job, 'date', run_date=datetime.now() + timedelta(seconds=10))
    
    # Run AI calculations on startup (after 60 seconds to let scrapers finish)
    scheduler.add_job(run_ai_job, 'date', run_date=datetime.now() + timedelta(seconds=60))
    
    # Run initial model training on startup (after 120 seconds, needs historical data)
    scheduler.add_job(run_model_training_job, 'date', run_date=datetime.now() + timedelta(seconds=120))
    
    # Schedule rate scraper to run every 1 hour
    scheduler.add_job(lambda: run_scrape_job(), 'interval', hours=1, id='scraper_hourly')
    
    # Schedule news scraper to run every 1 hour
    scheduler.add_job(lambda: run_news_scrape_job(), 'interval', hours=1, id='news_scraper_hourly')
    
    # Schedule AI calculations to run every 6 hours
    scheduler.add_job(lambda: run_ai_job(), 'interval', hours=6, id='ai_calculations_6h')
    
    # Schedule model retraining weekly (every 7 days)
    scheduler.add_job(lambda: run_model_training_job(), 'interval', days=7, id='model_training_weekly')
    
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

def run_news_scrape_job():
    """Run multi-source news scraper."""
    logger.info("Running news scrape job...")
    try:
        scrape_news_task()
    except Exception as e:
        logger.error(f"Error in news scrape job: {e}")

def run_model_training_job():
    """Run OLS model training from historical data."""
    logger.info("Running model training job...")
    try:
        from model_trainer import train_and_store, is_model_stale
        db = SessionLocal()
        try:
            if is_model_stale(db, max_age_days=7):
                result = train_and_store(db)
                if result:
                    logger.info(
                        f"Model trained: R²={result['r_squared']}, "
                        f"MAE={result['mae']}%, points={result['training_points']}"
                    )
                else:
                    logger.warning("Model training returned None (insufficient data?)")
            else:
                logger.info("Model is fresh, skipping training")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in model training job: {e}")

def run_ai_job():
    """Run AI calculations and store results, then refresh cache."""
    logger.info("Running AI calculations job...")
    try:
        run_ai_calculations_task()
        # Invalidate cache after new results are generated
        ai_cache.invalidate()
        logger.info("Cache invalidated after AI calculations completed")
    except Exception as e:
        logger.error(f"Error in AI job: {e}")

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
def read_rates(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    # Cache rates for 5 minutes (scraper runs hourly, rates change slowly)
    cached = ai_cache.get("rates")
    if cached is not None:
        return cached

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

    # 2. Get Reference Rates (Yesterday's Closing / Last available before today)
    cutoff_time = latest_time - timedelta(hours=20)
    
    # DEBUG LOGGING
    logger.info(f"CALC DEBUG: Latest Time: {latest_time}, Cutoff: {cutoff_time}")
    
    # Fetch rates from 48 hours ago to cutoff_time
    history_start = latest_time - timedelta(hours=48)
    
    # Get all rates from history window
    history_rates = db.query(GoldRate).filter(
        GoldRate.created_at >= history_start,
        GoldRate.created_at <= cutoff_time
    ).order_by(GoldRate.created_at.desc()).all()
    
    logger.info(f"CALC DEBUG: Found {len(history_rates)} history rates between {history_start} and {cutoff_time}")
    
    reference_rates_map = {}
    
    # Populate reference map with the *most recent* rate found in that past window for each key
    for rate in history_rates:
        key = f"{rate.region}-{rate.purity}"
        if key not in reference_rates_map:
            reference_rates_map[key] = rate.price
            # Trace just one key to avoid spam
            if rate.region == "India" and rate.purity == "24 Carat":
                logger.info(f"CALC DEBUG: Found ref for India-24 Carat: {rate.price} at {rate.created_at}")

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
            if key == "India-24 Carat":
                 logger.info(f"CALC DEBUG: India-24 Calc: Curr={current_price}, Prev={prev_price}")
            
            if prev_price > 0:
                change = current_price - prev_price
                change_percent = (change / prev_price) * 100
        else:
            if key == "India-24 Carat":
                logger.info("CALC DEBUG: India-24 Carat NOT found in reference map")
        
        response.append({
            "region": rate.region,
            "purity": rate.purity,
            "price": rate.price,
            "currency": rate.currency,
            "change": round(change, 2),
            "change_percent": round(change_percent, 2),
            "updated_at": rate.created_at.isoformat() if rate.created_at else None
        })

    ai_cache.set("rates", response, ttl_seconds=300)
    return response

@app.get("/api/rates/history")
def read_rates_history(
    region: str, 
    purity: str, 
    days: int = 7, 
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
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
def get_news(
    limit: int = 20, 
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """Get latest gold news articles. Cached for 10 minutes."""
    cached = ai_cache.get("news", limit=limit)
    if cached is not None:
        return cached

    news = db.query(GoldNews).order_by(GoldNews.published_at.desc()).limit(limit).all()
    
    result = [{
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

    ai_cache.set("news", result, ttl_seconds=600, limit=limit)
    return result

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

@app.get("/api/prediction")
def get_prediction(
    region: str,
    purity: str,
    days: int = 7,  # Not used anymore, always returns 7-day predictions from stored data
    history_days: int = 30, # Not used anymore
    use_factors: bool = False, # Not used anymore, stored results always include factors
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get price predictions for a region/purity.
    Returns pre-calculated results from the database (updated every 6 hours).
    Cached for 1 hour to reduce database load.
    """
    # Check cache first
    cached = ai_cache.get("prediction", region=region, purity=purity)
    if cached is not None:
        return cached
    
    # Get the latest stored prediction result for this region/purity
    prediction_result = db.query(PredictionResult).filter(
        PredictionResult.region == region,
        PredictionResult.purity == purity
    ).order_by(PredictionResult.executed_at.desc()).first()
    
    if not prediction_result:
        result = {
            "predictions": [], 
            "trend": "No Data", 
            "slope": 0,
            "r_squared": 0,
            "confidence_score": 0,
            "executed_at": None,
            "message": "No pre-calculated data available. AI job may not have run yet.",
            "data_points": 0
        }
        # Cache "no data" for 5 min to avoid repeated DB queries
        ai_cache.set("prediction", result, ttl_seconds=300, region=region, purity=purity)
        return result
    
    result = {
        "predictions": prediction_result.predictions or [],
        "trend": prediction_result.trend,
        "slope": prediction_result.slope,
        "r_squared": prediction_result.r_squared,
        "confidence_score": prediction_result.confidence_score,
        "std_error": prediction_result.std_error,
        "data_points": prediction_result.data_points,
        "factor_attribution": prediction_result.factor_attribution,
        "factors_applied": prediction_result.factors_applied,
        "executed_at": prediction_result.executed_at.isoformat() if prediction_result.executed_at else None,
        "cached": True
    }
    
    # Store in cache (1 hour TTL)
    ai_cache.set("prediction", result, region=region, purity=purity)
    
    return result

@app.get("/api/prediction-accuracy")
def get_prediction_accuracy(
    region: str,
    purity: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get prediction accuracy track record for a region/purity.
    Returns evaluated past predictions compared to actual prices,
    plus aggregate accuracy metrics.
    Cached for 1 hour.
    """
    cached = ai_cache.get("prediction-accuracy", region=region, purity=purity)
    if cached is not None:
        return cached

    # Get evaluated accuracy records, most recent first
    records = db.query(PredictionAccuracy).filter(
        PredictionAccuracy.region == region,
        PredictionAccuracy.purity == purity
    ).order_by(PredictionAccuracy.predicted_at.desc()).limit(limit).all()

    if not records:
        result = {
            "accuracy_records": [],
            "chart_data": [],
            "summary": {
                "total_evaluated": 0,
                "avg_mae": None,
                "avg_mape": None,
                "direction_accuracy_pct": None,
                "best_mape": None,
                "worst_mape": None
            },
            "message": "No accuracy data yet. Predictions need at least 7 days to be evaluated."
        }
        ai_cache.set("prediction-accuracy", result, ttl_seconds=300, region=region, purity=purity)
        return result

    # Build chart data: flatten all comparison points into a timeline
    chart_data = []
    seen_dates = {}
    for rec in reversed(records):  # oldest first for chart
        for point in (rec.comparison_data or []):
            date = point.get('date')
            if date and date not in seen_dates:
                seen_dates[date] = True
                chart_data.append({
                    "date": date,
                    "predicted": point.get('predicted_price'),
                    "actual": point.get('actual_price'),
                    "error_pct": point.get('error_pct')
                })

    # Sort chart data by date
    chart_data.sort(key=lambda x: x['date'])

    # Aggregate summary metrics
    total = len(records)
    avg_mae = sum(r.mae for r in records) / total
    avg_mape = sum(r.mape for r in records) / total
    direction_correct_count = sum(r.direction_correct for r in records)
    direction_accuracy_pct = round((direction_correct_count / total) * 100, 1)

    mapes = [r.mape for r in records]
    best_mape = min(mapes)
    worst_mape = max(mapes)

    # Build response records
    accuracy_records = [{
        "predicted_at": r.predicted_at.isoformat() if r.predicted_at else None,
        "region": r.region,
        "purity": r.purity,
        "mae": r.mae,
        "mape": r.mape,
        "direction_correct": bool(r.direction_correct),
        "days_evaluated": r.days_evaluated,
        "trend_predicted": r.trend_predicted,
        "trend_actual": r.trend_actual,
        "comparison_data": r.comparison_data
    } for r in records]

    result = {
        "accuracy_records": accuracy_records,
        "chart_data": chart_data,
        "summary": {
            "total_evaluated": total,
            "avg_mae": round(avg_mae, 2),
            "avg_mape": round(avg_mape, 2),
            "direction_accuracy_pct": direction_accuracy_pct,
            "best_mape": round(best_mape, 2),
            "worst_mape": round(worst_mape, 2)
        }
    }

    ai_cache.set("prediction-accuracy", result, region=region, purity=purity)
    return result


@app.get("/api/model-performance")
def get_model_performance(
    limit: int = 5,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key),
):
    """
    Get gold factor OLS model performance: latest training metrics and history.

    Returns latest TrainedModel snapshot plus the last N training runs (for trend).
    """
    history = get_model_metrics_history(db, limit=limit)
    latest = history[0] if history else None
    return {
        "latest": latest,
        "history": history,
    }


@app.get("/api/model-drift")
def get_model_drift(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key),
):
    """
    Get model and data drift status: model metrics, feature distribution, concept drift.

    Single model health endpoint for performance and drift validation.
    """
    model_drift = get_model_drift_status(db)
    feature_drift = compute_feature_drift(db, recent_days=14)
    concept_drift = get_concept_drift_status(db)
    any_drift = (
        model_drift.get("model_metrics_drift", False)
        or feature_drift.get("data_drift", False)
        or concept_drift.get("concept_drift", False)
    )
    return {
        "model_metrics_drift": model_drift,
        "data_drift": feature_drift,
        "concept_drift": concept_drift,
        "any_drift": any_drift,
    }


@app.get("/api/market-mood")
def get_market_mood(
    region: str,
    purity: str = None,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get market mood index for a region.
    Returns pre-calculated results from the database (updated every 6 hours).
    Cached for 1 hour to reduce database load.
    """
    # Check cache first
    cached = ai_cache.get("market-mood", region=region, purity=purity or "default")
    if cached is not None:
        return cached
    
    # Get the latest stored mood result for this region
    query = db.query(MarketMoodResult).filter(
        MarketMoodResult.region == region
    )
    
    if purity:
        query = query.filter(MarketMoodResult.purity == purity)
    
    mood_result = query.order_by(MarketMoodResult.executed_at.desc()).first()
    
    if not mood_result:
        result = {
            "mood_score": 50, 
            "mood_label": "No Data", 
            "factors": {},
            "executed_at": None,
            "message": "No pre-calculated data available. AI job may not have run yet."
        }
        ai_cache.set("market-mood", result, ttl_seconds=300, region=region, purity=purity or "default")
        return result
    
    result = {
        "mood_score": mood_result.mood_score,
        "mood_label": mood_result.mood_label,
        "factors": mood_result.factors or {},
        "details": mood_result.details or {},
        "executed_at": mood_result.executed_at.isoformat() if mood_result.executed_at else None,
        "cached": True
    }
    
    # Store in cache (1 hour TTL)
    ai_cache.set("market-mood", result, region=region, purity=purity or "default")
    
    return result

@app.get("/api/news-sentiment")
def get_news_sentiment(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get sentiment analysis of recent gold news articles using VADER AI.
    Returns pre-calculated results from the database (updated every 6 hours).
    Cached for 1 hour to reduce database load.
    """
    # Check cache first
    cached = ai_cache.get("news-sentiment")
    if cached is not None:
        return cached
    
    # Get the latest stored sentiment result
    sentiment_result = db.query(NewsSentimentResult).order_by(
        NewsSentimentResult.executed_at.desc()
    ).first()
    
    if not sentiment_result:
        result = {
            "overall_sentiment": 0,
            "sentiment_label": "Neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "bullish_percent": 0,
            "total_articles": 0,
            "recent_headlines": [],
            "analysis_method": "VADER",
            "executed_at": None,
            "message": "No pre-calculated data available. AI job may not have run yet.",
            "cached": False
        }
        return result
    
    result = {
        "overall_sentiment": sentiment_result.overall_sentiment,
        "sentiment_label": sentiment_result.sentiment_label,
        "bullish_count": sentiment_result.bullish_count,
        "bearish_count": sentiment_result.bearish_count,
        "neutral_count": sentiment_result.neutral_count,
        "bullish_percent": sentiment_result.bullish_percent,
        "total_articles": sentiment_result.total_articles,
        "recent_headlines": sentiment_result.recent_headlines or [],
        "analysis_method": sentiment_result.analysis_method or "VADER",
        "vader_scores": {
            "avg_positive": sentiment_result.avg_positive,
            "avg_negative": sentiment_result.avg_negative,
            "avg_neutral": sentiment_result.avg_neutral
        } if sentiment_result.avg_positive is not None else None,
        "executed_at": sentiment_result.executed_at.isoformat() if sentiment_result.executed_at else None,
        "cached": True
    }
    
    # Store in cache (1 hour TTL)
    ai_cache.set("news-sentiment", result)
    
    return result

@app.get("/api/external-factors")
def get_external_factors_api(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get external market factors (USD strength, etc.).
    Returns pre-calculated results from the database (updated every 6 hours).
    Cached for 1 hour to reduce database load.
    """
    # Check cache first
    cached = ai_cache.get("external-factors")
    if cached is not None:
        return cached
    
    # Get the latest stored external factors result
    factors_result = db.query(ExternalFactorsResult).order_by(
        ExternalFactorsResult.executed_at.desc()
    ).first()
    
    if not factors_result:
        result = {
            "usd_index": 100,
            "usd_direction": "No Data",
            "usd_impact": 0,
            "executed_at": None,
            "message": "No pre-calculated data available. AI job may not have run yet.",
            "cached": False
        }
        return result
    
    result = {
        "usd_index": factors_result.usd_index,
        "eur_rate": factors_result.eur_rate,
        "usd_direction": factors_result.usd_direction,
        "usd_impact": factors_result.usd_impact,
        "treasury_yield_10y": factors_result.treasury_yield_10y,
        "interest_rate_impact": factors_result.interest_rate_impact,
        "central_bank_net_change": factors_result.central_bank_net_change,
        "central_bank_impact": factors_result.central_bank_impact,
        "combined_impact": factors_result.combined_impact,
        "executed_at": factors_result.executed_at.isoformat() if factors_result.executed_at else None,
        "cached": True
    }
    
    # Store in cache (1 hour TTL)
    ai_cache.set("external-factors", result)
    
    return result


@app.get("/api/geopolitical-risk")
def get_geopolitical_risk(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get current geopolitical risk index.
    Returns pre-calculated results from the database (updated every 6 hours).
    """
    cached = ai_cache.get("geopolitical-risk")
    if cached is not None:
        return cached

    risk_result = db.query(GeoRiskResult).order_by(
        GeoRiskResult.executed_at.desc()
    ).first()

    if not risk_result:
        result = {
            "risk_score": 10,
            "risk_label": "Low",
            "active_events_count": 0,
            "top_events": [],
            "category_breakdown": {},
            "gold_impact_estimate": 0.0,
            "trend": "Stable",
            "executed_at": None,
            "cached": False
        }
        return result

    result = {
        "risk_score": risk_result.risk_score,
        "risk_label": risk_result.risk_label,
        "active_events_count": risk_result.active_events_count,
        "top_events": risk_result.top_events or [],
        "category_breakdown": risk_result.category_breakdown or {},
        "gold_impact_estimate": risk_result.gold_impact_estimate,
        "trend": risk_result.trend,
        "executed_at": risk_result.executed_at.isoformat() if risk_result.executed_at else None,
        "cached": True
    }

    ai_cache.set("geopolitical-risk", result)
    return result


@app.get("/api/geopolitical-events")
def get_geopolitical_events(
    limit: int = 20,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """Get recent classified geopolitical events."""
    cached = ai_cache.get("geopolitical-events", limit=limit)
    if cached is not None:
        return cached

    events = db.query(GeopoliticalEvent).order_by(
        GeopoliticalEvent.event_date.desc()
    ).limit(limit).all()

    result = [{
        "id": e.id,
        "title": e.title,
        "category": e.category,
        "severity_score": e.severity_score,
        "gold_impact_direction": e.gold_impact_direction,
        "gold_impact_magnitude": e.gold_impact_magnitude,
        "region_affected": e.region_affected,
        "source": e.source,
        "is_seed_data": bool(e.is_seed_data),
        "event_date": e.event_date.isoformat() if e.event_date else None,
    } for e in events]

    ai_cache.set("geopolitical-events", result, limit=limit)
    return result


@app.get("/api/geo-backtest")
def get_geo_backtest(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get all backtested geopolitical events with gold price impact data.
    Used for the public backtesting dashboard.
    """
    cached = ai_cache.get("geo-backtest")
    if cached is not None:
        return cached

    results = db.query(GeoBacktestResult).order_by(
        GeoBacktestResult.event_date.asc()
    ).all()

    if not results:
        # Run backtest on the fly if no results exist yet
        from geopolitical import run_full_backtest, get_category_statistics, get_backtest_summary
        backtest_data = run_full_backtest()
        if backtest_data:
            response = {
                "events": backtest_data,
                "categories": get_category_statistics(backtest_data),
                "summary": get_backtest_summary(backtest_data),
                "cached": False
            }
            ai_cache.set("geo-backtest", response, ttl_seconds=3600)
            return response
        return {"events": [], "categories": [], "summary": {"total_events": 0}, "cached": False}

    events = []
    for r in results:
        events.append({
            "event_name": r.event_name,
            "event_date": r.event_date.isoformat() if r.event_date else None,
            "category": r.category,
            "severity_score": r.severity_score,
            "description": r.description,
            "region_affected": r.region_affected,
            "price_at_event": r.price_at_event,
            "price_before_7d": r.price_before_7d,
            "price_after_1d": r.price_after_1d,
            "price_after_7d": r.price_after_7d,
            "price_after_30d": r.price_after_30d,
            "price_after_90d": r.price_after_90d,
            "impact_1d_pct": r.impact_1d_pct,
            "impact_7d_pct": r.impact_7d_pct,
            "impact_30d_pct": r.impact_30d_pct,
            "impact_90d_pct": r.impact_90d_pct,
            "price_chart_data": r.price_chart_data or [],
        })

    from geopolitical import get_category_statistics, get_backtest_summary
    response = {
        "events": events,
        "categories": get_category_statistics(events),
        "summary": get_backtest_summary(events),
        "cached": True
    }

    ai_cache.set("geo-backtest", response, ttl_seconds=3600)
    return response


@app.get("/api/geo-backtest/{event_id}")
def get_geo_backtest_event(
    event_id: int,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """Get a single backtested event with full price chart data."""
    result = db.query(GeoBacktestResult).filter(GeoBacktestResult.id == event_id).first()

    if not result:
        raise HTTPException(status_code=404, detail="Backtest event not found")

    return {
        "event_name": result.event_name,
        "event_date": result.event_date.isoformat() if result.event_date else None,
        "category": result.category,
        "severity_score": result.severity_score,
        "description": result.description,
        "region_affected": result.region_affected,
        "price_at_event": result.price_at_event,
        "price_before_7d": result.price_before_7d,
        "price_after_1d": result.price_after_1d,
        "price_after_7d": result.price_after_7d,
        "price_after_30d": result.price_after_30d,
        "price_after_90d": result.price_after_90d,
        "impact_1d_pct": result.impact_1d_pct,
        "impact_7d_pct": result.impact_7d_pct,
        "impact_30d_pct": result.impact_30d_pct,
        "impact_90d_pct": result.impact_90d_pct,
        "price_chart_data": result.price_chart_data or [],
    }


@app.get("/api/ai-status")
def get_ai_status(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get status of AI calculations - when they last ran and counts.
    Cached for 5 minutes.
    """
    # Check cache first (shorter TTL for status)
    cached = ai_cache.get("ai-status")
    if cached is not None:
        return cached
    
    # Get latest execution times from each table
    mood_latest = db.query(MarketMoodResult).order_by(MarketMoodResult.executed_at.desc()).first()
    sentiment_latest = db.query(NewsSentimentResult).order_by(NewsSentimentResult.executed_at.desc()).first()
    prediction_latest = db.query(PredictionResult).order_by(PredictionResult.executed_at.desc()).first()
    factors_latest = db.query(ExternalFactorsResult).order_by(ExternalFactorsResult.executed_at.desc()).first()
    
    # Get counts
    mood_count = db.query(MarketMoodResult).count()
    sentiment_count = db.query(NewsSentimentResult).count()
    prediction_count = db.query(PredictionResult).count()
    factors_count = db.query(ExternalFactorsResult).count()
    
    result = {
        "market_mood": {
            "last_executed": mood_latest.executed_at.isoformat() if mood_latest else None,
            "total_records": mood_count
        },
        "news_sentiment": {
            "last_executed": sentiment_latest.executed_at.isoformat() if sentiment_latest else None,
            "total_records": sentiment_count
        },
        "predictions": {
            "last_executed": prediction_latest.executed_at.isoformat() if prediction_latest else None,
            "total_records": prediction_count
        },
        "external_factors": {
            "last_executed": factors_latest.executed_at.isoformat() if factors_latest else None,
            "total_records": factors_count
        },
        "schedule": "Every 6 hours",
        "cache": ai_cache.stats(),
        "cached": True
    }
    
    # Store in cache (5 minute TTL for status)
    ai_cache.set("ai-status", result, ttl_seconds=300)
    
    return result


@app.get("/api/cache-stats")
def get_cache_stats(
    api_key: APIKey = Depends(get_api_key)
):
    """Get cache statistics."""
    return {
        "cache": ai_cache.stats(),
        "ttl_seconds": 1800,
        "ttl_minutes": 30,
        "description": "In-memory cache for AI endpoints. Refreshes every 30 minutes or when new AI results are generated."
    }


@app.post("/api/cache-clear")
def clear_cache(
    api_key: APIKey = Depends(get_api_key),
    _admin: bool = Depends(require_admin)
):
    """Clear all cached data (admin only)."""
    ai_cache.invalidate()
    return {
        "message": "Cache cleared successfully",
        "cleared_at": datetime.now().isoformat()
    }


@app.post("/api/ai-trigger")
def trigger_ai_calculations(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key),
    _admin: bool = Depends(require_admin)
):
    """
    Manually trigger AI calculations (admin only).
    """
    # Clear cache before running new calculations
    ai_cache.invalidate()
    
    # Run AI calculations in background
    import threading
    thread = threading.Thread(target=run_ai_job)
    thread.start()
    
    return {
        "message": "AI calculations triggered. Cache cleared. Results will be available shortly.",
        "triggered_at": datetime.now().isoformat()
    }


@app.get("/api/news-stats")
def get_news_stats(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """
    Get statistics about scraped news articles.
    """
    from sqlalchemy import func
    
    total_news = db.query(GoldNews).count()
    
    # News by source
    source_counts = db.query(
        GoldNews.source,
        func.count(GoldNews.id).label('count')
    ).group_by(GoldNews.source).all()
    
    news_by_source = {row[0]: row[1] for row in source_counts}
    
    # Latest news time
    latest = db.query(GoldNews).order_by(GoldNews.created_at.desc()).first()
    
    # News from last 7 days
    cutoff = datetime.now() - timedelta(days=7)
    recent_count = db.query(GoldNews).filter(GoldNews.published_at >= cutoff).count()
    
    return {
        "total_articles": total_news,
        "articles_last_7_days": recent_count,
        "news_by_source": news_by_source,
        "latest_scrape": latest.created_at.isoformat() if latest else None,
        "schedule": "Every 1 hour"
    }


@app.post("/api/news-trigger")
def trigger_news_scrape(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key),
    _admin: bool = Depends(require_admin)
):
    """
    Manually trigger news scraping (admin only).
    """
    # Run news scraper in background
    import threading
    thread = threading.Thread(target=run_news_scrape_job)
    thread.start()
    
    return {
        "message": "News scraping triggered. New articles will be available shortly.",
        "triggered_at": datetime.now().isoformat()
    }


@app.get("/api/export/rates")
def export_rates(
    region: str = None,
    purity: str = None,
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """Export gold rates to CSV"""
    csv_data = export_rates_to_csv(db, region, purity)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=gold_rates_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

@app.get("/api/export/news")
def export_news(
    db: Session = Depends(get_db),
    api_key: APIKey = Depends(get_api_key)
):
    """Export gold news to CSV"""
    csv_data = export_news_to_csv(db)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=gold_news_{datetime.now().strftime('%Y%m%d')}.csv"}
    )


@app.get("/api/admin/stats")
def get_admin_stats(
    api_key: APIKey = Depends(get_api_key),
    _admin: bool = Depends(require_admin)
):
    """
    Get portfolio statistics for admin dashboard.
    Bypasses RLS by querying the database directly.
    Requires the server-side-only admin key (see require_admin).
    """
    from sqlalchemy import text
    from datetime import date
    import json
    
    db = SessionLocal()
    try:
        # Get user data from auth.users table (includes signup dates and metadata)
        total_registered = 0
        daily_signups = {}
        users_by_country = {}
        
        # Initialize last 14 days
        today = date.today()
        for i in range(14):
            d = today - timedelta(days=i)
            daily_signups[d.isoformat()] = 0
        
        try:
            # Query auth.users for signup dates and country metadata
            auth_result = db.execute(text("""
                SELECT id, created_at, raw_user_meta_data
                FROM auth.users
                ORDER BY created_at DESC
            """))
            
            for row in auth_result:
                total_registered += 1
                
                # Daily signups from actual registration date
                if row[1]:  # created_at
                    signup_date = row[1].strftime('%Y-%m-%d')
                    if signup_date in daily_signups:
                        daily_signups[signup_date] += 1
                
                # Users by country from metadata
                if row[2]:  # raw_user_meta_data
                    try:
                        metadata = row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {}
                        country = metadata.get('country', 'Unknown')
                        if country:
                            users_by_country[country] = users_by_country.get(country, 0) + 1
                    except:
                        users_by_country['Unknown'] = users_by_country.get('Unknown', 0) + 1
                        
        except Exception as auth_err:
            logger.warning(f"Could not query auth.users: {auth_err}")
        
        # Query portfolio_items table directly (bypasses RLS)
        result = db.execute(text("""
            SELECT 
                id,
                user_id,
                gold_type,
                weight_grams,
                purchase_price,
                purchase_date,
                created_at
            FROM portfolio_items
            ORDER BY created_at DESC
        """))
        
        items = []
        for row in result:
            items.append({
                "id": str(row[0]),
                "user_id": str(row[1]),
                "gold_type": row[2],
                "weight_grams": float(row[3]) if row[3] else 0,
                "purchase_price": float(row[4]) if row[4] else 0,
                "purchase_date": row[5].isoformat() if row[5] else None,
                "created_at": row[6].isoformat() if row[6] else None
            })
        
        # Calculate stats
        unique_users = set(item["user_id"] for item in items)
        total_weight = sum(item["weight_grams"] for item in items)
        total_value = sum(item["weight_grams"] * item["purchase_price"] for item in items)
        
        # Gold type distribution
        gold_distribution = {}
        for item in items:
            gold_type = item["gold_type"] or "Unknown"
            gold_distribution[gold_type] = gold_distribution.get(gold_type, 0) + item["weight_grams"]
        
        # Convert daily signups to sorted list
        daily_signups_list = [
            {"date": d, "count": c}
            for d, c in sorted(daily_signups.items())
        ]
        
        return {
            "totalRegisteredUsers": total_registered,
            "totalUsersWithPortfolio": len(unique_users),
            "totalPortfolioItems": len(items),
            "totalGoldWeight": round(total_weight, 2),
            "totalInvestmentValue": round(total_value, 2),
            "goldTypeDistribution": gold_distribution,
            "usersByCountry": users_by_country,
            "recentActivity": items[:10],
            "dailySignups": daily_signups_list
        }
        
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    finally:
        db.close()
