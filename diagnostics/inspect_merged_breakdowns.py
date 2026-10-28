import sqlite3
import sys
sys.path.insert(0, '/home/sk/isp_v2')
from database import calculate_customer_realtime_balance, get_customer_billing_breakdown

conn = sqlite3.connect('/home/sk/isp_v2/test_merge.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, name, phone, billing_type, monthly_fee, due_date, expiry_date, status, billing_start_date FROM customers ORDER BY id DESC")
custs = cur.fetchall()

print(f"Total customers: {len(custs)}")
sample_ids = [193, 174, 18, 87, 170, 109, 92, 123, 73, 120]

for cid in sample_ids:
    c = cur.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    b = calculate_customer_realtime_balance(cid, conn)
    bk = get_customer_billing_breakdown(cid)
    print(f"ID #{cid:<3} {c['name']:<22} | Due: {c['due_date']} (Exp: {c['expiry_date']})")
    print(f"    Realtime: bal={b['balance']:>7.2f} SAR (owed={b['total_owed']}, paid={b['total_paid']}) | BD total_due={bk['total_due']}")
    if bk.get('unpaid_cycles'):
        print(f"    Unpaid cycles: {[(u['month'], u['expected_fee'], u['rem_due']) for u in bk['unpaid_cycles']]}")
    else:
        print("    Unpaid cycles: None (ALL SETTLED)")

conn.close()
