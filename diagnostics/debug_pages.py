import sqlite3
import requests
import time

conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit()

session_id = row[0]
print('Using session:', session_id[:8] + '...')

pages = [
    '/',
    '/customers',
    '/balance',
    '/balance/report',
    '/approvals',
    '/collections',
    '/whatsapp',
    '/gateway',
    '/olt',
    '/packages',
    '/resellers',
    '/hotspot',
    '/portal'
]
c.execute("SELECT id FROM customers WHERE status = 'active' LIMIT 1")
cust_row = c.fetchone()
if cust_row:
    cid = cust_row[0]
    pages.append(f'/customers/{cid}/edit')
    pages.append(f'/customers/{cid}/usage')

cookies = {'cybernet_session': session_id}
for p in pages:
    url = f'http://127.0.0.1:9911{p}'
    t0 = time.time()
    try:
        r = requests.get(url, cookies=cookies, timeout=15)
        elapsed = time.time() - t0
        print(f'{p:<25} -> {r.status_code} ({len(r.content)} bytes) in {elapsed:.2f}s')
    except Exception as e:
        elapsed = time.time() - t0
        print(f'{p:<25} -> ERROR: {e} after {elapsed:.2f}s')
