import sqlite3, requests, re

conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit()

session_id = row[0]
cookies = {'cybernet_session': session_id}

res = requests.get('http://127.0.0.1:9911/gateway', cookies=cookies, timeout=10)
print(f"GET /gateway: status {res.status_code}, len {len(res.content)}")

for router_name in ["Cybernet Router-20", "Cybernet Router-30", "Cybernet Router-10"]:
    if router_name in res.text:
        print(f"Found {router_name} in gateway page: YES")
    else:
        print(f"Found {router_name} in gateway page: NO")

online_matches = re.findall(r'Status:\s*ONLINE', res.text)
print(f"Total 'Status: ONLINE' matches: {len(online_matches)}")

# Also test selecting router 3
res_r3 = requests.get('http://127.0.0.1:9911/gateway?router_id=3', cookies=cookies, timeout=10)
print(f"GET /gateway?router_id=3: status {res_r3.status_code}, len {len(res_r3.content)}")
print(f"Router-10 details present in R3 view: {'RB760iGS' in res_r3.text or 'Router-10' in res_r3.text}")
