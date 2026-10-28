import sqlite3
import os
import sys
from datetime import datetime

sys.path.insert(0, '/home/sk/isp_v2')
import mikrotik_client

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else ('/home/tserver/isp_v2/isp_v2.db' if os.path.exists('/home/tserver/isp_v2/isp_v2.db') else 'isp_v2.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

today_str = datetime.now().strftime("%Y-%m-%d")
now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
hour_int = datetime.now().hour

print(f"Normalizing traffic accounting for date: {today_str} on {db_path}")

# 1. Purge corrupted multi-terabyte rows from today
cursor.execute("DELETE FROM customer_traffic_hourly WHERE date_str = ?", (today_str,))
h_del = cursor.rowcount
cursor.execute("DELETE FROM customer_traffic_daily WHERE date_str = ?", (today_str,))
d_del = cursor.rowcount
conn.commit()
print(f"Purged {h_del} corrupted hourly records and {d_del} daily records from today.")

# 2. Query live MikroTik hosts from fleet
hosts = mikrotik_client.broadcast_get_hotspot_hosts_raw()
print(f"Queried {len(hosts)} hosts from fleet routers.")

# Build map of customer devices
cursor.execute("SELECT id, customer_id, UPPER(mac_address) as mac FROM customer_devices WHERE status = 'approved'")
cust_devices = {}
for r in cursor.fetchall():
    cust_devices[r["mac"]] = (r["customer_id"], r["id"])

cursor.execute("SELECT id, UPPER(pppoe_username) as pppoe FROM customers WHERE pppoe_username IS NOT NULL AND pppoe_username != ''")
pppoe_custs = {}
for r in cursor.fetchall():
    pppoe_custs[r["pppoe"]] = r["id"]

# Consolidate real session bytes across routers per MAC
real_telemetry = {}
for h in hosts:
    mac = (h.get("mac-address") or "").strip().upper()
    if not mac:
        continue
    b_out = int(h.get("bytes-out", 0) or 0)
    b_in = int(h.get("bytes-in", 0) or 0)
    if mac not in real_telemetry or b_out > real_telemetry[mac]["bytes_out"]:
        real_telemetry[mac] = {
            "bytes_out": b_out,
            "bytes_in": b_in,
            "ip": h.get("address")
        }

# PPPoE
pppoe_sessions = mikrotik_client.broadcast_get_active_pppoe_sessions()
for u_name, p_sess in pppoe_sessions.items():
    clean_u = (u_name or "").strip().upper()
    if not clean_u:
        continue
    pp_key = f"PPPOE:{clean_u}"
    b_out = int(p_sess.get("bytes_out", 0) or p_sess.get("tx_bytes", 0) or 0)
    b_in = int(p_sess.get("bytes_in", 0) or p_sess.get("rx_bytes", 0) or 0)
    real_telemetry[pp_key] = {
        "bytes_out": b_out,
        "bytes_in": b_in,
        "ip": p_sess.get("address")
    }

# Insert accurate baseline traffic
inserted_count = 0
for mac, dat in real_telemetry.items():
    cust_id = None
    dev_id = None
    if mac.startswith("PPPOE:"):
        u = mac.split(":", 1)[1]
        cust_id = pppoe_custs.get(u)
    else:
        mapping = cust_devices.get(mac)
        if mapping:
            cust_id, dev_id = mapping

    if not cust_id:
        continue

    d_bytes = dat["bytes_out"]
    u_bytes = dat["bytes_in"]
    t_bytes = d_bytes + u_bytes

    if t_bytes <= 0:
        continue

    cursor.execute("""
        INSERT INTO customer_traffic_hourly
        (customer_id, mac_address, device_id, date_str, hour_int, download_bytes, upload_bytes, total_bytes, active_seconds, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cust_id, mac, dev_id, today_str, hour_int, d_bytes, u_bytes, t_bytes, 1800, now_str))

    cursor.execute("""
        INSERT INTO customer_traffic_daily
        (customer_id, mac_address, device_id, date_str, download_bytes, upload_bytes, total_bytes, active_seconds, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cust_id, mac, dev_id, today_str, d_bytes, u_bytes, t_bytes, 1800, now_str))

    inserted_count += 1

conn.commit()
print(f"Successfully inserted {inserted_count} normalized baseline records for today.")

# Verify top consumers now
cursor.execute("""
    SELECT c.name, SUM(h.download_bytes) as d_sum, SUM(h.upload_bytes) as u_sum
    FROM customer_traffic_hourly h
    JOIN customers c ON h.customer_id = c.id
    WHERE h.date_str = ?
    GROUP BY c.id
    ORDER BY d_sum DESC
    LIMIT 10
""", (today_str,))
print("\nTop 10 Normalized Consumers for Today:")
for r in cursor.fetchall():
    d = r['d_sum']
    print(f"  {r['name']}: {d / (1024*1024*1024):.2f} GB ({d / (1024*1024):.1f} MB)")
