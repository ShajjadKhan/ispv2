import routeros_api

for ip in ["10.20.30.10", "10.12.14.1"]:
    try:
        connection = routeros_api.RouterOsApiPool(ip, username="admin", password="adminn1", plaintext_login=True)
        api = connection.get_api()
        res = api.get_resource('/system/resource').get()[0]
        print(f"Connection to {ip} SUCCESS! Identity: {api.get_resource('/system/identity').get()[0].get('name')}, CPU: {res.get('cpu-load')}%, Uptime: {res.get('uptime')}")
        connection.disconnect()
    except Exception as e:
        print(f"Connection to {ip} FAILED: {e}")
