class LotItem:

    def __init__(
        self,
        sale_price: float,
        lot_id: str = "",
        title: str = "",
        bid: float = 0.0,
        shipping_cost: float = 0.0,
        is_free_shipping: bool = True,
        target_margin: float = 0.35,
        market_fee_pct: float = 0.1325,
        ad_fee_pct: float = 0.02,
        buyer_premium_pct: float = 0.15,
        sales_tax_pct: float = 0.06,
    ):
        self.sale_price = sale_price
        self.lot_id = lot_id
        self.title = title
        self.bid = bid
        self.shipping_cost = shipping_cost
        self.is_free_shipping = is_free_shipping
        self.target_margin = target_margin
        self.market_fee_pct = market_fee_pct
        self.ad_fee_pct = ad_fee_pct
        self.buyer_premium_pct = buyer_premium_pct
        self.sales_tax_pct = sales_tax_pct

    @property
    def total_fee_pct(self) -> float:
        """Combined selling fee percentage (Market Fee + Promoted Ad Fee)."""
        return self.market_fee_pct + self.ad_fee_pct

    @property
    def true_value(self) -> float:
        """Calculates True Value (TV): Net resale proceeds after platform fees

        and outbound shipping expenses.
        """
        fees = self.sale_price * self.total_fee_pct
        if self.is_free_shipping:
            return self.sale_price - fees - self.shipping_cost
        return self.sale_price - fees

    @property
    def true_cost(self) -> float:
        """Total out-of-pocket cash required at current bid (Bid x 1.15 x 1.06)."""
        multiplier = (1.0 + self.buyer_premium_pct) * (
            1.0 + self.sales_tax_pct
        )
        return round(self.bid * multiplier, 2)

    @property
    def max_acquisition_cost(self) -> float:
        """Calculates Max Acquisition Cost (MAC): MAC = TV * (1 - Margin)."""
        if self.true_value <= 0:
            return 0.0
        return self.true_value * (1.0 - self.target_margin)

    @property
    def max_bid(self) -> float:
        """Calculates Max Hammer Bid (MB).

        Accounts for Buyer's Premium (P) and Sales Tax (TP) applied to (MB + P):
        MAC = MB * (1 + Premium) * (1 + Tax) -> MB = MAC / [(1 + Premium) * (1 + Tax)]
        """
        if self.max_acquisition_cost <= 0:
            return 0.0

        acquisition_multiplier = (1.0 + self.buyer_premium_pct) * (
            1.0 + self.sales_tax_pct
        )
        return round(self.max_acquisition_cost / acquisition_multiplier, 2)

    @property
    def net_profit(self) -> float:
        """Calculates projected net profit at current bid (True Value - True Cost)."""
        return round(self.true_value - self.true_cost, 2)

    def to_dict(self, target_margin: float = None) -> dict:
        """Converts internal lot attributes and calculated metrics directly into a

        clean dictionary for CSV export.
        """
        margin = (
            target_margin
            if target_margin is not None
            else getattr(self, "target_margin", 0.35)
        )

        return {
            "lot": getattr(self, "lot_id", ""),
            "title": getattr(self, "title", ""),
            "current_bid": getattr(self, "bid", 0.0),
            "max_allowable_bid": self.max_bid,
            "projected_sale": self.sale_price,
            "net_profit": round(
                self.true_value - self.max_acquisition_cost, 2
            ),
            "margin": margin,
        }
    
# =====================================================================
# STANDALONE SANITY TEST (Runs only when executing this file directly)
# =====================================================================
if __name__ == "__main__":
    print("--- TESTING LOT_ITEM_V2 MATHEMATICAL MODEL ---")

    # Example: $100 Market Floor, 35% Target Margin, 15% Premium, 6% Tax
    test_item = LotItem(
        sale_price=100.00,
        shipping_cost=0.0,
        is_free_shipping=True,
        target_margin=0.35,
        buyer_premium_pct=0.15,
        sales_tax_pct=0.06,
    )

    print(f"Sales Price (SP)         : ${test_item.sale_price:.2f}")
    print(
        f"Total Fee % (13.25%+2%)   : {test_item.total_fee_pct*100:.2f}% (${test_item.sale_price * test_item.total_fee_pct:.2f})"
    )
    print(f"True Value (TV)           : ${test_item.true_value:.2f}")
    print(
        f"Target Margin (M)         : {test_item.target_margin*100:.0f}% (${test_item.true_value * test_item.target_margin:.2f})"
    )
    print(
        f"Max Acquisition Cost (MAC): ${test_item.max_acquisition_cost:.2f}"
    )
    print(f"Calculated Max Bid (MB)   : ${test_item.max_bid:.2f}")

    # Reverse Verification
    mb = test_item.max_bid
    premium = mb * test_item.buyer_premium_pct
    tax = (mb + premium) * test_item.sales_tax_pct
    total_out_of_pocket = mb + premium + tax

    print("\n--- REVERSE OUT-OF-POCKET VERIFICATION ---")
    print(f"Hammer Bid               : ${mb:.2f}")
    print(f"+ 15% Buyer Premium      : ${premium:.2f}")
    print(f"+ 6% Sales Tax on (MB+P) : ${tax:.2f}")
    print(f"= Total Out-of-Pocket    : ${total_out_of_pocket:.2f}")
    print(
        f"Target MAC Target        : ${test_item.max_acquisition_cost:.2f} (Difference: ${abs(total_out_of_pocket - test_item.max_acquisition_cost):.2f})"
    )