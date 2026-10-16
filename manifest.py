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

    def get_profitable_items(self, minimum_margin=35.0):
        """Returns a list of LotItem objects meeting or exceeding the margin gatekeeper""" #with the changes we are making we wont have a margin gatekeeper because the user sets the limit and the max bid is produced we will have to add weighted formula if the item is expense and returns good amount with low margin gate keep only low returns at high margins
        return [item for item in self.items if item.calculate_margin() >= minimum_margin]

    def total_required_capital(self): #later we need to have max capital input and for auction an optional time expiring weighting for order of ending lots
        """Calculates total cash required to purchase all items at current bids."""
        return round(sum(item.calculate_net_profit() for item in self.items), 2)

    def total_projected_profit(self):
        """Calculates total net profit across all items in the manifest."""
        return round(sum(item.calculate_net_profit() for item in self.items), 2)