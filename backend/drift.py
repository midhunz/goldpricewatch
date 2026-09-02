"""
Drift - Concept drift detection using live prediction accuracy over time.

Compares recent PredictionAccuracy records (e.g. last 7 days) to an older
window (e.g. previous 7 days or baseline). Flags concept drift when
recent MAPE worsens significantly or direction accuracy drops below threshold.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from models import PredictionAccuracy

logger = logging.getLogger(__name__)

# Default windows (days) for recent vs previous/baseline
CONCEPT_DRIFT_RECENT_DAYS = 7
CONCEPT_DRIFT_PREVIOUS_DAYS = 7
# Relative increase in MAPE to flag (e.g. 20% worse)
CONCEPT_DRIFT_MAPE_WORSE_PCT = 20.0
# Direction accuracy below this (0-100) flags drift
CONCEPT_DRIFT_DIRECTION_ACCURACY_MIN = 50.0


def get_concept_drift_status(
    db: Session,
    recent_days: int = CONCEPT_DRIFT_RECENT_DAYS,
    previous_days: int = CONCEPT_DRIFT_PREVIOUS_DAYS,
    mape_worse_pct_threshold: float = CONCEPT_DRIFT_MAPE_WORSE_PCT,
    direction_accuracy_min: float = CONCEPT_DRIFT_DIRECTION_ACCURACY_MIN,
) -> Dict:
    """
    Compare recent vs previous windows of PredictionAccuracy and return concept drift status.

    Uses predicted_at to bucket records. Recent = last recent_days, previous = the
    previous_days before that. Returns aggregate MAPE and direction accuracy for
    each window and a concept_drift flag plus message.
    """
    now = datetime.now()
    recent_start = now - timedelta(days=recent_days)
    previous_end = recent_start
    previous_start = previous_end - timedelta(days=previous_days)

    # Records in recent window
    recent_records: List[PredictionAccuracy] = (
        db.query(PredictionAccuracy)
        .filter(
            PredictionAccuracy.predicted_at >= recent_start,
            PredictionAccuracy.predicted_at <= now,
        )
        .all()
    )
    # Records in previous window
    previous_records: List[PredictionAccuracy] = (
        db.query(PredictionAccuracy)
        .filter(
            PredictionAccuracy.predicted_at >= previous_start,
            PredictionAccuracy.predicted_at < previous_end,
        )
        .all()
    )

    def _aggregate(records: List[PredictionAccuracy]) -> Dict:
        if not records:
            return {
                "count": 0,
                "avg_mape": None,
                "direction_accuracy_pct": None,
            }
        n = len(records)
        avg_mape = sum(r.mape for r in records if r.mape is not None) / n
        direction_correct = sum(r.direction_correct for r in records if r.direction_correct is not None)
        direction_accuracy_pct = (direction_correct / n) * 100 if n else None
        return {
            "count": n,
            "avg_mape": round(avg_mape, 4) if avg_mape is not None else None,
            "direction_accuracy_pct": round(direction_accuracy_pct, 1) if direction_accuracy_pct is not None else None,
        }

    recent_agg = _aggregate(recent_records)
    previous_agg = _aggregate(previous_records)

    concept_drift = False
    reasons: List[str] = []

    if recent_agg["count"] < 2:
        message = (
            "Not enough recent accuracy records (need at least 2 in recent window) "
            f"to assess concept drift. Recent count={recent_agg['count']}."
        )
        return {
            "concept_drift": False,
            "message": message,
            "recent": recent_agg,
            "previous": previous_agg,
            "recent_window_start": recent_start.isoformat(),
            "recent_window_end": now.isoformat(),
            "previous_window_start": previous_start.isoformat(),
            "previous_window_end": previous_end.isoformat(),
        }

    if previous_agg["avg_mape"] is not None and previous_agg["avg_mape"] > 0:
        recent_mape = recent_agg["avg_mape"] or 0
        prev_mape = previous_agg["avg_mape"]
        mape_increase_pct = ((recent_mape - prev_mape) / prev_mape) * 100
        if mape_increase_pct > mape_worse_pct_threshold:
            concept_drift = True
            reasons.append(f"MAPE increased by {mape_increase_pct:.1f}% (threshold {mape_worse_pct_threshold}%)")

    if recent_agg["direction_accuracy_pct"] is not None and recent_agg["direction_accuracy_pct"] < direction_accuracy_min:
        concept_drift = True
        reasons.append(
            f"Direction accuracy {recent_agg['direction_accuracy_pct']:.1f}% "
            f"below minimum {direction_accuracy_min}%"
        )

    message = (
        "Concept drift detected: " + "; ".join(reasons)
        if concept_drift
        else "No significant concept drift in live prediction accuracy."
    )

    return {
        "concept_drift": concept_drift,
        "message": message,
        "recent": recent_agg,
        "previous": previous_agg,
        "recent_window_start": recent_start.isoformat(),
        "recent_window_end": now.isoformat(),
        "previous_window_start": previous_start.isoformat(),
        "previous_window_end": previous_end.isoformat(),
    }
