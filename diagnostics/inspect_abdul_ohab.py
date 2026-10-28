import sqlite3
import sys
sys.path.insert(0, '/home/sk/isp_v2')
from database import calculate_customer_realtime_balance

conn = sqlite3.connect('/home/sk/isp_v2/test_merge.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM customers WHERE name LIKE '%Abdul Ohab%'")
c = cur.fetchone()
print("Abdul Ohab customer:", dict(c))

cur.execute("SELECT * FROM collections WHERE customer_id = ?", (c["id"],))
cols = cur.fetchall()
print(f"Collections count for Abdul Ohab: {len(cols)}")
for col in cols:
    print("  ", dict(col))

rt = calculate_customer_realtime_balance(c["id"], conn)
print("Abdul Ohab realtime balance:", rt)
