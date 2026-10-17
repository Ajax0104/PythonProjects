from lot_item import LotItem

# Item with $100 sale price, $10 current bid, quantity 1
item = LotItem(
    lot_id="8800", bid="10.00", sale_price="100.00", quantity=1
)

print(f"True Cost: ${item.calculate_true_cost():.2f}")  # Should return $12.19
print(f"Net Profit: ${item.calculate_net_profit():.2f}")
print(f"Max Bid for 35% Margin: ${item.calculate_max_bid(35.0):.2f}")