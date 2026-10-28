import sqlite3, os

conn = sqlite3.connect('isp.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('=== TABLES ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for r in cur.fetchall():
    print(' ', r[0])

print('\n=== INDEXES ===')
cur.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name")
for r in cur.fetchall():
    print(f'  [{r["tbl_name"]}] {r["name"]}')

print('\n=== ROW COUNTS ===')
for t in ['customers','devices','connection_requests','collections','packages']:
    cur.execute(f'SELECT COUNT(*) as cnt FROM {t}')
    print(f'  {t}: {cur.fetchone()["cnt"]} rows')

print('\n=== CUSTOMER COLUMNS ===')
cur.execute("PRAGMA table_info(customers)")
for r in cur.fetchall():
    print(f'  {r["name"]} ({r["type"]})')

print('\n=== DB FILE SIZE ===')
size = os.path.getsize('isp.db')
print(f'  isp.db: {size/1024:.1f} KB')
conn.close()
