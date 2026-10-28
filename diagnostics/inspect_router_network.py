import routeros_api
import json

routers = [
    {"name": "Router-20", "host": "10.20.30.1", "user": "admin", "pass": "adminn"},
    {"name": "Router-30", "host": "10.20.30.12", "user": "admin", "pass": "adminn3"},
    {"name": "Router-10", "host": "10.20.30.10", "user": "admin", "pass": "adminn1"},
]

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
        print(f"\n==================== {r['name']} ({r['host']}) ====================")
        
        # IP Addresses
        ips = api.get_resource('/ip/address').get()
        print("IP Addresses:")
        for ip in ips:
            print(f"  {ip.get('address')} on {ip.get('interface')} ({ip.get('comment', '')})")
            
        # Hotspot servers & profiles
        try:
            hs_srv = api.get_resource('/ip/hotspot').get()
            print("Hotspot Servers:")
            for s in hs_srv:
                print(f"  {s.get('name')} interface={s.get('interface')} profile={s.get('profile')}")
        except Exception as e:
            print("Hotspot server err:", e)
            
        # VLANs / Bridges
        try:
            vlans = api.get_resource('/interface/vlan').get()
            print("VLANs:")
            for v in vlans:
                print(f"  {v.get('name')} vlan-id={v.get('vlan-id')} interface={v.get('interface')}")
        except Exception as e:
            print("VLAN err:", e)

        pool.disconnect()
    except Exception as e:
        print(f"Failed to connect to {r['name']}: {e}")
