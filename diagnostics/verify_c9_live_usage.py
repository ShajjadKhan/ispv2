import sqlite3
import requests

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print("No active admin session found!")
    exit(1)

session_id = row[0]
print(f"Using active admin session: {session_id[:8]}...")
s = requests.Session()
s.cookies.set('cybernet_session', session_id)

# 1. HTML View
r1 = s.get('http://127.0.0.1:9911/customers/9/usage')
print(f"GET /customers/9/usage -> {r1.status_code} ({len(r1.text)} bytes)")
print(" - PPPoE Meter found in HTML:", 'PPPoE Router Hardware Meter' in r1.text)
print(" - LIVE TUNNEL CONNECTED found:", 'LIVE TUNNEL CONNECTED' in r1.text)
print(" - B1G7D found:", 'B1G7D' in r1.text)

# 2. JSON API
r2 = s.get('http://127.0.0.1:9911/api/customers/9/usage')
print(f"\nGET /api/customers/9/usage -> {r2.status_code}")
data = r2.json()
print(" - is_online:", data.get('is_online'))
print(" - total_download:", data.get('total_download'))
print(" - total_upload:", data.get('total_upload'))
print(" - total_traffic:", data.get('total_traffic'))
print(" - pppoe_session:", data.get('pppoe_session', {}).get('interface'), data.get('pppoe_session', {}).get('total_formatted'))
print(" - devices:", len(data.get('devices', [])))
for d in data.get('devices', []):
    print(f"   * {d.get('friendly_name')} [{d.get('mac_address')}]: {d.get('formatted_total')} (Online: {d.get('is_online')})")

# 3. WhatsApp dispute proof
r3 = s.get('http://127.0.0.1:9911/api/customers/9/usage/whatsapp')
print(f"\nGET /api/customers/9/usage/whatsapp -> {r3.status_code}")
print(" - WhatsApp dispute proof generated successfully:", r3.json().get('success'))

# 4. Check other PPPoE customers
print("\n=== All PPPoE Customers in DB ===")
c.execute("SELECT id, name, connection_type, pppoe_username, pppoe_profile FROM customers WHERE connection_type IN ('pppoe', 'both') OR (pppoe_username IS NOT NULL AND TRIM(pppoe_username) != '')")
pp_rows = c.fetchall()
for p in pp_rows:
    print(f"Customer #{p[0]}: {p[1]} ({p[2]}) - User: {p[3]}")
    r_cust = s.get(f'http://127.0.0.1:9911/api/customers/{p[0]}/usage')
    if r_cust.status_code == 200:
        c_data = r_cust.json()
        print(f"   Usage -> Total: {c_data.get('total_traffic')}, Down: {c_data.get('total_download')}, Up: {c_data.get('total_upload')}, Online: {c_data.get('is_online')}")

