from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, JSON
from sqlalchemy.sql import func
from database import Base
from datetime import datetime

class GoldRate(Base):
    __tablename__ = "gold_rates"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String, index=True)
    purity = Column(String)
    price = Column(String) # Storing as string to keep original format if needed, or could parse to float
    currency = Column(String)
    created_at = Column(DateTime, default=datetime.now)

class GoldNews(Base):
    __tablename__ = "gold_news"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500))
    summary = Column(Text)
    source = Column(String(100))
    url = Column(Text)  # Changed to Text for long Google News URLs
    image_url = Column(String(1000))
    slug = Column(String(200), unique=True, index=True)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, index=True)
    owner = Column(String(100))
    is_active = Column(Integer, default=1) # 1 for active, 0 for inactive
    tier = Column(String(20), default="free") # free or paid
    created_at = Column(DateTime, default=datetime.now)


# ============== AI Results Storage ==============

class MarketMoodResult(Base):
    """Stores pre-calculated market mood scores"""
    __tablename__ = "market_mood_results"
    
    id = Column(Integer, primary_key=True, index=True)
    region = Column(String(50), index=True)
    purity = Column(String(20))
    mood_score = Column(Integer)  # 0-100
    mood_label = Column(String(20))  # Extreme Fear, Fear, Neutral, Greed, Extreme Greed
    factors = Column(JSON)  # {momentum, volatility, trend_strength, recent_change}
    details = Column(JSON)  # {ma_7, ma_30, volatility_percent, change_7d_percent, slope}
    executed_at = Column(DateTime, default=datetime.now, index=True)
    created_at = Column(DateTime, default=datetime.now)


class NewsSentimentResult(Base):
    """Stores pre-calculated news sentiment analysis using VADER AI"""
    __tablename__ = "news_sentiment_results"
    
    id = Column(Integer, primary_key=True, index=True)
    overall_sentiment = Column(Float)  # -1 to +1 (VADER compound score)
    sentiment_label = Column(String(20))  # Bullish, Bearish, Neutral
    bullish_count = Column(Integer)
    bearish_count = Column(Integer)
    neutral_count = Column(Integer)
    bullish_percent = Column(Float)
    total_articles = Column(Integer)
    recent_headlines = Column(JSON)  # [{title, sentiment, score, source, published_at, vader_scores}]
    analysis_method = Column(String(20), default="VADER")  # VADER or keywords
    avg_positive = Column(Float)  # Average VADER positive score
    avg_negative = Column(Float)  # Average VADER negative score
    avg_neutral = Column(Float)  # Average VADER neutral score
    executed_at = Column(DateTime, default=datetime.now, index=True)
    created_at = Column(DateTime, default=datetime.now)


class PredictionResult(Base):
    """Stores pre-calculated price predictions"""
    __tablename__ = "prediction_results"
    
    id = Column(Integer, primary_key=True, index=True)
    region = Column(String(50), index=True)
    purity = Column(String(20), index=True)
    predictions = Column(JSON)  # [{timestamp, price, upper_70, lower_70, upper_90, lower_90}]
    trend = Column(String(20))  # Up, Down, Neutral
    slope = Column(Float)
    r_squared = Column(Float)
    confidence_score = Column(Integer)
    std_error = Column(Float)
    data_points = Column(Integer)
    factor_attribution = Column(JSON)  # {trend, usd, sentiment, volatility}
    factors_applied = Column(JSON)  # {usd_impact, sentiment_score, volatility_damper}
    executed_at = Column(DateTime, default=datetime.now, index=True)
    created_at = Column(DateTime, default=datetime.now)


class ExternalFactorsResult(Base):
    """Stores pre-fetched external market factors"""
    __tablename__ = "external_factors_results"
    
    id = Column(Integer, primary_key=True, index=True)
    usd_index = Column(Float)
    eur_rate = Column(Float)
    usd_direction = Column(String(50))
    usd_impact = Column(Float)  # -1 to +1
    treasury_yield_10y = Column(Float, nullable=True)       # 10-Year Treasury yield %
    interest_rate_impact = Column(Float, nullable=True)      # -1 to +1
    central_bank_net_change = Column(Float, nullable=True)   # Net change in tonnes
    central_bank_impact = Column(Float, nullable=True)       # -1 to +1
    combined_impact = Column(Float)
    raw_data = Column(JSON)  # Full response for debugging
    executed_at = Column(DateTime, default=datetime.now, index=True)
    created_at = Column(DateTime, default=datetime.now)


# ============== Historical Data Tables ==============

class HistoricalGoldPrice(Base):
    """Daily gold spot prices in USD for backtesting and training"""
    __tablename__ = "historical_gold_prices"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True, nullable=False)
    price_usd = Column(Float, nullable=False)  # USD per troy oz
    source = Column(String(50), default="freegoldapi")
    created_at = Column(DateTime, default=datetime.now)


