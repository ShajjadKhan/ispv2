import routeros_api

c = routeros_api.RouterOsApiPool("10.12.14.1", "admin", "adminn1", plaintext_login=True)
api = c.get_api()
routes = api.get_resource('/ip/route').get()
for r in routes:
    print(r)
c.disconnect()
