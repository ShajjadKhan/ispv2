import sqlite3
import os

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else 'isp_v2.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check how many collections exist
cur.execute("SELECT count(*), sum(amount) FROM collections")
cnt, total = cur.fetchone()
print(f"Collections total records: {cnt}, total amount: {total} SAR")

# Check customers breakdown
cur.execute("""
    SELECT 
        billing_type,
        count(*) as total_custs,
        sum(case when credit_balance < 0 then 1 else 0 end) as negative_bal_custs,
        sum(case when credit_balance > 0 then 1 else 0 end) as positive_bal_custs,
        sum(case when credit_balance = 0 then 1 else 0 end) as zero_bal_custs
    FROM customers
    GROUP BY billing_type
""")
for r in cur.fetchall():
    print(dict(r))

# Check samples of customers with negative balance
cur.execute("""
    SELECT id, name, phone, billing_type, monthly_fee, due_date, expiry_date, credit_balance, status, billing_start_date
    FROM customers
    WHERE credit_balance < 0
    ORDER BY credit_balance ASC
    LIMIT 10
""")
print("\nMost negative balances:")
for r in cur.fetchall():
    print(dict(r))
