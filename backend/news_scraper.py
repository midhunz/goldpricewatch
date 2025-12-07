import feedparser
import re
from datetime import datetime
from database import SessionLocal
from models import GoldNews
import logging

logger = logging.getLogger(__name__)

def generate_slug(title):
    """Generate URL-friendly slug from title"""
    slug = title.lower()
    # Remove special characters, keep alphanumeric and spaces
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Limit to 60 characters
    slug = slug[:60].strip('-')
    return slug

def fetch_gold_news():
    """Fetch gold news from Google News RSS feed"""
    logger.info("Starting Gold News scrape...")
    
    # Google News RSS feed for gold-related news
    RSS_URL = "https://news.google.com/rss/search?q=gold+price+OR+gold+market+OR+gold+investment&hl=en-US&gl=US&ceid=US:en"
    
    try:
        feed = feedparser.parse(RSS_URL)
        db = SessionLocal()
        
        new_count = 0
        for entry in feed.entries[:20]:  # Limit to 20 most recent
            # Generate slug
            slug = generate_slug(entry.title)
            
            # Check if article already exists
            existing = db.query(GoldNews).filter(GoldNews.slug == slug).first()
            if existing:
                continue
            
            # Parse published date
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6])
            
            # Extract image (if available in media content)
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                image_url = entry.media_content[0].get('url')
            
            # Extract source from link (google news redirects)
            source = "Google News"
            if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                source = entry.source.title
            
            # Create news entry
            news = GoldNews(
                title=entry.title[:500],  # Limit title length
                summary=entry.get('summary', '')[:1000] if hasattr(entry, 'summary') else '',
                source=source[:100],
                url=entry.link,
                image_url=image_url[:1000] if image_url else None,
                slug=slug,
                published_at=published_at or datetime.now()
            )
            
            db.add(news)
            new_count += 1
        
        db.commit()
        logger.info(f"✅ Successfully added {new_count} new gold news articles")
        
    except Exception as e:
        logger.error(f"❌ Error fetching gold news: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # For testing
    logging.basicConfig(level=logging.INFO)
    fetch_gold_news()
