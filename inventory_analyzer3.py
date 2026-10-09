import csv

# --- Zone 1: Global Constants ---
EBAY_FEE_PERCENTAGE = 0.1325
MINIMUM_MARGIN = 10.0
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

    input_filename= "auction_manifest.csv"        
    output_filename = "profitable_lots.csv"

    # Create an empty list in memory to hold our survivors
    surviving_lots = []

    # Open input file for reading, and output file for writing simultaneously
    with open(input_filename, mode="r") as infile:
        reader = csv.DictReader(infile)
        
        for row in reader:
             
            try:
                # Safely attempt to convert all incoming CSV string values to floats
                bid = float(row["bid"])
                premium = float(row["premium"])
                tax = float(row["tax"])
                sale_price = float(row["projected_sale"])

            except ValueError:
                # log the corrupted lot and jump straight to the next iteration
                print(f"Skipped lot {row.get('lot', 'unknown')}: Invalid numerical data")
            
            true_cost = bid + premium + tax
        
            # Call our modular function
            net_profit, margin = calculate_metrics(sale_price, true_cost)

            if margin >= MINIMUM_MARGIN:

                # Inject our calculations directly into the row dictionary
                row["net_profit"] = net_profit
                row["margin"] = margin

                # Append (add) this dictionary to our list in memory
                surviving_lots.append(row)

    # sort the list in memory: Highest margin to lowest 
    sorted_survivors = sorted(
        surviving_lots,
        key=lambda item: float(item["margin"]),
        reverse=True
    )

    # Now, write the sorted data out to our CSv file
    if sorted_survivors:

        # Grab fieldnames from the first item and add our new columns
        fieldnames = list(sorted_survivors[0].keys())

        with open(output_filename, mode="w", newline="") as outfile:
                writer = csv.DictWriter(outfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sorted_survivors) # write all rows at once!

    print(f"\nAnalysis complete. {len(sorted_survivors)} winning lots sorted and exported to {output_filename}")

if __name__ == "__main__":
    main()