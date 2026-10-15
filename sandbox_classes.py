from lot_item import LotItem

# --- TEST DRIVE FOR DYNAMIC MAX-BID ENGINE ---
test_item = LotItem(
    lot_id="999",
    bid="0.00",  # Bid doesn't matter when calculating max allowable bid
    premium="2.50",
    tax="2.00",
    sale_price="60.00",
)

target = 35.0
max_allowed_bid = test_item.calculate_max_bid(target_margin=target)

print(f"Target Margin: {target}%")
print(f"Projected Sale Price: ${test_item.sales_price:.2f}")
print(f"Maximum Allowable Auction Bid: ${max_allowed_bid:.2f}")