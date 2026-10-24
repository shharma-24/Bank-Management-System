import sqlite3
from datetime import datetime

DB_NAME = "bank.db"
TRANSFER_LIMIT = 20000

#  DATABASE SETUP 
def connect_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def setup_database(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0 CHECK(balance >= 0)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_number TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            transaction_date TEXT,
            FOREIGN KEY(account_number)
                REFERENCES accounts(account_number)
        )
    """)

    # Add date column if an older database does not have it.
    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(transactions)"
        )
    ]

    if "transaction_date" not in columns:
        conn.execute(
            "ALTER TABLE transactions ADD COLUMN transaction_date TEXT"
        )

    # Old transactions without dates cannot recover their original date.
    migration_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("""
        UPDATE transactions
        SET transaction_date = ?
        WHERE transaction_date IS NULL OR transaction_date = ''
    """, (migration_time,))

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_account
        ON transactions(account_number)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_transactions_date
        ON transactions(transaction_date)
    """)

    conn.commit()

def record_transaction(
    conn, account_number, transaction_type, amount, description
):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("""
        INSERT INTO transactions
        (
            account_number,
            transaction_type,
            amount,
            description,
            transaction_date
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        account_number,
        transaction_type,
        amount,
        description,
        now
    ))

# LINKED LIST 
class Node:
    def __init__(self, data):
        self.data = data
        self.next = None

class TransactionHistory:
    def __init__(self):
        self.head = None

    def add(self, data):
        new_node = Node(data)

        if self.head is None:
            self.head = new_node
            return

        current = self.head

        while current.next is not None:
            current = current.next

        current.next = new_node

    def show(self):
        current = self.head

        if current is None:
            print("No transactions found.")
            return

        while current:
            print_transaction(current.data)
            current = current.next

def print_transaction(row):
    print("-" * 55)
    print(f"Transaction ID : {row['id']}")
    print(
        f"Date & Time    : "
        f"{row['transaction_date'] or 'Not available'}"
    )
    print(f"Type           : {row['transaction_type']}")
    print(f"Amount         : Rs. {row['amount']:.2f}")
    print(f"Description    : {row['description'] or '-'}")

def fetch_transactions(
    conn,
    account_number,
    where="",
    params=(),
    order_by="transaction_date DESC, id DESC"
):
    query = f"""
        SELECT *
        FROM transactions
        WHERE account_number = ? {where}
        ORDER BY {order_by}
    """

    return conn.execute(
        query, (account_number, *params)
    ).fetchall()

def show_rows(rows):
    if not rows:
        print("No matching transactions found.")
        return

    for row in rows:
        print_transaction(row)

#  INPUT HELPERS 
def read_amount(prompt):
    try:
        amount = float(input(prompt))
        if amount <= 0:
            print("Amount must be greater than zero.")
            return None
        return round(amount, 2)

    except ValueError:
        print("Please enter a valid number.")
        return None

def valid_date(date_text):
    try:
        datetime.strptime(date_text, "%Y-%m-%d")
        return True
    except ValueError:
        return False

#  BANK ACCOUNT CLASS 
class BankAccount:
    def __init__(self, conn, name, account_number, balance=0.0):
        self.conn = conn
        self.name = name
        self.account_number = account_number
        self.balance = float(balance)

    @classmethod
    def load(cls, conn, account_number):
        row = conn.execute("""
            SELECT *
            FROM accounts
            WHERE account_number = ?
        """, (account_number,)).fetchone()

        if row is None:
            return None

        return cls(
            conn,
            row["name"],
            row["account_number"],
            row["balance"]
        )

    def refresh_balance(self):
        row = self.conn.execute("""
            SELECT balance
            FROM accounts
            WHERE account_number = ?
        """, (self.account_number,)).fetchone()

        if row:
            self.balance = float(row["balance"])

    def show_balance(self):
        self.refresh_balance()
        
        print("\n----- ACCOUNT DETAILS -----")
        print(f"Name           : {self.name}")
        print(f"Account Number : {self.account_number}")
        print(f"Balance        : Rs. {self.balance:.2f}")

    def deposit(self, amount):
        if amount <= 0:
            print("Amount must be greater than zero.")
            return

        try:
            with self.conn:
                self.conn.execute("""
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE account_number = ?
                """, (amount, self.account_number))

                record_transaction(
                    self.conn,
                    self.account_number,
                    "Deposit",
                    amount,
                    "Cash deposit"
                )

            self.refresh_balance()
            print(f"Rs. {amount:.2f} deposited successfully.")

        except sqlite3.Error as error:
            print("Deposit failed:", error)

    def withdraw(self, amount):
        if amount <= 0:
            print("Amount must be greater than zero.")
            return

        self.refresh_balance()

        if amount > self.balance:
            print("Insufficient balance.")
            return

        try:
            with self.conn:
                self.conn.execute("""
                    UPDATE accounts
                    SET balance = balance - ?
                    WHERE account_number = ?
                """, (amount, self.account_number))

                record_transaction(
                    self.conn,
                    self.account_number,
                    "Withdrawal",
                    amount,
                    "Cash withdrawal"
                )

            self.refresh_balance()
            print(f"Rs. {amount:.2f} withdrawn successfully.")

        except sqlite3.Error as error:
            print("Withdrawal failed:", error)

    def transfer_money(self, receiver_account_number, amount):
        if amount <= 0:
            print("Amount must be greater than zero.")
            return

        if amount > TRANSFER_LIMIT:
            print(
                f"Transfer limit is Rs. {TRANSFER_LIMIT:.2f} "
                "per transaction."
            )
            return

        if receiver_account_number == self.account_number:
            print("You cannot transfer money to your own account.")
            return

        self.refresh_balance()

        if amount > self.balance:
            print("Insufficient balance.")
            return

        receiver = self.conn.execute("""
            SELECT account_number
            FROM accounts
            WHERE account_number = ?
        """, (receiver_account_number,)).fetchone()

        if receiver is None:
            print("Receiver account not found.")
            return

        try:
            # Both account updates happen in one database transaction.
            self.conn.execute("BEGIN IMMEDIATE")

            self.conn.execute("""
                UPDATE accounts
                SET balance = balance - ?
                WHERE account_number = ?
            """, (amount, self.account_number))

            self.conn.execute("""
                UPDATE accounts
                SET balance = balance + ?
                WHERE account_number = ?
            """, (amount, receiver_account_number))

            record_transaction(
                self.conn,
                self.account_number,
                "Transfer",
                amount,
                f"Transferred to account {receiver_account_number}"
            )

            record_transaction(
                self.conn,
                receiver_account_number,
                "Received",
                amount,
                f"Received from account {self.account_number}"
            )

            self.conn.commit()
            self.refresh_balance()

            print(f"Rs. {amount:.2f} transferred successfully.")

        except sqlite3.Error as error:
            self.conn.rollback()
            print("Transfer failed; changes rolled back:", error)

    def transaction_history(self):
        rows = fetch_transactions(
            self.conn,
            self.account_number
        )

        linked_list = TransactionHistory()

        for row in rows:
            linked_list.add(row)

        linked_list.show()

    def search_by_date(self):
        date_text = input(
            "Enter date (YYYY-MM-DD): "
        ).strip()

        if not valid_date(date_text):
            print(
                "Invalid date. Use YYYY-MM-DD, "
                "for example 2026-10-20."
            )
            return

        rows = fetch_transactions(
            self.conn,
            self.account_number,
            "AND substr(transaction_date, 1, 10) = ?",
            (date_text,)
        )
        show_rows(rows)

    def filter_by_type(self):
        print(
            "\nTransaction types: "
            "Deposit, Withdrawal, Transfer, Received"
        )

        kind = input(
            "Enter transaction type: "
        ).strip().title()

        allowed = {
            "Deposit",
            "Withdrawal",
            "Transfer",
            "Received"
        }

        if kind not in allowed:
            print("Invalid transaction type.")
            return

        rows = fetch_transactions(
            self.conn,
            self.account_number,
            "AND transaction_type = ?",
            (kind,)
        )
        show_rows(rows)

    def sort_transactions(self):
        print("\n1. Newest first")
        print("2. Oldest first")
        print("3. Amount: low to high")
        print("4. Amount: high to low")

        choice = input("Choose sorting option: ").strip()

        orders = {
            "1": "transaction_date DESC, id DESC",
            "2": "transaction_date ASC, id ASC",
            "3": "amount ASC, id DESC",
            "4": "amount DESC, id DESC"
        }

        if choice not in orders:
            print("Invalid sorting option.")
            return

        rows = fetch_transactions(
            self.conn,
            self.account_number,
            order_by=orders[choice]
        )
        show_rows(rows)

    def search_by_date_range(self):
        start = input(
            "Start date (YYYY-MM-DD): "
        ).strip()

        end = input(
            "End date (YYYY-MM-DD): "
        ).strip()

        if not valid_date(start) or not valid_date(end):
            print("Invalid date. Use YYYY-MM-DD.")
            return

        if start > end:
            print("Start date cannot be after end date.")
            return

        rows = fetch_transactions(
            self.conn,
            self.account_number,
            "AND substr(transaction_date, 1, 10) BETWEEN ? AND ?",
            (start, end)
        )
        show_rows(rows)

#  CREATE ACCOUNT 
def create_account(conn):
    print("\n----- CREATE ACCOUNT -----")

    name = input("Enter full name: ").strip()
    account_number = input(
        "Choose an account number: "
    ).strip()

    if not name or not account_number:
        print("Name and account number cannot be empty.")
        return

    exists = conn.execute("""
        SELECT 1
        FROM accounts
        WHERE account_number = ?
    """, (account_number,)).fetchone()

    if exists:
        print("This account number already exists.")
        return

    initial_balance = input(
        "Initial deposit (press Enter for Rs. 0): "
    ).strip()

    if initial_balance == "":
        balance = 0.0
    else:
        try:
            balance = float(initial_balance)

            if balance < 0:
                print("Initial balance cannot be negative.")
                return

            balance = round(balance, 2)

        except ValueError:
            print("Please enter a valid amount.")
            return

    try:
        with conn:
            conn.execute("""
                INSERT INTO accounts
                (account_number, name, balance)
                VALUES (?, ?, ?)
            """, (account_number, name, balance))

            if balance > 0:
                record_transaction(
                    conn,
                    account_number,
                    "Deposit",
                    balance,
                    "Initial deposit"
                )

        print("Account created successfully!")
        print("Your account number is:", account_number)

    except sqlite3.Error as error:
        print("Could not create account:", error)

#  LOGIN 
def login(conn):
    account_number = input(
        "Enter account number: "
    ).strip()
    account = BankAccount.load(conn, account_number)

    if account is None:
        print(
            "Account not found. Please create an account first."
        )
        return

    print(f"Welcome, {account.name}!")
    account_menu(account)

#  ACCOUNT MENU 
def account_menu(account):
    while True:
        print("\n========== BANK MENU ==========")
        print("1. Show account details / balance")
        print("2. Deposit money")
        print("3. Withdraw money")
        print("4. Transfer money")
        print("5. View transaction history")
        print("6. Search transactions by specific date")
        print("7. Filter transactions by type")
        print("8. Sort transactions")
        print("9. Search transactions by date range")
        print("0. Logout")

        choice = input("Enter your choice: ").strip()

        if choice == "1":
            account.show_balance()

        elif choice == "2":
            amount = read_amount(
                "Enter deposit amount: Rs. "
            )
            if amount is not None:
                account.deposit(amount)

        elif choice == "3":
            amount = read_amount(
                "Enter withdrawal amount: Rs. "
            )
            if amount is not None:
                account.withdraw(amount)

        elif choice == "4":
            receiver = input(
                "Enter receiver account number: "
            ).strip()

            amount = read_amount(
                "Enter transfer amount: Rs. "
            )
            if amount is not None:
                account.transfer_money(receiver, amount)

        elif choice == "5":
            account.transaction_history()
        elif choice == "6":
            account.search_by_date()
        elif choice == "7":
            account.filter_by_type()
        elif choice == "8":
            account.sort_transactions()
        elif choice == "9":
            account.search_by_date_range()
        elif choice == "0":
            print("Logged out successfully.")
            break
        else:
            print("Invalid choice. Please try again.")

#  MAIN PROGRAM 
def main():
    conn = None

    try:
        conn = connect_db()
        setup_database(conn)

        while True:
            print("\n======= BANK MANAGEMENT SYSTEM =======")
            print("1. Create new account")
            print("2. Login to account")
            print("0. Exit")

            choice = input("Enter your choice: ").strip()

            if choice == "1":
                create_account(conn)
            elif choice == "2":
                login(conn)
            elif choice == "0":
                print(
                    "Thank you for using Bank Management System!"
                )
                break
            else:
                print("Invalid choice. Please try again.")

    except sqlite3.Error as error:
        print("Database error:", error)

    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    main()