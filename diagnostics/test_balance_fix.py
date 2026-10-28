import sqlite3
from datetime import date, datetime
import calendar

conn = sqlite3.connect('/home/sk/isp_v2/test_merge.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today = date.today()
today_str = today.strftime('%Y-%m-%d')

# Let's inspect all customers
cur.execute("SELECT id, name, monthly_fee, billing_start_date, status, credit_balance, billing_type, expiry_date, due_date FROM customers")
custs = cur.fetchall()

print(f"Total customers: {len(custs)}")

# Check collections
cur.execute("SELECT customer_id, coalesce(sum(amount + coalesce(waived_amount, 0)), 0) FROM collections GROUP BY customer_id")
colls = dict(cur.fetchall())

sample_checks = []
for c in custs:
    cid = c["id"]
    fee = float(c["monthly_fee"] or 0.0)
    exp_str = c["expiry_date"] or c["due_date"] or today_str
    try:
        exp_d = datetime.strptime(str(exp_str)[:10], "%Y-%m-%d").date()
    except Exception:
        exp_d = today

    paid = float(colls.get(cid, 0.0))
    days_rem = (exp_d - today).days

    # Evaluation
    # If today <= exp_d: customer is within valid subscription period.
    # No mid-month daily debt for unexpired days.
    # Any surplus credit (paid > accrued) is preserved.
    # Negative balance is only possible if today > exp_d (expired past due).
    is_unexpired = (today <= exp_d)
    
    sample_checks.append((cid, c["name"], exp_str, days_rem, is_unexpired, c["credit_balance"]))

print(f"Unexpired customers: {sum(1 for s in sample_checks if s[4])}")
print(f"Expired customers:   {sum(1 for s in sample_checks if not s[4])}")

for s in sample_checks[:15]:
    print(f"#{s[0]:<3} {s[1]:<22} | Exp: {s[2]} ({s[3]:>3}d left) | Unexpired: {s[4]} | Current CB: {s[5]}")

conn.close()
