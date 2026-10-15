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
        """Calculates total out-of-pocket acquisition cost."""
        return self.bid + self.premium + self.tax

    def calculate_net_profit(self):
        """Calculates true net profit after marketplace fees and shipping."""
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
        """Calculates margin percentage using internal net profit."""
        net_profit = self.calculate_net_profit()
        return round((net_profit / self.sales_price) * 100, 1)

    def calculate_max_bid(self, target_margin):
        """calculates maximum ceiling bid to achieve a target margin percentage"""
        target_net_profit = self.sales_price * (target_margin / 100.0)
        estimated_tax = self.sales_price * self.EFFECTIVE_TAX_RATE
        total_transaction_value = (
            self.sales_price + self.SHIPPING_COST + estimated_tax
        )
        marketplace_fee = total_transaction_value * self.EBAY_FEE_PERCENTAGE

        max_true_cost = (
            self.sales_price
            - target_net_profit
            - marketplace_fee
            - self.SHIPPING_COST
        )

        max_bid = max_true_cost - self.premium - self.tax
        # Ensure we don't return negative bids for unviable items
        return round(max(max_bid, 0.0), 2)