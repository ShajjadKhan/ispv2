import routeros_api

routers = [
    {"name": "Router-20", "host": "10.20.30.1", "user": "admin", "pass": "adminn"},
    {"name": "Router-30", "host": "10.20.30.12", "user": "admin", "pass": "adminn3"},
    {"name": "Router-10", "host": "10.12.14.1", "user": "admin", "pass": "adminn1"}
]

for r in routers:
    print(f"\n=================== {r['name']} ({r['host']}) Neighbors ===================")
    try:
        connection = routeros_api.RouterOsApiPool(r['host'], username=r['user'], password=r['pass'], plaintext_login=True)
        api = connection.get_api()
        
        neighbors = api.get_resource('/ip/neighbor').get()
        for n in neighbors:
            print(f"  Interface: {n.get('interface')} | Neighbor: {n.get('identity')} ({n.get('address')}) | MAC: {n.get('mac-address')} | Board: {n.get('board')}")
            
        connection.disconnect()
    except Exception as e:
        print(f"ERROR: {e}")
