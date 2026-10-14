import sys, time
sys.path.insert(0, '/home/tserver/isp_v2')
import database, mikrotik_client
from concurrent.futures import ThreadPoolExecutor

def get_router_short_code(router_name: str, router_id: int) -> str:
    name_l = (router_name or "").lower()
    if "10" in name_l:
        return "MK10"
    if "20" in name_l:
        return "MK20"
    if "30" in name_l:
        return "MK30"
    return f"R{router_id}"

start = time.time()
routers = database.get_all_routers(active_only=True)

def fetch_for_router(r):
    try:
        c = mikrotik_client.get_client_for_router(r)
        tmap = c.get_devices_telemetry_map(max_cache_age_sec=0)
        return r, tmap, None
    except Exception as e:
        return r, {}, str(e)

with ThreadPoolExecutor(max_workers=len(routers) or 1) as executor:
    results = list(executor.map(fetch_for_router, routers))

duration = (time.time() - start) * 1000
print(f"Parallel fetch for {len(routers)} routers took: {duration:.1f}ms")

# Now merge telemetry
# Mapping: mac -> merged_telemetry
fleet_telemetry = {}
all_mac_appearances = {}  # mac -> list of (r_info, telem)

for r, tmap, err in results:
    short_code = get_router_short_code(r.get("name"), r.get("id"))
    r_name = r.get("name") or f"Router {r.get('id')}"
    for mac, telem in tmap.items():
        if mac not in all_mac_appearances:
            all_mac_appearances[mac] = []
        telem_copy = dict(telem)
        telem_copy["router_id"] = r.get("id")
        telem_copy["router_name"] = r_name
        telem_copy["router_short_name"] = short_code
        all_mac_appearances[mac].append((r, telem_copy))

for mac, appearances in all_mac_appearances.items():
    # If device was seen on multiple routers, it has roaming activity
    is_roaming = len(appearances) > 1
    roaming_short_codes = [get_router_short_code(r.get("name"), r.get("id")) for r, _ in appearances]
    
    # Priority order:
    # 1. Any entry that is 'online'
    # 2. Any entry that is 'recent'
    # 3. 'offline'
    online_entries = [t for _, t in appearances if t.get("state") == "online"]
    recent_entries = [t for _, t in appearances if t.get("state") == "recent"]
    offline_entries = [t for _, t in appearances if t.get("state") == "offline"]

    if online_entries:
        # Choose the most active online entry (lowest idle_time if available, or first)
        best = online_entries[0]
        if len(online_entries) > 1:
            def get_idle(t):
                return mikrotik_client.parse_routeros_duration(t.get("idle_time")) or 999999
            best = min(online_entries, key=get_idle)
        
        final_telem = dict(best)
        final_telem["state"] = "online"
        final_telem["is_online"] = True
        final_telem["is_roaming"] = is_roaming
        final_telem["roaming_routers"] = roaming_short_codes
        if is_roaming:
            # Other routers where seen
            other_codes = [c for c in roaming_short_codes if c != final_telem["router_short_name"]]
            if other_codes:
                final_telem["roaming_label"] = f"Roaming Active on {final_telem['router_short_name']} (also on {', '.join(other_codes)})"
                final_telem["status_label"] = f"Online ({final_telem['router_short_name']} Roaming)"
            else:
                final_telem["roaming_label"] = f"Roaming Active on {final_telem['router_short_name']}"
                final_telem["status_label"] = f"Online ({final_telem['router_short_name']})"
        else:
            final_telem["roaming_label"] = f"Connected on {final_telem['router_short_name']}"
            final_telem["status_label"] = f"Online ({final_telem['router_short_name']})"
    elif recent_entries:
        # Choose the most recently seen entry (lowest last_seen)
        def get_seen(t):
            return mikrotik_client.parse_routeros_duration(t.get("last_seen")) or 999999
        best = min(recent_entries, key=get_seen)
        final_telem = dict(best)
        final_telem["state"] = "recent"
        final_telem["is_online"] = False
        final_telem["is_roaming"] = is_roaming
        final_telem["roaming_routers"] = roaming_short_codes
        if is_roaming:
            final_telem["roaming_label"] = f"Recently on {final_telem['router_short_name']} (Roamed across {', '.join(roaming_short_codes)})"
            final_telem["status_label"] = f"Recently Offline ({final_telem['router_short_name']})"
        else:
            final_telem["roaming_label"] = f"Recently on {final_telem['router_short_name']}"
            final_telem["status_label"] = f"Recently Offline ({final_telem['router_short_name']})"
    else:
        best = offline_entries[0] if offline_entries else {}
        final_telem = dict(best)
        final_telem["state"] = "offline"
        final_telem["is_online"] = False
        final_telem["is_roaming"] = is_roaming
        final_telem["roaming_routers"] = roaming_short_codes
        final_telem["roaming_label"] = "Offline"
        final_telem["status_label"] = "Offline"

    fleet_telemetry[mac] = final_telem

online_total = sum(1 for v in fleet_telemetry.values() if v.get("state") == "online")
roaming_online = sum(1 for v in fleet_telemetry.values() if v.get("state") == "online" and v.get("is_roaming"))
recent_total = sum(1 for v in fleet_telemetry.values() if v.get("state") == "recent")

print(f"Total Fleet MACs: {len(fleet_telemetry)}")
print(f"Total Online MACs: {online_total} (of which {roaming_online} are actively ROAMING across multiple routers!)")
print(f"Total Recent MACs: {recent_total}")

print("\nSample Active Roaming Devices:")
count = 0
for mac, telem in fleet_telemetry.items():
    if telem.get("is_roaming") and telem.get("is_online"):
        print(f"  MAC: {mac} -> {telem.get('status_label')} | IP: {telem.get('live_ip')} | {telem.get('roaming_label')}")
        count += 1
        if count >= 8:
            break
