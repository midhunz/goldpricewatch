"""
Model Trainer - Train multi-factor OLS regression from historical data.

Aligns historical gold prices, Treasury yields, and USD index by date,
computes daily features (returns, yield changes, momentum), then fits
a multi-variate OLS regression to learn factor coefficients.

The learned coefficients replace the hardcoded WEIGHT_* constants in
prediction.py, giving data-driven factor scaling.

Retrains weekly; results stored in the trained_models table.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    HistoricalGoldPrice,
    HistoricalTreasuryYield,
    HistoricalUsdIndex,
    TrainedModel,
)

logger = logging.getLogger(__name__)

MODEL_NAME = "gold_factor_ols"
MIN_DATA_POINTS = 100  # Minimum feature rows to attempt training
MIN_ALIGNED_ROWS = 161  # Need 61 for first feature row + 100 for min points (realized_vol needs 60-day lookback)


# ---------------------------------------------------------------------------
# 1. Align historical tables by date
# ---------------------------------------------------------------------------

def align_historical_data(db: Session) -> List[Dict]:
    """
    Inner-join the 3 historical tables on date.

    Returns a list of dicts sorted by date:
        [{"date": date, "gold": float, "usd": float, "yield_10y": float}, ...]
    """
    gold_rows = (
        db.query(HistoricalGoldPrice.date, HistoricalGoldPrice.price_usd)
        .order_by(HistoricalGoldPrice.date)
        .all()
    )
    yield_rows = (
        db.query(HistoricalTreasuryYield.date, HistoricalTreasuryYield.yield_10y)
        .order_by(HistoricalTreasuryYield.date)
        .all()
    )
    usd_rows = (
        db.query(HistoricalUsdIndex.date, HistoricalUsdIndex.usd_index)
        .order_by(HistoricalUsdIndex.date)
        .all()
    )

    # Build lookup dicts keyed by date
    yield_map = {row.date: row.yield_10y for row in yield_rows}
    usd_map = {row.date: row.usd_index for row in usd_rows}

    aligned: List[Dict] = []
    for row in gold_rows:
        d = row.date
        if d in yield_map and d in usd_map:
            aligned.append({
                "date": d,
                "gold": row.price_usd,
                "usd": usd_map[d],
                "yield_10y": yield_map[d],
            })

    logger.info(
        f"Aligned {len(aligned)} data points "
        f"(gold={len(gold_rows)}, yields={len(yield_rows)}, usd={len(usd_rows)})"
    )
    return aligned


# ---------------------------------------------------------------------------
# 2. Compute features from aligned data
# ---------------------------------------------------------------------------

def compute_features(aligned: List[Dict]) -> Tuple[np.ndarray, np.ndarray, List[str], Dict[str, float]]:
    """
    From aligned raw data, compute daily features for regression.

    Features (X columns):
        - usd_return:   daily % change in USD index
        - yield_change: daily absolute change in 10Y Treasury yield
        - momentum:     10-day MA / 50-day MA ratio of gold price
        - realized_vol: 10-day rolling std of gold daily returns (%)

    Target (y):
        - gold_return:  daily % change in gold price

    Returns:
        (X, y, feature_names, feature_stds)  where X is (N, 4) and y is (N,)
    """
    n = len(aligned)
    if n < 61:  # Need 50 for MA-50 and 10 prior returns for realized_vol
        return np.array([]), np.array([]), [], {}

    # Pre-compute gold prices for moving averages
    gold_prices = [row["gold"] for row in aligned]

    feature_names = ["usd_return", "yield_change", "momentum", "realized_vol"]
    X_rows: List[List[float]] = []
    y_rows: List[float] = []

    for i in range(60, n):
        prev = aligned[i - 1]
        curr = aligned[i]

        # Skip rows with zero or missing values
        if prev["gold"] <= 0 or prev["usd"] <= 0:
            continue

        # Target: gold daily return (%)
        gold_return = (curr["gold"] - prev["gold"]) / prev["gold"] * 100

        # Feature 1: USD index daily return (%)
        usd_return = (curr["usd"] - prev["usd"]) / prev["usd"] * 100

        # Feature 2: Yield absolute daily change (basis points)
        yield_change = curr["yield_10y"] - prev["yield_10y"]

        # Feature 3: Momentum (MA-10 / MA-50 ratio, centered around 0)
        ma_10 = sum(gold_prices[i - 9 : i + 1]) / 10
        ma_50 = sum(gold_prices[i - 49 : i + 1]) / 50
        momentum = (ma_10 / ma_50 - 1.0) * 100 if ma_50 > 0 else 0

        # Feature 4: 10-day rolling std of gold daily returns (%)
        returns_10 = []
        for j in range(i - 9, i + 1):
            p_prev = aligned[j - 1]["gold"]
            p_curr = aligned[j]["gold"]
            if p_prev > 0:
                returns_10.append((p_curr - p_prev) / p_prev * 100)
        realized_vol = float(np.std(returns_10)) if len(returns_10) >= 2 else 0.0

        X_rows.append([usd_return, yield_change, momentum, realized_vol])
        y_rows.append(gold_return)

    X = np.array(X_rows, dtype=np.float64)
    y = np.array(y_rows, dtype=np.float64)

    logger.info(f"Computed {len(y)} feature rows with {len(feature_names)} features")

    # Compute feature standard deviations (needed to convert coefficients to weights)
    feature_stds = {}
    if len(X) > 0:
        for i, name in enumerate(feature_names):
            feature_stds[name] = float(np.std(X[:, i]))

    return X, y, feature_names, feature_stds


def _compute_features_with_dates(
    aligned: List[Dict],
) -> Tuple[np.ndarray, np.ndarray, List[str], Dict[str, float], List]:
    """
    Same as compute_features but also returns list of dates (one per row).
    Returns (X, y, feature_names, feature_stds, row_dates).
    """
    n = len(aligned)
    if n < 61:
        return np.array([]), np.array([]), [], {}, []

    gold_prices = [row["gold"] for row in aligned]
    feature_names = ["usd_return", "yield_change", "momentum", "realized_vol"]
    X_rows: List[List[float]] = []
    y_rows: List[float] = []
    date_rows: List = []

    for i in range(60, n):
        prev = aligned[i - 1]
        curr = aligned[i]
        if prev["gold"] <= 0 or prev["usd"] <= 0:
            continue
        gold_return = (curr["gold"] - prev["gold"]) / prev["gold"] * 100
        usd_return = (curr["usd"] - prev["usd"]) / prev["usd"] * 100
        yield_change = curr["yield_10y"] - prev["yield_10y"]
        ma_10 = sum(gold_prices[i - 9 : i + 1]) / 10
        ma_50 = sum(gold_prices[i - 49 : i + 1]) / 50
        momentum = (ma_10 / ma_50 - 1.0) * 100 if ma_50 > 0 else 0
        returns_10 = []
        for j in range(i - 9, i + 1):
            p_prev = aligned[j - 1]["gold"]
            p_curr = aligned[j]["gold"]
            if p_prev > 0:
                returns_10.append((p_curr - p_prev) / p_prev * 100)
        realized_vol = float(np.std(returns_10)) if len(returns_10) >= 2 else 0.0
        X_rows.append([usd_return, yield_change, momentum, realized_vol])
        y_rows.append(gold_return)
        date_rows.append(curr["date"])

    X = np.array(X_rows, dtype=np.float64)
    y = np.array(y_rows, dtype=np.float64)
    feature_stds = {}
    if len(X) > 0:
        for i, name in enumerate(feature_names):
            feature_stds[name] = float(np.std(X[:, i]))
    return X, y, feature_names, feature_stds, date_rows


# ---------------------------------------------------------------------------
# 3. OLS regression via numpy
# ---------------------------------------------------------------------------

def train_ols(
    X: np.ndarray, y: np.ndarray
) -> Tuple[np.ndarray, float, float]:
    """
    Fit multi-variate OLS: y = X_aug @ beta  (X_aug includes intercept column).

    Returns:
        (beta, r_squared, residual_std)
        beta[0] is the intercept; beta[1:] are feature coefficients.
    """
    n, k = X.shape

    # Augment X with intercept column
    ones = np.ones((n, 1))
    X_aug = np.hstack([ones, X])

    # Solve via least squares (handles rank-deficient cases)
    beta, residuals, rank, sv = np.linalg.lstsq(X_aug, y, rcond=None)

    # Predictions and R²
    y_pred = X_aug @ beta
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Residual standard deviation
    residual_std = math.sqrt(ss_res / max(n - k - 1, 1))

    return beta, float(r_squared), float(residual_std)


# ---------------------------------------------------------------------------
# 4. Validation (train/test split)
# ---------------------------------------------------------------------------

def validate_model(
    X: np.ndarray, y: np.ndarray, train_ratio: float = 0.8
) -> Dict:
    """
    80/20 train/test split validation.

    Returns dict with coefficients, R², MAE, MAPE, and other metrics.
    """
    n = len(y)
    split = int(n * train_ratio)

    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # Train on first 80%
    beta, r_sq_train, residual_std = train_ols(X_train, y_train)

    # Evaluate on test set
    ones_test = np.ones((len(X_test), 1))
    X_test_aug = np.hstack([ones_test, X_test])
    y_pred_test = X_test_aug @ beta

    errors = np.abs(y_test - y_pred_test)
    mae = float(np.mean(errors))

    # MAPE: avoid division by zero for near-zero returns
    nonzero_mask = np.abs(y_test) > 0.001
    if np.any(nonzero_mask):
        mape = float(np.mean(errors[nonzero_mask] / np.abs(y_test[nonzero_mask])) * 100)
    else:
        mape = 0.0

    # R² on test set
    ss_res_test = np.sum((y_test - y_pred_test) ** 2)
    ss_tot_test = np.sum((y_test - np.mean(y_test)) ** 2)
    r_sq_test = 1 - ss_res_test / ss_tot_test if ss_tot_test > 0 else 0.0

    return {
        "beta": beta,
        "r_squared_train": r_sq_train,
        "r_squared_test": float(r_sq_test),
        "mae": mae,
        "mape": mape,
        "residual_std": residual_std,
        "train_points": split,
        "test_points": n - split,
    }


# ---------------------------------------------------------------------------
# 5. Full pipeline: train on all data, validate, store
# ---------------------------------------------------------------------------

def train_and_store(db: Session) -> Optional[Dict]:
    """
    End-to-end training pipeline:
      1. Align historical data
      2. Compute features
      3. Validate with 80/20 split (for metrics)
      4. Retrain on ALL data (for production coefficients)
      5. Store in trained_models table

    Returns the stored model info dict, or None on failure.
    """
    logger.info("=== Starting model training ===")

    # 1. Align
    aligned = align_historical_data(db)
    if len(aligned) < MIN_ALIGNED_ROWS:
        logger.warning(
            f"Not enough aligned data ({len(aligned)} < {MIN_ALIGNED_ROWS}). "
            "Skipping training."
        )
        return None

    # 2. Features
    X, y, feature_names, feature_stds = compute_features(aligned)
    if len(y) < MIN_DATA_POINTS:
        logger.warning(
            f"Not enough feature rows ({len(y)} < {MIN_DATA_POINTS}). "
            "Skipping training."
        )
        return None

    # 3. Validate (80/20 split)
    val = validate_model(X, y)

    logger.info(
        f"Validation: R²_train={val['r_squared_train']:.4f}, "
        f"R²_test={val['r_squared_test']:.4f}, "
        f"MAE={val['mae']:.4f}%, MAPE={val['mape']:.1f}%"
    )

    # 4. Retrain on ALL data for production coefficients
    beta_full, r_sq_full, residual_std_full = train_ols(X, y)

    coefficients = {"intercept": round(float(beta_full[0]), 6)}
    for i, name in enumerate(feature_names):
        coefficients[name] = round(float(beta_full[i + 1]), 6)

    # Store feature standard deviations alongside coefficients
    # These are used to convert raw coefficients to calibrated weights:
    #   calibrated_weight = abs(coefficient) * feature_std
    coefficients["_feature_stds"] = {
        k: round(v, 6) for k, v in feature_stds.items()
    }

    # Determine training period
    dates = [row["date"] for row in aligned]
    period_start = dates[0]
    period_end = dates[-1]

    logger.info(
        f"Full model: R²={r_sq_full:.4f}, coefficients={coefficients}, "
        f"period={period_start} to {period_end}"
    )

    # 5. Store
    record = TrainedModel(
        model_name=MODEL_NAME,
        coefficients=coefficients,
        feature_names=feature_names,
        r_squared=round(r_sq_full, 4),
        mae=round(val["mae"], 4),
        mape=round(val["mape"], 2),
        training_points=len(y),
        test_points=val["test_points"],
        training_period_start=period_start,
        training_period_end=period_end,
        residual_std=round(residual_std_full, 4),
        executed_at=datetime.now(),
    )
    db.add(record)
    db.commit()

    result = {
        "model_name": MODEL_NAME,
        "coefficients": coefficients,
        "feature_names": feature_names,
        "r_squared": round(r_sq_full, 4),
        "mae": round(val["mae"], 4),
        "mape": round(val["mape"], 2),
        "training_points": len(y),
        "test_points": val["test_points"],
        "residual_std": round(residual_std_full, 4),
        "period": f"{period_start} to {period_end}",
    }

    logger.info(f"=== Model training complete. Stored as '{MODEL_NAME}'. ===")
    return result


# ---------------------------------------------------------------------------
# 6. Load latest trained model
# ---------------------------------------------------------------------------

def load_latest_model(db: Session) -> Optional[Dict]:
    """
    Load the most recent trained model from the database.

    Returns dict with coefficients and metrics, or None if no model exists.
    """
    record = (
        db.query(TrainedModel)
        .filter(TrainedModel.model_name == MODEL_NAME)
        .order_by(TrainedModel.executed_at.desc())
        .first()
    )

    if not record:
        return None

    return {
        "coefficients": record.coefficients,
        "feature_names": record.feature_names,
        "r_squared": record.r_squared,
        "mae": record.mae,
        "mape": record.mape,
        "residual_std": record.residual_std,
        "training_points": record.training_points,
        "executed_at": record.executed_at,
    }


def is_model_stale(db: Session, max_age_days: int = 7) -> bool:
    """Check if the latest model is older than max_age_days."""
    record = (
        db.query(TrainedModel)
        .filter(TrainedModel.model_name == MODEL_NAME)
        .order_by(TrainedModel.executed_at.desc())
        .first()
    )

    if not record:
        return True  # No model = stale

    age = datetime.now() - record.executed_at
    return age > timedelta(days=max_age_days)


# ---------------------------------------------------------------------------
# 7. Performance and drift validation
# ---------------------------------------------------------------------------

def get_model_metrics_history(db: Session, limit: int = 5) -> List[Dict]:
    """
    Return the last N trained model records with their metrics (for trend view).

    Each dict includes: model_name, r_squared, mae, mape, residual_std,
    training_points, test_points, training_period_start, training_period_end, executed_at.
    """
    records = (
        db.query(TrainedModel)
        .filter(TrainedModel.model_name == MODEL_NAME)
        .order_by(TrainedModel.executed_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "model_name": r.model_name,
            "r_squared": r.r_squared,
            "mae": r.mae,
            "mape": r.mape,
            "residual_std": r.residual_std,
            "training_points": r.training_points,
            "test_points": r.test_points,
            "training_period_start": r.training_period_start.isoformat() if r.training_period_start else None,
            "training_period_end": r.training_period_end.isoformat() if r.training_period_end else None,
            "executed_at": r.executed_at.isoformat() if r.executed_at else None,
        }
        for r in records
    ]


# Default thresholds for model-metrics drift (tunable)
DRIFT_R2_DROP_THRESHOLD = 0.05
DRIFT_MAE_INCREASE_PCT = 20.0
DRIFT_MAPE_INCREASE_PCT = 20.0


def get_model_drift_status(
    db: Session,
    r2_drop_threshold: float = DRIFT_R2_DROP_THRESHOLD,
    mae_increase_pct: float = DRIFT_MAE_INCREASE_PCT,
    mape_increase_pct: float = DRIFT_MAPE_INCREASE_PCT,
) -> Dict:
    """
    Compare latest vs previous TrainedModel run and return drift status.

    Returns dict with: latest, previous, delta_r2, delta_mae, delta_mape,
    model_metrics_drift (bool), message.
    """
    records = (
        db.query(TrainedModel)
        .filter(TrainedModel.model_name == MODEL_NAME)
        .order_by(TrainedModel.executed_at.desc())
        .limit(2)
        .all()
    )
    if len(records) < 2:
        return {
            "latest": _record_to_metrics_dict(records[0]) if records else None,
            "previous": None,
            "delta_r2": None,
            "delta_mae": None,
            "delta_mape": None,
            "model_metrics_drift": False,
            "message": "Not enough training history (need at least 2 runs) to compute drift.",
        }
    latest, previous = records[0], records[1]
    latest_d = _record_to_metrics_dict(latest)
    previous_d = _record_to_metrics_dict(previous)
    delta_r2 = (latest.r_squared or 0) - (previous.r_squared or 0)
    delta_mae = (latest.mae or 0) - (previous.mae or 0)
    delta_mape = (latest.mape or 0) - (previous.mape or 0)
    prev_mae = previous.mae or 1e-9
    prev_mape = previous.mape or 1e-9
    mae_pct = (delta_mae / prev_mae) * 100 if prev_mae else 0
    mape_pct = (delta_mape / prev_mape) * 100 if prev_mape else 0
    # Drift: R² dropped by more than threshold, or MAE/MAPE increased by more than threshold
    r2_drift = delta_r2 < -r2_drop_threshold
    mae_drift = mae_pct > mae_increase_pct
    mape_drift = mape_pct > mape_increase_pct
    model_metrics_drift = r2_drift or mae_drift or mape_drift
    message = (
        "Model metrics drift detected: "
        + ", ".join(
            filter(
                None,
                [
                    f"R² drop {delta_r2:.4f}" if r2_drift else None,
                    f"MAE +{mae_pct:.1f}%" if mae_drift else None,
                    f"MAPE +{mape_pct:.1f}%" if mape_drift else None,
                ]
            )
        )
        if model_metrics_drift
        else "No significant model metrics drift."
    )
    return {
        "latest": latest_d,
        "previous": previous_d,
        "delta_r2": round(delta_r2, 4),
        "delta_mae": round(delta_mae, 4),
        "delta_mape": round(delta_mape, 4),
        "model_metrics_drift": model_metrics_drift,
        "message": message,
    }


def _record_to_metrics_dict(r: TrainedModel) -> Dict:
    return {
        "r_squared": r.r_squared,
        "mae": r.mae,
        "mape": r.mape,
        "residual_std": r.residual_std,
        "training_points": r.training_points,
        "test_points": r.test_points,
        "training_period_start": r.training_period_start.isoformat() if r.training_period_start else None,
        "training_period_end": r.training_period_end.isoformat() if r.training_period_end else None,
        "executed_at": r.executed_at.isoformat() if r.executed_at else None,
    }


FEATURE_DRIFT_DEVIATION_PCT = 30.0


def compute_feature_drift(
    db: Session,
    recent_days: int = 14,
    deviation_pct_threshold: float = FEATURE_DRIFT_DEVIATION_PCT,
) -> Dict:
    """
    Compare recent feature distributions (last recent_days) to training window.

    Uses the latest TrainedModel's training_period_start/end as the training
    window. Returns per-feature stats (training vs recent mean/std) and
    data_drift (True if any feature's recent mean or std deviates by more
    than deviation_pct_threshold from training).
    """
    from datetime import date as date_type

    latest = (
        db.query(TrainedModel)
        .filter(TrainedModel.model_name == MODEL_NAME)
        .order_by(TrainedModel.executed_at.desc())
        .first()
    )
    if not latest or not latest.training_period_start or not latest.training_period_end:
        return {
            "data_drift": False,
            "message": "No trained model or training period to compare.",
            "training_stats": {},
            "recent_stats": {},
            "feature_drift_detected": [],
        }

    aligned = align_historical_data(db)
    if len(aligned) < 51:
        return {
            "data_drift": False,
            "message": "Insufficient aligned data for feature drift.",
            "training_stats": {},
            "recent_stats": {},
            "feature_drift_detected": [],
        }

    X, y, feature_names, feature_stds, row_dates = _compute_features_with_dates(aligned)
    if len(row_dates) == 0:
        return {
            "data_drift": False,
            "message": "No feature rows computed.",
            "training_stats": {},
            "recent_stats": {},
            "feature_drift_detected": [],
        }

    train_start = latest.training_period_start
    train_end = latest.training_period_end
    today = date_type.today()
    recent_start = today - timedelta(days=recent_days)

    train_mask = np.array(
        [train_start <= d <= train_end for d in row_dates], dtype=bool
    )
    recent_mask = np.array([d >= recent_start for d in row_dates], dtype=bool)

    training_stats = {}
    recent_stats = {}
    feature_drift_detected = []

    for j, name in enumerate(feature_names):
        col = X[:, j]
        train_vals = col[train_mask]
        recent_vals = col[recent_mask]
        if len(train_vals) == 0:
            training_stats[name] = {"mean": None, "std": None}
        else:
            training_stats[name] = {
                "mean": float(np.mean(train_vals)),
                "std": float(np.std(train_vals)) if len(train_vals) > 1 else 0.0,
            }
        if len(recent_vals) == 0:
            recent_stats[name] = {"mean": None, "std": None}
        else:
            recent_stats[name] = {
                "mean": float(np.mean(recent_vals)),
                "std": float(np.std(recent_vals)) if len(recent_vals) > 1 else 0.0,
            }
        t_mean = training_stats[name]["mean"]
        t_std = training_stats[name]["std"]
        r_mean = recent_stats[name]["mean"]
        r_std = recent_stats[name]["std"]
        if t_mean is None or r_mean is None:
            continue
        denom_mean = abs(t_mean) + 1e-9
        denom_std = abs(t_std) + 1e-9
        mean_pct = abs(r_mean - t_mean) / denom_mean * 100
        std_pct = abs(r_std - t_std) / denom_std * 100 if t_std is not None and r_std is not None else 0
        if mean_pct > deviation_pct_threshold or std_pct > deviation_pct_threshold:
            feature_drift_detected.append(name)

    data_drift = len(feature_drift_detected) > 0
    message = (
        f"Data drift detected in features: {feature_drift_detected}."
        if data_drift
        else "No significant feature distribution drift."
    )
    return {
        "data_drift": data_drift,
        "message": message,
        "training_stats": training_stats,
        "recent_stats": recent_stats,
        "feature_drift_detected": feature_drift_detected,
        "training_points": int(np.sum(train_mask)),
        "recent_points": int(np.sum(recent_mask)),
    }


# ---------------------------------------------------------------------------
# CLI entry point for manual training
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Ensure tables exist (handles first-time runs on new DBs)
    from database import engine, Base
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        result = train_and_store(db)
        if result:
            print(f"\nTrained model: {result['model_name']}")
            print(f"  Coefficients: {result['coefficients']}")
            print(f"  R²: {result['r_squared']}")
            print(f"  MAE: {result['mae']}%")
            print(f"  MAPE: {result['mape']}%")
            print(f"  Training points: {result['training_points']}")
            print(f"  Period: {result['period']}")
        else:
            print("Training failed - insufficient data")
    finally:
        db.close()
