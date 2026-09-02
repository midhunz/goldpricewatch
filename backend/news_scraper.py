import feedparser
import re
from datetime import datetime
from database import SessionLocal
from models import GoldNews
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Initialize VADER sentiment analyzer
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _vader_analyzer = SentimentIntensityAnalyzer()
    
    # Add gold/finance-specific lexicon updates
    # Positive financial terms (bullish for gold)
    _vader_analyzer.lexicon.update({
        'surge': 3.0,
        'surges': 3.0,
        'surging': 3.0,
        'rally': 2.5,
        'rallies': 2.5,
        'bullish': 3.0,
        'record high': 3.5,
        'all-time high': 3.5,
        'soar': 3.0,
        'soars': 3.0,
        'breakout': 2.5,
        'momentum': 1.5,
        'safe haven': 2.0,
        'haven': 1.5,
        'accumulate': 1.5,
        'inflation hedge': 2.0,
        'upbeat': 2.0,
        'outperform': 2.0,
        'outperforms': 2.0,
    })
    
    # Negative financial terms (bearish for gold)
    _vader_analyzer.lexicon.update({
        'plunge': -3.0,
        'plunges': -3.0,
        'crash': -3.5,
        'crashes': -3.5,
        'bearish': -3.0,
        'sell-off': -2.5,
        'selloff': -2.5,
        'slump': -2.5,
        'slumps': -2.5,
        'tumble': -2.5,
        'tumbles': -2.5,
        'correction': -1.5,
        'profit taking': -1.0,
        'retreat': -1.5,
        'retreats': -1.5,
        'underperform': -2.0,
        'underperforms': -2.0,
    })
    
    VADER_AVAILABLE = True
    logger.info("✅ VADER sentiment analyzer initialized with financial lexicon")
except ImportError:
    VADER_AVAILABLE = False
    _vader_analyzer = None
    logger.warning("⚠️ VADER not available, falling back to keyword matching")

# Fallback: Sentiment keywords (used if VADER not available)
BULLISH_KEYWORDS = [
    'surge', 'surges', 'surging', 'rally', 'rallies', 'rallying',
    'rise', 'rises', 'rising', 'gain', 'gains', 'gaining',
    'bullish', 'record high', 'all-time high', 'ath', 'soar', 'soars',
    'demand', 'strong demand', 'buying', 'accumulate', 'jump', 'jumps',
    'climb', 'climbs', 'positive', 'upbeat', 'optimistic', 'boost',
    'breakout', 'momentum', 'safe haven', 'refuge', 'haven',
    'inflation hedge', 'geopolitical', 'uncertainty', 'crisis'
]

BEARISH_KEYWORDS = [
    'fall', 'falls', 'falling', 'drop', 'drops', 'dropping',
    'decline', 'declines', 'declining', 'crash', 'crashes', 'crashing',
    'bearish', 'sell-off', 'selloff', 'weak', 'weakness', 'plunge',
    'plunges', 'slump', 'slumps', 'tumble', 'tumbles', 'slide', 'slides',
    'loss', 'losses', 'losing', 'down', 'lower', 'lows', 'retreat',
    'pressure', 'negative', 'pessimistic', 'correction', 'profit taking'
]


def analyze_sentiment_vader(text: str) -> Tuple[float, str, Dict]:
    """
    Analyze sentiment using VADER (Valence Aware Dictionary for Sentiment Reasoning).
    
    VADER is specifically designed for social media and news text. It handles:
    - Capitalization (GREAT vs great)
    - Punctuation (great!!!)
    - Negations (not good)
    - Intensifiers (very, extremely)
    - Conjunctions (good but not great)
    
    Args:
        text: The text to analyze
        
    Returns:
        Tuple of (score, label, details) where:
            - score: -1 to +1 (bearish to bullish)
            - label: "Bullish", "Bearish", or "Neutral"
            - details: Dict with pos, neg, neu, compound scores
    """
    if not text or not VADER_AVAILABLE:
        return 0.0, "Neutral", {}
    
    # Get VADER scores
    scores = _vader_analyzer.polarity_scores(text)
    
    # compound score is normalized between -1 and +1
    compound = scores['compound']
    
    # Determine label based on compound score
    # Using thresholds typical for VADER
    if compound >= 0.15:
        label = "Bullish"
    elif compound <= -0.15:
        label = "Bearish"
    else:
        label = "Neutral"
    
    return round(compound, 3), label, {
        "positive": round(scores['pos'], 3),
        "negative": round(scores['neg'], 3),
        "neutral": round(scores['neu'], 3),
        "compound": round(compound, 3)
    }


