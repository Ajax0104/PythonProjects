class LotItem:

    def __init__(
        self,
        sale_price: float,
        shipping_cost: float = 0.0,
        is_free_shipping: bool = True,
        target_margin: float = 0.35,  # Kept at 35% default
        market_fee_pct: float = 0.1325,  # Standard eBay base fee (13.25%)
        ad_fee_pct: float = 0.02,  # Promoted listing rate (2.0%)
        buyer_premium_pct: float = 0.15,  # Crowe/Auction Buyer Premium (15%)
        sales_tax_pct: float = 0.06,  # Michigan Sales Tax (6%)
    ):
        self.sale_price = sale_price
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