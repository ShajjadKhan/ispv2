#!/usr/bin/env python3
import sqlite3
import requests

conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit(1)

session_id = row[0]
print(f"Using session: {session_id[:8]}...")
session = requests.Session()
session.cookies.set('cybernet_session', session_id)

# 1. Test /api/hotspot/sharing-suspects
api_res = session.get("http://127.0.0.1:9911/api/hotspot/sharing-suspects")
print(f"/api/hotspot/sharing-suspects -> {api_res.status_code}: {api_res.json()}")
assert api_res.status_code == 200 and api_res.json().get("success"), "API sharing-suspects failed"
print("  [✓] /api/hotspot/sharing-suspects returned 200 OK with success=True!")

# 2. Test /customers HTML
cust_res = session.get("http://127.0.0.1:9911/customers")
print(f"/customers -> {cust_res.status_code}")
assert cust_res.status_code == 200
assert "badge-hotspot-sharing" in cust_res.text, "badge-hotspot-sharing missing from /customers CSS"
assert "data-sharing=" in cust_res.text, "data-sharing missing from /customers rows"
print("  [✓] /customers contains data-sharing attributes and badge-hotspot-sharing CSS!")

# 3. Test /customers/2/edit HTML
edit_res = session.get("http://127.0.0.1:9911/customers/2/edit")
print(f"/customers/2/edit -> {edit_res.status_code}")
assert edit_res.status_code == 200
assert "Hotspot Sharing" in edit_res.text, "Hotspot Sharing missing from /customers/2/edit"
assert "sideHotspotSharing" in edit_res.text, "sideHotspotSharing missing from /customers/2/edit"
print("  [✓] /customers/2/edit contains Hotspot Sharing Live Account Snapshot indicator!")

# 4. Test Dashboard / HTML
dash_res = session.get("http://127.0.0.1:9911/")
print(f"/ (Dashboard) -> {dash_res.status_code}")
assert dash_res.status_code == 200
assert "badge-hotspot-sharing" in dash_res.text, "badge-hotspot-sharing missing from dashboard CSS"
print("  [✓] / (Dashboard) contains badge-hotspot-sharing styling!")

print("\nALL HOTSPOT SHARING VERIFICATION CHECKS PASSED 100%!")
