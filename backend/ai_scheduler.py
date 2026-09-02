"""
AI Scheduler - Calculates and stores AI results every 6 hours

This module runs as a background job to pre-calculate:
- Market Mood scores for all regions
- News Sentiment analysis
- Price Predictions with confidence bands
- External factors (USD strength)

Results are stored in the database and served directly via API.
"""

import logging
import statistics
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    GoldRate, 
    GoldNews,
    MarketMoodResult, 
    NewsSentimentResult, 
    PredictionResult,
    PredictionAccuracy,
    ExternalFactorsResult,
    GeopoliticalEvent,
    GeoRiskResult,
    GeoBacktestResult
)
from market_mood import calculate_market_mood
from news_scraper import get_news_sentiment_summary
from prediction import predict_future_prices, predict_with_factors
from external_factors import get_external_factors, get_usd_strength
from geopolitical import (
    classify_news_article,
    calculate_geo_risk_index,
    run_full_backtest,
    load_seed_events
)
from model_trainer import (
    train_and_store,
    load_latest_model,
    is_model_stale,
    get_model_drift_status,
    compute_feature_drift,
)
from drift import get_concept_drift_status

logger = logging.getLogger(__name__)

# Regions to calculate AI results for
REGIONS = ['India', 'UAE', 'Saudi Arabia', 'Qatar', 'Oman', 'Bahrain', 'Kuwait']


def parse_price(price_str: str) -> float:
    """Parse price string to float."""
    if not price_str:
        return 0.0
    clean = price_str
    if "₹" in clean:
        clean = clean.split("₹")[0]
    clean = clean.replace(",", "").strip()
    try:
        return float(clean)
    except ValueError:
        return 0.0


def get_region_purities(db: Session, region: str) -> List[str]:
    """Get available purities for a region."""
    purities = db.query(GoldRate.purity).filter(
        GoldRate.region == region
    ).distinct().all()
    return [p[0] for p in purities if p[0]]


def get_history_data(db: Session, region: str, purity: str, days: int = 30) -> List[Dict]:
    """Fetch historical price data for a region/purity."""
    cutoff_date = datetime.now() - timedelta(days=days)
    
    rates = db.query(GoldRate).filter(
        GoldRate.region == region,
        GoldRate.purity == purity,
        GoldRate.created_at >= cutoff_date
    ).order_by(GoldRate.created_at.asc()).all()
    
    history_data = []
    for rate in rates:
        price_val = parse_price(rate.price)
        if price_val > 0:
            history_data.append({
                "timestamp": rate.created_at.isoformat(),
                "price": price_val
            })
    
    return history_data


def calculate_and_store_market_mood(
    db: Session,
    usd_impact: float = 0.0,
    interest_rate_impact: float = 0.0,
    news_sentiment: float = 0.0,
    geo_risk_score: float = 0.0,
    central_bank_impact: float = 0.0,
):
    """Calculate and store market mood for all regions using multi-signal inputs."""
    logger.info("Calculating market mood (v2 multi-signal) for all regions...")
    execution_time = datetime.now()
    stored_count = 0

    for region in REGIONS:
        purities = get_region_purities(db, region)

        for purity in purities[:1]:  # First purity per region for mood
            try:
                history_data = get_history_data(db, region, purity, days=30)

                if len(history_data) < 7:
                    continue

                # Get slope from prediction for backward compatibility
                prediction_result = predict_future_prices(history_data, days_ahead=7)
                slope = prediction_result.get("slope", 0)

                # Calculate mood with all available signals
                mood_result = calculate_market_mood(
                    history_data,
                    slope=slope,
                    usd_impact=usd_impact,
                    interest_rate_impact=interest_rate_impact,
                    news_sentiment=news_sentiment,
                    geo_risk_score=geo_risk_score,
                    central_bank_impact=central_bank_impact,
                )

                mood_record = MarketMoodResult(
                    region=region,
                    purity=purity,
                    mood_score=mood_result.get("mood_score", 50),
                    mood_label=mood_result.get("mood_label", "Neutral"),
                    factors=mood_result.get("factors", {}),
                    details=mood_result.get("details", {}),
                    executed_at=execution_time,
                )
                db.add(mood_record)
                stored_count += 1

            except Exception as e:
                logger.error(f"Error calculating mood for {region}/{purity}: {e}")

    db.commit()
    logger.info(f"Stored {stored_count} market mood results")


