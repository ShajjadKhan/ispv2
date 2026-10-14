import sys
sys.path.insert(0, '/home/tserver/isp_v2')
from main import router_client

st = router_client.get_live_status()
print("Router-20 status:")
print("Online:", st.get("online"))
print("Interfaces:")
for iface in st.get("interfaces", []):
    print(f"  {iface.get('name')}: running={iface.get('running')}, type={iface.get('type')}, comment={iface.get('comment')}")
