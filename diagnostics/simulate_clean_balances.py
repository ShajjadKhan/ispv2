import sqlite3
from datetime import date, datetime, timedelta
import calendar

conn = sqlite3.connect('/home/sk/isp_v2/test_merge.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

today = date.today()
today_str = today.strftime('%Y-%m-%d')

cur.execute("""
    SELECT id, name, phone, billing_type, monthly_fee, due_date, expiry_date, credit_balance, status, billing_start_date, join_date
    FROM customers
    ORDER BY id DESC
""")
customers = cur.fetchall()

print(f"Simulating balance resolution for {len(customers)} customers on {today_str}:")

# Let's inspect how many collections exist per customer in test_merge.db
cur.execute("SELECT customer_id, sum(amount) FROM collections GROUP BY customer_id")
colls_by_cust = dict(cur.fetchall())

results = []
for c in customers:
    cid = c["id"]
    fee = float(c["monthly_fee"] or 0.0)
    exp_str = c["expiry_date"] or c["due_date"] or today_str
    try:
        exp_d = datetime.strptime(str(exp_str)[:10], "%Y-%m-%d").date()
    except Exception:
        exp_d = today

    status = (c["status"] or "active").strip().lower()
    days_rem = (exp_d - today).days

    # In a proper subscription model:
    # 1. If customer is active and expiry_date >= today:
    #    Their subscription is running and valid until expiry_date.
    #    Days remaining = days_rem >= 0.
    #    Current cycle is covered.
    # 2. If expiry_date < today:
    #    Account is expired by abs(days_rem) days.
    #    Debt accrues for the days active past expiry.
    # 3. Any extra payments deposited into credit_balance are preserved.
    
    current_stored_bal = float(c["credit_balance"] or 0.0)
    
    # Let's see: if days_rem >= 0 (unexpired):
    # Should stored_bal be negative?
    if days_rem >= 0 and current_stored_bal < 0:
        # Why was it negative? Because daily accrual deducted days of the current active cycle!
        # Clean balance for an unexpired customer is 0.00 (settled) or positive credit!
        clean_bal = 0.0
    else:
        clean_bal = current_stored_bal

    results.append({
        "id": cid,
        "name": c["name"],
        "exp": str(exp_d),
        "days_rem": days_rem,
        "old_bal": current_stored_bal,
        "new_bal": clean_bal,
        "status": status
    })

neg_before = sum(1 for r in results if r["old_bal"] < 0)
neg_after = sum(1 for r in results if r["new_bal"] < 0)
print(f"Negative balance customers before: {neg_before}")
print(f"Negative balance customers after:  {neg_after}")

print("\nSample transformed accounts:")
for r in results[:20]:
    print(f"ID #{r['id']:<3} {r['name']:<22} | Exp: {r['exp']} ({r['days_rem']:>3}d left) | Old: {r['old_bal']:>8.2f} SAR -> New: {r['new_bal']:>6.2f} SAR")

conn.close()
