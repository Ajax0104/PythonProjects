import csv
from comp_engine import process_manifest_comps
from lot_item import LotItem
from manifest import Manifest

# --- GLOBAL CONSTANTS ---
TARGET_MARGIN = 35.0
    
def main():
    print("Running Inventory Analyzer v4 (object-oriented Pipeline)...")

    process_manifest_comps(
        input_file="auction_manifest.csv", output_file="auction_manifest.csv"
    )
    
    input_filename = "auction_manifest.csv"
    output_filename = "profitable_lots.csv"
    batch = Manifest("Crowe Owasso Manifest")

    with open(input_filename, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)

        for row in reader:
            try:
                # Instantiates LotItem (premium and tax calculated automatically inside LotItem)
                item = LotItem(
                    lot_id=row["lot"],
                    title=row.get("title", ""),
                    bid=row["bid"],
                    sale_price=row["projected_sale"]
                )
                batch.add_item(item)
            except ValueError:
                print(
                    f"Skipped lot {row.get('lot', 'unknown')}: Invalid numerical data"
                    )
                continue

    # Retrieve items meeting or exceeding margin gatekeeper directly from Manifest
    viable_items = batch.get_viable_lots(target_margin=TARGET_MARGIN)

    # Sort winners descending by margin
    sorted_winners = sorted(
        viable_items, 
        key=lambda item: item.calculate_max_bid(TARGET_MARGIN),
        reverse=True,
    )

    # Calculate capital and profit metrics exclusively for winning/viable lots
    viable_capital_at_current = sum(
        item.calculate_true_cost() for item in sorted_winners
    )
    viable_capital_at_max = sum(
        item.calculate_max_bid(TARGET_MARGIN) * 1.219
        for item in sorted_winners
    )
    viable_projected_profit = sum(
        item.calculate_net_profit() for item in sorted_winners
    )

    # Export auction sheet to CSV
    if sorted_winners:
        export_rows = [
            {
                "lot": item.lot_id,
                "title": item.title,
                "current_bid": item.bid,
                "max_allowable_bid": item.calculate_max_bid(TARGET_MARGIN),
                "projected_sale": item.sales_price,
                "net_profit": item.calculate_net_profit(),
                "margin": item.calculate_margin(),
            }
            for item in sorted_winners
        ]

        fieldnames = list(export_rows[0].keys())
        with open(
            output_filename, mode="w", newline="", encoding="utf-8"
            ) as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(export_rows)

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