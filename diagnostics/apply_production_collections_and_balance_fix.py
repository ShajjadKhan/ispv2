import sqlite3
import shutil
import sys
from datetime import datetime, date

sys.path.insert(0, '/home/sk/isp_v2')

now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
db_path = '/home/sk/isp_v2/isp_v2.db'
backup_path = f'/home/sk/isp_v2/backups/isp_v2.db.backup_before_balance_fix_{now_str}.db'

# Step 1: Backup current DB
print(f"[1] Creating safety backup of isp_v2.db at {backup_path}...")
shutil.copyfile(db_path, backup_path)
print("    Safety backup created successfully.")

# Step 2: Merge 336 historical collections from backup into production isp_v2.db
print("[2] Merging missing historical collections from backup...")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT count(*), coalesce(sum(amount), 0) FROM collections")
c_before, s_before = cur.fetchone()
print(f"    Active collections before: {c_before} rows, sum = {s_before:.2f} SAR")

cur.execute("ATTACH DATABASE '/home/sk/isp_v2/backups/isp_v2.db.before_clean_keep_real_20261015_220307.db' AS backup_db")
cur.execute("""
    INSERT OR IGNORE INTO collections (id, customer_id, amount, billing_type, notes, collected_at, collected_by, month_year, is_settled, waived_amount)
    SELECT id, customer_id, amount, billing_type, notes, collected_at, collected_by, month_year, is_settled, waived_amount
    FROM backup_db.collections
""")
conn.commit()

cur.execute("SELECT count(*), coalesce(sum(amount), 0) FROM collections")
c_after, s_after = cur.fetchone()
print(f"    Active collections after:  {c_after} rows, sum = {s_after:.2f} SAR (+{c_after - c_before} merged)")
cur.execute("DETACH DATABASE backup_db")

# Step 3: Run sync_all_customer_realtime_balances
print("[3] Running sync_all_customer_realtime_balances() with unexpired subscription guard...")
import database
updated_cnt = database.sync_all_customer_realtime_balances(conn)
print(f"    Updated {updated_cnt} customer balances.")

# Step 4: Audit final balance states
print("[4] Auditing final subscriber balance states across all 155 accounts...")
cur.execute("SELECT count(*) FROM customers WHERE credit_balance < 0")
neg_cnt = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM customers WHERE credit_balance = 0")
settled_cnt = cur.fetchone()[0]

cur.execute("SELECT count(*) FROM customers WHERE credit_balance > 0")
credit_cnt = cur.fetchone()[0]

print(f"    Accounts with negative balance (debt): {neg_cnt}")
print(f"    Accounts settled (0.00 SAR):           {settled_cnt}")
print(f"    Accounts with positive credit balance: {credit_cnt}")

# Check specific accounts from user paste
sample_cids = [197, 193, 192, 191, 188, 178, 174, 18, 87, 170]
print("\n[5] Sample accounts verification:")
for cid in sample_cids:
    c = cur.execute("SELECT id, name, expiry_date, due_date, credit_balance, status FROM customers WHERE id = ?", (cid,)).fetchone()
    if c:
        rt = database.calculate_customer_realtime_balance(cid, conn)
        bk = database.get_customer_billing_breakdown(cid)
        print(f"    #{c['id']:<3} {c['name']:<22} | Exp: {c['expiry_date']} | Wallet: {c['credit_balance']:>6.2f} SAR | RT: {rt['balance']:>6.2f} SAR | Due: {bk['total_due']:>6.2f} SAR | Status: {c['status']}")

conn.close()
print("\n>>> PRODUCTION COLLECTIONS MERGE & SUBSCRIPTION BALANCE RESOLUTION COMPLETE <<<")
