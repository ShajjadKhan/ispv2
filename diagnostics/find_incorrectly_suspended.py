import sqlite3
from datetime import datetime

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today_str = datetime.now().strftime("%Y-%m-%d")
print(f"Today is: {today_str}")

# Find any customer where due_date >= today OR expiry_date >= today but status is suspended
cur.execute("""
    SELECT id, name, phone, status, expiry_date, due_date, credit_balance
    FROM customers
    WHERE (due_date >= ? OR expiry_date >= ?)
      AND status = 'suspended'
""", (today_str, today_str))
rows = cur.fetchall()
print(f"\nCustomers with future date but status='suspended': {len(rows)}")
for r in rows:
    print(" ", dict(r))

# Find any customer where devices are blocked but customer has future date
cur.execute("""
    SELECT cd.id as dev_id, cd.mac_address, cd.status as dev_status, c.id as cust_id, c.name, c.status as cust_status, c.expiry_date, c.due_date
    FROM customer_devices cd
    JOIN customers c ON cd.customer_id = c.id
    WHERE (c.due_date >= ? OR c.expiry_date >= ?)
      AND cd.status = 'blocked'
""", (today_str, today_str))
dev_rows = cur.fetchall()
print(f"\nBlocked devices under customers with future date: {len(dev_rows)}")
for d in dev_rows:
    print(" ", dict(d))

conn.close()
