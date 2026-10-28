import routeros_api

connection = routeros_api.RouterOsApiPool("10.12.14.1", username="admin", password="adminn1", plaintext_login=True)
api = connection.get_api()

print("=== ROUTER-10 DETAIL ===")
print("--- ALL BRIDGES ---")
print(api.get_resource('/interface/bridge').get())

print("--- ALL BRIDGE PORTS ---")
print(api.get_resource('/interface/bridge/port').get())

print("--- ALL POOLS ---")
print(api.get_resource('/ip/pool').get())

print("--- ALL DHCP SERVERS ---")
print(api.get_resource('/ip/dhcp-server').get())

print("--- ALL DHCP NETWORKS ---")
print(api.get_resource('/ip/dhcp-server/network').get())

print("--- ALL PPPOE SERVERS ---")
print(api.get_resource('/interface/pppoe-server/server').get())

print("--- ALL PPP PROFILES ---")
print(api.get_resource('/ppp/profile').get())

print("--- ALL PPP SECRETS ---")
print(api.get_resource('/ppp/secret').get())

print("--- ALL PPP AAA ---")
print(api.get_resource('/ppp/aaa').get())

print("--- ALL HOTSPOT SERVERS ---")
print(api.get_resource('/ip/hotspot').get())

print("--- ALL HOTSPOT PROFILES ---")
print(api.get_resource('/ip/hotspot/profile').get())

connection.disconnect()
