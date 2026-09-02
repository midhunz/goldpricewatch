"""
Print gold price model validation result and reasons for low accuracy to the console.
Uses existing model_trainer, drift, and DB only. No new system implementation.
Run from backend: python validate_console.py
"""

import sys
from datetime import datetime

# Run from backend directory so imports work
if __name__ == "__main__":
    from database import SessionLocal
    from models import PredictionAccuracy
    from model_trainer import (
        get_model_metrics_history,
        get_model_drift_status,
        compute_feature_drift,
    )
    from drift import get_concept_drift_status

    def _reasons():
        return [
            ("Simple linear trend extrapolation", "Price forecasts use a straight-line fit on past prices. Gold is volatile and mean-reverting, so extrapolating a line tends to be weak beyond a few days."),
            ("Factor model predicts daily returns, not price levels", "The OLS model predicts daily gold return (%), not the 7-day price path. R² on daily returns is often low; small errors compound over the horizon."),
            ("Only three factors in the OLS model", "USD return, yield change, momentum. Geopolitics and other drivers are not trained from history, so their impact may be mis-scaled."),
            ("Region-specific prices add noise", "Evaluation uses scraped rates per region/purity. Different currencies and premiums add noise vs a single USD series."),
            ("Actuals from scraped daily averages", "If scraping is sparse or delayed, the 'actual' price used for MAE/MAPE is noisy."),
            ("Short 7-day horizon and direction threshold", "Small price moves can flip direction; trend from slope (e.g. > 0.5 = Up) is arbitrary and can misclassify."),
            ("No volatility or regime features", "The model does not adapt to high- vs low-volatility periods."),
            ("Retraining is time-based only", "Model retrains every 7 days regardless of performance or drift."),
        ]

    db = SessionLocal()
    try:
        print("=" * 60)
        print("GOLD PRICE PREDICTION MODEL – VALIDATION (CONSOLE)")
        print("=" * 60)
        print(f"Run at: {datetime.now().isoformat()}\n")

        # ----- Current result: training -----
        print("--- CURRENT RESULT ---")
        history = get_model_metrics_history(db, limit=5)
        if history:
            latest = history[0]
            print("Training (latest):")
            print(f"  R² = {latest.get('r_squared')}, MAE = {latest.get('mae')}, MAPE = {latest.get('mape')}%")
            print(f"  residual_std = {latest.get('residual_std')}, points = {latest.get('training_points')}")
            print(f"  period = {latest.get('training_period_start')} to {latest.get('training_period_end')}")
            print(f"  executed_at = {latest.get('executed_at')}")
        else:
            print("Training: no trained model in DB.")

        # ----- Comparison: latest vs previous training -----
        try:
            drift = get_model_drift_status(db)
            if drift.get("previous") and drift.get("latest"):
                print("\n--- COMPARISON (latest vs previous training) ---")
                print(f"  delta R²   = {drift.get('delta_r2')}")
                print(f"  delta MAE  = {drift.get('delta_mae')}")
                print(f"  delta MAPE = {drift.get('delta_mape')}")
                print(f"  {drift.get('message', '')}")
        except Exception:
            pass

        # ----- Current result: live accuracy -----
        records = db.query(PredictionAccuracy).order_by(PredictionAccuracy.predicted_at.desc()).limit(100).all()
        if records:
            n = len(records)
            maes = [r.mae for r in records if r.mae is not None]
            mapes = [r.mape for r in records if r.mape is not None]
            avg_mae = sum(maes) / len(maes) if maes else None
            avg_mape = sum(mapes) / len(mapes) if mapes else None
            direction_correct = sum(r.direction_correct or 0 for r in records)
            dir_pct = round((direction_correct / n) * 100, 1)
            print("\nLive prediction accuracy (last 100 evaluated):")
            print(f"  total_evaluated = {n}, avg_mae = {round(avg_mae, 2) if avg_mae is not None else 'N/A'}, avg_mape = {round(avg_mape, 2) if avg_mape is not None else 'N/A'}%")
            print(f"  direction_accuracy_pct = {dir_pct}%")
        else:
            print("\nLive prediction accuracy: no evaluation records yet.")

        # ----- Drift -----
        try:
            model_drift = get_model_drift_status(db)
            feature_drift = compute_feature_drift(db, recent_days=14)
            concept_drift = get_concept_drift_status(db)
            print("\nDrift summary:")
            print(f"  model_metrics_drift = {model_drift.get('model_metrics_drift', False)}")
            print(f"  data_drift = {feature_drift.get('data_drift', False)}")
            print(f"  concept_drift = {concept_drift.get('concept_drift', False)}")
        except Exception as e:
            print(f"\nDrift check skipped: {e}")

        # ----- Reasons for low accuracy -----
        print("\n" + "=" * 60)
        print("REASONS FOR (POTENTIAL) LOW ACCURACY")
        print("=" * 60)
        for i, (title, desc) in enumerate(_reasons(), 1):
            print(f"\n{i}. {title}")
            print(f"   {desc}")
        print("\n" + "=" * 60)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
