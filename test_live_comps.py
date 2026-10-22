from ebay_comp_scraper import fetch_ebay_sold_median, fetch_ebay_sold_prices

# Specific target lots from manifest
TARGET_LOTS = [
    {
        "lot": "8158",
        "title": "Right Passenger Running Board Motor 2021-25",
        "bid": "2.00",
    },
    {
        "lot": "8159",
        "title": "Fridge Freezer Door Gasket for Whirlpool/Kenmore",
        "bid": "2.00",
    },
    {
        "lot": "8160",
        "title": "Black Stick-On Wall Headboard - 6-Piece Queen",
        "bid": "2.00",
    },
    {
        "lot": "8161",
        "title": "Sakugi 5-Tier Storage Shelves, Heavy Duty Black",
        "bid": "16.00",
    },
    {
        "lot": "8162",
        "title": "Impala Rear Driver Power Window Regulator (2 Pins)",
        "bid": "2.00",
    },
    {
        "lot": "8163",
        "title": "Ultrasonic Tooth/Retainer Cleaner 45kHz 200ml",
        "bid": "6.00",
    },
]


def run_targeted_spot_check():
    print("--- TARGETED MANIFEST LOTS SPOT CHECK ---\n")

    for item in TARGET_LOTS:
        lot_id = item["lot"]
        title = item["title"]
        bid = item["bid"]

        prices = fetch_ebay_sold_prices(title)
        median_price = fetch_ebay_sold_median(title)

        print(f"Lot #{lot_id}")
        print(f"  Title      : {title}")
        print(f"  Current Bid: ${bid}")
        print(f"  Raw Prices : {prices}")
        if median_price:
            print(f"  LIVE MEDIAN: ${median_price:.2f}")
        else:
            print(f"  LIVE MEDIAN: No Match Found")
        print("-" * 65)


if __name__ == "__main__":
    run_targeted_spot_check()