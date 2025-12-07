import requests
from bs4 import BeautifulSoup
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://gulfnews.com/gold-forex"

def get_soup(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, "lxml")
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

def scrape_uae_rates():
    soup = get_soup(BASE_URL)
    if not soup:
        return []
    
    rates = []
    # Note: This selector is a best guess based on typical news site structures. 
    # We might need to adjust it after inspecting the actual HTML more closely if this fails.
    # Looking for the table or list containing rates.
    # Based on the text content seen earlier, it's likely in a specific section.
    
    # Attempting to find the gold rate container
    # Often these are in tables or specific divs.
    # For now, I will try to find the section by text and then parse siblings/children.
    
    try:
        # This is a placeholder logic. Real scraping requires precise selectors.
        # Since I cannot inspect the live DOM interactively easily, I will try a generic approach
        # or assume a standard table structure if found.
        
        # Let's look for the "UAE Gold Rates" section
        section = soup.find("h3", string=lambda t: t and "UAE Gold Rates" in t)
        if section:
            # The table usually follows the header
            table = section.find_next("table")
            if table:
                rows = table.find_all("tr")
                for row in rows[1:]: # Skip header
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        purity = cols[0].get_text(strip=True)
                        price = cols[1].get_text(strip=True)
                        rates.append({
                            "region": "UAE",
                            "purity": purity,
                            "price": price,
                            "currency": "AED"
                        })
    except Exception as e:
        logger.error(f"Error parsing UAE rates: {e}")

    return rates

def scrape_country_rates(country, url_suffix, currency):
    url = f"{BASE_URL}/{url_suffix}"
    soup = get_soup(url)
    if not soup:
        return []
    
    rates = []
    try:
        # Generic table scraper for the sub-pages
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) >= 2:
                    purity = cols[0].get_text(strip=True)
                    price = cols[1].get_text(strip=True)
                    
                    # Clean up India price if needed
                    if country == "India":
                        # Example format: "12,791₹127,910/ 10g"
                        # We want to extract the main price, likely the 10g one or just make it readable.
                        # Let's try to split by '₹' if present
                        if '₹' in price:
                            parts = price.split('₹')
                            if len(parts) > 1:
                                # Take the part with / 10g usually, or just the first part if it's per gram
                                # Let's just keep the original for now but maybe format it better in frontend
                                # Or better, let's try to get the 10g price which is usually the standard for India
                                pass
                    
                    # Basic validation to ensure it looks like a rate row
                    if "K" in purity or "Carat" in purity:
                        rates.append({
                            "region": country,
                            "purity": purity,
                            "price": price,
                            "currency": currency
                        })
            if rates: # If we found rates in a table, stop looking at other tables
                break
    except Exception as e:
        logger.error(f"Error parsing {country} rates: {e}")
        
    return rates

def get_all_rates():
    all_rates = []
    
    # UAE
    uae_rates = scrape_uae_rates()
    if uae_rates:
        all_rates.extend(uae_rates)
    
    # India
    india_rates = scrape_country_rates("India", "india-gold-prices", "INR")
    if india_rates:
        all_rates.extend(india_rates)
        
    # Oman
    oman_rates = scrape_country_rates("Oman", "oman-gold-prices", "OMR")
    if oman_rates:
        all_rates.extend(oman_rates)
        
    # Qatar
    qatar_rates = scrape_country_rates("Qatar", "qatar-gold-prices", "QAR")
    if qatar_rates:
        all_rates.extend(qatar_rates)
        
    # Saudi
    saudi_rates = scrape_country_rates("Saudi Arabia", "saudi-gold-prices", "SAR")
    if saudi_rates:
        all_rates.extend(saudi_rates)
        
    # Bahrain
    bahrain_rates = scrape_country_rates("Bahrain", "bahrain-gold-prices", "BHD")
    if bahrain_rates:
        all_rates.extend(bahrain_rates)
        
    # Kuwait
    kuwait_rates = scrape_country_rates("Kuwait", "kuwait-gold-prices", "KWD")
    if kuwait_rates:
        all_rates.extend(kuwait_rates)
        
    return all_rates

if __name__ == "__main__":
    # Test the scraper
    print(get_all_rates())
