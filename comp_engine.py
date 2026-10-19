import csv
import re


def estimate_market_value(title):
    """Analyzes product titles against hardware, tool, and consumer goods pricing rules to estimate realistic resale comps."""
    title_lower = title.lower()

    # Rule-based category matchers: (Pattern, Target Resale Price)
    pricing_rules = [
        # High-Margin Hardware & Tools
        (r"panasonic|exhaust fan|vent fan", 110.00),
        (r"tankless|water heater", 180.00),
        (r"dewalt|milwaukee|makita|bosch|ryobi", 95.00),
        (r"air compressor|generator|pressure washer", 140.00),
        (r"faucet|shower valve|plumbing", 65.00),
        (r"thermostat|nest|ecobee", 75.00),
        # Home & Utility
        (r"air purifier", 85.00),
        (r"mini fridge|refrigerator", 110.00),
        (r"heat sealer", 35.00),
        (r"toilet seat|commode|bidet", 45.00),
        (r"lap desk", 30.00),
        (r"litter box", 35.00),
        (r"car seat cushion|memory foam", 40.00),
        (r"pilates|reformer", 150.00),
        (r"kids bike|bicycle", 75.00),
        (r"rain guards|cable railing", 50.00),
        (r"rug|mat", 45.00),
        (r"oven|air fryer", 80.00),
        (r"starbucks|tumbler", 18.00),
    ]

    for pattern, price in pricing_rules:
        if re.search(pattern, title_lower):
            return price

    # Fallback conservative baseline for unmatched general merchandise
    return 25.00


def process_manifest_comps(
    input_file="auction_manifest.csv", output_file="auction_manifest.csv"
):
    """Reads manifest, evaluates titles against pricing rules, and updates projected_sale values."""
    rows = []

    with open(input_file, mode="r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)
        fieldnames = reader.fieldnames

        for row in reader:
            title = row.get("title", "")
            estimated_price = estimate_market_value(title)
            row["projected_sale"] = f"{estimated_price:.2f}"
            rows.append(row)

    with open(output_file, mode="w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Successfully applied clean market comps across {len(rows)} items in '{output_file}'."
    )


if __name__ == "__main__":
    print("--- STAGE 2: PRODUCT COMP ENGINE ---")
    process_manifest_comps()