import sqlite3

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute("SELECT id, name FROM customers")
rows = c.fetchall()

print(f"Total customers: {len(rows)}")
for cid, name in rows:
    if "'" in name or '"' in name or '\\' in name:
        print(f"Customer {cid}: {repr(name)}")
