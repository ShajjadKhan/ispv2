#!/usr/bin/env python3
"""
Deploy Hotspot Tethering Detection Rules across MikroTik Fleet (Router-20, Router-30, Router-10).
Adds prerouting mangle rules matching ingress TTL=63 (Android/iOS tethering) and TTL=127 (Windows tethering)
on ether4 and sfp1 to dynamically populate the 'hotspot_sharing_suspects' address-list with a 2h timeout.
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

def apply_tethering_detection(router_info):
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

        ttl_targets = [
            ("equal:63", "Android/iOS"),
            ("equal:127", "Windows PC")
        ]

        for iface in interfaces:
            for ttl_val, platform in ttl_targets:
                found = False
                for r in existing_rules:
                    if (r.get("chain") == "prerouting" and
                        r.get("action") == "add-src-to-address-list" and
                        r.get("address-list") == "hotspot_sharing_suspects" and
                        r.get("ttl") == ttl_val and
                        r.get("in-interface") == iface):
                        found = True
                        print(f"  [✓] {iface} (TTL {ttl_val}): Detection rule already exists (Packets: {r.get('packets')})")
                        break

                if not found:
                    print(f"  [+] {iface} (TTL {ttl_val} - {platform}): Adding detection rule...")
                    mangle_resource.add(
                        chain="prerouting",
                        action="add-src-to-address-list",
                        **{"address-list": "hotspot_sharing_suspects"},
                        **{"address-list-timeout": "2h"},
                        ttl=ttl_val,
                        passthrough="yes",
                        **{"in-interface": iface},
                        comment=f"CyberNet: Hotspot sharing detected {ttl_val} {iface}"
                    )
                    print(f"  [✓] {iface} (TTL {ttl_val}): Rule added successfully!")

        # Verify active rules
        updated_rules = mangle_resource.get()
        print(f"\n  Current Mangle Rules on {name}:")
        for r in updated_rules:
            cmt = r.get("comment", "")
            cmt_str = f" [{cmt}]" if cmt else ""
            print(f"    - Chain: {r.get('chain')} | Action: {r.get('action')} | TTL: {r.get('ttl')} / {r.get('new-ttl')} | In: {r.get('in-interface')} / Out: {r.get('out-interface')}{cmt_str}")

        pool.disconnect()
        return True
    except Exception as e:
        print(f"  [✗] ERROR on {name}: {e}")
        return False

def main():
    print("=" * 65)
    print("CYBERNET OS: DEPLOYING HOTSPOT TETHERING DETECTION RULES")
    print("=" * 65)

    all_success = True
    for r in routers:
        ok = apply_tethering_detection(r)
        if not ok:
            all_success = False

    print("\n" + "=" * 65)
    if all_success:
        print("ALL ROUTERS CONFIGURED WITH TETHERING DETECTION SUCCESSFULLY!")
    else:
        print("SOME ROUTERS FAILED DEPLOYMENT. CHECK LOGS ABOVE.")
    print("=" * 65)

if __name__ == "__main__":
    main()
