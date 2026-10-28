import sys
sys.path.insert(0, '/home/tserver/isp_v2')
from main import router_client
import routeros_api

router_client.refresh_from_db()
pool = routeros_api.RouterOsApiPool(
    router_client.host,
    username=router_client.username,
    password=router_client.password,
    port=router_client.port,
    use_ssl=router_client.use_ssl,
    ssl_verify=False,
    plaintext_login=True
)
api = pool.get_api()
ping_res = api.get_resource('/ping')
res = ping_res.call('', {'address': '135.181.39.96', 'count': '3'})
print("MikroTik Ping to Hetzner result:")
for r in res:
    print(r)
pool.disconnect()
