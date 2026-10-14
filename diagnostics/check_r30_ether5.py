import routeros_api

connection = routeros_api.RouterOsApiPool("10.20.30.12", username="admin", password="adminn3", plaintext_login=True)
api = connection.get_api()

print("=== CHECK ROUTER-30 FOR ether5 REFERENCES ===")
for path in ['/ip/dhcp-server', '/ip/dhcp-server/network', '/ip/hotspot', '/interface/pppoe-server/server', '/ip/firewall/nat', '/ip/firewall/filter']:
    res = api.get_resource(path).get()
    for item in res:
        item_str = str(item)
        if 'ether5' in item_str:
            print(f"Found in {path}: {item}")

print("=== CHECK ROUTER-30 BRIDGE SETTINGS ===")
print(api.get_resource('/interface/bridge').get())

connection.disconnect()
