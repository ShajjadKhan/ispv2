import routeros_api
import sqlite3
import json
import re

print("=== 1. FETCHING CUSTOMERS & DEVICES FROM DB ===")
conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT id, name, phone, notes, status, pppoe_username FROM customers")
customers = {c["id"]: dict(c) for c in cur.fetchall()}

cur.execute("SELECT id, customer_id, mac_address, ip_address, status, device_name FROM customer_devices")
devices = {d["mac_address"].upper(): dict(d) for d in cur.fetchall() if d["mac_address"]}

print(f"Loaded {len(customers)} customers and {len(devices)} devices from DB.")

# Router connection info
routers = [
    {"name": "Router-20", "host": "10.20.30.1", "user": "admin", "pass": "adminn"},
    {"name": "Router-30", "host": "10.20.30.12", "user": "admin", "pass": "adminn3"},
    {"name": "Router-10", "host": "10.20.30.10", "user": "admin", "pass": "adminn1"},
]

all_hosts = []
all_leases = []
all_arp = []
all_bridge_hosts = []

for r in routers:
    try:
        pool = routeros_api.RouterOsApiPool(
            r["host"],
            username=r["user"],
            password=r.get("pass", ""),
            port=8728,
            use_ssl=False,
            plaintext_login=True
        )
        api = pool.get_api()
        print(f"Connected to {r['name']} ({r['host']})")

        # 1. Hotspot hosts
        try:
            hs = api.get_resource('/ip/hotspot/host').get()
            for h in hs:
                h["_router"] = r["name"]
                all_hosts.append(h)
        except Exception as e:
            print(f"  Hotspot error on {r['name']}: {e}")

        # 2. DHCP leases
        try:
            leases = api.get_resource('/ip/dhcp-server/lease').get()
            for l in leases:
                l["_router"] = r["name"]
                all_leases.append(l)
        except Exception as e:
            print(f"  DHCP error on {r['name']}: {e}")

        # 3. ARP
        try:
            arp = api.get_resource('/ip/arp').get()
            for a in arp:
                a["_router"] = r["name"]
                all_arp.append(a)
        except Exception as e:
            print(f"  ARP error on {r['name']}: {e}")

        # 4. Bridge hosts
        try:
            b_hosts = api.get_resource('/interface/bridge/host').get()
            for bh in b_hosts:
                bh["_router"] = r["name"]
                all_bridge_hosts.append(bh)
        except Exception as e:
            print(f"  Bridge host error on {r['name']}: {e}")

        pool.disconnect()
    except Exception as e:
        print(f"Failed to connect to {r['name']}: {e}")

print(f"\nTotal collected: {len(all_hosts)} Hotspot hosts, {len(all_leases)} DHCP leases, {len(all_arp)} ARP entries, {len(all_bridge_hosts)} bridge hosts.")

# Save dump
data_dump = {
    "hosts": all_hosts,
    "leases": all_leases,
    "arp": all_arp,
    "bridge_hosts": all_bridge_hosts
}
with open("/tmp/mikrotik_fleet_dump.json", "w") as f:
    json.dump(data_dump, f, indent=2)
print("Saved /tmp/mikrotik_fleet_dump.json")

# Map online MACs to Customers and Rooms
matched_subscribers = []
for h in all_hosts:
    mac = h.get("mac-address", "").upper()
    if mac in devices:
        dev = devices[mac]
        cust = customers.get(dev["customer_id"], {})
        matched_subscribers.append({
            "router": h.get("_router"),
            "ip": h.get("address"),
            "mac": mac,
            "customer_id": dev["customer_id"],
            "name": cust.get("name"),
            "notes": cust.get("notes"),
            "bytes_in": h.get("bytes-in"),
            "bytes_out": h.get("bytes-out"),
            "uptime": h.get("uptime")
        })

print(f"\nMatched {len(matched_subscribers)} online subscribers currently active.")
# Print sample by building
b1_matches = [m for m in matched_subscribers if "B1" in (m.get("notes") or "").upper()]
b2_matches = [m for m in matched_subscribers if "B2" in (m.get("notes") or "").upper()]
print(f"B1 Active Matches: {len(b1_matches)} | B2 Active Matches: {len(b2_matches)}")

with open("/tmp/matched_online_subscribers.json", "w") as f:
    json.dump(matched_subscribers, f, indent=2)
print("Saved /tmp/matched_online_subscribers.json")
