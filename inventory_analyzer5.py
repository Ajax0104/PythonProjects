import os
import pandas as pd
from comp_engine import clean_title_for_search, estimate_market_value

# File paths
MANIFEST_FILE = "auction_manifest.csv"
OUTPUT_PROFITABLE = "profitable_lots.csv"
OUTPUT_ACTIONABLE = "actionable_bids.csv"


def calculate_max_bid(
    market_floor, min_margin_pct=0.30, fee_reserve_pct=0.15
):
    """Max Bid Formula: Market Floor * (1 - (Target Margin + Seller Fees))"""
    if not market_floor or market_floor <= 0:
        return 0.0
    max_bid = market_floor * (1.0 - (min_margin_pct + fee_reserve_pct))
    return round(max(max_bid, 0.0), 2)


def run_full_pipeline():
    if not os.path.exists(MANIFEST_FILE):
        print(f"[ERROR] Manifest file '{MANIFEST_FILE}' not found.")
        return

    print("--- STARTING CROWE MANIFEST UNDERWRITING PIPELINE ---")
    df = pd.read_csv(MANIFEST_FILE)

    # Locate title column flexibly
    title_col = next(
        (
            col
            for col in df.columns
            if "title" in col.lower()
            or "item" in col.lower()
            or "description" in col.lower()
        ),
        None,
    )
    if not title_col:
        print("[ERROR] Could not locate title/description column in CSV.")
        return

    cleaned_titles = []
    smart_floors = []
    max_bids = []

    total_items = len(df)
    print(f"Loaded {total_items} items from {MANIFEST_FILE}.\n")

    for idx, row in df.iterrows():
        raw_title = str(row[title_col])
        clean_title = clean_title_for_search(raw_title)

        # Pull smart market floor via comp_engine (which calls ebay_api_client)
        floor_price = estimate_market_value(raw_title)
        bid_limit = calculate_max_bid(floor_price)

        cleaned_titles.append(clean_title)
        smart_floors.append(floor_price)
        max_bids.append(bid_limit)

        print(
            f"[{idx+1}/{total_items}] Cleaned: '{clean_title[:35]}...' -> Floor: ${floor_price:.2f} | Max Bid: ${bid_limit:.2f}"
        )

    # Inject calculated columns into DataFrame
    df["Cleaned_Search_Title"] = cleaned_titles
    df["Smart_Market_Floor"] = smart_floors
    df["Max_Bid_Limit"] = max_bids

    # Export full dataset to CSV
    df.to_csv(OUTPUT_PROFITABLE, index=False)
    print(f"\n[SUCCESS] Full manifest output written to '{OUTPUT_PROFITABLE}'")

    # Filter and export actionable positive bids (> $0.00)
    actionable_df = df[df["Max_Bid_Limit"] > 0].copy()
    actionable_df.to_csv(OUTPUT_ACTIONABLE, index=False)
    print(
        f"[SUCCESS] Exported {len(actionable_df)} actionable bids to '{OUTPUT_ACTIONABLE}'"
    )


if __name__ == "__main__":
    run_full_pipeline()