def calculate_and_store_news_sentiment(db: Session):
    """Calculate and store news sentiment analysis using VADER AI."""
    logger.info("Calculating news sentiment with VADER...")
    execution_time = datetime.now()
    
    try:
        sentiment_data = get_news_sentiment_summary(db)
        
        sentiment_record = NewsSentimentResult(
            overall_sentiment=sentiment_data.get("overall_sentiment", 0),
            sentiment_label=sentiment_data.get("sentiment_label", "Neutral"),
            bullish_count=sentiment_data.get("bullish_count", 0),
            bearish_count=sentiment_data.get("bearish_count", 0),
            neutral_count=sentiment_data.get("neutral_count", 0),
            bullish_percent=sentiment_data.get("bullish_percent", 0),
            total_articles=sentiment_data.get("total_articles", 0),
            recent_headlines=sentiment_data.get("recent_headlines", []),
            analysis_method=sentiment_data.get("analysis_method", "VADER"),
            avg_positive=sentiment_data.get("avg_positive", 0),
            avg_negative=sentiment_data.get("avg_negative", 0),
            avg_neutral=sentiment_data.get("avg_neutral", 0),
            executed_at=execution_time
        )
        db.add(sentiment_record)
        db.commit()
        logger.info(f"Stored news sentiment result (method: {sentiment_data.get('analysis_method', 'VADER')})")
        
    except Exception as e:
        logger.error(f"Error calculating news sentiment: {e}")
        db.rollback()


def classify_and_store_geo_events(db: Session):
    """Classify recent news articles as geopolitical events."""
    logger.info("Classifying news for geopolitical events...")
    execution_time = datetime.now()
    stored_count = 0

    # Get news from last 7 days not yet classified
    cutoff = datetime.now() - timedelta(days=7)
    recent_news = db.query(GoldNews).filter(
        GoldNews.published_at >= cutoff
    ).order_by(GoldNews.published_at.desc()).limit(100).all()

    # Get already classified news IDs
    existing_ids = set()
    existing = db.query(GeopoliticalEvent.news_id).filter(
        GeopoliticalEvent.news_id.isnot(None)
    ).all()
    existing_ids = {e[0] for e in existing}

    for news in recent_news:
        if news.id in existing_ids:
            continue

        result = classify_news_article(news.title, news.summary or "")
        if result is None:
            continue

        geo_event = GeopoliticalEvent(
            news_id=news.id,
            title=news.title[:500],
            category=result["category"],
            severity_score=result["severity_score"],
            gold_impact_direction=result["gold_impact_direction"],
            gold_impact_magnitude=result["gold_impact_magnitude"],
            region_affected="Global",
            keywords_matched=result["keywords_matched"],
            source=news.source,
            is_seed_data=0,
            event_date=news.published_at or datetime.now(),
        )
        db.add(geo_event)
        stored_count += 1

    db.commit()
    logger.info(f"Classified {stored_count} new geopolitical events from news")


def calculate_and_store_geo_risk(db: Session) -> float:
    """
    Calculate and store the geopolitical risk index.
    Returns the risk impact score (-1 to 1) for use in predictions.
    """
    logger.info("Calculating geopolitical risk index...")
    execution_time = datetime.now()

    # Get recent geopolitical events (last 14 days)
    cutoff = datetime.now() - timedelta(days=14)
    recent_events = db.query(GeopoliticalEvent).filter(
        GeopoliticalEvent.event_date >= cutoff
    ).all()

    events_data = [
        {
            "title": e.title,
            "category": e.category,
            "severity_score": e.severity_score,
            "gold_impact_direction": e.gold_impact_direction,
            "event_date": e.event_date,
        }
        for e in recent_events
    ]

    risk_result = calculate_geo_risk_index(events_data)

    # Store result
    risk_record = GeoRiskResult(
        risk_score=risk_result["risk_score"],
        risk_label=risk_result["risk_label"],
        active_events_count=risk_result["active_events_count"],
        top_events=risk_result["top_events"],
        category_breakdown=risk_result["category_breakdown"],
        gold_impact_estimate=risk_result["gold_impact_estimate"],
        trend=risk_result["trend"],
        executed_at=execution_time,
    )
    db.add(risk_record)
    db.commit()
    logger.info(f"Stored geo risk: {risk_result['risk_score']}/100 ({risk_result['risk_label']})")

    # Convert risk score to impact for predictions (-1 to 1)
    # Higher risk = more bullish for gold
    return risk_result["risk_score"] / 100.0


