import sqlite3
import os
import sys

sys.path.insert(0, '/home/sk/isp_v2')
import mikrotik_client

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else ('/home/tserver/isp_v2/isp_v2.db' if os.path.exists('/home/tserver/isp_v2/isp_v2.db') else 'isp_v2.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("Connected to:", db_path)

# Query live MikroTik hosts
hosts = mikrotik_client.broadcast_get_hotspot_hosts_raw()
print(f"Queried {len(hosts)} hosts from fleet.")

# For each MAC address, get the highest bytes-in and bytes-out recorded across routers
mac_telemetry = {}
for h in hosts:
    mac = (h.get("mac-address") or "").strip().upper()
    if not mac:
        continue
    b_out = int(h.get("bytes-out", 0) or 0)
    b_in = int(h.get("bytes-in", 0) or 0)
    ip = h.get("address")
    router_name = h.get("router_name", "Router-20")

    if mac not in mac_telemetry:
        mac_telemetry[mac] = {
            "bytes_out": b_out,
            "bytes_in": b_in,
            "ip": ip,
            "router_name": router_name
        }
    else:
        # Keep maximum (active router session)
        if b_out > mac_telemetry[mac]["bytes_out"]:
            mac_telemetry[mac]["bytes_out"] = b_out
            mac_telemetry[mac]["bytes_in"] = b_in
            mac_telemetry[mac]["ip"] = ip
            mac_telemetry[mac]["router_name"] = router_name

# Query active PPPoE sessions
pppoe_sessions = mikrotik_client.broadcast_get_active_pppoe_sessions()
print(f"Queried {len(pppoe_sessions)} PPPoE sessions.")
for u_name, p_sess in pppoe_sessions.items():
    clean_u = (u_name or "").strip()
    if not clean_u:
        continue
    pp_key = f"PPPOE:{clean_u.upper()}"
    b_out = int(p_sess.get("bytes_out", 0) or p_sess.get("tx_bytes", 0) or 0)
    b_in = int(p_sess.get("bytes_in", 0) or p_sess.get("rx_bytes", 0) or 0)
    ip = p_sess.get("address")
    r_name = p_sess.get("router_name", "Router-20")

    mac_telemetry[pp_key] = {
        "bytes_out": b_out,
        "bytes_in": b_in,
        "ip": ip,
        "router_name": r_name
    }

print(f"Total unique devices tracked: {len(mac_telemetry)}")
top_devs = sorted(mac_telemetry.items(), key=lambda x: x[1]["bytes_out"], reverse=True)[:10]
print("\nTop 10 Live Wire Devices:")
for m, dat in top_devs:
    gb = dat['bytes_out'] / (1024 * 1024 * 1024)
    print(f"  {m} ({dat['router_name']}) -> {gb:.2f} GB ({dat['bytes_out']} bytes)")
