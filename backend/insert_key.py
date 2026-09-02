from database import SessionLocal
from models import APIKey

def insert_key():
    db = SessionLocal()
    try:
        # Check if exists
        existing = db.query(APIKey).filter(APIKey.key == "test-dev-key").first()
        if existing:
            print("Key 'test-dev-key' already exists.")
            return

        new_key = APIKey(key="test-dev-key", owner="local-dev", tier="paid")
        db.add(new_key)
        db.commit()
        print("Inserted key: test-dev-key")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    insert_key()
