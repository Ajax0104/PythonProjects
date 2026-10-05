# Project 2: eBay Inventory, using actual crowe invoice & Profit Analyzer

#CR auction manifest items
#Format: "SKU-CATEGORY-ITEM_NAME|ESTIMATED_SALE_PRICE|ACQUISITION_COST|ESTIMATED_SHIP"

import csv

# Constants
EBAY_FEE_PERCENTAGE = 0.1325 # ~13.25 eBay final value fee NOTE FOR GEMINI THIS FIGURE VARIES by category
MINIMUM_MARGIN = 35.0

print("=" * 90)
print("                     AUCTION INVOICE BATCH PROCESSOR                    ")
print("=" * 90)

# Storage List (To keep data in memory after the loop finishes)

processed_inventory = []
actionable_bids = []

# Open and read the external CSV file (instead of hardcoded list)

with open('auction_manifest.csv', mode='r') as file:
    reader = csv.DictReader(file)

    for row in reader:

        #CSV reads numbers as strings-we must convert them to floats for math!
        true_cost = float(row["bid"]) + float(row["premium"]) + float(row["tax"])
        sale_price = float(row["projected_sale"])

        # Marketplace Fee
        marketplace_fee = sale_price * EBAY_FEE_PERCENTAGE

        # Net profit & margin calculations
        net_profit = round(sale_price - (true_cost + marketplace_fee), 2)
        margin = round((net_profit / sale_price) * 100, 1)

        # save the processed data into our storage list
        # Notice we convert lot back to int or keep as string depending on preference
        processed_inventory.append({
            "lot": int(row["lot"]),
            "title": row["title"],
            "true_cost": true_cost,
            "sale_price": sale_price,
            "net_profit": net_profit,
            "margin": margin
        })

# Display formatted profit summary table
print(f"{'LOT':<6} | {'ITEM TITLE':<38} | {'TRUE COST':<10} | {'SALE':<8} | {'PROFIT':<8} | {'MARGIN':<6}")
print("-" * 90)

for item in processed_inventory:
    print(f"{item['lot']:<6} | {item['title']:<38} | ${item['true_cost']:<9.2f} | ${item['sale_price']:<7.2f} | ${item['net_profit']:<7.2f} | {item['margin']:<5.1f}%")

print("=" * 90)
print(f"HIGH-POTENTIAL INVENTORY (margin >= {MINIMUM_MARGIN}%):")
print("=" * 90)
print(f"{'LOT':<6} | {'ITEM TITLE':<38} | {'TRUE COST':<10} | {'SALE':<8} | {'PROFIT':<8} | {'MARGIN':<6}")
print("-" * 90)

# Filter and display only the items that pass your business rule
for item in processed_inventory:
    if item["margin"] >= MINIMUM_MARGIN:
        actionable_bids.append(item) #CApture the winner into our action list
        print(f"{item['lot']:<6} | {item['title']:<38} | ${item['true_cost']:<9.2f} | ${item['sale_price']:<7.2f} | ${item['net_profit']:<7.2f} | {item['margin']:<5.1f}%")    

print("-" * 90)
print(f"Total items audited: {len(processed_inventory)}")
print(f"Total items cleared for action: {len(actionable_bids)}")

# Export actionable bids to a new CSV file for the next pipeline

output_filename = "actionable_bids.csv"
fieldnames = ["lot", "title", "true_cost", "sale_price", "net_profit", "margin"]

with open(output_filename, mode="w", newline="") as outfile:
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)

    # Write the column headers first
    writer.writeheader()

    # Write each winning item row-by-row
    for item in actionable_bids:
        writer.writerow(item)

print(f"\Succesfully exported {len(actionable_bids)} actionable bids to '{output_filename}'!")