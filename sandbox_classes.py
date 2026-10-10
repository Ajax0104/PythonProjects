class LotItem: #never tell me to copy paste code unless it is something i shouldnt be learning at the moment
    """blueprint for individual auction lots.""" 

    #Class Constants (shared across every LotItem object created)
    EBAY_FEE_PERCENTAGE = 0.1325
    SHIPPING_COST = 16.50
    EFFECTIVE_TAX_RATE = 0.08

    def __init__(self, lot_id, bid, premium, tax, sale_price):
        # __init__ runs automattically when a new object is created
        self.lot_id = lot_id 
        self.bid = float(bid)
        self.premium = float(premium)
        self.tax = float(tax)
        self.sale_price = float(sale_price)

    def calculate_true_cost(self):
        """Calculates total acquisition cost (bid + buyer's premium + sales tax)."""
        return self.bid + self.premium + self.tax

    def calculate_net_profit(self): 
        """Calculates true net profit after eBay fees and shipping expenses"""
        true_cost = self.calculate_true_cost()
        estimated_tax = self.sale_price * self.EFFECTIVE_TAX_RATE
        total_transaction_value = self.sale_price + self.SHIPPING_COST + estimated_tax
        marketplace_fee = total_transaction_value * self.EBAY_FEE_PERCENTAGE

        return round(self.sale_price - (true_cost + marketplace_fee + self.SHIPPING_COST), 2)

    def calculate_margin(self):
        """Calculates margin percentage using real net profit."""
        net_profit = self.calculate_net_profit()
        return round((net_profit / self.sale_price) * 100, 1)

# --- TEST Drive ---
lot_a = LotItem(lot_id="101", bid="25.00", premium="2.50", tax="2.00", sale_price="60.00")

print(f"Lot Identifier: {lot_a.lot_id}")
print(f"Calculated true Cost: ${lot_a.calculate_true_cost():.2f}")
print(f"Real Net Profit: ${lot_a.calculate_net_profit():.2f}")
print(f"Calculated Margin: {lot_a.calculate_margin():.1f}%")