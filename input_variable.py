#Assign variable for user first name, last name, hours worked, pay rate
#output user name and weekly earnings

first_name = input("what is your first name")
last_name = input("what is your last name")
hours_worked = float(input("how many hours did you work"))
hourly_rate = float(input("how many dollars an hour do you make, rounded to the nearest whole"))

#STUDY NOTE--- need understand how to do this as a float and perform math with the different saved variable.
#Imagine that an input for a number has to be wrote with an if statement that can properly store user in[ut to correct assignment

weekly_pay = hours_worked * hourly_rate

print("Your weekly pay check will be", weekly_pay, "before taxes")
