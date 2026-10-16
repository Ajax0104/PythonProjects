import csv
from lot_item import LotItem
from manifest import Manifest

# --- ZONE 2: GLOBAL CONSTANTS ---
MINIMUM_MARGIN = 35.0

# --- ZONE 3: MAIN EXECUTION ---    
def main():
    print("Running Inventory Analyzer v4 (object-oriented Pipeline)...")

    input_filename = "auction_manifest.csv"
    output_filename = "profitable_lots.csv"
    batch = Manifest("Crowe Owasso Manifest")

    with open(input_filename, mode="r") as infile:
        reader = csv.DictReader(infile)

        for row in reader:
            try:
                # Instantiating a smart LotItem object straight from the CSV row
                item = LotItem(
                    lot_id=row["lot"],
                    bid=row["bid"],
                    premium=row["premium"],
                    tax=row["tax"],
                    sale_price=row["projected_sale"]
                )
                batch.add_item(item)
            except ValueError:
                print(
                    f"Skipped lot {row.get('lot', 'unknown')}: Invalid numerical data"
                    )
                continue

            # Retrieve items meeting or exceeding margin gatekeeper directly from Manifest
    profitable_items = batch.get_profitable_items(
        minimum_margin=MINIMUM_MARGIN
    )

    # Sort winners descending by margin
    sorted_winners = sorted(
        profitable_items, key=lambda item: item.calculate_margin(), reverse=True
    )

    # Export structured winners to CSV
    if sorted_winners:
        export_rows = [
            {
                "lot": item.lot_id,
                "current_bid": item.bid,
                "premium": item.premium,
                "tax": item.tax,
                "max_allowable_bid": item.calculate_max_bid(
                    target_margin=MINIMUM_MARGIN
                ),
                "projected_sale": item.sales_price,
                "net_profit": item.calculate_net_profit(),
                "margin": item.calculate_margin(),
            }
            for item in sorted_winners
        ]

        fieldnames = list(export_rows[0].keys())
        with open(output_filename, mode="w", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(export_rows)

    # Output batch-level metrics managed by Manifest container
    print(f"\n--- {batch.manifest_name} Summary ---")
    print(f"Total Items Ingested: {len(batch.items)}")
    print(f"Total Capital Required: ${batch.total_required_capital():.2f}")
    print(f"Total Projected Net Profit: ${batch.total_projected_profit():.2f}")
    print(
        f"Winning Lots Exported (>= {MINIMUM_MARGIN}% Margin): {len(sorted_winners)} -> {output_filename}"
    )


if __name__ == "__main__":
    main()