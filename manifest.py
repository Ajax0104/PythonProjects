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
            if item.calculate_max_bid(target_margin) >= item.bid
        ]

    def total_required_capital(self): 
        """Calculates total cash required to purchase all items at current bids."""
        return round(sum(item.calculate_true_cost() for item in self.items), 2)

    def total_projected_profit(self):
        """Calculates total net profit across all items at current bids."""
        return round(sum(item.calculate_net_profit() for item in self.items), 2)