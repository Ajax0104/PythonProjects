# Slicing and Formatting Practice

inventory = [
    "FAN-6001-BATH",
    "FAN-6002-BATH",
    "PUMP-301-HYDRONIC",
    "VALVE-102-COPPER",
    "FAN-6003-BATH"
]

print("--- Inventory Summary ---")

# Extract category codes (first 3 Letter) using slicing
for item in inventory:
   category = item[:3]        # Slice first 3 Characters
   item_id = item[4:8]        # Slice middle ID number

   print(f"category: {category} | ID: {item_id} | Full Code: {item}")

# Quick Slice challenge: Grab only the last 3 items in the list

recent_items = inventory[-3:]
print(f"\nLast 3 iitems added: {recent_items}")