def seed_historical_events(db: Session):
    """Seed historical geopolitical events, adding any new ones from the JSON."""
    from geopolitical import GEO_CATEGORIES

    events = load_seed_events()
    if not events:
        return

    # Get titles of already-seeded events to avoid duplicates
    existing_titles = set()
    existing = db.query(GeopoliticalEvent.title).filter(
        GeopoliticalEvent.is_seed_data == 1
    ).all()
    existing_titles = {t[0] for t in existing}

    new_count = 0
    for event in events:
        if event["name"] in existing_titles:
            continue

        cat_info = GEO_CATEGORIES.get(event.get("category", ""), {})
        geo_event = GeopoliticalEvent(
            title=event["name"],
            category=event.get("category", "unknown"),
            severity_score=event.get("severity", 5),
            gold_impact_direction=cat_info.get("gold_direction", "bullish"),
            gold_impact_magnitude=event.get("impact_7d_pct", 0) / 100,
            region_affected=event.get("region_affected", "Global"),
            keywords_matched=[],
            source="Historical Seed Data",
            is_seed_data=1,
            event_date=datetime.strptime(event["date"], "%Y-%m-%d"),
        )
        db.add(geo_event)
        new_count += 1

    if new_count > 0:
        db.commit()
        logger.info(f"Seeded {new_count} new historical geopolitical events (total: {len(events)})")
    else:
        logger.info(f"All {len(events)} seed events already present")


def run_and_store_backtest(db: Session):
    """Run backtest and store results for any new seed events."""
    existing_count = db.query(GeoBacktestResult).count()
    seed_count = db.query(GeopoliticalEvent).filter(
        GeopoliticalEvent.is_seed_data == 1
    ).count()
    if existing_count > 0 and existing_count >= seed_count:
        return  # Already backtested all events

    logger.info("Running geopolitical backtest...")
    results = run_full_backtest()

    for r in results:
        record = GeoBacktestResult(
            event_name=r["event_name"],
            event_date=datetime.strptime(r["event_date"][:10], "%Y-%m-%d"),
            category=r["category"],
            severity_score=r.get("severity_score", 5),
            description=r.get("description", ""),
            region_affected=r.get("region_affected", "Global"),
            price_at_event=r.get("price_at_event"),
            price_before_7d=r.get("price_before_7d"),
            price_after_1d=r.get("price_after_1d"),
            price_after_7d=r.get("price_after_7d"),
            price_after_30d=r.get("price_after_30d"),
            price_after_90d=r.get("price_after_90d"),
            impact_1d_pct=r.get("impact_1d_pct"),
            impact_7d_pct=r.get("impact_7d_pct"),
            impact_30d_pct=r.get("impact_30d_pct"),
            impact_90d_pct=r.get("impact_90d_pct"),
            price_chart_data=r.get("price_chart_data", []),
        )
        db.add(record)

    db.commit()
    logger.info(f"Stored {len(results)} backtest results")


def train_model_if_stale(db: Session) -> Optional[Dict]:
    """
    Check if the trained OLS model is older than 7 days and retrain if so.
    Returns the current trained model dict (loaded or freshly trained), or None.
    """
    try:
        if is_model_stale(db, max_age_days=7):
            logger.info("Trained model is stale or missing -- retraining...")
            train_and_store(db)
        else:
            logger.info("Trained model is fresh -- skipping retraining")

        return load_latest_model(db)
    except Exception as e:
        logger.error(f"Error during model training check: {e}")
        return load_latest_model(db)  # Return whatever exists


