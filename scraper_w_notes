import csv  # Standard Python library to read and write CSV spreadsheet files
import re  # Regular Expression library used to search, isolate, and clean text patterns
import requests  # HTTP library used to fetch web page source HTML from URLs
from bs4 import (
    BeautifulSoup,
)  # HTML parser library used to search and navigate web elements


def clean_lot_title(raw_text, lot_id):
    """Strips catalog clutter (packaging/damage status) from raw card text to isolate clean product titles and condition flags."""
    # Step 1: Normalize whitespace (replace multiple spaces/newlines with a single space)
    text = re.sub(r"\s+", " ", raw_text).strip()

    # Step 2: Extract packaging status ('Yes', 'No', or 'Unknown') using regex pattern
    packaging_match = re.search(
        r"In Packaging\?:\s*(Yes|No|Unknown)", text, re.I
    )
    packaging = packaging_match.group(1) if packaging_match else "Unknown"

    # Step 3: Extract damage status ('Yes', 'No', or 'Unknown') using regex pattern
    damaged_match = re.search(r"Damaged\?:\s*(Yes|No|Unknown)", text, re.I)
    damaged = damaged_match.group(1) if damaged_match else "Unknown"

    # Step 4: Isolate clean product title by capturing text after 'Lot XXXX:' and before 'In Packaging' or pricing
    title_pattern = rf"Lot\s*{lot_id}:?\s*(.*?)(?=In Packaging\?:|Damaged\?:|Ends:|\$|\Z)"
    title_match = re.search(title_pattern, text, re.I)

    if title_match and title_match.group(1).strip():
        clean_title = title_match.group(1).strip()
    else:
        # Fallback split: trim raw string directly at 'In Packaging' keyword
        clean_title = text.split("In Packaging")[0].strip()
        clean_title = re.sub(
            rf"^Lot\s*{lot_id}:?\s*", "", clean_title, flags=re.I
        ).strip()

    # Step 5: Clean quotes and cap length to preserve clean CSV formatting
    clean_title = clean_title.strip(' "')[:100]

    return clean_title, packaging, damaged


def fetch_crowe_catalog(
    catalog_url="https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166",
    total_pages=1,
):
    """Scrapes lot titles, condition flags, current high bids, and lot IDs directly from target catalog URL."""
    # Define browser user-agent header so auction server treats our script like a standard web browser
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # Clean trailing query symbols (? or &) from raw catalog URL input
    base_url = catalog_url.rstrip("?&")
    scraped_lots = []  # List to store dictionary records for every lot card parsed

    # Loop through requested page range (page 1 to total_pages)
    for page in range(1, total_pages + 1):
        # Build clean pagination link: base_url?page=N
        page_url = f"{base_url}?page={page}"
        print(f"Fetching page {page} of {total_pages}: {page_url}")

        try:
            # Issue GET request over internet to fetch HTML content of catalog page
            response = requests.get(page_url, headers=headers, timeout=10)
            response.raise_for_status()  # Trigger exception if HTTP response code is 4xx or 5xx
        except requests.RequestException as error:
            print(f"Failed to fetch page {page}: {error}")
            continue  # Skip to next page iteration if network request fails

        # Parse raw HTML text string into navigable BeautifulSoup object
        soup = BeautifulSoup(response.text, "html.parser")

        # Find all HTML div container elements matching lot card class names
        lot_cards = soup.find_all("div", class_=re.compile(r"lot|item|card", re.I))
        if not lot_cards:
            # Secondary CSS fallback selector if class names vary
            lot_cards = soup.select("[class*='lot'], [class*='item']")

        # Iterate over every HTML lot card container found on current catalog page
        for card in lot_cards:
            # Convert HTML card block into single raw text string with space separators
            text = card.get_text(separator=" ", strip=True)

            # Search text for 'Lot [digits]' pattern
            lot_match = re.search(r"Lot\s*(\d+)", text, re.I)
            # Search text for '$[dollars].[cents]' current bid pattern
            bid_match = re.search(r"\$(\d+\.\d{2})", text)

            # Only process block if valid Lot ID and Current Bid were detected
            if lot_match and bid_match:
                lot_id = (
                    lot_match.group(1)
                )  # Extracted numerical ID string (e.g., '8014')
                bid = bid_match.group(1)  # Extracted dollar string (e.g., '10.00')

                # Pass card text to helper function to extract clean product title and condition tags
                title, packaging, damaged = clean_lot_title(text, lot_id)

                # Append structured lot dictionary record to master scraped list
                scraped_lots.append(
                    {
                        "lot": lot_id,
                        "title": title,
                        "bid": bid,
                        "packaging": packaging,
                        "damaged": damaged,
                        "projected_sale": "0.00",  # Placeholder value to be updated by Stage 2 comp engine
                    }
                )

    return scraped_lots


def export_to_manifest(data, filename="auction_manifest.csv"):
    """Writes scraped lot dictionaries into auction_manifest.csv spreadsheet format."""
    if not data:
        print("No lot data extracted. Check card selector or target URL.")
        return

    # Column headers for generated CSV file
    fieldnames = [
        "lot",
        "title",
        "bid",
        "packaging",
        "damaged",
        "projected_sale",
    ]

    # Open CSV file for writing with UTF-8 encoding and newline handling
    with open(filename, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()  # Write header row (lot, title, bid, packaging, damaged, projected_sale)
        writer.writerows(
            data
        )  # Write all scraped lot dictionary rows into spreadsheet

    print(f"\nSuccessfully saved {len(data)} live scraped lots to '{filename}'")


# Standard Python execution entry point
if __name__ == "__main__":
    print("--- CROWE CATALOG INGESTION ENGINE ---")

    # Live target catalog URL (Crowe Amazon Semi Load Auction #8166)
    TARGET_CATALOG_URL = "https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166"

    # Execute catalog scrape for page 1
    lots = fetch_crowe_catalog(catalog_url=TARGET_CATALOG_URL, total_pages=1)
    # Write scraped lot records to auction_manifest.csv
    export_to_manifest(lots)