import csv
from comp_engine import estimate_market_value
from crowe_scraper import scrape_manifest
from lot_item import LotItem
from manifest import Manifest

# --- GLOBAL CONSTANTS ---
TARGET_MARGIN = 35.0
    
def main():
    print("Running Inventory Analyzer v4 (object-oriented Pipeline)...")

    input_filename = "auction_manifest.csv"
    output_filename = "profitable_lots.csv"

    try:
        scrape_manifest(input_filename)
    except Exception as e:
        print(f"Scraper skipped/failed ({e})")

    batch = Manifest("Crowe Owasso Manifest")

    with open(input_filename, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)

        # 1. Slice only the first 50 rows for testing
        rows = list(reader)[:50]  # Take first 10 lots for testing

        audit_rows = []
        
        for idx, row in enumerate(rows, start=1):
            try:
                raw_title = row.get("title", "")
                bid_val = float(row.get("bid", 0.0) or 0.0)

                print(
                    f"[{idx}/50] Comping lot {row.get('lot', '')}: {raw_title[:30]}..."
                )

                # Lookup market floor valuation
                projected_sale, comps = estimate_market_value(raw_title)

                for rank, comp in enumerate(comps, start=1):
                    audit_rows.append({
                        "crowe_lot": row.get("lot", ""),
                        "crowe_title": raw_title,
                        "comp_rank": rank,
                        "ebay_title": comp.get("ebay_title", ""),
                        "ebay_price": comp.get("ebay_price", 0.0),
                        "item_url": comp.get("item_url", ""),
                    })

                item = LotItem(
                    lot_id=row.get("lot", ""),
                    title=raw_title,
                    bid=bid_val,
                    sale_price=projected_sale,
                )
                batch.add_item(item)
            except (ValueError, KeyError):
                print(
                    f"Skipped lot {row.get('lot', 'unknown')}: Invalid numerical data"
                )
                continue

    # Retrieve items meeting or exceeding margin gatekeeper directly from Manifest
    viable_items = batch.get_viable_lots()

    # Sort winners descending by margin
    sorted_winners = sorted(
        viable_items, 
        key=lambda item: item.max_bid,
        reverse=True,
    )

    # Calculate capital and profit metrics exclusively for winning/viable lots
    viable_capital_at_current = sum(
        item.true_cost for item in sorted_winners
    )
    viable_capital_at_max = sum(
        item.max_acquisition_cost for item in sorted_winners
    )
    
    viable_projected_profit = sum(
        item.net_profit for item in sorted_winners
    )

    # Export auction sheet to CSV
    if sorted_winners:
        export_rows = [item.to_dict(TARGET_MARGIN) for item in sorted_winners]
        fieldnames = list(export_rows[0].keys())
        
        with open(
            output_filename, mode="w", newline="", encoding="utf-8"
        ) as outfile:
            
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(export_rows)

    if audit_rows:

        with open("comp_audit.csv", mode="w", newline="", encoding="utf-8") as f:

            writer = csv.DictWriter(f, fieldnames=list(audit_rows[0].keys()))
            writer.writeheader()
            writer.writerows(audit_rows)

   # Summary Readout
    print(f"\n==========================================")
    print(f"--- {batch.manifest_name} Underwriting Summary ---")
    print(f"==========================================")
    print(f"Total Catalog Lots Ingested : {len(batch.items)}")
    print(
        f"Total Full Catalog Cost     : ${batch.total_required_capital():.2f}"
    )
    print(f"------------------------------------------")
    print(
        f"Viable Actionable Lots      : {len(sorted_winners)} -> {output_filename}"
    )
    print(
        f"Capital Needed (At Current) : ${viable_capital_at_current:.2f}"
    )
    print(
        f"Capital Ceiling (At Max Bid): ${viable_capital_at_max:.2f}"
    )
    print(
        f"Projected Viable Net Profit : ${viable_projected_profit:.2f}"
    )
    print(f"==========================================")


if __name__ == "__main__":
    main()