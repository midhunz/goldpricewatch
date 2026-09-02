"""
Multi-source Gold News Scraper
Fetches gold news from multiple sources for robust sentiment analysis.
"""

import feedparser
import requests
from bs4 import BeautifulSoup
import re
import ssl
from datetime import datetime, timedelta
from database import SessionLocal
from models import GoldNews
import logging
from typing import List, Dict, Optional
import time
import random

# ── Fix SSL for macOS Python (system certs often missing) ──
import os
_SSL_CONTEXT = None
try:
    import certifi
    # Set env var so all Python SSL (incl. feedparser's urllib) uses certifi certs
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    # Also install a global opener for urllib
    import urllib.request
    _https_handler = urllib.request.HTTPSHandler(context=_SSL_CONTEXT)
    urllib.request.install_opener(urllib.request.build_opener(_https_handler))
except ImportError:
    pass

logger = logging.getLogger(__name__)

# User agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]

# RSS Feed sources — gold-specific
RSS_SOURCES = [
    {
        "name": "Google News Gold",
        "url": "https://news.google.com/rss/search?q=gold+price+OR+gold+market+OR+bullion&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
        "gold_filter": True,
    },
    {
        "name": "Yahoo Finance Gold",
        "url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US",
        "type": "rss",
        "gold_filter": True,
    },
    {
        "name": "Investing.com Gold",
        "url": "https://www.investing.com/rss/news_301.rss",
        "type": "rss",
        "gold_filter": True,
    },
]

# RSS feeds for geopolitical / macro news that impacts gold
GEO_RSS_SOURCES = [
    {
        "name": "Google News Geopolitical",
        "url": "https://news.google.com/rss/search?q=tariff+OR+sanctions+OR+trade+war+OR+geopolitical+gold&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
        "gold_filter": False,  # Accept all — geo classifier will filter
    },
    {
        "name": "Google News Central Banks",
        "url": "https://news.google.com/rss/search?q=central+bank+gold+OR+fed+rate+OR+de-dollarization+OR+BRICS+gold&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
        "gold_filter": False,
    },
    {
        "name": "Google News Conflict",
        "url": "https://news.google.com/rss/search?q=war+gold+OR+iran+strait+hormuz+OR+ukraine+russia+ceasefire+OR+taiwan+conflict&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
        "gold_filter": False,
    },
    {
        "name": "Reuters World",
        "url": "https://news.google.com/rss/search?q=site:reuters.com+gold+OR+tariff+OR+sanctions+OR+central+bank&hl=en-US&gl=US&ceid=US:en",
        "type": "rss",
        "gold_filter": False,
    },
]

# Web scraping sources (as backup)
WEB_SOURCES = [
    {
        "name": "Kitco",
        "url": "https://www.kitco.com/news/",
        "type": "web"
    },
    {
        "name": "BullionVault",
        "url": "https://www.bullionvault.com/gold-news",
        "type": "web"
    },
]


def get_random_headers() -> Dict:
    """Get random headers to avoid blocking"""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }


def generate_slug(title: str) -> str:
    """Generate URL-friendly slug from title"""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug[:60].strip('-')
    return slug


def is_gold_related(title: str, summary: str = "") -> bool:
    """Check if article is related to gold (strict — for gold-specific feeds)."""
    text = f"{title} {summary}".lower()
    gold_keywords = [
        'gold', 'bullion', 'precious metal', 'xau', 'gold price',
        'gold rate', 'gold market', 'gold futures', 'gold etf',
        'gold mining', 'gold demand', 'central bank gold', 'gold reserve',
    ]
    return any(kw in text for kw in gold_keywords)


