#!/usr/bin/env python3
"""
Deep Audit of Cybernet Router-20 for PPPoE and Hotspot configuration.
Connects via routeros_api using credentials from isp_v2 database.
"""
import sys
import os
import pprint

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import routeros_api

def audit_router():
    routers = database.get_all_routers(active_only=True)
    if not routers:
        print("No active routers found in database!")
        return

    r = routers[0]
    print(f"Connecting to Router: {r['name']} ({r['host']}:{r['port']}) as {r['username']}...")

    try:
        pool = routeros_api.RouterOsApiPool(
            r['host'],
            username=r['username'],
            password=r['password'],
            port=r['port'],
            use_ssl=False,
            ssl_verify=False,
            plaintext_login=True
        )
        api = pool.get_api()
        print("✓ Connected to RouterOS API successfully!\n")

        # 1. System Identity & Resources
        ident = api.get_resource("/system/identity").get()
        print(f"System Identity: {ident[0].get('name') if ident else 'Unknown'}")
        
        res = api.get_resource("/system/resource").get()
        if res:
            print(f"Board: {res[0].get('board-name')}, Version: {res[0].get('version')}, Uptime: {res[0].get('uptime')}")

        # 2. Interfaces
        print("\n--- INTERFACES ---")
        ifaces = api.get_resource("/interface").get()
        for i in ifaces:
            print(f"  • {i.get('name')} | Type: {i.get('type')} | Running: {i.get('running')} | Disabled: {i.get('disabled')}")

        # 3. IP Addresses
        print("\n--- IP ADDRESSES ---")
        ips = api.get_resource("/ip/address").get()
        for ip in ips:
            print(f"  • {ip.get('address')} on {ip.get('interface')} (network: {ip.get('network')})")

        # 4. IP Pools
        print("\n--- IP POOLS ---")
        pools = api.get_resource("/ip/pool").get()
        for p in pools:
            print(f"  • {p.get('name')}: {p.get('ranges')}")

        # 5. PPPoE Server Instances
        print("\n--- PPPoE SERVERS (/interface/pppoe-server/server) ---")
        try:
            pppoe_servers = api.get_resource("/interface/pppoe-server/server").get()
            if not pppoe_servers:
                print("  [NONE] No PPPoE server instances configured!")
            for s in pppoe_servers:
                print(f"  • Service: {s.get('service-name')} | Interface: {s.get('interface')} | Profile: {s.get('default-profile')} | Disabled: {s.get('disabled')}")
        except Exception as e:
            print(f"  Error reading pppoe-server: {e}")

        # 6. PPP Profiles
        print("\n--- PPP PROFILES (/ppp/profile) ---")
        try:
            ppp_profiles = api.get_resource("/ppp/profile").get()
            for prof in ppp_profiles:
                print(f"  • {prof.get('name')} | Local: {prof.get('local-address')} | Remote: {prof.get('remote-address')} | Rate: {prof.get('rate-limit')} | DNS: {prof.get('dns-server')}")
        except Exception as e:
            print(f"  Error reading ppp profile: {e}")

        # 7. PPP Secrets
        print("\n--- PPP SECRETS (/ppp/secret) ---")
        try:
            secrets = api.get_resource("/ppp/secret").get()
            print(f"  Total Secrets: {len(secrets)}")
            for sec in secrets[:10]:
                print(f"  • User: {sec.get('name')} | Service: {sec.get('service')} | Profile: {sec.get('profile')} | Disabled: {sec.get('disabled')} | Comment: {sec.get('comment')}")
        except Exception as e:
            print(f"  Error reading ppp secret: {e}")

        # 8. PPP AAA (RADIUS for PPP)
        print("\n--- PPP AAA (/ppp/aaa) ---")
        try:
            aaa = api.get_resource("/ppp/aaa").get()
            if aaa:
                print(f"  • use-radius: {aaa[0].get('use-radius')} | accounting: {aaa[0].get('accounting')} | interim-update: {aaa[0].get('interim-update')}")
        except Exception as e:
            print(f"  Error reading ppp aaa: {e}")

        # 9. RADIUS Servers configured on MikroTik
        print("\n--- RADIUS (/radius) ---")
        try:
            radii = api.get_resource("/radius").get()
            if not radii:
                print("  [NONE] No RADIUS servers configured on this router!")
            for rad in radii:
                print(f"  • Server: {rad.get('address')} | Services: {rad.get('service')} | Port: {rad.get('authentication-port')}/{rad.get('accounting-port')} | Disabled: {rad.get('disabled')}")
        except Exception as e:
            print(f"  Error reading radius: {e}")

        # 10. Hotspot Servers & Profiles
        print("\n--- HOTSPOT SERVERS (/ip/hotspot) ---")
        try:
            hs = api.get_resource("/ip/hotspot").get()
            for h in hs:
                print(f"  • {h.get('name')} on {h.get('interface')} | Profile: {h.get('profile')} | Disabled: {h.get('disabled')}")
        except Exception as e:
            print(f"  Error reading hotspot: {e}")

        # 11. PPPoE Server Full Configuration
        print("\n--- PPPoE SERVER DETAILED CONFIG ---")
        try:
            pppoe_srv = api.get_resource("/interface/pppoe-server/server").get()
            for s in pppoe_srv:
                print(f"  {s}")
        except Exception as e:
            print(f"  Error reading pppoe-server details: {e}")

        # 12. NAT Rules
        print("\n--- NAT RULES (/ip/firewall/nat) ---")
        try:
            nats = api.get_resource("/ip/firewall/nat").get()
            for n in nats:
                print(f"  • chain={n.get('chain')} action={n.get('action')} out-iface={n.get('out-interface')} src-addr={n.get('src-address')} comment={n.get('comment')}")
        except Exception as e:
            print(f"  Error reading nat: {e}")

        # 13. Firewall Filter Rules
        print("\n--- FIREWALL FILTER RULES (/ip/firewall/filter) ---")
        try:
            filters = api.get_resource("/ip/firewall/filter").get()
            for f in filters:
                print(f"  • chain={f.get('chain')} action={f.get('action')} in-iface={f.get('in-interface')} comment={f.get('comment')}")
        except Exception as e:
            print(f"  Error reading filter: {e}")

        # 14. Walled Garden IP (/ip/hotspot/walled-garden/ip)
        print("\n--- WALLED GARDEN IP (/ip/hotspot/walled-garden/ip) ---")
        try:
            wg = api.get_resource("/ip/hotspot/walled-garden/ip").get()
            for w in wg:
                print(f"  • action={w.get('action')} dst-address={w.get('dst-address')} src-address={w.get('src-address')} comment={w.get('comment')}")
        except Exception as e:
            print(f"  Error reading walled-garden ip: {e}")

        pool.disconnect()

    except Exception as e:
        print(f"Failed to connect or query router: {e}")

if __name__ == "__main__":
    audit_router()