def calculate_and_store_predictions(db: Session, trained_model: Optional[Dict] = None):
    """Calculate and store price predictions for all regions."""
    logger.info("Calculating predictions for all regions...")
    execution_time = datetime.now()
    stored_count = 0

    # Get external factors for multi-factor prediction
    try:
        external = get_external_factors()
        usd_impact = external.get('usd', {}).get('impact', 0)
        interest_rate_impact = external.get('interest_rate', {}).get('impact', 0)
        central_bank_impact = external.get('central_bank', {}).get('impact', 0)
    except Exception:
        usd_impact = 0
        interest_rate_impact = 0
        central_bank_impact = 0

    # Get sentiment score
    try:
        sentiment_data = get_news_sentiment_summary(db)
        sentiment_score = sentiment_data.get('overall_sentiment', 0)
    except Exception:
        sentiment_score = 0

    # Get geopolitical risk impact
    try:
        geo_risk = db.query(GeoRiskResult).order_by(
            GeoRiskResult.executed_at.desc()
        ).first()
        geo_risk_impact = (geo_risk.risk_score / 100.0) if geo_risk else 0
    except Exception:
        geo_risk_impact = 0

    model_tag = "trained" if trained_model else "fallback"
    logger.info(
        f"Prediction factors ({model_tag}): USD={usd_impact}, IR={interest_rate_impact}, "
        f"Sentiment={sentiment_score}, Geo={geo_risk_impact}, CB={central_bank_impact}"
    )

    for region in REGIONS:
        purities = get_region_purities(db, region)

        for purity in purities:
            try:
                history_data = get_history_data(db, region, purity, days=30)

                if len(history_data) < 3:
                    continue

                # Calculate prediction with all factors + trained model
                result = predict_with_factors(
                    history_data,
                    days_ahead=7,
                    usd_impact=usd_impact,
                    sentiment_score=sentiment_score,
                    geo_risk_impact=geo_risk_impact,
                    interest_rate_impact=interest_rate_impact,
                    central_bank_impact=central_bank_impact,
                    trained_model=trained_model,
                )

                # Store result
                prediction_record = PredictionResult(
                    region=region,
                    purity=purity,
                    predictions=result.get("predictions", []),
                    trend=result.get("trend", "Neutral"),
                    slope=result.get("slope", 0),
                    r_squared=result.get("r_squared", 0),
                    confidence_score=result.get("confidence_score", 0),
                    std_error=result.get("std_error", 0),
                    data_points=result.get("data_points", 0),
                    factor_attribution=result.get("factor_attribution"),
                    factors_applied=result.get("factors_applied"),
                    executed_at=execution_time
                )
                db.add(prediction_record)
                stored_count += 1

            except Exception as e:
                logger.error(f"Error calculating prediction for {region}/{purity}: {e}")

    db.commit()
    logger.info(f"Stored {stored_count} prediction results")


def calculate_and_store_external_factors(db: Session):
    """Fetch and store external market factors."""
    logger.info("Fetching external factors...")
    execution_time = datetime.now()
    
    try:
        external = get_external_factors()
        usd_data = external.get('usd', {})
        ir_data = external.get('interest_rate', {})
        cb_data = external.get('central_bank', {})
        
        factors_record = ExternalFactorsResult(
            usd_index=usd_data.get('usd_index', 100),
            eur_rate=usd_data.get('eur_rate', 0.92),
            usd_direction=usd_data.get('direction', 'Neutral'),
            usd_impact=usd_data.get('impact', 0),
            treasury_yield_10y=ir_data.get('yield_10y'),
            interest_rate_impact=ir_data.get('impact', 0),
            central_bank_net_change=cb_data.get('net_change_tonnes'),
            central_bank_impact=cb_data.get('impact', 0),
            combined_impact=external.get('combined_impact', 0),
            raw_data=external,
            executed_at=execution_time
        )
        db.add(factors_record)
        db.commit()
        logger.info(
            f"Stored external factors: USD={usd_data.get('impact', 0)}, "
            f"10Y={ir_data.get('yield_10y', 'N/A')}%, "
            f"CB={cb_data.get('net_change_tonnes', 0)}t"
        )
        
    except Exception as e:
        logger.error(f"Error fetching external factors: {e}")
        db.rollback()


