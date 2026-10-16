from lot_item import LotItem
from manifest import Manifest

# Initialize container
batch = Manifest("Crowe Owosso Manifest #42")

# Instantiate items
item1 = LotItem(lot_id="101", bid="25.00", premium="2.50", tax="2.00", sale_price="120.00")
item2 = LotItem(lot_id="102", bid="45.00", premium="4.50", tax="3.60", sale_price="60.00")  # Low margin

# Add items to manifest container
batch.add_item(item1)
batch.add_item(item2)

print(f"--- {batch.manifest_name} Summary ---")
print(f"Total Items Ingested: {len(batch.items)}")
print(f"Total Capital Required: ${batch.total_required_capital():.2f}")
print(f"Total Projected Net Profit: ${batch.total_projected_profit():.2f}")

winners = batch.get_profitable_items(minimum_margin=35.0)
print(f"Profitable Winners (>= 35% Margin): {len(winners)}")
for win in winners:
    print(f"  -> Lot {win.lot_id}: Margin {win.calculate_margin()}% | Max Bid: ${win.calculate_max_bid(35.0):.2f}")