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
ips = api.get_resource('/ip/address').get()
print("Router-20 IP addresses:")
for ip in ips:
    print(f"  {ip.get('interface')}: {ip.get('address')} (network: {ip.get('network')})")
pool.disconnect()
