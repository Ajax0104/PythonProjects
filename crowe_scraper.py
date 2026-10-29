import csv  # Standard Python library to read and write CSV spreadsheet files
import os
from pathlib import Path
import re  # Regular Expression library used to search, isolate, and clean text patterns
import tempfile
import time
import requests  # HTTP library used to fetch web page source HTML from URLs
from bs4 import (
    BeautifulSoup,
)  # HTML parser library used to search and navigate web elements


class IngestionError(RuntimeError):
    """The requested catalog could not be safely collected or published."""


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
    """Collect every requested page, or raise without returning partial data.

    Checks cover request failures, pages without parseable lots, visible lot IDs
    that cannot be parsed, and pages that add no new lots. They do not prove the
    configured page count covers the auction or that HTML exposes every lot.
    """
    if total_pages < 1 or max_retries < 1:
        raise IngestionError("total_pages and max_retries must be positive")
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
                    raise IngestionError(
                        f"Page {page} failed after {max_retries} attempts: {page_url}"
                    ) from error

        if response.status_code != 200:
            raise IngestionError(f"Page {page} returned unexpected HTTP {response.status_code}")

        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
        if content_type and content_type not in ("text/html", "application/xhtml+xml"):
            raise IngestionError(f"Page {page} returned non-HTML content: {content_type}")

        soup = BeautifulSoup(response.text, "html.parser")

        lot_cards = soup.find_all("div", class_=re.compile(r"lot|item|card", re.I))
        if not lot_cards:
            lot_cards = soup.select("[class*='lot'], [class*='item']")

        page_lots = set()
        visible_lots = set()
        previous_count = len(scraped_lots)
        for card in lot_cards:
            text = card.get_text(separator=" ", strip=True)
            visible_lots.update(re.findall(r"Lot\s*(\d+)", text, re.I))

            lot_match = re.search(r"Lot\s*(\d+)", text, re.I)
            bid_match = re.search(r"\$(\d+\.\d{2})", text)

            if lot_match and bid_match:
                lot_id = lot_match.group(1)

                bid = bid_match.group(1)
                title, packaging, damaged = clean_lot_title(text, lot_id)
                if not title:
                    raise IngestionError(f"Page {page}: lot {lot_id} has no parseable title")
                page_lots.add(lot_id)

                # Keep the existing featured/banner deduplication behavior.
                if lot_id in seen_lots:
                    continue
                seen_lots.add(lot_id)

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

        if not page_lots:
            raise IngestionError(f"Page {page} contains no parseable lots")
        missing_lots = visible_lots - page_lots
        if missing_lots:
            raise IngestionError(
                f"Page {page} contains unparseable lot IDs: {', '.join(sorted(missing_lots))}"
            )
        if len(scraped_lots) == previous_count:
            raise IngestionError(f"Page {page} adds no new lots; pagination cannot be verified")

    return scraped_lots

def export_to_manifest(data, filename="auction_manifest.csv"):
    """Publish a complete CSV atomically, leaving the old file intact on failure."""
    if not data:
        raise IngestionError("No lot data extracted; manifest was not replaced")

    # Column headers for generated CSV file
    fieldnames = [
        "lot",
        "title",
        "bid",
        "projected_sale",
    ]

    destination = Path(filename)
    staged_path = None
    try:
        # Same directory keeps staging and replacement on the same filesystem.
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as outfile:
            staged_path = Path(outfile.name)
            writer = csv.DictWriter(outfile, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)
            outfile.flush()
            os.fsync(outfile.fileno())
        os.replace(staged_path, destination)
    except (OSError, csv.Error) as error:
        raise IngestionError(f"Could not publish manifest: {destination}") from error
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)

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
