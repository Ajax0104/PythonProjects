# A mock dataset containing clean data and corrupted real world-data
raw_maifest = [
    {"lot": "101", "item": "Power Drill", "bid": "25.00"},
    {"lot": "102", "item": "Band Saw", "bid": "N/A"},       # Corrupted: text
    {"lot": "103", "item": "Router", "bid": ""},            # Corrupted: empty
    {"lot": "104", "item": "Sander", "bid": "40.50"}
]

print("--- STARTING MANIFEST PROCESSING ---")

for row in raw_maifest:
    try:
        # Convert the string bid into float
        clean_bid = float(row["bid"])
        print(f"SUCCESS: Lot {row['lot']} ({row['item']}) parsed cleanly at ${clean_bid}")

    except ValueError:
        # Catch conversion failures gracefully
        print(f"SKIPPED: Lot {row['lot']} ({row['item']}) contains bad bid data: '{row['bid']}'")

print("--- PROCESSING COMPLETE ---")