import re
import statistics
import urllib.parse
import xml.etree.ElementTree as ET
from curl_cffi import requests


def fetch_ebay_sold_prices(query, max_results=10):
    """Fetches sold listings via eBay's RSS XML endpoint to bypass Akamai HTML bot challenges."""
    # Sanitize title to top 5 core words
    clean_query = (
        query.replace('"', "")
        .replace("''", "")
        .replace("-", " ")
        .replace(",", " ")
    )
    words = clean_query.split()[:5]
    search_str = " ".join(words)

    encoded = urllib.parse.quote(search_str)
    # _rss=1 outputs clean XML feed data without Akamai HTML bot challenges
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}&LH_Sold=1&LH_Complete=1&_rss=1"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/xml,application/xml,application/rss+xml;q=0.9",
    }

    try:
        response = requests.get(
            url, headers=headers, impersonate="chrome120", timeout=10
        )
        print(f"  [DEBUG] Query URL   : {url}")
        print(f"  [DEBUG] Status Code : {response.status_code}")

        if response.status_code != 200:
            print(f"  [DEBUG] Blocked with status {response.status_code}")
            return []

        # Parse raw RSS XML response
        root = ET.fromstring(response.content)
        prices = []

        for item in root.findall(".//item"):
            title_text = item.findtext("title", default="")
            desc_text = item.findtext("description", default="")
            combined_text = f"{title_text} {desc_text}"

            # Extract dollar values from RSS title and description elements
            matches = re.findall(r"\$(\d+(?:\.\d{2})?)", combined_text)
            if matches:
                # First match in eBay RSS item description is the final transaction price
                val = float(matches[0])
                if val > 1.0:
                    prices.append(val)

            if len(prices) >= max_results:
                break

        print(f"  [DEBUG] RSS Prices Extracted: {len(prices)}")
        return prices

    except Exception as err:
        print(f"  [DEBUG] XML Parse Exception: {err}")
        return []


def fetch_ebay_sold_median(query):
    """Calculates median price across active sold results."""
    prices = fetch_ebay_sold_prices(query)
    if not prices:
        return None
    return round(statistics.median(prices), 2)