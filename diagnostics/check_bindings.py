import sys, os
sys.path.insert(0, '/home/tserver/isp_v2')
import database, routeros_api
r = database.get_all_routers(active_only=True)[0]
pool = routeros_api.RouterOsApiPool(r['host'], username=r['username'], password=r['password'], port=r['port'], plaintext_login=True)
api = pool.get_api()
bindings = api.get_resource('/ip/hotspot/ip-binding').get()
print('Total IP Bindings:', len(bindings))
for b in bindings:
    print(f'  {b.get( mac-address)} -> {b.get(type)} (bypassed={b.get(type) == bypassed}) [{b.get(comment)}]')
