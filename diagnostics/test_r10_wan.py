import routeros_api

c = routeros_api.RouterOsApiPool("10.12.14.1", "admin", "adminn1", plaintext_login=True)
api = c.get_api()
for ip in ['8.8.8.8', '1.1.1.1', '192.168.22.1']:
    res = api.get_binary_resource('/').call('ping', {'address': ip.encode(), 'count': b'3'})
    print(f"Router-10 ping {ip}: {res}")
c.disconnect()
