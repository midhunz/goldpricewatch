from sqlalchemy import Column, Integer, String, Float, DateTime, Text
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
    url = Column(String(1000))
    image_url = Column(String(1000))
    slug = Column(String(200), unique=True, index=True)
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
