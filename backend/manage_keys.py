import secrets
import argparse
from database import SessionLocal, engine, Base
from models import APIKey

# Ensure tables are created
Base.metadata.create_all(bind=engine)

def generate_key():
    return secrets.token_urlsafe(32)

def create_key(owner, tier="free"):
    db = SessionLocal()
    try:
        new_key = generate_key()
        api_key = APIKey(
            key=new_key,
            owner=owner,
            tier=tier
        )
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        print(f"Created API Key for {owner}:")
        print(f"Key: {new_key}")
        print(f"Tier: {tier}")
        return api_key
    finally:
        db.close()

def list_keys():
    db = SessionLocal()
    try:
        keys = db.query(APIKey).all()
        print(f"{'ID':<5} | {'Owner':<20} | {'Tier':<10} | {'Status':<10} | {'Key Prefix':<10}")
        print("-" * 65)
        for k in keys:
            status = "Active" if k.is_active else "Inactive"
            prefix = k.key[:8] + "..."
            print(f"{k.id:<5} | {k.owner:<20} | {k.tier:<10} | {status:<10} | {prefix:<10}")
    finally:
        db.close()

def revoke_key(key_id):
    db = SessionLocal()
    try:
        api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
        if api_key:
            api_key.is_active = 0
            db.commit()
            print(f"Revoked key {key_id} for {api_key.owner}")
        else:
            print(f"Key ID {key_id} not found")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage GoldPriceWatch API Keys")
    subparsers = parser.add_subparsers(dest="command")

    # Create
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--owner", required=True)
    create_parser.add_argument("--tier", choices=["free", "paid"], default="free")

    # List
    list_parser = subparsers.add_parser("list")

    # Revoke
    revoke_parser = subparsers.add_parser("revoke")
    revoke_parser.add_argument("--id", type=int, required=True)

    args = parser.parse_args()

    if args.command == "create":
        create_key(args.owner, args.tier)
    elif args.command == "list":
        list_keys()
    elif args.command == "revoke":
        revoke_key(args.id)
    else:
        parser.print_help()
