import sqlite3
from datetime import date

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today_str = date.today().strftime('%Y-%m-%d')
print("Today:", today_str)

cur.execute("SELECT count(*) FROM customers WHERE status = 'active' AND (expiry_date >= ? OR due_date >= ?)", (today_str, today_str))
active_unexpired = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM customers WHERE status = 'active' AND (expiry_date < ? AND (due_date IS NULL OR due_date < ?))", (today_str, today_str))
active_expired = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM customers WHERE status = 'suspended'")
suspended_count = cur.fetchone()[0]

print(f"Active unexpired: {active_unexpired}")
print(f"Active expired (due/overdue): {active_expired}")
print(f"Suspended: {suspended_count}")

# Check the expired ones
cur.execute("SELECT id, name, phone, due_date, expiry_date, credit_balance, status FROM customers WHERE expiry_date < ? AND (due_date IS NULL OR due_date < ?)", (today_str, today_str))
print("\nExpired customers:")
for r in cur.fetchall():
    print(" ", dict(r))
