# Script demonstrating python ;ists, append(), len(), sum, and list iteration

pay_records = []

print("--- Pay Records Collector ---")
print("Enter pay amounts one by one. Type 'done' when finished.\n")

while True:
	user_input = input("Enter pay amount (or 'done'): ")

	if user_input.strip().lower() == "done":
		break

	pay = float(user_input)
	pay_records.append(pay)

print("\n--- Processing Recorded Pay ---")

# Guard clause checking if the list has any items
if len(pay_records) > 0:
	total = sum(pay_records)
	count = len(pay_records)
	average = total / count

	print(f"Total Entries Recorded: {count}")
	print(f"Total Pay: ${total:.2f}")
	print(f"Average Pay: ${average:.2f}\n")

	print("Itemized Entry Breakdown:")
	print("Index\t\tAmount")
	print("------------------------")

	# Iteration throuhj the list using a for loop
	for index, record in enumerate(pay_records, start=1):
		print(f"#{index}\t\t${record:.2f}")
else:
	print("No pay records entered.")
