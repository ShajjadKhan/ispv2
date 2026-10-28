import sqlite3

conn = sqlite3.connect('/home/tserver/billing_reminder/bills.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

c = cur.execute("SELECT * FROM customers WHERE mobile LIKE '%0561380133%'").fetchone()
if c:
    print("Hasib in bills.db:", dict(c))
    cols = cur.execute("SELECT * FROM collections WHERE customer_id = ?", (c["id"],)).fetchall()
    print("Collections in bills.db count:", len(cols))
    for col in cols:
        print(" ", dict(col))
else:
    print("Hasib not found in bills.db")