def evaluate_prediction_accuracy(db: Session):
    """
    Evaluate past predictions against actual prices.

    For each PredictionResult that is at least 3 days old and hasn't been
    evaluated yet, look up actual prices from gold_rates on those dates and
    compute MAE, MAPE, and direction accuracy.

    Uses batched queries per region/purity to avoid N+1 query overhead on
    remote databases (e.g. Supabase).
    """
    logger.info("Evaluating prediction accuracy...")
    stored_count = 0

    # Already-evaluated prediction IDs
    evaluated_ids = set()
    rows = db.query(PredictionAccuracy.prediction_id).all()
    evaluated_ids = {r[0] for r in rows}

    # Predictions made at least 3 days ago (partial evaluation is useful)
    cutoff = datetime.now() - timedelta(days=3)
    old_predictions = db.query(PredictionResult).filter(
        PredictionResult.executed_at <= cutoff
    ).order_by(PredictionResult.executed_at.desc()).limit(500).all()

    # Filter already evaluated
    to_evaluate = [p for p in old_predictions if p.id not in evaluated_ids]
    if not to_evaluate:
        logger.info("No new predictions to evaluate")
        return

    # Group predictions by (region, purity) to batch rate lookups
    from collections import defaultdict as _defaultdict
    grouped = _defaultdict(list)
    for pred in to_evaluate:
        grouped[(pred.region, pred.purity)].append(pred)

    rate_start = datetime.now() - timedelta(days=21)
    today_str = datetime.now().strftime("%Y-%m-%d")

    for (region, purity), preds in grouped.items():
        # Pre-fetch all rates for this region/purity in one query
        all_rates = db.query(GoldRate).filter(
            GoldRate.region == region,
            GoldRate.purity == purity,
            GoldRate.created_at >= rate_start
        ).all()

        # Build daily price lookup (median to reduce impact of outliers/sparse scrape)
        daily_prices = _defaultdict(list)
        for r in all_rates:
            day = r.created_at.strftime("%Y-%m-%d")
            price = parse_price(r.price)
            if price > 0:
                daily_prices[day].append(price)
        daily_avg = {d: statistics.median(ps) for d, ps in daily_prices.items()}

        if not daily_avg:
            continue

        for pred_result in preds:
            predictions_json = pred_result.predictions or []
            if not predictions_json:
                continue

            comparison_data = []
            errors = []
            pct_errors = []

            for pred_point in predictions_json:
                pred_date_str = pred_point.get('timestamp', '')[:10]
                pred_price = pred_point.get('price', 0)
                if not pred_date_str or pred_price <= 0:
                    continue

                actual_price = daily_avg.get(pred_date_str)
                if actual_price is None:
                    continue

                error = abs(pred_price - actual_price)
                error_pct = (error / actual_price) * 100 if actual_price > 0 else 0

                comparison_data.append({
                    "date": pred_date_str,
                    "predicted_price": round(pred_price, 2),
                    "actual_price": round(actual_price, 2),
                    "error": round(error, 2),
                    "error_pct": round(error_pct, 2)
                })
                errors.append(error)
                pct_errors.append(error_pct)

            if len(comparison_data) < 2:
                continue  # Need at least 2 days of data

            mae = sum(errors) / len(errors)
            mape = sum(pct_errors) / len(pct_errors)

            # Direction accuracy
            first_actual = comparison_data[0]['actual_price']
            last_actual = comparison_data[-1]['actual_price']
            actual_change = last_actual - first_actual
            trend_actual = "Up" if actual_change > 0 else "Down" if actual_change < 0 else "Neutral"
            trend_predicted = pred_result.trend or "Neutral"
            direction_correct = 1 if trend_predicted == trend_actual else 0

            accuracy_record = PredictionAccuracy(
                region=region,
                purity=purity,
                prediction_id=pred_result.id,
                predicted_at=pred_result.executed_at,
                comparison_data=comparison_data,
                mae=round(mae, 2),
                mape=round(mape, 4),
                direction_correct=direction_correct,
                days_evaluated=len(comparison_data),
                trend_predicted=trend_predicted,
                trend_actual=trend_actual,
            )
            db.add(accuracy_record)
            stored_count += 1

    if stored_count > 0:
        db.commit()
    logger.info(f"Evaluated {stored_count} prediction accuracy records")


