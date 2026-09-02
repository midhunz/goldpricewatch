"""
External Factors Module

Fetches and caches external market data that influences gold prices:
- USD Index (via exchange rate API)
- Real Interest Rates / 10-Year Treasury Yield (via FRED API)
- Central Bank Gold Activity (via IMF SDMX API)

Note: Uses free APIs with rate limiting considerations.
Data is cached to minimize API calls.
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import urllib.request

logger = logging.getLogger(__name__)

# Simple in-memory cache
_cache: Dict[str, Dict] = {}
CACHE_DURATION_HOURS = 6
CACHE_DURATION_HOURS_LONG = 24  # For monthly data sources (IMF)

def _get_cached(key: str) -> Optional[Dict]:
    """Get cached data if not expired."""
    if key in _cache:
        cached = _cache[key]
        if datetime.now() - cached['timestamp'] < timedelta(hours=CACHE_DURATION_HOURS):
            return cached['data']
    return None

def _set_cache(key: str, data: Dict):
    """Store data in cache."""
    _cache[key] = {
        'timestamp': datetime.now(),
        'data': data
    }

def _get_cached_long(key: str) -> Optional[Dict]:
    """Get cached data with longer TTL (24 hours) for monthly data sources."""
    if key in _cache:
        cached = _cache[key]
        if datetime.now() - cached['timestamp'] < timedelta(hours=CACHE_DURATION_HOURS_LONG):
            return cached['data']
    return None


def get_real_interest_rate() -> Dict:
    """
    Get 10-Year US Treasury Yield from FRED API.

    Higher yields = bearish for gold (opportunity cost of holding non-yielding asset).
    Lower yields = bullish for gold.

    Requires FRED_API_KEY environment variable (free at fredaccount.stlouisfed.org).

    Returns:
        Dict with yield_10y, impact (-1 to 1), direction, timestamp
    """
    cached = _get_cached('real_interest_rate')
    if cached:
        return cached

    fred_api_key = os.getenv('FRED_API_KEY', '')
    if not fred_api_key:
        logger.warning("FRED_API_KEY not set; skipping Treasury yield fetch")
        return {
            'yield_10y': None,
            'impact': 0,
            'direction': 'API key not configured',
            'timestamp': datetime.now().isoformat()
        }

    try:
        url = (
            "https://api.stlouisfed.org/fred/series/observations"
            f"?series_id=DGS10&api_key={fred_api_key}&file_type=json"
            "&sort_order=desc&limit=10"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())

        observations = data.get('observations', [])

        # Find the most recent non-missing value
        yield_10y = None
        for obs in observations:
            val = obs.get('value', '.')
            if val != '.':
                yield_10y = float(val)
                break

        if yield_10y is None:
            logger.warning("No valid 10Y yield data from FRED")
            return {
                'yield_10y': None,
                'impact': 0,
                'direction': 'Data unavailable',
                'timestamp': datetime.now().isoformat()
            }

        # Calculate gold impact from yield level
        # Neutral zone: 3.5% - 4.5%
        # High yields (>4.5%) = bearish for gold
        # Low yields (<3.5%) = bullish for gold
        if yield_10y > 4.5:
            direction = "High Yields (Bearish for Gold)"
            impact = -1 * min((yield_10y - 4.0) / 3.0, 1.0)
        elif yield_10y < 3.5:
            direction = "Low Yields (Bullish for Gold)"
            impact = min((4.0 - yield_10y) / 3.0, 1.0)
        else:
            # Neutral zone with slight linear scaling
            direction = "Neutral Yields"
            impact = -1 * (yield_10y - 4.0) / 5.0  # Small impact in neutral zone

        result = {
            'yield_10y': round(yield_10y, 2),
            'impact': round(impact, 2),
            'direction': direction,
            'timestamp': datetime.now().isoformat()
        }

        _set_cache('real_interest_rate', result)
        return result

    except Exception as e:
        logger.warning(f"Failed to fetch Treasury yield from FRED: {e}")

    return {
        'yield_10y': None,
        'impact': 0,
        'direction': 'Data unavailable',
        'timestamp': datetime.now().isoformat()
    }


def get_central_bank_activity() -> Dict:
    """
    Get central bank gold reserve changes from the IMF SDMX JSON API.

    Net buying by central banks = bullish for gold (demand driver).
    Net selling = bearish for gold.

    Uses International Financial Statistics (IFS) dataset for gold reserves
    in troy ounces for major gold-buying countries.

    Returns:
        Dict with net_change_tonnes, direction, impact, top_buyers, timestamp
    """
    cached = _get_cached_long('central_bank_activity')
    if cached:
        return cached

    # Major central bank gold buyers to track
    # ISO country codes: CN=China, IN=India, TR=Turkey, RU=Russia, PL=Poland
    countries = ['CN', 'IN', 'TR', 'RU', 'PL']
    country_names = {
        'CN': 'China', 'IN': 'India', 'TR': 'Turkey',
        'RU': 'Russia', 'PL': 'Poland'
    }

    try:
        # IMF IFS: RAXG_USD = Gold reserves in USD (millions)
        # Frequency=M (monthly), countries joined by +
        country_str = '+'.join(countries)
        # Fetch last 6 months of data
        end_year = datetime.now().year
        start_period = f"{end_year - 1}-01"
        end_period = f"{end_year}-12"

        url = (
            f"http://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/"
            f"IFS/M.{country_str}.RAXG_USD"
            f"?startPeriod={start_period}&endPeriod={end_period}"
        )

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode())

        # Parse the SDMX JSON response
        dataset = data.get('CompactData', {}).get('DataSet', {})
        series_list = dataset.get('Series', [])
        if isinstance(series_list, dict):
            series_list = [series_list]

        country_changes: List[Dict] = []
        total_net_change_usd = 0.0

        for series in series_list:
            country_code = series.get('@REF_AREA', '')
            obs_data = series.get('Obs', [])
            if isinstance(obs_data, dict):
                obs_data = [obs_data]

            if len(obs_data) < 2:
                continue

            # Sort by time period, get last two observations
            obs_sorted = sorted(obs_data, key=lambda x: x.get('@TIME_PERIOD', ''))
            recent = obs_sorted[-1]
            previous = obs_sorted[-2]

            try:
                recent_val = float(recent.get('@OBS_VALUE', 0))
                prev_val = float(previous.get('@OBS_VALUE', 0))
                change = recent_val - prev_val

                country_changes.append({
                    'country': country_names.get(country_code, country_code),
                    'change_usd_millions': round(change, 2),
                    'direction': 'buying' if change > 0 else 'selling' if change < 0 else 'unchanged',
                    'period': recent.get('@TIME_PERIOD', '')
                })
                total_net_change_usd += change
            except (ValueError, TypeError):
                continue

        # Convert USD millions change to approximate tonnes
        # Rough conversion: gold ~$2000/oz, 1 tonne = 32150.7 oz
        # $1M USD ~ 0.0155 tonnes at $2000/oz
        net_change_tonnes = total_net_change_usd * 0.0155

        # Calculate impact: significant buying = bullish
        # Threshold: >50 tonnes combined monthly = strong signal
        if net_change_tonnes > 20:
            direction = "Strong Central Bank Buying (Bullish)"
            impact = min(net_change_tonnes / 100, 1.0)
        elif net_change_tonnes > 5:
            direction = "Moderate Central Bank Buying (Slightly Bullish)"
            impact = net_change_tonnes / 100
        elif net_change_tonnes < -20:
            direction = "Central Bank Selling (Bearish)"
            impact = max(-1.0, net_change_tonnes / 100)
        elif net_change_tonnes < -5:
            direction = "Moderate Central Bank Selling (Slightly Bearish)"
            impact = net_change_tonnes / 100
        else:
            direction = "Neutral Central Bank Activity"
            impact = 0

        # Sort by absolute change for top buyers
        top_buyers = sorted(
            country_changes, key=lambda x: abs(x['change_usd_millions']), reverse=True
        )

        result = {
            'net_change_tonnes': round(net_change_tonnes, 2),
            'net_change_usd_millions': round(total_net_change_usd, 2),
            'direction': direction,
            'impact': round(impact, 2),
            'top_buyers': top_buyers[:5],
            'timestamp': datetime.now().isoformat()
        }

        _set_cache('central_bank_activity', result)
        return result

    except Exception as e:
        logger.warning(f"Failed to fetch central bank data from IMF: {e}")

    # Return neutral on failure (data is lagged anyway)
    return {
        'net_change_tonnes': 0,
        'net_change_usd_millions': 0,
        'direction': 'Data unavailable',
        'impact': 0,
        'top_buyers': [],
        'timestamp': datetime.now().isoformat()
    }


def get_usd_strength() -> Dict:
    """
    Get USD strength indicator based on exchange rates.
    
    Uses EUR/USD rate as a proxy for USD index.
    - Higher EUR/USD = weaker USD = bullish for gold
    - Lower EUR/USD = stronger USD = bearish for gold
    
    Returns:
        Dict with usd_index, change, and direction
    """
    cached = _get_cached('usd_strength')
    if cached:
        return cached
    
    try:
        # Use exchangerate.host (free, no API key required)
        url = "https://api.exchangerate.host/latest?base=USD&symbols=EUR,GBP,JPY,CHF"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        if data.get('success', True) and 'rates' in data:
            eur_rate = data['rates'].get('EUR', 0.92)
            gbp_rate = data['rates'].get('GBP', 0.79)
            jpy_rate = data['rates'].get('JPY', 149.0)
            chf_rate = data['rates'].get('CHF', 0.88)
            
            # Calculate a simple USD index proxy
            # Base values are approximate long-term averages
            eur_component = (0.92 / eur_rate) * 57.6  # EUR weight ~57.6%
            jpy_component = (jpy_rate / 130) * 13.6   # JPY weight ~13.6%
            gbp_component = (0.79 / gbp_rate) * 11.9  # GBP weight ~11.9%
            chf_component = (0.88 / chf_rate) * 3.6   # CHF weight ~3.6%
            
            # Simplified DXY calculation (not exact, but indicative)
            usd_index = eur_component + jpy_component + gbp_component + chf_component + 13.3
            
            # Normalize around 100 (historical DXY average)
            usd_index = round(usd_index, 2)
            
            # Direction relative to neutral (100)
            if usd_index > 102:
                direction = "Strong USD (Bearish for Gold)"
                impact = -1 * min((usd_index - 100) / 10, 1)  # -1 to 0
            elif usd_index < 98:
                direction = "Weak USD (Bullish for Gold)"
                impact = min((100 - usd_index) / 10, 1)  # 0 to 1
            else:
                direction = "Neutral"
                impact = 0
            
            result = {
                'usd_index': usd_index,
                'eur_rate': round(eur_rate, 4),
                'direction': direction,
                'impact': round(impact, 2),
                'timestamp': datetime.now().isoformat()
            }
            
            _set_cache('usd_strength', result)
            return result
            
    except Exception as e:
        logger.warning(f"Failed to fetch USD data: {e}")
    
    # Return neutral values on error
    return {
        'usd_index': 100,
        'eur_rate': 0.92,
        'direction': 'Data unavailable',
        'impact': 0,
        'timestamp': datetime.now().isoformat()
    }


def get_volatility_index() -> Dict:
    """
    Get a simplified volatility indicator.
    
    In absence of VIX API, we use a proxy based on recent gold price movement
    stored in our database.
    
    Returns:
        Dict with volatility level and impact
    """
    # This would typically be calculated from our database
    # For now, return a neutral placeholder
    return {
        'volatility_level': 'Moderate',
        'impact': 0,
        'timestamp': datetime.now().isoformat()
    }


def get_external_factors() -> Dict:
    """
    Get all external factors that influence gold prices.
    
    Returns:
        Dict with all factor data and combined impact score
    """
    usd_data = get_usd_strength()
    volatility_data = get_volatility_index()
    interest_rate_data = get_real_interest_rate()
    central_bank_data = get_central_bank_activity()
    
    # Calculate combined impact (-1 to 1) using realistic weights
    # USD (28%), Interest Rate (18%), Central Bank (7%) of the total model
    # But for combined_impact here, normalize to just external factors
    usd_impact = usd_data.get('impact', 0)
    ir_impact = interest_rate_data.get('impact', 0)
    cb_impact = central_bank_data.get('impact', 0)
    vol_impact = volatility_data.get('impact', 0)
    
    # Weighted combination of external-only factors
    combined_impact = (
        usd_impact * 0.45 +
        ir_impact * 0.30 +
        cb_impact * 0.15 +
        vol_impact * 0.10
    )
    
    return {
        'usd': usd_data,
        'interest_rate': interest_rate_data,
        'central_bank': central_bank_data,
        'volatility': volatility_data,
        'combined_impact': round(combined_impact, 2),
        'timestamp': datetime.now().isoformat()
    }


def get_factor_attribution(
    trend_impact: float,
    usd_impact: float = 0,
    sentiment_impact: float = 0,
    volatility_impact: float = 0
) -> Dict:
    """
    Calculate factor attribution showing what drives the prediction.
    
    Args:
        trend_impact: Impact from historical trend analysis
        usd_impact: Impact from USD strength (-1 to 1)
        sentiment_impact: Impact from news sentiment (-1 to 1)
        volatility_impact: Impact from volatility (-1 to 1)
        
    Returns:
        Dict with factor contributions as percentages
    """
    # Convert impacts to percentages (assuming they add up to total prediction change)
    total_magnitude = abs(trend_impact) + abs(usd_impact) + abs(sentiment_impact) + abs(volatility_impact)
    
    if total_magnitude == 0:
        return {
            'trend': {'value': 0, 'percent': 50},
            'usd': {'value': 0, 'percent': 25},
            'sentiment': {'value': 0, 'percent': 15},
            'volatility': {'value': 0, 'percent': 10}
        }
    
    return {
        'trend': {
            'value': round(trend_impact, 2),
            'percent': round(abs(trend_impact) / total_magnitude * 100),
            'direction': 'up' if trend_impact > 0 else 'down' if trend_impact < 0 else 'neutral'
        },
        'usd': {
            'value': round(usd_impact, 2),
            'percent': round(abs(usd_impact) / total_magnitude * 100),
            'direction': 'up' if usd_impact > 0 else 'down' if usd_impact < 0 else 'neutral'
        },
        'sentiment': {
            'value': round(sentiment_impact, 2),
            'percent': round(abs(sentiment_impact) / total_magnitude * 100),
            'direction': 'up' if sentiment_impact > 0 else 'down' if sentiment_impact < 0 else 'neutral'
        },
        'volatility': {
            'value': round(volatility_impact, 2),
            'percent': round(abs(volatility_impact) / total_magnitude * 100),
            'direction': 'up' if volatility_impact > 0 else 'down' if volatility_impact < 0 else 'neutral'
        }
    }
