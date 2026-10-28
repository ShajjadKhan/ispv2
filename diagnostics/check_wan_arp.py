import routeros_api

routers = [
    ("Router-20", "10.20.30.1", "admin", "adminn"),
    ("Router-30", "10.20.30.12", "admin", "adminn3"),
    ("Router-10", "10.12.14.1", "admin", "adminn1")
]

for name, ip, u, p in routers:
    c = routeros_api.RouterOsApiPool(ip, u, p, plaintext_login=True)
    api = c.get_api()
    arp = api.get_resource('/ip/arp').get(address='192.168.11.1')
    routes = api.get_resource('/ip/route').get(dst_address='0.0.0.0/0')
    print(f"{name}: 192.168.11.1 MAC = {arp[0].get('mac-address') if arp else 'None'} | Default Gateway = {routes[0].get('gateway') if routes else 'None'}")
    c.disconnect()
