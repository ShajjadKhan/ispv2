import routeros_api
import time

pool = routeros_api.RouterOsApiPool('10.20.30.1', username='admin', password='adminn', port=8728, use_ssl=False, plaintext_login=True)
api = pool.get_api()

t0 = time.time()
pppoe_ifaces = api.get_resource('/interface').get(type='pppoe-in')
t1 = time.time()
print(f"Query /interface?type=pppoe-in took {t1-t0:.3f}s, found {len(pppoe_ifaces)} interfaces:")
for p in pppoe_ifaces:
    print(f"Name: {p.get('name')}, rx-byte: {p.get('rx-byte')}, tx-byte: {p.get('tx-byte')}, running: {p.get('running')}")

pool.disconnect()
