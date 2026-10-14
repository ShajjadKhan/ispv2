import routeros_api

routers = [
    {"name": "Router-20", "host": "10.20.30.1", "user": "admin", "pass": "adminn"},
    {"name": "Router-30", "host": "10.20.30.12", "user": "admin", "pass": "adminn3"},
    {"name": "Router-10", "host": "10.12.14.1", "user": "admin", "pass": "adminn1"}
]

for r in routers:
    print(f"\n=================== {r['name']} ({r['host']}) ===================")
    try:
        connection = routeros_api.RouterOsApiPool(r['host'], username=r['user'], password=r['pass'], plaintext_login=True)
        api = connection.get_api()
        
        print("--- BRIDGES ---")
        bridges = api.get_resource('/interface/bridge').get()
        for b in bridges:
            print(f"  Bridge: {b.get('name')} | protocol-mode: {b.get('protocol-mode')} | running: {b.get('running')}")
            
        print("--- BRIDGE PORTS ---")
        ports = api.get_resource('/interface/bridge/port').get()
        for p in ports:
            print(f"  Port: {p.get('interface')} on Bridge: {p.get('bridge')} | disabled: {p.get('disabled')} | hw: {p.get('hw')}")
            
        print("--- IP ADDRESSES ---")
        ips = api.get_resource('/ip/address').get()
        for ip in ips:
            print(f"  IP: {ip.get('address')} on {ip.get('interface')} (network: {ip.get('network')})")
            
        print("--- PPPOE SERVERS ---")
        pppoes = api.get_resource('/interface/pppoe-server/server').get()
        for ppp in pppoes:
            print(f"  PPPoE: {ppp.get('service-name')} on {ppp.get('interface')} | profile: {ppp.get('default-profile')} | disabled: {ppp.get('disabled')}")
            
        print("--- HOTSPOT SERVERS ---")
        hs = api.get_resource('/ip/hotspot').get()
        for h in hs:
            print(f"  Hotspot: {h.get('name')} on {h.get('interface')} | profile: {h.get('profile')} | disabled: {h.get('disabled')}")
            
        print("--- INTERFACES ---")
        ifaces = api.get_resource('/interface').get()
        for iface in ifaces:
            if iface.get('type') in ['ether', 'bridge']:
                print(f"  {iface.get('name')} ({iface.get('type')}): running={iface.get('running')}, comment={iface.get('comment')}")

        connection.disconnect()
    except Exception as e:
        print(f"ERROR: {e}")
