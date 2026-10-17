# --- ZONE 1: class definition ---
class LotItem:
    """Blueprint for individual auction lots with internal financial math.""" 

    EBAY_FEE_PERCENTAGE = 0.1325
    SHIPPING_COST = 16.50
    EFFECTIVE_TAX_RATE = 0.08

    BUYER_PREMIUM_RATE = 0.15 # 15% Crowe Premium
    AUCTION_TAX_RATE = 0.06  # 6% MI Sales Tax

    def __init__(self, lot_id, bid, sale_price, quantity=1, title="", description=""):
        self.lot_id = lot_id
        self.bid = float(bid)
        self.sales_price = float(sale_price)
        self.quantity = int(quantity)
        self.title = title
        self.description = description
    @property
    def premium(self):
        """Calculates buyer's premium based on current bid."""
        return round(self.bid * self.BUYER_PREMIUM_RATE, 2)

    @property
    def tax(self):
        """Calculates auction sales tax on (bid + premium)."""
        return round((self.bid + self.premium) * self.AUCTION_TAX_RATE, 2)

    def calculate_true_cost(self, custom_bid=None):
        """Calculates total acquisition cost using bid x 1.15 x 1.06."""
        eval_bid = float(custom_bid) if custom_bid is not None else self.bid
        return round(eval_bid * (1 + self.BUYER_PREMIUM_RATE) * (1 + self.AUCTION_TAX_RATE), 2)

    def calculate_net_profit(self):
        """Calculates true net profit after marketplace fees and shipping."""
        true_cost = self.calculate_true_cost()
        gross_sale = self.sales_price * self.quantity
        estimated_tax = gross_sale * self.EFFECTIVE_TAX_RATE
        total_transaction_value = (
            gross_sale + self.SHIPPING_COST + estimated_tax
        )
        marketplace_fee = total_transaction_value * self.EBAY_FEE_PERCENTAGE

        return round(
            gross_sale - (true_cost + marketplace_fee + self.SHIPPING_COST), 2
        )

    def calculate_margin(self):
        """Calculates margin percentage using internal net profit."""
        gross_sale = self.sales_price * self.quantity
        if gross_sale == 0:
            return 0.0
        return round((self.calculate_net_profit() / gross_sale) * 100, 1)
    
    def calculate_max_bid(self, target_margin=35.0):
        """Reverse calculates max allowable bid considering premium and tax multiplier (1.219)."""
        gross_sale = self.sales_price * self.quantity
        target_net_profit = gross_sale * (target_margin / 100.0)
        estimated_tax = gross_sale * self.EFFECTIVE_TAX_RATE
        total_transaction_value = gross_sale + self.SHIPPING_COST + estimated_tax
        marketplace_fee = total_transaction_value * self.EBAY_FEE_PERCENTAGE

        max_true_cost = (
            gross_sale - target_net_profit - marketplace_fee - self.SHIPPING_COST
        )

        # Reverse multiplier: max_true_cost / (1 + premium_rate) / (1 + tax_rate)
        max_bid = max_true_cost / (1 + self.BUYER_PREMIUM_RATE) / (1 + self.AUCTION_TAX_RATE)
        return round(max(max_bid, 0.0), 2)