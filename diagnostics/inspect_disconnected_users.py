import sqlite3

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

for cid in [29, 155]:
    print("="*60)
    cur.execute('SELECT * FROM customers WHERE id = ?', (cid,))
    c = dict(cur.fetchone())
    print("CUSTOMER", cid, c['name'], c['phone'])
    print("  status:", c['status'])
    print("  expiry_date:", c['expiry_date'])
    print("  due_date:", c['due_date'])
    print("  billing_type:", c['billing_type'])
    print("  monthly_fee:", c['monthly_fee'])
    print("  credit_balance:", c['credit_balance'])
    print("  created_at:", c['created_at'])
    print("  join_date:", c['join_date'])
    print("  billing_start_date:", c['billing_start_date'])
    
    print("  COLLECTIONS:")
    cur.execute('SELECT * FROM collections WHERE customer_id = ? ORDER BY id', (cid,))
    colls = cur.fetchall()
    print(f"  Count: {len(colls)}")
    for col in colls:
        print("   ", dict(col))
        
    # Billing cycles query removed

    print("  CUSTOMER DEVICES:")
    cur.execute('SELECT * FROM customer_devices WHERE customer_id = ? ORDER BY id', (cid,))
    devs = cur.fetchall()
    for d in devs:
        print("   ", dict(d))

    print("  CONNECTION REQUESTS:")
    cur.execute('SELECT * FROM connection_requests WHERE customer_id = ? OR phone = ? ORDER BY id', (cid, c['phone']))
    reqs = cur.fetchall()
    for r in reqs:
        print("   ", dict(r))

conn.close()
