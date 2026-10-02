#Script demonstrating a sentinel-controlled while loop with average calculation and zero protection

total_pay = 0.0
count = 0

print("--- Pay Roll Tracker ---")
print("Enter pay amounts one by one. Type 'done' when finished.\n")

while True:
	user_input = input("Enter pay amount (or 'done'): ")

	# check if user wants to stop and clean white space
	if user_input.strip().lower() == "done":
		break # ends loop

	# Process the entry
	pay = float(user_input)
	total_pay = total_pay + pay  #Accumulate total
	count = count +1             #track number of entries made

print("\n--- Sumary ---")
print(f"total Entries: {count}")
print(f"total Pay: ${total_pay:.2f}")

# Guard clause to prevent dividing by zero if no enties were added
if count > 0:
	average_pay = total_pay / count
	print(f"Average Pay: ${average_pay:.2f}")
else:
	print("average Pay: N/A (No entries recorded)")