def run_ai_calculations():
    """
    Main function to run all AI calculations.
    Called by the scheduler every 6 hours.
    """
    logger.info(f"Starting AI calculations at {datetime.now()}")
    
    db = SessionLocal()
    try:
        # 0. Train / refresh OLS model if stale (weekly)
        trained_model = train_model_if_stale(db)

        # 0b. Log drift status and force retrain if any drift detected
        try:
            model_drift = get_model_drift_status(db)
            feature_drift = compute_feature_drift(db, recent_days=14)
            concept_drift = get_concept_drift_status(db)
            any_drift = (
                model_drift.get("model_metrics_drift", False)
                or feature_drift.get("data_drift", False)
                or concept_drift.get("concept_drift", False)
            )
            if model_drift.get("model_metrics_drift"):
                logger.warning(f"Model metrics drift: {model_drift.get('message', '')}")
            if feature_drift.get("data_drift"):
                logger.warning(f"Data drift: {feature_drift.get('message', '')}")
            if concept_drift.get("concept_drift"):
                logger.warning(f"Concept drift: {concept_drift.get('message', '')}")
            if any_drift:
                logger.info("Drift detected — forcing model retrain")
                train_and_store(db)
                trained_model = load_latest_model(db)
        except Exception as drift_err:
            logger.debug(f"Drift check skipped or failed: {drift_err}")

        # 1. External factors first (needed for predictions + mood)
        calculate_and_store_external_factors(db)

        # 2. News sentiment (needed for predictions + mood)
        calculate_and_store_news_sentiment(db)

        # 3. Geopolitical analysis
        seed_historical_events(db)  # One-time seed
        classify_and_store_geo_events(db)
        calculate_and_store_geo_risk(db)
        run_and_store_backtest(db)  # One-time backtest

        # ── Gather signals for mood + predictions ──
        usd_impact = 0.0
        interest_rate_impact = 0.0
        central_bank_impact = 0.0
        news_sentiment = 0.0
        geo_risk_score = 0.0

        try:
            ext = db.query(ExternalFactorsResult).order_by(
                ExternalFactorsResult.executed_at.desc()
            ).first()
            if ext:
                usd_impact = ext.usd_impact or 0.0
                interest_rate_impact = ext.interest_rate_impact or 0.0
                central_bank_impact = ext.central_bank_impact or 0.0
        except Exception:
            pass

        try:
            sent = db.query(NewsSentimentResult).order_by(
                NewsSentimentResult.executed_at.desc()
            ).first()
            if sent:
                news_sentiment = sent.overall_sentiment or 0.0
        except Exception:
            pass

        try:
            geo = db.query(GeoRiskResult).order_by(
                GeoRiskResult.executed_at.desc()
            ).first()
            if geo:
                geo_risk_score = float(geo.risk_score or 0)
        except Exception:
            pass

        logger.info(
            f"Mood signals: USD={usd_impact}, IR={interest_rate_impact}, "
            f"Sent={news_sentiment:.2f}, Geo={geo_risk_score}, CB={central_bank_impact}"
        )

        # 4. Market mood for all regions (now multi-signal)
        calculate_and_store_market_mood(
            db,
            usd_impact=usd_impact,
            interest_rate_impact=interest_rate_impact,
            news_sentiment=news_sentiment,
            geo_risk_score=geo_risk_score,
            central_bank_impact=central_bank_impact,
        )

        # 5. Predictions for all regions/purities (uses trained model + geo risk)
        calculate_and_store_predictions(db, trained_model=trained_model)

        # 6. Evaluate accuracy of past predictions against actual prices
        evaluate_prediction_accuracy(db)
        
        logger.info(f"AI calculations completed at {datetime.now()}")
        
    except Exception as e:
        logger.error(f"Error in AI calculations: {e}")
        db.rollback()
    finally:
        db.close()


def cleanup_old_results(days_to_keep: int = 30):
    """Remove AI results older than specified days."""
    logger.info(f"Cleaning up results older than {days_to_keep} days...")
    
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(days=days_to_keep)
        
        db.query(MarketMoodResult).filter(MarketMoodResult.executed_at < cutoff).delete()
        db.query(NewsSentimentResult).filter(NewsSentimentResult.executed_at < cutoff).delete()
        db.query(PredictionResult).filter(PredictionResult.executed_at < cutoff).delete()
        db.query(PredictionAccuracy).filter(PredictionAccuracy.created_at < cutoff).delete()
        db.query(ExternalFactorsResult).filter(ExternalFactorsResult.executed_at < cutoff).delete()
        db.query(GeoRiskResult).filter(GeoRiskResult.executed_at < cutoff).delete()
        # Keep seed events and backtest results permanently; only clean detected events
        db.query(GeopoliticalEvent).filter(
            GeopoliticalEvent.is_seed_data == 0,
            GeopoliticalEvent.event_date < cutoff
        ).delete()
        
        db.commit()
        logger.info("Cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    # For manual testing
    logging.basicConfig(level=logging.INFO)
    run_ai_calculations()
