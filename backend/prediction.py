from datetime import datetime, timedelta
import logging
import math

logger = logging.getLogger(__name__)

def timestamp_to_ordinal(ts_iso):
    """Convert ISO timestamp to ordinal for regression."""
    dt = datetime.fromisoformat(ts_iso)
    return dt.toordinal()

def ordinal_to_timestamp(ordinal):
    """Convert ordinal back to ISO timestamp."""
    dt = datetime.fromordinal(int(ordinal))
    return dt.isoformat()

def simple_linear_regression(x_values, y_values):
    """
    Calculates the slope (m) and y-intercept (b) for y = mx + b
    using the least squares method.
    
    Returns: (slope, intercept, r_squared, std_error, x_mean, ss_xx)
    """
    n = len(x_values)
    if n < 2:
        return 0, 0, 0, 0, 0, 0
        
    sum_x = sum(x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values))
    sum_xx = sum(x * x for x in x_values)
    sum_yy = sum(y * y for y in y_values)
    
    x_mean = sum_x / n
    y_mean = sum_y / n
    
    # SS_xx = sum((x - x_mean)^2)
    ss_xx = sum_xx - (sum_x ** 2) / n
    # SS_yy = sum((y - y_mean)^2)
    ss_yy = sum_yy - (sum_y ** 2) / n
    # SS_xy = sum((x - x_mean)(y - y_mean))
    ss_xy = sum_xy - (sum_x * sum_y) / n
    
    if ss_xx == 0:
        return 0, 0, 0, 0, x_mean, 0
    
    # Calculate slope (m) and intercept (b)
    m = ss_xy / ss_xx
    b = y_mean - m * x_mean
    
    # Calculate R-squared (coefficient of determination)
    if ss_yy == 0:
        r_squared = 1.0  # Perfect fit if no variance
    else:
        r_squared = (ss_xy ** 2) / (ss_xx * ss_yy)
    
    # Calculate standard error of estimate
    # SSE = sum((y - y_pred)^2)
    y_predicted = [m * x + b for x in x_values]
    sse = sum((y - y_pred) ** 2 for y, y_pred in zip(y_values, y_predicted))
    
    if n > 2:
        mse = sse / (n - 2)  # Mean squared error
        std_error = math.sqrt(mse)
    else:
        std_error = 0
    
    return m, b, r_squared, std_error, x_mean, ss_xx


def calculate_prediction_interval(x_new, x_mean, ss_xx, std_error, n, confidence=0.70):
    """
    Calculate prediction interval for a new x value.
    
    Uses t-distribution approximation for prediction intervals.
    For 70% confidence: t ≈ 1.04 (approx for large n)
    For 90% confidence: t ≈ 1.65 (approx for large n)
    """
    # t-values for different confidence levels (approximation for n > 30)
    t_values = {
        0.70: 1.04,
        0.80: 1.28,
        0.90: 1.65,
        0.95: 1.96
    }
    
    t = t_values.get(confidence, 1.04)
    
    if ss_xx == 0 or n < 3:
        return 0
    
    # Standard error of prediction for new observation
    # SE_pred = std_error * sqrt(1 + 1/n + (x_new - x_mean)^2 / SS_xx)
    se_pred = std_error * math.sqrt(1 + 1/n + ((x_new - x_mean) ** 2) / ss_xx)
    
    # Prediction interval half-width
    interval = t * se_pred
    
    return interval

def aggregate_to_daily(history_data):
    """
    Aggregate hourly/multi-scrape data into daily averages.
    This reduces noise and gives the regression a cleaner signal.
    
    Returns: List of dicts with 'timestamp' (date string) and 'price' (daily avg)
    """
    from collections import defaultdict
    daily_prices = defaultdict(list)
    
    for d in history_data:
        dt = datetime.fromisoformat(d['timestamp'])
        day_key = dt.date().isoformat()
        daily_prices[day_key].append(float(d['price']))
    
    daily_data = []
    for day_key in sorted(daily_prices.keys()):
        prices = daily_prices[day_key]
        avg_price = sum(prices) / len(prices)
        daily_data.append({
            "timestamp": f"{day_key}T12:00:00",
            "price": avg_price
        })
    
    return daily_data


