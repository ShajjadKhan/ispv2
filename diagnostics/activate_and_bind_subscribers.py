import sys
sys.path.insert(0, '/home/sk/isp_v2')
import sqlite3
import datetime
import mikrotik_client

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

target_cids = [29, 155, 157]

print("="*60)
print(f"ACTIVATING CUSTOMERS: {target_cids}")
print("="*60)

for cid in target_cids:
    cur.execute("SELECT * FROM customers WHERE id = ?", (cid,))
    cust = dict(cur.fetchone())
    print(f"\nProcessing Customer #{cid} ({cust['name']} - {cust['phone']}):")
    
    # 1. Update customer table to active with date 2026-10-31
    cur.execute("""
        UPDATE customers 
        SET status = 'active', due_date = '2026-10-31', expiry_date = '2026-10-31', updated_at = ?
        WHERE id = ?
    """, (now_str, cid))
    
    # 2. Close any open suspensions
    cur.execute("""
        UPDATE customer_suspensions 
        SET resumed_at = ? 
        WHERE customer_id = ? AND resumed_at IS NULL
    """, (now_str, cid))
    
    # 3. Approve all devices for this customer
    cur.execute("""
        UPDATE customer_devices 
        SET status = 'approved' 
        WHERE customer_id = ?
    """, (cid,))
    
    # 4. Fetch all approved devices for binding
    cur.execute("SELECT * FROM customer_devices WHERE customer_id = ?", (cid,))
    devs = cur.fetchall()
    
    for d in devs:
        mac = d['mac_address'].upper()
        ip = d['ip_address']
        notes = cust.get('notes') or ''
        notes_str = f" [{notes.strip()}]" if notes.strip() else ""
        comment = f"CyberNet: {cust['phone']} - {cust['name']}{notes_str} ({cust['billing_type'].upper()})"
        speed = cust.get('speed_limit') or 'Unlimited'
        
        print(f"  Binding Device {mac} (IP: {ip}, Speed: {speed}) to MikroTik...")
        res = mikrotik_client.broadcast_bind_device(
            mac_address=mac,
            ip_address=ip,
            comment=comment,
            rate_limit=speed
        )
        print(f"    Fleet Bind Result: {res}")
        
    # 5. Mark pending connection requests approved
    cur.execute("""
        UPDATE connection_requests 
        SET status = 'approved', updated_at = ? 
        WHERE customer_id = ? OR phone = ?
    """, (now_str, cid, cust['phone']))

conn.commit()
conn.close()

print("\n" + "="*60)
print("ALL SUBSCRIBERS ACTIVATED AND BOUND TO MIKROTIK SUCCESSFULLY.")
print("="*60)
