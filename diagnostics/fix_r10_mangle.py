import routeros_api

c = routeros_api.RouterOsApiPool("10.12.14.1", "admin", "adminn1", plaintext_login=True)
api = c.get_api()
mangle = api.get_resource('/ip/firewall/mangle')

for r in mangle.get():
    if r.get('out-interface') == 'ether5':
        print(f"Removing mangle rule for ether5: {r}")
        mangle.remove(id=r.get('id'))

print("Remaining mangle rules on Router-10:")
for r in mangle.get():
    print(r)

c.disconnect()
