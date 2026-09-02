from sqlalchemy.orm import Session
from database import SessionLocal
from models import GoldRate
from datetime import datetime, timedelta

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

def inspect_india():
    db = SessionLocal()
    try:
        now = datetime.now()
        print(f"Current Time: {now}")
        
        cutoff_20h = now - timedelta(hours=20)
        start_48h = now - timedelta(hours=48)
        
        print(f"Looking for data between {start_48h} and {cutoff_20h}")
        
        print(f"\n--- Checking India ---")
        
        # Recent rates
        recent = db.query(GoldRate).filter(GoldRate.region == "India").order_by(GoldRate.created_at.desc()).limit(3).all()
        print("Latest 3 rates:")
        for r in recent:
            parsed = parse_price(r.price)
            print(f"  {r.created_at}: {r.purity} - Raw: '{r.price}' -> Parsed: {parsed}")
            
        # History window rates
        history = db.query(GoldRate).filter(
            GoldRate.region == "India",
            GoldRate.created_at >= start_48h,
            GoldRate.created_at <= cutoff_20h
        ).order_by(GoldRate.created_at.desc()).all()
        
        print(f"Found {len(history)} rates in history window (20-48h ago).")
        if history:
            print("Sample history rates:")
            target_purities = ["22 Carat", "24 Carat"]
            for purity in target_purities:
                rate = next((r for r in history if r.purity == purity), None)
                if rate:
                    parsed = parse_price(rate.price)
                    print(f"  [{purity}] {rate.created_at}: Raw: '{rate.price}' -> Parsed: {parsed}")
                else:
                    print(f"  [{purity}] No history found in window")
                
    finally:
        db.close()

if __name__ == "__main__":
    inspect_india()
