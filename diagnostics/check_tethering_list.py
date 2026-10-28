#!/usr/bin/env python3
import routeros_api

routers = [
    ('Router-20', '10.20.30.1', 'admin', 'adminn'),
    ('Router-30', '10.20.30.12', 'admin', 'adminn3'),
    ('Router-10', '10.12.14.1', 'admin', 'adminn1')
]

for name, ip, u, p in routers:
    try:
        pool = routeros_api.RouterOsApiPool(ip, username=u, password=p, plaintext_login=True)
        api = pool.get_api()
        entries = api.get_resource('/ip/firewall/address-list').get(list='hotspot_sharing_suspects')
        rules = api.get_resource('/ip/firewall/mangle').get()
        print(f"\n=================== {name} ({ip}) ===================")
        print(f"Address List (hotspot_sharing_suspects): {len(entries)} detected IPs")
        for e in entries:
            print(f"  - IP: {e.get('address')} | Timeout: {e.get('timeout')} | Added: {e.get('creation-time')}")
        print("Detection Mangle Rule Hits:")
        for r in rules:
            if r.get("address-list") == "hotspot_sharing_suspects":
                print(f"  - {r.get('in-interface')} | TTL: {r.get('ttl')} | Packets: {r.get('packets')} ({r.get('bytes')} bytes)")
        pool.disconnect()
    except Exception as ex:
        print(f"{name} error: {ex}")
