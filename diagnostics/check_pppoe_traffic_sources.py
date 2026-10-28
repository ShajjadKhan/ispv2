import routeros_api

pool = routeros_api.RouterOsApiPool('10.20.30.1', username='admin', password='adminn', port=8728, use_ssl=False, plaintext_login=True)
api = pool.get_api()

print('=== PPP ACTIVE ===')
for act in api.get_resource('/ppp/active').get(name='B1G7D'):
    print(act)

print('\n=== INTERFACES matching B1G7D ===')
for iface in api.get_resource('/interface').get():
    if 'B1G7D' in iface.get('name', ''):
        print(iface)

print('\n=== ALL PPPoE INTERFACES ===')
for iface in api.get_resource('/interface').get():
    if iface.get('type') in ('pppoe-in', 'ppp-in'):
        print(f"{iface.get('name')}: rx-byte={iface.get('rx-byte')}, tx-byte={iface.get('tx-byte')}")

print('\n=== QUEUES matching B1G7D ===')
for q in api.get_resource('/queue/simple').get():
    if 'B1G7D' in q.get('name', ''):
        print(q)

pool.disconnect()
