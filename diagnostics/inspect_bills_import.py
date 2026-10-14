import sqlite3

b_conn = sqlite3.connect('/home/tserver/billing_reminder/bills.db')
b_conn.row_factory = sqlite3.Row
isp_conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
isp_conn.row_factory = sqlite3.Row

# Total collections in bills.db
b_cols = b_conn.execute("SELECT COUNT(*), SUM(amount) FROM collections WHERE amount > 0").fetchone()
print(f"bills.db total collections: {b_cols[0]} records, {b_cols[1]} SAR")

# Total collections in isp_v2.db
i_cols = isp_conn.execute("SELECT COUNT(*), SUM(amount) FROM collections WHERE amount > 0").fetchone()
print(f"isp_v2.db total collections: {i_cols[0]} records, {i_cols[1]} SAR")

# Sample customers in bills.db vs isp_v2.db
print("\nComparing customers between bills.db and isp_v2.db:")
for name in ['Ashfaq', 'Tarek Hassan', 'BADSHA', 'Rajesh', 'MOHAMMAD ARAFAT']:
    b_c = b_conn.execute("SELECT * FROM customers WHERE name LIKE ?", (f"%{name}%",)).fetchone()
    i_c = isp_conn.execute("SELECT * FROM customers WHERE name LIKE ?", (f"%{name}%",)).fetchone()
    
    print(f"\n--- {name} ---")
    if b_c:
        b_paid = b_conn.execute("SELECT SUM(amount) FROM collections WHERE customer_id = ?", (b_c['id'],)).fetchone()[0] or 0.0
        print(f"  bills.db : ID={b_c['id']}, monthly_fee={b_c['monthly_fee']}, start={b_c['billing_start_date']}, total_paid={b_paid}")
    else:
        print("  bills.db : NOT FOUND")
        
    if i_c:
        i_paid = isp_conn.execute("SELECT SUM(amount) FROM collections WHERE customer_id = ?", (i_c['id'],)).fetchone()[0] or 0.0
        print(f"  isp_v2.db: ID={i_c['id']}, monthly_fee={i_c['monthly_fee']}, start={i_c['billing_start_date']}, credit_balance={i_c['credit_balance']}, total_paid={i_paid}")
    else:
        print("  isp_v2.db: NOT FOUND")

# Check PHP getCustomerBalance for Ashfaq (ID 77) in bills.db
import subprocess
php_code = """
require_once '/home/tserver/billing_reminder/billing_logic.php';
$db = new SQLite3('/home/tserver/billing_reminder/bills.db');
$b = getCustomerBalance($db, 77);
echo json_encode($b);
"""
res = subprocess.run(["php", "-r", php_code], capture_output=True, text=True)
print("\nAshfaq (ID 77) in bills.db using billing_logic.php:")
print(" ", res.stdout)
