import csv
import io
from sqlalchemy.orm import Session
from models import GoldRate, GoldNews

def export_rates_to_csv(db: Session, region: str = None, purity: str = None):
    query = db.query(GoldRate)
    if region:
        query = query.filter(GoldRate.region == region)
    if purity:
        query = query.filter(GoldRate.purity == purity)
    
    rates = query.order_by(GoldRate.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Region", "Purity", "Price", "Currency", "Created At"])
    
    for rate in rates:
        writer.writerow([
            rate.id,
            rate.region,
            rate.purity,
            rate.price,
            rate.currency,
            rate.created_at.isoformat() if rate.created_at else ""
        ])
    
    return output.getvalue()

def export_news_to_csv(db: Session):
    articles = db.query(GoldNews).order_by(GoldNews.published_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Title", "Source", "URL", "Published At", "Summary"])
    
    for article in articles:
        writer.writerow([
            article.id,
            article.title,
            article.source,
            article.url,
            article.published_at.isoformat() if article.published_at else "",
            article.summary
        ])
    
    return output.getvalue()