def predict_future_prices(history_data, days_ahead=7):
    """
    Predicts future prices based on historical data with confidence intervals.
    
    Aggregates raw scrape data to daily averages before regression to reduce
    intra-day noise and produce a more meaningful trend signal.
    
    Args:
        history_data: List of dicts with 'timestamp' and 'price'
        days_ahead: Number of days to predict
        
    Returns:
        dict containing:
            - predictions: List of {timestamp, price, upper_70, lower_70, upper_90, lower_90}
            - trend: "Up", "Down", or "Neutral"
            - slope: The slope of the regression line
            - r_squared: Coefficient of determination (model fit quality)
            - confidence_score: Overall confidence percentage (0-100)
    """
    if not history_data or len(history_data) < 3:
        return {
            "predictions": [], 
            "trend": "Insufficient Data", 
            "slope": 0,
            "r_squared": 0,
            "confidence_score": 0
        }
    
    raw_count = len(history_data)
    
    # Aggregate to daily averages to reduce hourly noise
    daily_data = aggregate_to_daily(history_data)
    
    # Fall back to raw data only if we have fewer than 3 daily points
    if len(daily_data) < 3:
        sorted_data = sorted(history_data, key=lambda x: x['timestamp'])
    else:
        sorted_data = daily_data
    
    # Prepare X (timestamps) and Y (prices)
    x_values = [timestamp_to_ordinal(d['timestamp']) for d in sorted_data]
    y_values = [float(d['price']) for d in sorted_data]
    n = len(x_values)
    
    # Perform regression with statistics
    m, b, r_squared, std_error, x_mean, ss_xx = simple_linear_regression(x_values, y_values)

    # Widen bands when recent volatility is high (scale by recent daily return vol)
    vol_scale = 1.0
    if len(y_values) >= 6:
        recent_returns = []
        for j in range(len(y_values) - 5, len(y_values)):
            if y_values[j - 1] > 0:
                recent_returns.append((y_values[j] - y_values[j - 1]) / y_values[j - 1])
        if len(recent_returns) >= 2:
            mean_r = sum(recent_returns) / len(recent_returns)
            recent_vol = math.sqrt(sum((r - mean_r) ** 2 for r in recent_returns) / (len(recent_returns) - 1))
            # if daily vol > 0.8%, widen bands (e.g. 0.008 = 0.8%)
            vol_scale = 1.0 + min(1.0, recent_vol / 0.008)

    # Generate predictions with confidence bands
    last_date_ordinal = x_values[-1]
    predictions = []

    for i in range(1, days_ahead + 1):
        future_ordinal = last_date_ordinal + i
        future_price = m * future_ordinal + b

        # Calculate prediction intervals (scaled by recent vol)
        interval_70 = calculate_prediction_interval(
            future_ordinal, x_mean, ss_xx, std_error, n, confidence=0.70
        ) * vol_scale
        interval_90 = calculate_prediction_interval(
            future_ordinal, x_mean, ss_xx, std_error, n, confidence=0.90
        ) * vol_scale

        predictions.append({
            "timestamp": ordinal_to_timestamp(future_ordinal),
            "price": round(future_price, 2),
            "upper_70": round(future_price + interval_70, 2),
            "lower_70": round(future_price - interval_70, 2),
            "upper_90": round(future_price + interval_90, 2),
            "lower_90": round(future_price - interval_90, 2)
        })

    # Mean-reversion pull: blend linear forecast toward recent average (reduces over-extrapolation)
    current_price = y_values[-1] if y_values else 0
    if len(y_values) >= 5 and current_price > 0:
        recent_ma = sum(y_values[-5:]) / 5
        for i, pred in enumerate(predictions):
            linear_p = pred["price"]
            alpha = min(0.15, 0.05 + i * 0.01)  # 5% day1 up to 12% day7
            blend = (1 - alpha) * linear_p + alpha * recent_ma
            pred["price"] = round(blend, 2)
            half_70 = (pred["upper_70"] - pred["lower_70"]) / 2
            pred["upper_70"] = round(pred["price"] + half_70, 2)
            pred["lower_70"] = round(pred["price"] - half_70, 2)
            half_90 = (pred["upper_90"] - pred["lower_90"]) / 2
            pred["upper_90"] = round(pred["price"] + half_90, 2)
            pred["lower_90"] = round(pred["price"] - half_90, 2)

    # Confidence-aware trend: use 7-day implied return and band confirmation
    trend = "Neutral"
    if predictions and current_price > 0:
        pred_day7 = predictions[-1]["price"]
        lower_70_day7 = predictions[-1]["lower_70"]
        upper_70_day7 = predictions[-1]["upper_70"]
        implied_return_pct = (pred_day7 - current_price) / current_price * 100
        if implied_return_pct > 0.5 and lower_70_day7 > current_price:
            trend = "Up"
        elif implied_return_pct < -0.5 and upper_70_day7 < current_price:
            trend = "Down"
    
    # Calculate confidence score (0-100)
    # Components:
    #   1. R² from daily regression (40%) - how well a line fits daily prices
    #   2. Data sufficiency (25%) - enough days of data for reliable trend
    #   3. Trend consistency (20%) - are recent days moving in the same direction
    #   4. Prediction narrowness (15%) - tighter bands = more confidence
    
    # R² component (on daily data, R² is much more meaningful)
    r2_score = min(r_squared * 1.2, 1.0)  # Slight boost, cap at 1.0
    
    # Data sufficiency: ramp up confidence with more daily data points
    days_available = len(daily_data)
    data_score = min(days_available / 14, 1.0)  # Full confidence at 14+ days
    
    # Trend consistency: check if recent days agree on direction
    if len(y_values) >= 5:
        recent = y_values[-5:]
        direction_changes = sum(
            1 for i in range(1, len(recent))
            if (recent[i] - recent[i-1]) * (recent[-1] - recent[0]) < 0
        )
        consistency_score = max(0, 1.0 - direction_changes * 0.25)
    else:
        consistency_score = 0.5
    
    # Prediction narrowness: compare band width to price level
    if predictions and y_values:
        mid_price = y_values[-1]
        band_width = predictions[0]['upper_70'] - predictions[0]['lower_70']
        if mid_price > 0:
            relative_width = band_width / mid_price
            # Narrow bands (<5%) = high score, wide bands (>20%) = low score
            narrowness_score = max(0, min(1.0, 1.0 - (relative_width - 0.02) / 0.18))
        else:
            narrowness_score = 0.5
    else:
        narrowness_score = 0.5
    
    confidence_score = int(
        (r2_score * 0.40 + data_score * 0.25 + consistency_score * 0.20 + narrowness_score * 0.15) * 100
    )
    confidence_score = max(10, min(95, confidence_score))  # Clamp 10-95 (never 0 or 100)
        
    return {
        "predictions": predictions,
        "trend": trend,
        "slope": round(m, 4),
        "r_squared": round(r_squared, 4),
        "confidence_score": confidence_score,
        "std_error": round(std_error, 2),
        "data_points": raw_count
    }


