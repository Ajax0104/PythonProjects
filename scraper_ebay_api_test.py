import pandas as pd
from comp_engine import clean_title_for_search
from ebay_api_client import fetch_lowest_active_bin

MANIFEST_FILE = "auction_manifest.csv"

def test_full_crowe_api_run():
    print("--- TESTING EBAY API AGAINST FULL CROWE LIST ---")
    df = pd.read_csv(MANIFEST_FILE)
    
    # Identify title column
    title_col = next((col for col in df.columns if "title" in col.lower() or "item" in col.lower() or "description" in col.lower()), None)
    if not title_col:
        print(f"[ERROR] Could not find title column in {MANIFEST_FILE}")
        return

    print(f"Loaded {len(df)} items. Beginning API queries...\n")
    
    for idx, row in df.iterrows():
        raw_title = str(row[title_col])
        clean_title = clean_title_for_search(raw_title)
        
        # Query eBay API active floor
        floor_price = fetch_lowest_active_bin(clean_title)
        
        print(f"[{idx+1}/{len(df)}]")
        print(f"  RAW  : {raw_title}")
        print(f"  CLEAN: {clean_title}")
        print(f"  FLOOR: ${floor_price:.2f}\n")

if __name__ == "__main__":
    test_full_crowe_api_run()