import sqlite3
import shutil

# Make test copy
shutil.copyfile('/home/sk/isp_v2/isp_v2.db', '/home/sk/isp_v2/test_merge.db')

conn = sqlite3.connect('/home/sk/isp_v2/test_merge.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Attach backup
cur.execute("ATTACH DATABASE '/home/sk/isp_v2/backups/isp_v2.db.before_clean_keep_real_20261015_220307.db' AS backup_db")

# Insert missing collections
cur.execute("""
    INSERT OR IGNORE INTO collections (id, customer_id, amount, billing_type, notes, collected_at, collected_by, month_year, is_settled, waived_amount)
    SELECT id, customer_id, amount, billing_type, notes, collected_at, collected_by, month_year, is_settled, waived_amount
    FROM backup_db.collections
""")
conn.commit()

cur.execute("SELECT count(*), sum(amount) FROM collections")
row = cur.fetchone()
print(f"After merge in test_merge.db: count = {row[0]}, sum = {row[1]}")

# Now test balance calculation for Tarek Hassan and Hasib
import sys
sys.path.insert(0, '/home/sk/isp_v2')
from database import calculate_customer_realtime_balance

tarek = calculate_customer_realtime_balance(174, conn)
print("Tarek Hassan balance after merge:", tarek)

hasib = calculate_customer_realtime_balance(18, conn)
print("Hasib balance after merge:", hasib)

arafat = calculate_customer_realtime_balance(87, conn)
print("Mohammad Arafat balance after merge:", arafat)

conn.close()
