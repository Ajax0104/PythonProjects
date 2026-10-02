# script demonstrating a for loop with step intervals and tabbed formatting

rate = float(input("Enter hourly pay rate: "))

print("\nHours\t\tGross Pay")
print("-------------------------")

# range(start, stop, step) -> starts at 10, stops before 41, increments by 10
for hours in range(10, 41, 10):
	pay = hours * rate
	print(f"{hours}\t\t${pay:.2f}")
