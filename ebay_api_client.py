import os
import requests
from dotenv import load_dotenv

# Load credentials from local env files
load_dotenv()
load_dotenv("ebayapikeys.env")

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")


def get_oauth_token():
    """Fetches eBay OAuth Application Access Token."""
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        return None

    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }
    try:
        res = requests.post(
            url,
            headers=headers,
            data=data,
            auth=(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET),
            timeout=5,
        )
        if res.status_code == 200:
            return res.json().get("access_token")
    except Exception:
        pass
    return None


def calculate_smart_market_floor(prices):
    """Calculates outlier-dampened market floor from top 3 active BIN listings.

    If top 3 mean is >15% higher than the lowest price, adjusts floor upward
    by 50% of the difference to eliminate fire-sale outliers.
    """
    if not prices:
        return 0.0

    prices = sorted(prices)[:3]
    lowest = prices[0]

    if len(prices) == 1:
        return round(lowest, 2)

    mean_top3 = sum(prices) / len(prices)

    # Outlier check: If mean is >15% above lowest, adjust floor up
    if (mean_top3 - lowest) / lowest > 0.15:
        dampened_floor = lowest + 0.50 * (mean_top3 - lowest)
        return round(dampened_floor, 2)

    return round(lowest, 2)


def fetch_lowest_active_bin(query_title):
    """Queries eBay Browse API for active Buy It Now listings, applies smart outlier

    dampening, and falls back to dynamic keyword mock engine during developer key review.
    """
    if not query_title:
        return 0.0, []

    token = get_oauth_token()

    # 1. LIVE API PATH (Runs when keys are active)
    if token:
        url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "q": query_title,
            "filter": "buyingOptions:{FIXED_PRICE}",
            "limit": "5",
            "sort": "price",
        }
        try:
            res = requests.get(url, headers=headers, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                items = data.get("itemSummaries", [])
                prices = []
                raw_comps = []

                for item in items:
                    price_val = float(item.get("price", {}).get("value", 0.0))
                    if price_val > 0:
                        prices.append(price_val)

                        raw_comps.append({
                            "ebay_title": item.get("title", ""),
                            "ebay_price": price_val,
                            "item_url": item.get("itemWebUrl", "")
                        })

                if prices:
                    floor_price = calculate_smart_market_floor(prices)
                    return floor_price, raw_comps
                
        except Exception:
            pass

    # 2. MOCK FALLBACK PATH (Feeds top 3 price clusters into Outlier Engine for Dev Testing)
    title_clean = query_title.lower()
    mock_market_floors = [
        ("panasonic", [100.00, 140.00, 150.00]),  # Outlier test: dampens $100 fire-sale to ~$115
        ("tankless", [180.00, 220.00, 230.00]),
        ("water heater", [160.00, 190.00, 200.00]),
        ("dewalt", [90.00, 120.00, 130.00]),
        ("milwaukee", [100.00, 135.00, 145.00]),
        ("makita", [85.00, 110.00, 120.00]),
        ("bosch", [75.00, 100.00, 110.00]),
        ("ryobi", [55.00, 75.00, 80.00]),
        ("thermostat", [70.00, 90.00, 95.00]),
        ("nest", [75.00, 95.00, 100.00]),
        ("ecobee", [80.00, 100.00, 105.00]),
        ("faucet", [60.00, 80.00, 85.00]),
        ("shower", [65.00, 85.00, 90.00]),
        ("air purifier", [90.00, 115.00, 125.00]),
        ("compressor", [120.00, 160.00, 170.00]),
        ("generator", [180.00, 230.00, 250.00]),
        ("vacuum", [70.00, 90.00, 95.00]),
        ("shark", [80.00, 100.00, 110.00]),
        ("dyson", [130.00, 170.00, 180.00]),
        ("light", [40.00, 55.00, 60.00]),
        ("lock", [50.00, 65.00, 70.00]),
        ("bidet", [35.00, 48.00, 52.00]),
    ]

    for keyword, mock_prices in mock_market_floors:
        if keyword in title_clean:
            return calculate_smart_market_floor(mock_prices), []

    return 0.0, []