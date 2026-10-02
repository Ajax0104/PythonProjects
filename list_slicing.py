# Script demonstrating list slicing, sub-list extraction, and top-n reporting

inventory = [
	"impact Driver",
	"Circular Saw",
	"Exhaust Fan",
	"Thermostat",
	"Pressure Washer",
	"Angle Grinder"
]

print("---Full Inventory Manifest ---")
print(f"Total Item: {len(inventory)}")
print(f"Items: {inventory}\n")

# 1. Basic Range Slice (index 1 up to index 4)

mid_tier = inventory[1:4]
print("--- Slice [1:4] (Items at index 1, 2, 3) ---")
print(f"Sub-list: {mid_tier}\n")

# 2. Extract First 3 Items

top_three = inventory[:3]
print("--- First 3 Items ---")
print(f"Top 3: {top_three}\n")

# 3. Extract Recent / Last 2 Items

recent_additions = inventory[-2:]
print("--- Last 2 Items [-2:] ---")
print(f"Recent: {recent_additions}\n")

# 4 Copying a List via Slicing [:]

inventory_backup = inventory[:]
print("--- Full List Copy [:] ---")
print(f"Backup matches original: {inventory_backup == inventory}")
