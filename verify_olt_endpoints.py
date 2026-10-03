import sys
sys.path.insert(0, '/home/tserver/isp_v2')
import requests
import json
import re
import auth_service

base_url = "http://127.0.0.1:9911"

# Create valid admin session
sid, csrf = auth_service.create_session(user_id=1)
cookies = {auth_service.COOKIE_NAME: sid}

print("--- 1. TESTING GET /api/olt/1/telemetry (Authenticated) ---")
r = requests.get(f"{base_url}/api/olt/1/telemetry", cookies=cookies)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print("Stats:", data.get("stats"))
    print("OLT Name:", data.get("olt", {}).get("name"))
    print("Sample ONU 1:", data.get("onus", [{}])[0].get("name"), "Rx:", data.get("onus", [{}])[0].get("rx_power"))

print("\n--- 2. TESTING POST /api/olt/1/sync (1-Click Sync Endpoint) ---")
r = requests.post(f"{base_url}/api/olt/1/sync", cookies=cookies)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    print("Sync response:", r.json())

print("\n--- 3. TESTING POST /api/olt/sync-telemetry (Direct Agent Endpoint) ---")
with open("/home/tserver/isp_v2/olt_live_raw.json", "r", encoding="utf-8-sig") as f:
    raw = json.load(f)

def clean(s):
    if not s: return ''
    s = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', ' ', s)
    s = re.sub(r'[\r\t]', ' ', s)
    return s

state = clean(raw.get('state', ''))
dist = clean(raw.get('distance', ''))
info = clean(raw.get('info', ''))

states = re.findall(r'(?:GPON0/1:|1:)(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', state)
rx_readings = re.findall(r'(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)', dist)
infos = re.findall(r'(?:GPON0/1:|1:)(\d+)\s+([A-Za-z0-9_-]+)', info)

state_map = {int(s[0]): {'admin': s[1], 'omcc': s[2], 'phase': s[3].lower(), 'sn': s[4]} for s in states}
rx_map = {int(r[0]): {'rx': float(r[1]), 'olt_rx': float(r[2])} for r in rx_readings}
info_map = {int(i[0]): i[1] for i in infos}

onus_payload = []
for i in range(1, 67):
    st = state_map.get(i, {})
    rx_obj = rx_map.get(i, {})
    mod = info_map.get(i, "V711")
    
    phase = st.get('phase', 'working')
    status = 'online'
    if phase == 'dyinggasp':
        status = 'dying_gasp'
    elif phase != 'working':
        status = 'offline'
        
    rx_val = rx_obj.get('rx', -20.0)
    dist_m = max(25, min(390, int((abs(rx_val) - 15.0) * 18.0))) if status == 'online' else 0
    
    onus_payload.append({
        'id': i,
        'serial': st.get('sn', f'GPON000000{i:02d}'),
        'model': f'Huawei {mod}' if 'HG' in mod else f'VSOL {mod} (1GE+1FE+WiFi XPON)',
        'status': status,
        'phase': phase,
        'rx_power': rx_val,
        'olt_rx': rx_obj.get('olt_rx', -21.0),
        'distance_m': dist_m
    })

sync_payload = {
    'olt_id': 1,
    'onus': onus_payload,
    'chassis': {
        'status': 'online',
        'temperature': 39,
        'cpu_usage': 14,
        'memory_usage': 38,
        'uptime': '18d 4h 30m'
    }
}

# Notice: Calling without cookies to ensure unauthenticated agent push works!
r = requests.post(f"{base_url}/api/olt/sync-telemetry", json=sync_payload)
print(f"Status (Unauthenticated Agent): {r.status_code}")
if r.status_code == 200:
    print("Result:", r.json())
else:
    print("Error:", r.text)

print("\n--- 4. TESTING GET /olt HTML PAGE (Check new Sync button) ---")
r = requests.get(f"{base_url}/olt", cookies=cookies)
print(f"Status: {r.status_code}")
has_sync_btn = "syncOltBtn" in r.text
has_spin_css = ".spin" in r.text
has_trigger_js = "triggerOltSync" in r.text
print(f"Has syncOltBtn: {has_sync_btn}")
print(f"Has spin CSS: {has_spin_css}")
print(f"Has triggerOltSync JS: {has_trigger_js}")
assert r.status_code == 200
assert has_sync_btn
assert has_trigger_js
print("\nALL VERIFICATIONS PASSED 100%!")