# ============== Factor Weight Constants (Fallback) ==============
# Used when no trained model is available. Once a model is trained from
# historical data, these are replaced by data-driven calibrated weights.
FALLBACK_WEIGHT_TREND = 0.22
FALLBACK_WEIGHT_USD = 0.28
FALLBACK_WEIGHT_INTEREST_RATE = 0.18
FALLBACK_WEIGHT_SENTIMENT = 0.07      # No historical training data; always manual
FALLBACK_WEIGHT_GEO = 0.10            # No historical training data; always manual
FALLBACK_WEIGHT_CENTRAL_BANK = 0.07   # No historical training data; always manual
# Volatility: damper range 0.70–1.0 (not a directional weight)

# Target total for directional weights (volatility is a separate damper)
_WEIGHT_TARGET_SUM = 0.92


def _get_calibrated_weights(trained_model=None):
    """
    Derive factor weights from a trained model's coefficients, or fall back
    to manual defaults.

    For trained factors (USD, interest rate, momentum/trend), the calibrated
    weight is ``abs(coefficient) * feature_std_dev`` -- this converts the raw
    regression coefficient into a "max daily impact %" that accounts for the
    typical magnitude of each feature.

    Untrained factors (sentiment, geopolitical, central bank) keep their
    manual weights. All weights are then normalized to sum to ~0.92.

    Returns dict with keys: trend, usd, interest_rate, sentiment, geo, central_bank
    """
    if trained_model is None:
        return {
            'trend': FALLBACK_WEIGHT_TREND,
            'usd': FALLBACK_WEIGHT_USD,
            'interest_rate': FALLBACK_WEIGHT_INTEREST_RATE,
            'sentiment': FALLBACK_WEIGHT_SENTIMENT,
            'geo': FALLBACK_WEIGHT_GEO,
            'central_bank': FALLBACK_WEIGHT_CENTRAL_BANK,
        }

    coeffs = trained_model.get('coefficients', {})
    stds = coeffs.get('_feature_stds', {})

    # Calibrated weight = |coefficient| * feature_std  (standardized effect)
    raw_trend = abs(coeffs.get('momentum', 0)) * stds.get('momentum', 1)
    raw_usd = abs(coeffs.get('usd_return', 0)) * stds.get('usd_return', 1)
    raw_ir = abs(coeffs.get('yield_change', 0)) * stds.get('yield_change', 1)

    # Ensure minimums so no factor is completely zeroed out
    raw_trend = max(raw_trend, 0.02)
    raw_usd = max(raw_usd, 0.02)
    raw_ir = max(raw_ir, 0.02)

    # Manual weights for factors without historical training data
    raw_sentiment = FALLBACK_WEIGHT_SENTIMENT
    raw_geo = FALLBACK_WEIGHT_GEO
    raw_cb = FALLBACK_WEIGHT_CENTRAL_BANK

    # Normalize to target sum
    total = raw_trend + raw_usd + raw_ir + raw_sentiment + raw_geo + raw_cb
    if total > 0:
        scale = _WEIGHT_TARGET_SUM / total
        return {
            'trend': round(raw_trend * scale, 4),
            'usd': round(raw_usd * scale, 4),
            'interest_rate': round(raw_ir * scale, 4),
            'sentiment': round(raw_sentiment * scale, 4),
            'geo': round(raw_geo * scale, 4),
            'central_bank': round(raw_cb * scale, 4),
        }

    # Unreachable fallback
    return _get_calibrated_weights(None)


