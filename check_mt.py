import sys
sys.path.insert(0, '/home/tserver/isp_v2')
import routeros_api

connection = routeros_api.RouterOsApiPool('10.20.30.1', username='admin', password='adminn', port=8728, plaintext_login=True)
api = connection.get_api()

print("--- FETCHING OLT WEB UI FROM MIKROTIK ---")
try:
    res = api.get_resource('/').call('tool/fetch', {
        'url': 'https://192.168.200.200',
        'check-certificate': 'no',
        'output': 'user',
        'as-value': ''
    })
    print("Fetch HTTPS res:", res)
except Exception as e:
    print("Fetch HTTPS err:", e)

try:
    res = api.get_resource('/').call('tool/fetch', {
        'url': 'http://192.168.200.200',
        'output': 'user',
        'as-value': ''
    })
    print("Fetch HTTP res:", res)
except Exception as e:
    print("Fetch HTTP err:", e)

connection.disconnect()
