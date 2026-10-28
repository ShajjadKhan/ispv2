import routeros_api

routers = [
    {"name": "Router-20", "host": "10.20.30.1", "user": "admin", "pass": "adminn"},
    {"name": "Router-30", "host": "10.20.30.12", "user": "admin", "pass": "adminn3"},
    {"name": "Router-10", "host": "10.12.14.1", "user": "admin", "pass": "adminn1"}
]

for r in routers:
    print(f"\n=================== {r['name']} Mangle Rules ===================")
    try:
        connection = routeros_api.RouterOsApiPool(r['host'], username=r['user'], password=r['pass'], plaintext_login=True)
        api = connection.get_api()
        mangle = api.get_resource('/ip/firewall/mangle').get()
        for m in mangle:
            cmt = f" [{m.get('comment')}]" if m.get('comment') else ""
            print(f"  {m.get('chain')} | {m.get('action')} | TTL: {m.get('new-ttl')} | Out: {m.get('out-interface')} | {m.get('packets')} pkts ({m.get('bytes')} bytes){cmt}")
        connection.disconnect()
    except Exception as e:
        print(f"ERROR: {e}")
