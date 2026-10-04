# Project 1: eBay Imvemtory & Profit Analyzer

#Simulated raw auction manifest items
#Format: "SKU-CATEGORY-ITEM_NAME|ESTIMATED_SALE_PRICE|ACQUISITION_COST|ESTIMATED_SHIP"

raw_manifest = [
    "FAN-BATH-Panasonic Whisper Ceiling Fan|85.00|18.50|12.00",
    "PUMP-HYDRONIC-Taco Circulator Pump 1/8HP|145.00|32.00|15.50",
    "VALVE-COPPER-Sweat Ball Valve 3/4in 5-Pack|42.00|8.00|7.25",
    "EXHAUST-VENT-Broan-NuTone Vent Hood|110.00|25.00|18.00",
    "TOOL-POWER-Milwaukee M18 Fuel Drill|130.00|45.00|11.00"
]

EBAY_FEE_PERCENTAGE = 0.1325 # ~13.25 eBay final value fee
parsed_inventory = []

print("=" * 80)
print("                     EBAY INVENTORY PROFIT ANALYZER                    ")
print("=" * 80)

for line in raw_manifest:
    # First split: Separate SKU structure from financial numbers using '|'
    sku_part, sale_price, buy_cost, shipping_cost = line.split("|")

    #convert financial strings to floats for math
    sale_price = float(sale_price)
    buy_cost = float(buy_cost)
    shipping_cost = float(shipping_cost)

    # Second split: Parse SKU code into Prefix, Category, and Item Name
    prefix, category, item_name = sku_part.split("-", 2) # Max 2 splits so item_name stays intact

    #Profit Calculation Logic
    ebay_fee = sale_price * EBAY_FEE_PERCENTAGE
    total_cost = buy_cost + shipping_cost + ebay_fee
    net_profit = sale_price - total_cost
    margin = (net_profit / sale_price) * 100

    # Save record to list of Dictionaries
    parsed_inventory.append({
        "sku_prefix": prefix,
        "category": category,
        "name": item_name,
        "sale_price": sale_price,
        "buy_cost": buy_cost,
        "net_profit": net_profit,
        "margin": margin
    })

# Display formatted profit summary table
print(f"{'ITEM NAME':<35} | {'SALE':<8} | {'COST':<8} | {'PROFIT':<8} | {'MARGIN':<6}")
print("-" * 80)

for item in parsed_inventory:
    print(f"{item['name']:<35} | ${item['sale_price']:<7.2f} | ${item['buy_cost']:<7.2f} | ${item['net_profit']:<7.2f} | {item['margin']:<5.2f}%")

print("=" * 80)