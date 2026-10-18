import csv
import re
import requests
from bs4 import BeautifulSoup

def fetch_crowe_catalog(
        catalog_url="https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166", 
        total_pages=1,
    ): #this will eventually need to be available to be imputed through user wish
    """Scrapes lot titles, current high bids, and lot IDs from Crowe catalog pages."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    # Clean trailing ? or & from user input URL
    base_url = catalog_url.rstrip("?&")
    scraped_lots = []

    for page in range(1, total_pages + 1):
        # Constructs clean pagination URL: https://bids.crauctions.com/auctions/.../8166?page=1
        page_url = f"{base_url}?page={page}"
        print(f"Fetching page {page} of {total_pages}: {page_url}")

        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"Failed to fetch {page_url}: {error}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        # Select all lot container cards
        lot_cards = soup.find_all("div", class_=re.compile(r"lot|item|card", re.I))
        if not lot_cards:
            lot_cards = soup.select("[class*='lot'], [class*='item']")

        for card in lot_cards:
            text = card.get_text(separator=" ", strip=True)

            # Extract Lot Number (e.g., Lot 8800) and Current Bid ($X.XX)
            lot_match = re.search(r"Lot\s*(\d+)", text, re.I)
            bid_match = re.search(r"\$(\d+\.\d{2})", text)

            if lot_match and bid_match:
                lot_id = lot_match.group(1)
                bid = bid_match.group(1)

                clean_text = re.sub(r"\s+", " ", text).strip()
                title_match = re.search(
                    rf"Lot\s*{lot_id}:?\s*([^$]+)", clean_text, re.I
                )
                title = (
                    title_match.group(1).strip()[:80]
                    if title_match
                    else f"Lot {lot_id}"
                )

                scraped_lots.append(
                    {
                        "lot": lot_id,
                        "title": title,
                        "bid": bid,
                        "projected_sale": "0.00",
                    }
                )

    return scraped_lots


def export_to_manifest(data, filename="auction_manifest.csv"):
    if not data:
        print("No lot data extracted. Check card selector or URL structure.")
        return

    fieldnames = ["lot", "title", "bid", "projected_sale"]
    with open(filename, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    print(f"\nSuccessfully saved {len(data)} live lots to '{filename}'")


if __name__ == "__main__":
    print("--- CROWE CATALOG INGESTION ENGINE ---")

    # TARGET AUCTION CATALOG URL
    TARGET_CATALOG_URL = "https://bids.crauctions.com/auctions/48980-amazon-semi-load-auction-8166"

    lots = fetch_crowe_catalog(catalog_url=TARGET_CATALOG_URL, total_pages=1)
    export_to_manifest(lots)