def is_geo_or_gold_related(title: str, summary: str = "") -> bool:
    """Check if article is gold-related OR geopolitically relevant to gold."""
    if is_gold_related(title, summary):
        return True
    text = f"{title} {summary}".lower()
    geo_keywords = [
        'tariff', 'sanctions', 'trade war', 'central bank', 'fed rate',
        'interest rate', 'de-dollarization', 'brics', 'safe haven',
        'war', 'conflict', 'iran', 'ukraine', 'taiwan', 'missile',
        'recession', 'bank collapse', 'inflation', 'monetary policy',
        'currency crisis', 'dollar', 'treasury yield', 'rate cut',
        'rate hike', 'geopolitical', 'ceasefire', 'peace talks',
    ]
    return any(kw in text for kw in geo_keywords)


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats"""
    if not date_str:
        return None
    
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%d %b %Y',
        '%B %d, %Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    return None


def fetch_from_rss(source: Dict) -> List[Dict]:
    """Fetch news from RSS feed"""
    articles = []
    
    try:
        logger.info(f"Fetching RSS from {source['name']}...")
        
        # Parse RSS feed
        feed = feedparser.parse(source['url'])
        
        if feed.bozo and feed.bozo_exception:
            logger.warning(f"RSS parse warning for {source['name']}: {feed.bozo_exception}")
        
        for entry in feed.entries[:15]:  # Limit per source
            title = entry.get('title', '').strip()
            if not title:
                continue
            
            summary = entry.get('summary', entry.get('description', '')).strip()
            
            # Filter content based on source config
            use_strict_filter = source.get('gold_filter', True)
            if use_strict_filter:
                if not is_gold_related(title, summary):
                    continue
            else:
                if not is_geo_or_gold_related(title, summary):
                    continue
            
            # Clean up summary (remove HTML)
            summary = re.sub(r'<[^>]+>', '', summary)
            summary = re.sub(r'\s+', ' ', summary).strip()[:1000]
            
            # Extract source name
            news_source = source['name']
            if hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                news_source = entry.source.title
            
            # Parse published date
            published_at = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6])
                except:
                    pass
            if not published_at and hasattr(entry, 'published'):
                published_at = parse_date(entry.published)
            if not published_at:
                published_at = datetime.now()
            
            # Get image URL
            image_url = None
            if hasattr(entry, 'media_content') and entry.media_content:
                image_url = entry.media_content[0].get('url')
            elif hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
                image_url = entry.media_thumbnail[0].get('url')
            
            articles.append({
                'title': title[:500],
                'summary': summary,
                'source': news_source[:100],
                'url': entry.get('link', ''),
                'image_url': image_url[:1000] if image_url else None,
                'published_at': published_at
            })
        
        logger.info(f"✅ {source['name']}: Found {len(articles)} gold articles")
        
    except Exception as e:
        logger.error(f"❌ Error fetching RSS from {source['name']}: {e}")
    
    return articles


def fetch_from_kitco() -> List[Dict]:
    """Scrape gold news from Kitco"""
    articles = []
    
    try:
        logger.info("Scraping Kitco...")
        
        response = requests.get(
            "https://www.kitco.com/news/",
            headers=get_random_headers(),
            timeout=15,
            verify=certifi.where() if _SSL_CONTEXT else True,
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find news articles
        news_items = soup.find_all('article', class_='article-list__item')
        if not news_items:
            news_items = soup.find_all('div', class_='article-list__item')
        if not news_items:
            news_items = soup.select('.news-list a, .article a')
        
        for item in news_items[:10]:
            try:
                # Find title
                title_elem = item.find('h3') or item.find('h2') or item.find('a')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                
                # Find link
                link_elem = item.find('a', href=True)
                url = link_elem['href'] if link_elem else ''
                if url and not url.startswith('http'):
                    url = f"https://www.kitco.com{url}"
                
                # Find summary/description
                summary_elem = item.find('p') or item.find('div', class_='summary')
                summary = summary_elem.get_text(strip=True) if summary_elem else ''
                
                # Find image
                img_elem = item.find('img', src=True)
                image_url = img_elem.get('src') or img_elem.get('data-src') if img_elem else None
                if image_url and not image_url.startswith('http'):
                    image_url = f"https://www.kitco.com{image_url}"
                
                articles.append({
                    'title': title[:500],
                    'summary': summary[:1000],
                    'source': 'Kitco',
                    'url': url,
                    'image_url': image_url[:1000] if image_url else None,
                    'published_at': datetime.now()  # Kitco doesn't always show dates
                })
                
            except Exception as e:
                logger.debug(f"Error parsing Kitco item: {e}")
                continue
        
        logger.info(f"✅ Kitco: Found {len(articles)} articles")
        
    except Exception as e:
        logger.error(f"❌ Error scraping Kitco: {e}")
    
    return articles


def fetch_from_bullionvault() -> List[Dict]:
    """Scrape gold news from BullionVault"""
    articles = []
    
    try:
        logger.info("Scraping BullionVault...")
        
        response = requests.get(
            "https://www.bullionvault.com/gold-news",
            headers=get_random_headers(),
            timeout=15,
            verify=certifi.where() if _SSL_CONTEXT else True,
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find news articles
        news_items = soup.select('.news-item, .article-item, article')
        
        for item in news_items[:10]:
            try:
                title_elem = item.find('h2') or item.find('h3') or item.find('a')
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                
                link_elem = item.find('a', href=True)
                url = link_elem['href'] if link_elem else ''
                if url and not url.startswith('http'):
                    url = f"https://www.bullionvault.com{url}"
                
                summary_elem = item.find('p')
                summary = summary_elem.get_text(strip=True) if summary_elem else ''
                
                articles.append({
                    'title': title[:500],
                    'summary': summary[:1000],
                    'source': 'BullionVault',
                    'url': url,
                    'image_url': None,
                    'published_at': datetime.now()
                })
                
            except Exception as e:
                logger.debug(f"Error parsing BullionVault item: {e}")
                continue
        
        logger.info(f"✅ BullionVault: Found {len(articles)} articles")
        
    except Exception as e:
        logger.error(f"❌ Error scraping BullionVault: {e}")
    
    return articles


def fetch_from_newsapi() -> List[Dict]:
    """Fetch from NewsAPI (requires API key, but has free tier)"""
    articles = []
    
    # NewsAPI free tier - no key needed for google news endpoint alternative
    try:
        logger.info("Fetching from NewsAPI alternative...")
        
        # Use GNews API (free, no key for basic)
        url = "https://gnews.io/api/v4/search"
        params = {
            "q": "gold price",
            "lang": "en",
            "max": 10,
            "token": "demo"  # Demo token for testing
        }
        
        # This might not work in production, but serves as fallback
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            for article in data.get('articles', []):
                published_at = parse_date(article.get('publishedAt', ''))
                articles.append({
                    'title': article.get('title', '')[:500],
                    'summary': article.get('description', '')[:1000],
                    'source': article.get('source', {}).get('name', 'GNews')[:100],
                    'url': article.get('url', ''),
                    'image_url': article.get('image', '')[:1000] if article.get('image') else None,
                    'published_at': published_at or datetime.now()
                })
            logger.info(f"✅ GNews: Found {len(articles)} articles")
        
    except Exception as e:
        logger.debug(f"GNews fallback not available: {e}")
    
    return articles


def save_articles(articles: List[Dict]) -> int:
    """Save articles to database, avoiding duplicates"""
    db = SessionLocal()
    new_count = 0
    
    try:
        for article in articles:
            # Generate slug
            slug = generate_slug(article['title'])
            
            # Check for duplicate by slug only (URLs can be very long)
            existing = db.query(GoldNews).filter(GoldNews.slug == slug).first()
            
            if existing:
                continue
            
            # Truncate image_url if too long
            image_url = article.get('image_url')
            if image_url and len(image_url) > 1000:
                image_url = image_url[:1000]
            
            # Create news entry
            news = GoldNews(
                title=article['title'][:500] if article['title'] else '',
                summary=article['summary'][:2000] if article.get('summary') else '',
                source=article['source'][:100] if article.get('source') else 'Unknown',
                url=article['url'],  # Text field, no length limit
                image_url=image_url,
                slug=slug,
                published_at=article['published_at']
            )
            
            db.add(news)
            new_count += 1
        
        db.commit()
        logger.info(f"💾 Saved {new_count} new articles to database")
        
    except Exception as e:
        logger.error(f"❌ Error saving articles: {e}")
        db.rollback()
    finally:
        db.close()
    
    return new_count


def fetch_all_gold_news() -> int:
    """
    Main function: Fetch gold news from all sources
    Returns: Number of new articles added
    """
    logger.info("=" * 50)
    logger.info("Starting Multi-Source Gold News Scrape...")
    logger.info("=" * 50)
    
    all_articles = []
    
    # 1. Fetch from gold-specific RSS sources
    for source in RSS_SOURCES:
        articles = fetch_from_rss(source)
        all_articles.extend(articles)
        time.sleep(0.5)

    # 2. Fetch from geopolitical/macro RSS sources
    for source in GEO_RSS_SOURCES:
        articles = fetch_from_rss(source)
        all_articles.extend(articles)
        time.sleep(0.5)

    # 3. Fetch from web sources
    kitco_articles = fetch_from_kitco()
    all_articles.extend(kitco_articles)
    time.sleep(0.5)

    bullionvault_articles = fetch_from_bullionvault()
    all_articles.extend(bullionvault_articles)

    # 4. Try NewsAPI as fallback
    if len(all_articles) < 5:
        newsapi_articles = fetch_from_newsapi()
        all_articles.extend(newsapi_articles)
    
    logger.info(f"📰 Total articles collected: {len(all_articles)}")
    
    # Remove duplicates by title similarity
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article['title'].lower()[:50]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)
    
    logger.info(f"📰 Unique articles after dedup: {len(unique_articles)}")
    
    # Save to database
    new_count = save_articles(unique_articles)
    
    logger.info("=" * 50)
    logger.info(f"✅ Scrape complete. Added {new_count} new articles.")
    logger.info("=" * 50)
    
    return new_count


def cleanup_old_news(days: int = 30):
    """Remove news older than specified days"""
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(days=days)
        deleted = db.query(GoldNews).filter(GoldNews.published_at < cutoff).delete()
        db.commit()
        logger.info(f"🗑️ Cleaned up {deleted} old news articles (>{days} days)")
    except Exception as e:
        logger.error(f"Error cleaning up old news: {e}")
        db.rollback()
    finally:
        db.close()


# For testing
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Test the scraper
    count = fetch_all_gold_news()
    print(f"\n✅ Added {count} new articles")
    
    # Show what's in database
    db = SessionLocal()
    total = db.query(GoldNews).count()
    recent = db.query(GoldNews).order_by(GoldNews.published_at.desc()).limit(5).all()
    db.close()
    
    print(f"\n📊 Total articles in database: {total}")
    print("\n📰 Recent headlines:")
    for news in recent:
        print(f"  - {news.source}: {news.title[:60]}...")
