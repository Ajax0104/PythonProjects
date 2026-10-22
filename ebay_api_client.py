import base64
import os
import requests
from dotenv import load_dotenv

# Load API keys from local .env
load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID", "PENDING_APPROVAL")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET", "PENDING_APPROVAL")


def get_oauth_token():
    """Requests an OAuth 2.0 Client Credentials Access Token from eBay."""
    if (
        EBAY_CLIENT_ID == "PENDING_APPROVAL"
        or EBAY_CLIENT_SECRET == "PENDING_APPROVAL"
    ):
        return None

    auth_header = base64.b64encode(
        f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode("utf-8")
    ).decode("utf-8")

    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}",
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }

    try:
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
    except requests.RequestException:
        pass

    return None


def calculate_smart_market_floor(prices, outlier_threshold=0.15):
    """
    Evaluates top 3 lowest active prices. If mean of top 3 is > threshold (default 15%)
    above the lowest price, flags lowest as an outlier and adjusts market floor upward
    by 50% of the difference.
    """
    if not prices:
        return None

    sorted_prices = sorted(prices)
    lowest = sorted_prices[0]

    if len(sorted_prices) < 3:
        return round(lowest, 2)

    top_3 = sorted_prices[:3]
    mean_top3 = sum(top_3) / 3.0

    # Calculate percentage spread between top 3 mean and absolute lowest
    pct_spread = (mean_top3 - lowest) / lowest

    if pct_spread > outlier_threshold:
        # Outlier detected: Revert upward by 50% of the spread
        adjusted_floor = lowest + 0.5 * (mean_top3 - lowest)
        return round(adjusted_floor, 2)

    return round(lowest, 2)


def fetch_lowest_active_bin(query, outlier_threshold=0.15):
    """
    Queries eBay for top 3 lowest active Buy It Now listings and applies
    outlier dampening logic. Uses simulated top 3 spreads while API is in review.
    """
    token = get_oauth_token()

    # MOCK ENGINE (Simulates top 3 active price spreads during API review)
    if not token:
        mock_active_top3 = {
            # Outlier example: $10 fire-sale vs $22/$25 cluster (Spread > 15%)
            "regulator": [10.00, 22.00, 25.00],
            # Tight cluster example: Normal active market (Spread <= 15%)
            "shelves": [50.00, 52.00, 54.00],
            "motor": [40.00, 42.00, 48.00],
            "gasket": [18.00, 19.00, 20.00],
            "cleaner": [20.00, 21.00, 23.00],
        }

        for key, price_list in mock_active_top3.items():
            if key in query.lower():
                return calculate_smart_market_floor(
                    price_list, outlier_threshold
                )

        # Default fallback mock spread
        return calculate_smart_market_floor([25.00, 27.00, 28.00], outlier_threshold)

    # LIVE EBAY BROWSE API SEARCH
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    params = {
        "q": query,
        "limit": "3",  # Retrieve top 3 lowest price listings
        "filter": "buyingOptions:{FIXED_PRICE}",
        "sort": "price",
    }

    try:
        response = requests.get(
            url, headers=headers, params=params, timeout=10
        )
        if response.status_code == 200:
            items = response.json().get("itemSummaries", [])
            extracted_prices = []
            for item in items:
                val = item.get("price", {}).get("value")
                if val:
                    extracted_prices.append(float(val))

            if extracted_prices:
                return calculate_smart_market_floor(
                    extracted_prices, outlier_threshold
                )
    except requests.RequestException:
        pass

    return None


if __name__ == "__main__":
    print("--- TESTING SMART OUTLIER MARKET FLOOR ENGINE ---\n")

    # Test Case 1: Fire-Sale Outlier ($10 vs $22, $25)
    outlier_prices = [10.00, 22.00, 25.00]
    outlier_res = calculate_smart_market_floor(outlier_prices, outlier_threshold=0.15)
    print("Test 1: Fire-Sale Outlier")
    print(f"  Top 3 Prices : {outlier_prices}")
    print(f"  Top 3 Mean   : ${sum(outlier_prices)/3:.2f}")
    print(f"  Smart Floor  : ${outlier_res:.2f}  (Adjusted upward from $10.00)")
    print("-" * 55)

    # Test Case 2: Tight Market Cluster ($50, $52, $54)
    cluster_prices = [50.00, 52.00, 54.00]
    cluster_res = calculate_smart_market_floor(cluster_prices, outlier_threshold=0.15)
    print("Test 2: Tight Market Cluster")
    print(f"  Top 3 Prices : {cluster_prices}")
    print(f"  Top 3 Mean   : ${sum(cluster_prices)/3:.2f}")
    print(f"  Smart Floor  : ${cluster_res:.2f}  (Anchored to absolute lowest)")
    print("-" * 55)