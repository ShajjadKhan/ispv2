import sqlite3
import calendar
from datetime import datetime

def align_customers():
    db_path = '/home/tserver/isp_v2/isp_v2.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute('''
        UPDATE customers
        SET due_day = 1,
            billing_start_date = CASE 
                WHEN id IN (2, 12) THEN '2026-09-01'
                ELSE '2026-10-01'
            END,
            due_date = '2026-11-01',
            expiry_date = '2026-10-31'
        WHERE status != 'deleted'
    ''')
    conn.commit()
    print(f"Successfully aligned {cur.rowcount} customers to strict 1st-of-month calendar cycle.")

    # Print summary
    rows = cur.execute("SELECT id, name, billing_start_date, due_date, due_day, expiry_date FROM customers WHERE status != 'deleted'").fetchall()
    print("\nUpdated Customer Records:")
    for r in rows:
        print(f"#{r[0]} {r[1]}: start={r[2]}, due_date={r[3]}, due_day={r[4]}, expiry={r[5]}")

    conn.close()

if __name__ == '__main__':
    align_customers()
