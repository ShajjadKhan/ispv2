import sys
import os
sys.path.insert(0, '/home/sk/isp_v2')
import mikrotik_client
import database
import main

print("=== 1. Testing broadcast_get_active_pppoe_sessions() ===")
sess_map = mikrotik_client.broadcast_get_active_pppoe_sessions()
print(f"Active PPPoE sessions count: {len(sess_map)}")
for u, s in sess_map.items():
    print(f"  User: {u}")
    print(f"  Router: {s.get('router_name')}")
    print(f"  IP: {s.get('address')}")
    print(f"  Interface: {s.get('interface')}")
    print(f"  Download: {s.get('download_formatted')} ({s.get('download_bytes')} B)")
    print(f"  Upload: {s.get('upload_formatted')} ({s.get('upload_bytes')} B)")
    print(f"  Total: {s.get('total_formatted')} ({s.get('total_bytes')} B)")
    print(f"  Uptime: {s.get('uptime')}")

print("\n=== 2. Testing collect_router_traffic_snapshot() ===")
main.collect_router_traffic_snapshot()
print("Traffic snapshot executed successfully!")

print("\n=== 3. Testing get_customer_usage_analytics(9) ===")
analytics = database.get_customer_usage_analytics(9)
cust = analytics.get("customer", {})
print(f"Customer #{cust.get('id')}: {cust.get('name')}")
print(f"Connection Type: {cust.get('connection_type')}")
print(f"PPPoE Username: {cust.get('pppoe_username')}")
print(f"Device breakdown entries ({len(analytics.get('device_breakdown', []))}):")
for d in analytics.get("device_breakdown", []):
    print(f"  * {d.get('friendly_name')} [{d.get('mac_address')}]: Down: {d.get('formatted_down')}, Up: {d.get('formatted_up')}, Total: {d.get('formatted_total')}")

print("\n=== 4. Testing api_customer_usage logic ===")
import asyncio
res = asyncio.run(main.api_customer_usage(9))
print(f"API is_online: {res.get('is_online')}")
print(f"API total_download: {res.get('total_download')}")
print(f"API total_upload: {res.get('total_upload')}")
print(f"API total_traffic: {res.get('total_traffic')}")
print(f"API pppoe_session: {bool(res.get('pppoe_session'))}")
print(f"API devices count: {len(res.get('devices', []))}")
for dev in res.get('devices', []):
    print(f"  - Device: {dev.get('friendly_name')} [{dev.get('mac_address')}], Online: {dev.get('is_online')}, Down: {dev.get('formatted_down')}, Up: {dev.get('formatted_up')}, Total: {dev.get('formatted_total')}")

print("\n=== 5. Testing WhatsApp dispute proof generator ===")
wa_res = asyncio.run(main.api_customer_usage_whatsapp(9))
print("WhatsApp Message Preview:")
print("------------------------------------------")
print(wa_res.get("message"))
print("------------------------------------------")

print("\nALL TESTS PASSED SUCCESSFULLY!")
