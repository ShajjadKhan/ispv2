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
fetch_res = api.get_resource('/tool/fetch')
try:
    res = fetch_res.call('', {
        'url': 'http://api.ipify.org',
        'mode': 'http',
        'as-value': 'true'
    })
    print("Fetch result:", res)
except Exception as e:
    print("Fetch error:", e)
pool.disconnect()