class HistoricalTreasuryYield(Base):
    """Daily 10-Year US Treasury yield from FRED DGS10"""
    __tablename__ = "historical_treasury_yields"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True, nullable=False)
    yield_10y = Column(Float, nullable=False)  # Yield in percent, e.g. 4.25
    source = Column(String(50), default="fred_dgs10")
    created_at = Column(DateTime, default=datetime.now)


class HistoricalUsdIndex(Base):
    """Daily USD trade-weighted broad index from FRED DTWEXBGS"""
    __tablename__ = "historical_usd_index"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True, nullable=False)
    usd_index = Column(Float, nullable=False)  # Index value (Jan 2006 = 100)
    source = Column(String(50), default="fred_dtwexbgs")
    created_at = Column(DateTime, default=datetime.now)


# ============== Trained Model Storage ==============

class PredictionAccuracy(Base):
    """Stores evaluated prediction accuracy: predicted vs actual prices"""
    __tablename__ = "prediction_accuracy"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String(50), index=True)
    purity = Column(String(20), index=True)
    prediction_id = Column(Integer, index=True)  # ID of the PredictionResult evaluated
    predicted_at = Column(DateTime, index=True)   # When the prediction was made
    comparison_data = Column(JSON)  # [{date, predicted_price, actual_price, error, error_pct}]
    mae = Column(Float)            # Mean Absolute Error (currency units)
    mape = Column(Float)           # Mean Absolute Percentage Error (%)
    direction_correct = Column(Integer)  # 1 if predicted trend direction was correct, 0 otherwise
    days_evaluated = Column(Integer)     # How many of the 7 predicted days had actual data
    trend_predicted = Column(String(20)) # Up / Down / Neutral
    trend_actual = Column(String(20))    # Up / Down / Neutral (based on actual price movement)
    created_at = Column(DateTime, default=datetime.now)


class TrainedModel(Base):
    """Stores trained OLS model coefficients and validation metrics"""
    __tablename__ = "trained_models"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(50), index=True)  # "gold_factor_ols"
    coefficients = Column(JSON)      # {"intercept": 0.001, "usd": -0.45, "yield": -0.12, "momentum": 0.08}
    feature_names = Column(JSON)     # ["usd_return", "yield_change", "momentum"]
    r_squared = Column(Float)
    mae = Column(Float)              # Mean Absolute Error on test set
    mape = Column(Float)             # Mean Absolute Percentage Error
    training_points = Column(Integer)
    test_points = Column(Integer)
    training_period_start = Column(Date)
    training_period_end = Column(Date)
    residual_std = Column(Float)     # For confidence band calibration
    executed_at = Column(DateTime, default=datetime.now, index=True)


# ============== Geopolitical Analysis Models ==============

class GeopoliticalEvent(Base):
    """Detected geopolitical events from news + seed data"""
    __tablename__ = "geopolitical_events"

    id = Column(Integer, primary_key=True, index=True)
    news_id = Column(Integer, nullable=True, index=True)  # FK to gold_news (null for seed data)
    title = Column(String(500))
    category = Column(String(50), index=True)  # war_conflict, sanctions_trade, etc.
    severity_score = Column(Integer)  # 1-10
    gold_impact_direction = Column(String(20))  # bullish, bearish, neutral
    gold_impact_magnitude = Column(Float)  # -1 to 1
    region_affected = Column(String(200))
    keywords_matched = Column(JSON)
    source = Column(String(100))
    is_seed_data = Column(Integer, default=0)  # 1 for seed, 0 for detected
    event_date = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.now)


class GeoRiskResult(Base):
    """Pre-calculated geopolitical risk index scores"""
    __tablename__ = "geo_risk_results"

    id = Column(Integer, primary_key=True, index=True)
    risk_score = Column(Integer)  # 0-100
    risk_label = Column(String(30))  # Low, Moderate, Elevated, High, Extreme
    active_events_count = Column(Integer)
    top_events = Column(JSON)  # Top 5 events driving the score
    category_breakdown = Column(JSON)  # Score per category
    gold_impact_estimate = Column(Float)  # Expected % impact on gold
    trend = Column(String(20))  # Escalating, Stable, De-escalating
    executed_at = Column(DateTime, default=datetime.now, index=True)
    created_at = Column(DateTime, default=datetime.now)


class GeoBacktestResult(Base):
    """Pre-computed backtest results for historical geopolitical events"""
    __tablename__ = "geo_backtest_results"

    id = Column(Integer, primary_key=True, index=True)
    event_name = Column(String(500))
    event_date = Column(DateTime, index=True)
    category = Column(String(50), index=True)
    severity_score = Column(Integer)
    description = Column(Text)
    region_affected = Column(String(200))
    price_at_event = Column(Float)
    price_before_7d = Column(Float)
    price_after_1d = Column(Float)
    price_after_7d = Column(Float)
    price_after_30d = Column(Float)
    price_after_90d = Column(Float)
    impact_1d_pct = Column(Float)
    impact_7d_pct = Column(Float)
    impact_30d_pct = Column(Float)
    impact_90d_pct = Column(Float)
    price_chart_data = Column(JSON)  # 30d before + 90d after daily prices
    created_at = Column(DateTime, default=datetime.now)
