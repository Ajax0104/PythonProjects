from lot_item import LotItem

class Manifest:
    """Container class that manages a collection of LotItem objects"""

    def __init__(self, manifest_name="Auction Batch"):
        self.manifest_name = manifest_name
        self.items = [] # Holds LotItem instances

    def add_item(self, lot_item):
        """Appends a LotItem object to the manifest collection."""
        if isinstance(lot_item, LotItem):
            self.items.append(lot_item)
        else:
            raise TypeError("Only LotItem instances can be added to Manifest.")

    def get_viable_lots(self, target_margin=35.0):
        """Returns lots where the max allowable bid meets or exceeds the current bid."""
        return [
            item 
            for item in self.items 
            if item.max_bid >= item.bid
        ]

    def total_required_capital(self):
        """Calculates total out-of-pocket cash required for all items at current bids."""
        # MODIFIED: Replaced method call calculate_true_cost() with property item.true_cost
        return round(sum(item.true_cost for item in self.items), 2)

    def total_projected_profit(self):
        """Calculates total net profit across all items in the manifest at current bids."""
        # MODIFIED: Uses property item.net_profit directly
        return round(sum(item.net_profit for item in self.items), 2)