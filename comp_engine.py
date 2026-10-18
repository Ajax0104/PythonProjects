import csv
import re


def estimate_market_value(title):
    """Analyzes title keywords against a baseline pricing rule set to estimate resale comps."""
    title_lower = title.lower()

    # Rule-based keyword matching dictionary (Base market values)
    pricing_rules = [
        (r"air purifier", 85.00),
        (r"heat sealer", 35.00),
        (r"starbucks|cold cup|tumbler", 18.00),
        (r"toilet seat|commode", 45.00),
        (r"lap desk", 30.00),
        (r"wallpaper|mural", 25.00),
        (r"litter box", 35.00),
        (r"car seat cushion|memory foam", 40.00),
        (r"mini fridge|refrigerator", 110.00),
        (r"pilates|reformer", 150.00),
        (r"kids bike|bicycle", 75.00),
        (r"rain guards", 35.00),
        (r"cable railing", 65.00),
        (r"rug|mat", 50.00),
        (r"oven|air fryer", 80.00),
        (r"air mattress", 45.00),
    ]

    for pattern, price in pricing_rules:
        if re.search(pattern, title_lower):
            return price

    return 25.00


def process_manifest_comps(
    input_file="auction_manifest.csv", output_file="auction_manifest.csv"
):
    """Reads raw manifest, populates projected_sale values, and writes updated CSV."""
    rows = []

    # 1. Read input CSV and populate projected_sale values
    with open(input_file, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames

        for row in reader:
            if float(row.get("projected_sale", 0.0)) == 0.0:
                # Fixed function name match: estimate_market_value
                estimated_price = estimate_market_value(row["title"])
                row["projected_sale"] = f"{estimated_price:.2f}"
            rows.append(row)

    # 2. Write updated rows back to output file (Restored missing block)
    with open(output_file, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Successfully applied market comps across {len(rows)} items in '{output_file}'."
    )


if __name__ == "__main__":
    print("--- STAGE 2: COMP ENGINE VALUATION ---")
    process_manifest_comps()