import csv  # Standard Python library to read and write CSV spreadsheet files
import re  # Regular Expression library used to search, isolate, and clean text patterns
import time
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
    total_pages=18,
    max_retries=3,
):
    """Scrapes lot titles, condition flags, current high bids, and lot IDs with automatic retry handling on timeouts."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    base_url = catalog_url.rstrip("?&")
    scraped_lots = []
    seen_lots = set()  # Tracks processed Lot IDs to eliminate duplicate banner items

    for page in range(1, total_pages + 1):
        page_url = f"{base_url}?page={page}&items=50"
        print(f"Fetching page {page} of {total_pages}: {page_url}")

        response = None
        # Retry loop to handle transient network timeouts (e.g., Page 12 delay)
        for attempt in range(1, max_retries + 1):
            try:
                response = requests.get(page_url, headers=headers, timeout=20)
                response.raise_for_status()
                break  # Request succeeded, exit retry loop
            except requests.RequestException as error:
                print(
                    f"  Attempt {attempt}/{max_retries} failed for page {page}: {error}"
                )
                if attempt < max_retries:
                    time.sleep(2)  # Wait 2 seconds before retrying
                else:
                    print(
                        f"Skipping page {page} after {max_retries} failed attempts."
                    )

        if not response or response.status_code != 200:
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        lot_cards = soup.find_all("div", class_=re.compile(r"lot|item|card", re.I))
        if not lot_cards:
            lot_cards = soup.select("[class*='lot'], [class*='item']")

        for card in lot_cards:
            text = card.get_text(separator=" ", strip=True)

            lot_match = re.search(r"Lot\s*(\d+)", text, re.I)
            bid_match = re.search(r"\$(\d+\.\d{2})", text)

            if lot_match and bid_match:
                lot_id = lot_match.group(1)

                # Skip if lot was already scraped from a featured card or banner
                if lot_id in seen_lots:
                    continue
                seen_lots.add(lot_id)

                bid = bid_match.group(1)
                title, packaging, damaged = clean_lot_title(text, lot_id)

                scraped_lots.append(
                    {
                        "lot": lot_id,
                        "title": title,
                        "bid": bid,
                        "packaging": packaging,
                        "damaged": damaged,
                        "projected_sale": "0.00",
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
        "projected_sale",
    ]

    # Open CSV file for writing with UTF-8 encoding and newline handling
    with open(filename, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames, extrasaction="ignore")
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
    lots = fetch_crowe_catalog(catalog_url=TARGET_CATALOG_URL, total_pages=18)
    # Write scraped lot records to auction_manifest.csv
    export_to_manifest(lots)

def scrape_manifest(output_filename="auction_manifest.csv"):
    """Runs the full scrape and exports to CSV in one step."""
    lots = fetch_crowe_catalog()
    export_to_manifest(lots, filename=output_filename)