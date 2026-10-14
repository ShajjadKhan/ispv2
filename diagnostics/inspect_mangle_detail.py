import routeros_api

c = routeros_api.RouterOsApiPool("10.12.14.1", "admin", "adminn1", plaintext_login=True)
api = c.get_api()
mangle = api.get_resource('/ip/firewall/mangle').get()
for m in mangle:
    print(m)
c.disconnect()
