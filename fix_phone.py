import sqlite3

account_number = input("Enter your account number: ")
new_phone = input("Enter your correct 10-digit phone number: ")

if len(new_phone) != 10 or not new_phone.isdigit():
    print("Invalid phone number. It must be exactly 10 digits.")
else:
    connection = sqlite3.connect("smartbank.db")

    connection.execute(
        "UPDATE users SET phone = ? WHERE account_number = ?",
        (new_phone, account_number)
    )

    connection.commit()
    connection.close()

    print("Phone number updated successfully.")
    import sqlite3

account_number = "SB100001"
new_phone = "8349693510"

connection = sqlite3.connect("smartbank.db")

connection.execute(
    "UPDATE users SET phone = ? WHERE account_number = ?",
    (new_phone, account_number)
)

connection.commit()
connection.close()

print("Phone number updated successfully for", account_number)