def predict_with_factors(
    history_data,
    days_ahead=7,
    usd_impact=0,
    sentiment_score=0,
    geo_risk_impact=0,
    interest_rate_impact=0,
    central_bank_impact=0,
    trained_model=None,
):
    """
    Enhanced prediction incorporating multiple factors with calibrated weights.

    If a trained_model dict is provided (from model_trainer), factor weights
    are derived from the learned OLS coefficients. Otherwise, falls back to
    the manual FALLBACK_WEIGHT_* constants.

    All factor impacts are normalized to -1..+1 range, then converted to
    percentage-of-price adjustments with a decaying cumulation over the
    prediction horizon (front-loads impact, decays ~15%/day).

    Args:
        history_data: List of dicts with 'timestamp' and 'price'
        days_ahead: Number of days to predict
        usd_impact: USD strength impact (-1 to 1, positive = bullish for gold)
        sentiment_score: News sentiment score (-1 to 1)
        geo_risk_impact: Geopolitical risk impact (-1 to 1, positive = bullish)
        interest_rate_impact: Treasury yield impact (-1 to 1, positive = bullish)
        central_bank_impact: Central bank buying impact (-1 to 1, positive = bullish)
        trained_model: Optional dict from model_trainer.load_latest_model()

    Returns:
        dict containing predictions with factor attribution and model accuracy
    """
    # Get base prediction from linear regression
    base_result = predict_future_prices(history_data, days_ahead)

    if not base_result['predictions']:
        return base_result

    # Calculate current price from last historical data point
    if history_data:
        sorted_data = sorted(history_data, key=lambda x: x['timestamp'])
        current_price = float(sorted_data[-1]['price'])
    else:
        current_price = base_result['predictions'][0]['price']

    if current_price <= 0:
        return base_result

    # Get calibrated weights (data-driven or fallback)
    w = _get_calibrated_weights(trained_model)
    using_trained = trained_model is not None

    logger.info(
        f"Factor weights ({'trained' if using_trained else 'fallback'}): "
        f"trend={w['trend']:.3f} usd={w['usd']:.3f} ir={w['interest_rate']:.3f} "
        f"sent={w['sentiment']:.3f} geo={w['geo']:.3f} cb={w['central_bank']:.3f}"
    )

    # Per-day adjustment percentages (max ±weight% per day for each factor)
    usd_adj_pct = usd_impact * w['usd']
    ir_adj_pct = interest_rate_impact * w['interest_rate']
    sentiment_adj_pct = sentiment_score * w['sentiment']
    geo_adj_pct = geo_risk_impact * w['geo']
    cb_adj_pct = central_bank_impact * w['central_bank']

    # Calculate volatility damper from daily-aggregated data
    daily_data = aggregate_to_daily(history_data)
    if len(daily_data) >= 7:
        daily_prices = [float(d['price']) for d in daily_data[-14:]]
        mean_price = sum(daily_prices) / len(daily_prices)
        if mean_price > 0:
            variance = sum((p - mean_price) ** 2 for p in daily_prices) / len(daily_prices)
            volatility = math.sqrt(variance) / mean_price
            volatility_damper = max(0.70, 1 - volatility * 5)
        else:
            volatility_damper = 1.0
    else:
        volatility_damper = 1.0

    # Use residual_std from trained model for better confidence band calibration
    model_residual_std = None
    if trained_model:
        model_residual_std = trained_model.get('residual_std')

    # Apply adjustments to each prediction day
    adjusted_predictions = []
    for i, pred in enumerate(base_result['predictions']):
        day_number = i + 1

        # Decaying cumulation: impact decays ~15% per day beyond day 1
        decay_factor = max(0.3, 1.0 - 0.15 * (day_number - 1))
        cumulative_scale = day_number * decay_factor

        # Convert trend contribution to percentage of current price
        trend_contribution_abs = pred['price'] - current_price
        trend_adj_pct = (trend_contribution_abs / current_price) * 100

        # Weighted sum of all factor adjustments (all in % of price)
        weighted_change_pct = (
            trend_adj_pct * w['trend'] +
            usd_adj_pct * cumulative_scale +
            ir_adj_pct * cumulative_scale +
            sentiment_adj_pct * cumulative_scale +
            geo_adj_pct * cumulative_scale +
            cb_adj_pct * cumulative_scale
        )

        # Apply volatility damper to the entire change
        adjusted_change = current_price * (weighted_change_pct / 100) * volatility_damper
        adjusted_price = current_price + adjusted_change

        # Confidence bands: use model residual_std if available for calibration
        if model_residual_std and model_residual_std > 0:
            # residual_std is in daily return %. Scale by sqrt(days) for multi-day.
            band_70_abs = current_price * (model_residual_std / 100) * 1.04 * math.sqrt(day_number)
            band_90_abs = current_price * (model_residual_std / 100) * 1.65 * math.sqrt(day_number)
        else:
            # Fall back to regression-based bands
            band_70_abs = pred['upper_70'] - pred['price']
            band_90_abs = pred['upper_90'] - pred['price']

        adjusted_predictions.append({
            "timestamp": pred['timestamp'],
            "price": round(adjusted_price, 2),
            "upper_70": round(adjusted_price + band_70_abs, 2),
            "lower_70": round(adjusted_price - band_70_abs, 2),
            "upper_90": round(adjusted_price + band_90_abs, 2),
            "lower_90": round(adjusted_price - band_90_abs, 2)
        })

    # Calculate factor attribution (total contribution over full horizon)
    last_pred = adjusted_predictions[-1] if adjusted_predictions else None
    total_change = last_pred['price'] - current_price if last_pred else 0

    final_decay = max(0.3, 1.0 - 0.15 * (days_ahead - 1))
    final_cumulative = days_ahead * final_decay

    # Trend attribution: regression contribution * weight * damper
    base_trend_abs = base_result['predictions'][-1]['price'] - current_price if base_result['predictions'] else 0
    trend_attr_pct = (base_trend_abs / current_price) * 100 if current_price > 0 else 0
    trend_value = current_price * (trend_attr_pct * w['trend'] / 100) * volatility_damper

    usd_value = current_price * (usd_adj_pct * final_cumulative / 100) * volatility_damper
    ir_value = current_price * (ir_adj_pct * final_cumulative / 100) * volatility_damper
    sentiment_value = current_price * (sentiment_adj_pct * final_cumulative / 100) * volatility_damper
    geo_value = current_price * (geo_adj_pct * final_cumulative / 100) * volatility_damper
    cb_value = current_price * (cb_adj_pct * final_cumulative / 100) * volatility_damper

    def _direction(val):
        return 'up' if val > 0 else 'down' if val < 0 else 'neutral'

    factor_attribution = {
        'trend': {
            'value': round(trend_value, 2),
            'direction': _direction(trend_value),
            'label': 'Historical Trend'
        },
        'usd': {
            'value': round(usd_value, 2),
            'direction': _direction(usd_value),
            'label': 'USD Strength'
        },
        'interest_rate': {
            'value': round(ir_value, 2),
            'direction': _direction(ir_value),
            'label': 'Interest Rate'
        },
        'sentiment': {
            'value': round(sentiment_value, 2),
            'direction': _direction(sentiment_value),
            'label': 'News Sentiment'
        },
        'geopolitical': {
            'value': round(geo_value, 2),
            'direction': _direction(geo_value),
            'label': 'Geopolitical Risk'
        },
        'central_bank': {
            'value': round(cb_value, 2),
            'direction': _direction(cb_value),
            'label': 'Central Bank Activity'
        },
        'volatility': {
            'value': round(volatility_damper, 2),
            'direction': 'neutral',
            'label': 'Volatility Adjustment'
        }
    }

    # Determine trend based on adjusted predictions
    adjusted_trend = "Neutral"
    if total_change > current_price * 0.005:
        adjusted_trend = "Up"
    elif total_change < -current_price * 0.005:
        adjusted_trend = "Down"

    # Build model accuracy info
    model_accuracy = None
    if trained_model:
        model_accuracy = {
            "r_squared": trained_model.get('r_squared'),
            "mae_pct": trained_model.get('mae'),
            "mape_pct": trained_model.get('mape'),
            "training_points": trained_model.get('training_points'),
            "weights_source": "trained",
        }

    # Build factor weights summary for the UI (rounded percentages)
    factor_weights = {
        "trend": round(w['trend'] * 100, 1),
        "usd": round(w['usd'] * 100, 1),
        "interest_rate": round(w['interest_rate'] * 100, 1),
        "sentiment": round(w['sentiment'] * 100, 1),
        "geo": round(w['geo'] * 100, 1),
        "central_bank": round(w['central_bank'] * 100, 1),
    }

    return {
        "predictions": adjusted_predictions,
        "trend": adjusted_trend,
        "slope": base_result['slope'],
        "r_squared": base_result['r_squared'],
        "confidence_score": base_result['confidence_score'],
        "std_error": base_result['std_error'],
        "data_points": base_result['data_points'],
        "factor_attribution": factor_attribution,
        "factors_applied": {
            "usd_impact": usd_impact,
            "interest_rate_impact": interest_rate_impact,
            "sentiment_score": sentiment_score,
            "geo_risk_impact": geo_risk_impact,
            "central_bank_impact": central_bank_impact,
            "volatility_damper": round(volatility_damper, 2),
            "model_accuracy": model_accuracy,
            "factor_weights": factor_weights,
        }
    }
