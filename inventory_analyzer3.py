import csv

# --- Zone 1: Global Constants ---
EBAY_FEE_PERCENTAGE = 0.1325
MINIMUM_MARGIN = 35.0
SHIPPING_COST = 16.50
EFFECTIVE_TAX_RATE = 0.08 #Blended historical rate (~8%)

# --- Zone 2: Functions ----
def calculate_metrics(sale_price, true_cost):
    """Calculate marketplace fees, net profit, and margin percentage"""
    estimated_tax = sale_price * EFFECTIVE_TAX_RATE
    total_transaction_value = sale_price + SHIPPING_COST + estimated_tax
    marketplace_fee = total_transaction_value * EBAY_FEE_PERCENTAGE

    net_profit = round(
        sale_price - (true_cost + marketplace_fee + SHIPPING_COST), 2
    )
    margin = round((net_profit / sale_price) * 100, 1)

    return net_profit, margin

# --- Zone 3: Main Execution ---
def main():
    print("Running Inventory Analzer v3 (Modular Architecture)...")

    with open("auction_manifest.csv", mode="r") as file:   # Ask gemini why no space before =
        reader = csv.DictReader(file)

        surviving_items = 0

        for row in reader:
            true_cost = (
                float(row["bid"]) + float(row["premium"]) + float(row["tax"])
            )
            sale_price = float(row["projected_sale"])

            # Call our modular function
            net_profit, margin = calculate_metrics(sale_price, true_cost)

            if margin >= MINIMUM_MARGIN:
                surviving_items += 1
                print(
                    f"Passed: Lot {row['lot']} - {row['title']} | Margin: {margin}% | Profit: ${net_profit}"
                )

        print(f"\nAnalysis complete, Total survivors: {surviving_items}")


if __name__ == "__main__":
    main()