import sqlite3
import os

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else 'isp_v2.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get customer list
cur.execute("""
    SELECT id, name, phone, billing_type, monthly_fee, due_date, expiry_date, credit_balance, status, billing_start_date, join_date
    FROM customers
    ORDER BY id DESC
""")
customers = cur.fetchall()
print(f"Total customers: {len(customers)}")

owing_with_future_expiry = []
for c in customers:
    bal = float(c["credit_balance"] or 0.0)
    exp = str(c["expiry_date"] or "")
    status = str(c["status"])
    if bal < 0 and exp > "2026-10-16" and status == "active":
        owing_with_future_expiry.append(dict(c))

print(f"Active customers with future expiry but NEGATIVE balance: {len(owing_with_future_expiry)}")
for c in owing_with_future_expiry[:15]:
    print(f"ID #{c['id']:<4} | {c['name']:<20} | Type: {c['billing_type']:<8} | Bal: {c['credit_balance']:>8.2f} SAR | Expiry: {c['expiry_date']} | Start: {c['billing_start_date']}")
