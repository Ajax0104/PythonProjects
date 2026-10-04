# Project 2: eBay Inventory, using actual crowe invoice & Profit Analyzer

#CR auction manifest items
#Format: "SKU-CATEGORY-ITEM_NAME|ESTIMATED_SALE_PRICE|ACQUISITION_COST|ESTIMATED_SHIP"

invoice_lots = [
    {
        "lot": 7934, 
        "title": "AQUASTG Sand Filter Pump 1/2 HP", 
        "bid": 24.00, 
        "premium": 3.60, 
        "tax": 1.66, 
        "projected_sale": 85.00
    },
    {
        "lot": 7949, 
        "title": "American Mahjong Tile Set", 
        "bid": 30.00, 
        "premium": 4.50, 
        "tax": 2.07, 
        "projected_sale": 95.00
    },
    {
        "lot": 8084, 
        "title": "Canon imagePROGRAF TC-21 Printer", 
        "bid": 150.00, 
        "premium": 22.50, 
        "tax": 10.35, 
        "projected_sale": 320.00
    }
]

# Constants
EBAY_FEE_PERCENTAGE = 0.1325 # ~13.25 eBay final value fee NOTE FOR GEMINI THIS FIGURE VARIES by category
MINIMUM_MARGIN = 35.0

print("=" * 90)
print("                     AUCTION INVOICE BATCH PROCESSOR                    ")
print("=" * 90)

# Storage List (To keep data in memory after the loop finishes)
processed_inventory = []
actionable_bids = []

# Processing Loop
for lot in invoice_lots:
    # True acquisition cost math
    true_cost = lot["bid"] + lot["premium"] + lot["tax"]
    
    # Marketplace fees
    marketplace_fee = lot["projected_sale"] * EBAY_FEE_PERCENTAGE
    
    # Net profit & margin calculations
    net_profit = lot["projected_sale"] - (true_cost + marketplace_fee)
    margin = (net_profit / lot["projected_sale"]) * 100
    
    # Save the processed data into our storage list
    processed_inventory.append({
        "lot": lot["lot"],
        "title": lot["title"],
        "true_cost": true_cost,
        "sale_price": lot["projected_sale"],
        "net_profit": net_profit,
        "margin": margin
    })

# Display formatted profit summary table
print(f"{'LOT':<6} | {'ITEM TITLE':<32} | {'TRUE COST':<10} | {'SALE':<8} | {'PROFIT':<8} | {'MARGIN':<6}")
print("-" * 90)

for item in processed_inventory:
    print(f"{item['lot']:<6} | {item['title']:<32} | ${item['true_cost']:<9.2f} | ${item['sale_price']:<7.2f} | ${item['net_profit']:<7.2f} | {item['margin']:<5.1f}%")

print("=" * 90)
print(f"HIGH-POTENTIAL INVENTORY (margin >= {MINIMUM_MARGIN}%):")
print("=" * 90)
print(f"{'LOT':<6} | {'ITEM TITLE':<32} | {'TRUE COST':<10} | {'SALE':<8} | {'PROFIT':<8} | {'MARGIN':<6}")
print("-" * 90)

# Filter and display only the items that pass your business rule
for item in processed_inventory:
    if item["margin"] >= MINIMUM_MARGIN:
        actionable_bids.append(item) #CApture the winner into our action list
        print(f"{item['lot']:<6} | {item['title']:<32} | ${item['true_cost']:<9.2f} | ${item['sale_price']:<7.2f} | ${item['net_profit']:<7.2f} | {item['margin']:<5.1f}%")    

print("-" * 90)
print(f"Total items audited: {len(processed_inventory)}")
print(f"Total items cleared for action: {len(actionable_bids)}")