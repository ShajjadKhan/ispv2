#!/usr/bin/env python3
"""
Deploy Anti-Hotspot Tethering (TTL=1) Protection across MikroTik Fleet
Router-20, Router-30, and Router-10.
Sets new-ttl=set:1 on postrouting for ether4 and sfp1 hotspot interfaces.
"""
import routeros_api
import sys

routers = [
    {
        "name": "Router-20",
        "host": "10.20.30.1",
        "user": "admin",
        "pass": "adminn",
        "interfaces": ["ether4", "sfp1"]
    },
    {
        "name": "Router-30",
        "host": "10.20.30.12",
        "user": "admin",
        "pass": "adminn3",
        "interfaces": ["ether4", "sfp1"]
    },
    {
        "name": "Router-10",
        "host": "10.12.14.1",
        "user": "admin",
        "pass": "adminn1",
        "interfaces": ["ether4", "sfp1"]
    }
]

def apply_anti_tethering(router_info):
    name = router_info["name"]
    host = router_info["host"]
    user = router_info["user"]
    passwd = router_info["pass"]
    interfaces = router_info["interfaces"]

    print(f"\n=======================================================")
    print(f"Connecting to {name} ({host})...")
    print(f"=======================================================")

    try:
        pool = routeros_api.RouterOsApiPool(host, username=user, password=passwd, plaintext_login=True)
        api = pool.get_api()
        mangle_resource = api.get_resource('/ip/firewall/mangle')
        existing_rules = mangle_resource.get()

        for iface in interfaces:
            # Check if rule already exists for this interface
            found = False
            for r in existing_rules:
                if (r.get("chain") == "postrouting" and 
                    r.get("action") == "change-ttl" and 
                    r.get("new-ttl") == "set:1" and 
                    r.get("out-interface") == iface):
                    found = True
                    print(f"  [✓] {iface}: Rule already exists (ID: {r.get('id')}, Packets: {r.get('packets')}, Bytes: {r.get('bytes')})")
                    break

            if not found:
                print(f"  [+] {iface}: Adding change-ttl (new-ttl=set:1) rule...")
                mangle_resource.add(
                    chain="postrouting",
                    action="change-ttl",
                    **{"new-ttl": "set:1"},
                    passthrough="yes",
                    **{"out-interface": iface},
                    comment=f"CyberNet: Anti-Hotspot Tethering {iface}"
                )
                print(f"  [✓] {iface}: Anti-tethering rule added successfully!")

        # Verify active rules
        updated_rules = mangle_resource.get()
        print(f"\n  Current Mangle Rules on {name}:")
        for r in updated_rules:
            cmt = r.get("comment", "")
            cmt_str = f" ({cmt})" if cmt else ""
            print(f"    - Chain: {r.get('chain')} | Action: {r.get('action')} | New-TTL: {r.get('new-ttl')} | Out-Iface: {r.get('out-interface')}{cmt_str}")

        pool.disconnect()
        return True
    except Exception as e:
        print(f"  [✗] ERROR connecting/configuring {name}: {e}")
        return False

def main():
    print("=" * 65)
    print("CYBERNET OS: DEPLOYING ANTI-HOTSPOT TETHERING PROTECTION")
    print("=" * 65)

    all_success = True
    for r in routers:
        ok = apply_anti_tethering(r)
        if not ok:
            all_success = False

    print("\n" + "=" * 65)
    if all_success:
        print("[✓] ALL FLEET GATEWAYS CONFIGURED & VERIFIED SUCCESSFULLY!")
    else:
        print("[!] SOME ROUTERS ENCOUNTERED ERRORS - CHECK LOGS ABOVE")
    print("=" * 65)

if __name__ == "__main__":
    main()
