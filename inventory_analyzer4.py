import csv
from lot_item import LotItem

# --- ZONE 2: GLOBAL CONSTANTS ---
MINIMUM_MARGIN = 35.0

# --- ZONE 3: MAIN EXECUTION ---    
def main():
    print("Running Inventory Analyzer v4 (object-oriented Pipeline)...")

    input_filename = "auction_manifest.csv"
    output_filename = "profitable_lots.csv"
    surviving_lots = []

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
            except ValueError:
                print(
                    f"Skipped lot {row.get('lot', 'unknown')}: Invalid numerical data"
                    )
                continue

            #Asking the object directly for its margin calculation
            if item.calculate_margin() >= MINIMUM_MARGIN:
                # Store the object and its calculated metrics as a cleam dictionary for export
                surviving_lots.append(
                    {
                        "lot": item.lot_id,
                        "bid": item.bid,
                        "max_allowable_bid": item.calculate_max_bid(
                            target_margin=MINIMUM_MARGIN
                        ),
                        "premium": item.premium,
                        "tax": item.tax,
                        "projected_sale": item.sales_price,
                        "net_profit": item.calculate_net_profit(),
                        "margin": item.calculate_margin()
                    }
                )

    # Sort in memory esing the exported dictionary margin key
    sorted_survivors = sorted(surviving_lots, key=lambda x: x["margin"], reverse=True)

    # Export winners to CSV
    if sorted_survivors:
        fieldnames = list(sorted_survivors[0].keys())
        with open(output_filename, mode="w", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_survivors)

    print(
        f"\nAnalysis complete. {len(sorted_survivors)} winning lots sorted and exported to {output_filename}"
    )

if __name__ == "__main__":
    main()