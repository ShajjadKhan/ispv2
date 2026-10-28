import sqlite3
import sys
sys.path.insert(0, '/home/sk/isp_v2')

# Connect to test_merge.db
conn = sqlite3.connect('/home/sk/isp_v2/test_merge.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check collections count
cur.execute("SELECT count(*), coalesce(sum(amount), 0) FROM collections")
print("test_merge.db collections:", cur.fetchone())

# Now simulate updating credit_balance for all customers in test_merge.db with the unexpired guard
cur.execute("SELECT id, expiry_date, due_date, credit_balance, status FROM customers WHERE status != 'deleted'")
custs = cur.fetchall()

from datetime import date, datetime
today = date.today()

updates = []
for c in custs:
    exp_str = c["expiry_date"] or c["due_date"]
    cb = float(c["credit_balance"] or 0.0)
    if exp_str:
        try:
            exp_d = datetime.strptime(str(exp_str)[:10], "%Y-%m-%d").date()
            if today <= exp_d and cb < 0:
                updates.append((0.0, c["id"]))
        except Exception:
            pass

print(f"Total customers whose negative balance was resolved because subscription is active & unexpired: {len(updates)}")
cur.executemany("UPDATE customers SET credit_balance = ? WHERE id = ?", updates)
conn.commit()

# Now check how many negative balances remain
cur.execute("SELECT count(*) FROM customers WHERE credit_balance < 0")
neg_rem = cur.fetchone()[0]
print(f"Remaining negative balance accounts: {neg_rem}")

cur.execute("SELECT count(*) FROM customers WHERE credit_balance = 0")
settled_cnt = cur.fetchone()[0]
print(f"Settled accounts (0.00 SAR): {settled_cnt}")

cur.execute("SELECT count(*) FROM customers WHERE credit_balance > 0")
credit_cnt = cur.fetchone()[0]
print(f"Surplus credit accounts (> 0.00 SAR): {credit_cnt}")

# Check the Priority / Due queue in get_dashboard_metrics logic
cur.execute("""
    SELECT count(*) FROM customers 
    WHERE status = 'active' 
      AND ((expiry_date IS NOT NULL AND expiry_date <= date('now', '+3 days')) 
           OR (due_date IS NOT NULL AND due_date <= date('now', '+3 days')))
""")
due_3d = cur.fetchone()[0]
print(f"Accounts due in next 3 days: {due_3d}")

conn.close()
