import os
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supabase connection. Never hardcode credentials here - this repo is public.
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SUBA_BASE_URL")
if not DATABASE_URL:
    raise SystemExit("Set DATABASE_URL (or SUBA_BASE_URL) before running this script.")

def create_table():
    engine = create_engine(DATABASE_URL)
    
    # SQL to create table with reference to auth.users
    # Note: We must use the 'uuid' type for user_id to match auth.users.id
    sql = """
    create table if not exists portfolio_items (
      id uuid default gen_random_uuid() primary key,
      user_id uuid references auth.users not null,
      gold_type text not null,
      weight_grams numeric not null,
      purchase_price numeric not null,
      purchase_date date default now(),
      created_at timestamptz default now()
    );

    -- Enable RLS
    alter table portfolio_items enable row level security;

    -- Create Policies (Idempotent-ish: Drop first to avoid error)
    drop policy if exists "Users can view own items" on portfolio_items;
    create policy "Users can view own items" 
    on portfolio_items for select using (auth.uid() = user_id);

    drop policy if exists "Users can insert own items" on portfolio_items;
    create policy "Users can insert own items" 
    on portfolio_items for insert with check (auth.uid() = user_id);
    
    drop policy if exists "Users can update own items" on portfolio_items;
    create policy "Users can update own items" 
    on portfolio_items for update using (auth.uid() = user_id);

    drop policy if exists "Users can delete own items" on portfolio_items;
    create policy "Users can delete own items" 
    on portfolio_items for delete using (auth.uid() = user_id);
    
    -- Grant permissions to authenticated users (important for Supabase Client access)
    grant all on portfolio_items to authenticated;
    grant all on portfolio_items to service_role;
    """
    
    with engine.connect() as conn:
        logger.info("Creating portfolio_items table...")
        # Split statements or run as one block? sqlalchemy 'text' handles blocks well usually
        # But split by ; just in case
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception as e:
                logger.warning(f"Error executing statement (might exist): {e}")

        logger.info("Table creation script finished.")

if __name__ == "__main__":
    create_table()
