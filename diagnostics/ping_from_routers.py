import routeros_api

routers = [
    ("Router-20", "10.20.30.1", "admin", "adminn"),
    ("Router-30", "10.20.30.12", "admin", "adminn3"),
    ("Router-10", "10.12.14.1", "admin", "adminn1")
]

for name, ip, u, p in routers:
    c = routeros_api.RouterOsApiPool(ip, u, p, plaintext_login=True)
    api = c.get_api()
    try:
        res = api.get_binary_resource('/').call('ping', {'address': '135.181.39.96', 'count': '3'})
        print(f"{name} ping 135.181.39.96:\n{res}")
    except Exception as e:
        print(f"{name} ping ERROR: {e}")
    c.disconnect()
