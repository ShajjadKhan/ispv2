import sys, json
sys.path.insert(0, '/home/tserver/isp_v2')
import database, mikrotik_client

routers = database.get_all_routers(active_only=True)
all_t_maps = {}
for r in routers:
    c = mikrotik_client.get_client_for_router(r)
    try:
        tmap = c.get_devices_telemetry_map(max_cache_age_sec=0)
        all_t_maps[r["id"]] = tmap
        online_count = sum(1 for v in tmap.values() if v.get("state") == "online")
        recent_count = sum(1 for v in tmap.values() if v.get("state") == "recent")
        offline_count = sum(1 for v in tmap.values() if v.get("state") == "offline")
        print(f"Router #{r['id']} ({r['name']} @ {r['host']}):")
        print(f"  Telemetry MACs: {len(tmap)} (Online: {online_count}, Recent: {recent_count}, Offline: {offline_count})")
        for m, telem in list(tmap.items())[:3]:
            print(f"    MAC: {m} -> state={telem.get('state')}, label={telem.get('status_label')}, detail={telem.get('detail')}, ip={telem.get('live_ip')}")
    except Exception as e:
        print(f"Router #{r['id']} Error: {e}")

# Check MACs present on multiple routers
all_macs = set()
for tmap in all_t_maps.values():
    all_macs.update(tmap.keys())

print(f"\nTotal Unique MACs across fleet: {len(all_macs)}")
roaming_macs = []
for mac in all_macs:
    routers_with_mac = [rid for rid, tmap in all_t_maps.items() if mac in tmap]
    if len(routers_with_mac) > 1:
        states = {rid: all_t_maps[rid][mac].get("state") for rid in routers_with_mac}
        roaming_macs.append((mac, states))

print(f"MACs appearing on multiple routers (roaming history): {len(roaming_macs)}")
for mac, states in roaming_macs[:10]:
    print(f"  MAC {mac}: states={states}")
