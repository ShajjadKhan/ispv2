import routeros_api

routers = [
    {"name": "Router-20", "host": "10.20.30.1", "user": "admin", "pass": "adminn"},
    {"name": "Router-30", "host": "10.20.30.12", "user": "admin", "pass": "adminn3"},
    {"name": "Router-10", "host": "10.12.14.1", "user": "admin", "pass": "adminn1"}
]

for r in routers:
    print(f"\n=================== {r['name']} ({r['host']}) Bridge Ports Detail ===================")
    try:
        connection = routeros_api.RouterOsApiPool(r['host'], username=r['user'], password=r['pass'], plaintext_login=True)
        api = connection.get_api()
        
        ports = api.get_resource('/interface/bridge/port').get()
        for p in ports:
            print(f"  Port: {p.get('interface')} | Bridge: {p.get('bridge')} | Disabled: {p.get('disabled')} | Role: {p.get('role')} | Status: {p.get('status')}")
            
        connection.disconnect()
    except Exception as e:
        print(f"ERROR: {e}")