def analyze_sentiment_keywords(text: str) -> Tuple[float, str]:
    """
    Fallback: Analyze sentiment using keyword matching.
    Used when VADER is not available.
    """
    if not text:
        return 0.0, "Neutral"
    
    text_lower = text.lower()
    
    bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
    bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)
    
    total = bullish_count + bearish_count
    
    if total == 0:
        return 0.0, "Neutral"
    
    score = (bullish_count - bearish_count) / total
    
    if score > 0.2:
        label = "Bullish"
    elif score < -0.2:
        label = "Bearish"
    else:
        label = "Neutral"
    
    return round(score, 2), label


def analyze_sentiment(text: str) -> Tuple[float, str]:
    """
    Analyze sentiment of text using VADER (with keyword fallback).
    
    Args:
        text: The text to analyze (title + summary)
        
    Returns:
        Tuple of (score, label) where:
            - score: -1 to +1 (bearish to bullish)
            - label: "Bullish", "Bearish", or "Neutral"
    """
    if VADER_AVAILABLE:
        score, label, _ = analyze_sentiment_vader(text)
        return score, label
    else:
        return analyze_sentiment_keywords(text)


def get_news_sentiment_summary(db) -> Dict:
    """
    Get sentiment summary from recent news articles using VADER AI.
    
    Args:
        db: Database session
        
    Returns:
        Dict with sentiment statistics
    """
    from datetime import timedelta
    
    # Get news from last 7 days
    cutoff = datetime.now() - timedelta(days=7)
    recent_news = db.query(GoldNews).filter(
        GoldNews.published_at >= cutoff
    ).order_by(GoldNews.published_at.desc()).limit(50).all()
    
    if not recent_news:
        return {
            "overall_sentiment": 0,
            "sentiment_label": "Neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "bullish_percent": 0,
            "total_articles": 0,
            "recent_headlines": [],
            "analysis_method": "VADER" if VADER_AVAILABLE else "keywords",
            "avg_positive": 0,
            "avg_negative": 0,
            "avg_neutral": 0
        }
    
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    total_score = 0
    total_positive = 0
    total_negative = 0
    total_neutral_score = 0
    recent_headlines = []
    
    for news in recent_news:
        text = f"{news.title} {news.summary or ''}"
        
        if VADER_AVAILABLE:
            score, label, details = analyze_sentiment_vader(text)
            total_positive += details.get('positive', 0)
            total_negative += details.get('negative', 0)
            total_neutral_score += details.get('neutral', 0)
        else:
            score, label = analyze_sentiment_keywords(text)
            details = {}
        
        if label == "Bullish":
            bullish_count += 1
        elif label == "Bearish":
            bearish_count += 1
        else:
            neutral_count += 1
        
        total_score += score
        
        # Add to recent headlines (top 10)
        if len(recent_headlines) < 10:
            headline_data = {
                "title": news.title,
                "sentiment": label,
                "score": score,
                "source": news.source,
                "published_at": news.published_at.isoformat() if news.published_at else None
            }
            # Add VADER details if available
            if details:
                headline_data["vader_scores"] = details
            recent_headlines.append(headline_data)
    
    total = len(recent_news)
    avg_score = total_score / total if total > 0 else 0
    
    # Overall label based on average compound score
    if avg_score > 0.1:
        overall_label = "Bullish"
    elif avg_score < -0.1:
        overall_label = "Bearish"
    else:
        overall_label = "Neutral"
    
    # Calculate bullish percentage
    bullish_percent = (bullish_count / total * 100) if total > 0 else 0
    
    result = {
        "overall_sentiment": round(avg_score, 3),
        "sentiment_label": overall_label,
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "bullish_percent": round(bullish_percent, 1),
        "total_articles": total,
        "recent_headlines": recent_headlines,
        "analysis_method": "VADER" if VADER_AVAILABLE else "keywords"
    }
    
    # Add VADER averages if available
    if VADER_AVAILABLE:
        result["avg_positive"] = round(total_positive / total, 3) if total > 0 else 0
        result["avg_negative"] = round(total_negative / total, 3) if total > 0 else 0
        result["avg_neutral"] = round(total_neutral_score / total, 3) if total > 0 else 0
    
    return result


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
