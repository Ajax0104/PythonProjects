#Script demonstrating if / elif / else multi-branch logic

name = input("Enter employee name: ")
base_pay = float(input("enter base weekly pay: "))
rating = int(input("Enter performance rating (1-5): "))

if rating == 5:
	bonus_percentage = 0.20 # 20% bonus
elif rating == 4:
	bonus_percentage = 0.10 # 10% bonus
elif rating == 3:
	bonus_percentage = 0.05 # 5% bonus
elif rating == 2 or rating == 1:
	bonus_percentage = 0.00 # no bonus
else:
	bonus_percentage = 0.00
	print("Invalid rating entered. Defaulting bonus to 0%.")

bonus_amount = base_pay * bonus_percentage
total_payout = base_pay + bonus_amount

print(f'\n--- Pay Summary for {name} ---')
print(f'Base Pay: ${base_pay:.2f}')
print(f"Bonus ({bonus_percentage * 100}%): ${bonus_amount:.2f}")
print(f"Total Payout: ${total_payout:.2f}")
