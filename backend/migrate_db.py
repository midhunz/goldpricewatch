import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, GoldRate, GoldNews
import shutil

# Database Configurations
# Remote Postgres (Source)
PG_USER = "user"
PG_PASSWORD = "password"
PG_HOST = "142.93.222.194"
PG_PORT = "5432"
PG_DB = "goldrate"
PG_DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

# Local SQLite (Destination)
SQLITE_DB_PATH = "./data/goldrate.db"
SQLITE_DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH}"

def migrate():
    print("Starting migration...")
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)

    # 1. Connect to Source (Postgres)
    print(f"Connecting to source database: {PG_HOST}...")
    try:
        pg_engine = create_engine(PG_DATABASE_URL)
        PG_Session = sessionmaker(bind=pg_engine)
        pg_session = PG_Session()
        print("Connected to source.")
    except Exception as e:
        print(f"Failed to connect to source: {e}")
        return

    # 2. Connect to/Create Destination (SQLite)
    print(f"Connecting to destination database: {SQLITE_DB_PATH}...")
    sqlite_engine = create_engine(SQLITE_DATABASE_URL, connect_args={"check_same_thread": False})
    
    # Create tables in SQLite
    print("Creating tables in SQLite...")
    Base.metadata.create_all(sqlite_engine)
    
    SQLite_Session = sessionmaker(bind=sqlite_engine)
    sqlite_session = SQLite_Session()

    # 3. Migrate GoldRate
    print("Migrating GoldRate data...")
    try:
        gold_rates = pg_session.query(GoldRate).all()
        print(f"Found {len(gold_rates)} GoldRate records.")
        
        for idx, item in enumerate(gold_rates):
            # Create new object to avoid detention from pg session issues
            new_item = GoldRate(
                region=item.region,
                purity=item.purity,
                price=item.price,
                currency=item.currency,
                created_at=item.created_at
            )
            sqlite_session.add(new_item)
            if idx % 100 == 0:
                print(f"Processed {idx} GoldRate records...", end='\r')
        
        sqlite_session.commit()
        print(f"Successfully migrated {len(gold_rates)} GoldRate records.")
        
    except Exception as e:
        print(f"Error migrating GoldRate: {e}")
        sqlite_session.rollback()

    # 4. Migrate GoldNews
    print("Migrating GoldNews data...")
    try:
        gold_news = pg_session.query(GoldNews).all()
        print(f"Found {len(gold_news)} GoldNews records.")
        
        for idx, item in enumerate(gold_news):
             new_item = GoldNews(
                title=item.title,
                summary=item.summary,
                source=item.source,
                url=item.url,
                image_url=item.image_url,
                slug=item.slug,
                published_at=item.published_at,
                created_at=item.created_at
            )
             sqlite_session.add(new_item)
        
        sqlite_session.commit()
        print(f"Successfully migrated {len(gold_news)} GoldNews records.")

    except Exception as e:
        print(f"Error migrating GoldNews: {e}")
        sqlite_session.rollback()

    print("Migration completed.")
    pg_session.close()
    sqlite_session.close()

if __name__ == "__main__":
    migrate()
