import csv

# --- ZONE 1: class definition ---
class LotItem:
    """Blueprint for individual auction lots with internal financial math.""" 

    EBAY_FEE_PERCENTAGE = 0.1325
    SHIPPING_COST = 16.50
    EFFECTIVE_TAX_RATE = 0.08

    def __init__(self, lot_id, bid, premium, tax, sale_price):
        self.lot_id = lot_id
        self.bid = float(bid)
        self.premium = float(premium)
        self.tax = float(tax)
        self.sales_price = float(sale_price)        
        
    def calculate_true_cost(self):
        return self.bid + self.premium + self.tax

    def calculate_net_profit(self):
        true_cost = self.calculate_true_cost()
        estimated_tax = self.sales_price * self.EFFECTIVE_TAX_RATE
        total_transaction_value = (
            self.sales_price + self.SHIPPING_COST + estimated_tax
        )
        marketplace_fee = total_transaction_value * self.EBAY_FEE_PERCENTAGE

        return round(
            self.sales_price - (true_cost + marketplace_fee + self.SHIPPING_COST),
            2,
        )

    def calculate_margin(self):
        net_profit = self.calculate_net_profit()
        return round((net_profit / self.sales_price) * 100, 1)

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
                print(f"Skipped lot {row.get('lot', 'unknown')}: Invalid numerical data")
                continue

            #Asking the object directly for its margin calculation
            if item.calculate_margin() >= MINIMUM_MARGIN:
                # Store the object and its calculated metrics as a cleam dictionary for export
                surviving_lots.append({
                "lot": item.lot_id,
                "bid": item.bid,
                "premium": item.premium,
                "tax": item.tax,
                "projected_sale": item.sales_price,
                "net_profit": item.calculate_net_profit(),
                "margin": item.calculate_margin()
            })

    # Sort in memory esing the exported dictionary margin key
    sorted_survivors = sorted(surviving_lots, key=lambda x: x["margin"], reverse=True)

    # Export winners to CSV
    if sorted_survivors:
        fieldnames = list(sorted_survivors[0].keys())
        with open(output_filename, mode="w", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sorted_survivors)

    print(f"\nAnalysis complete. {len(sorted_survivors)} winning lots sorted and exported to {output_filename}")

if __name__ == "__main__":
    main()