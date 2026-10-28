import sqlite3

c1 = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
c2 = sqlite3.connect('/home/sk/isp_v2/backups/isp_v2.db.before_clean_keep_real_20261015_220307.db')

cur1 = c1.cursor()
cur2 = c2.cursor()

cur1.execute('SELECT count(*) FROM collections')
print('Active collections:', cur1.fetchone()[0])

cur2.execute('SELECT count(*) FROM collections')
print('Backup collections:', cur2.fetchone()[0])

cur1.execute('SELECT count(*) FROM customers')
print('Active customers:', cur1.fetchone()[0])

cur2.execute('SELECT count(*) FROM customers')
print('Backup customers:', cur2.fetchone()[0])

# Check what IDs exist in backup collections but not active
cur2.execute('SELECT id, customer_id, amount, collected_at FROM collections')
backup_cols = cur2.fetchall()

cur1.execute('SELECT id FROM collections')
active_ids = set(r[0] for r in cur1.fetchall())

missing_cols = [r for r in backup_cols if r[0] not in active_ids]
print(f'Collections in backup missing from active: {len(missing_cols)}')
if missing_cols:
    print('Sample missing collections:', missing_cols[:5])

# Check Tarek Hassan (ID 174) in backup collections
cur2.execute('SELECT * FROM collections WHERE customer_id = 174')
tarek_cols = cur2.fetchall()
print('Tarek Hassan collections in backup:', tarek_cols)
