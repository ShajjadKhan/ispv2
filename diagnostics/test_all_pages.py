import sqlite3, requests

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
c.execute('SELECT id FROM customers WHERE status = "active" LIMIT 1')
cust_row = c.fetchone()
if cust_row:
    cid = cust_row[0]
    pages.append(f'/customers/{cid}/usage')
    pages.append(f'/customers/{cid}/edit')

cookies = {'cybernet_session': session_id}
for p in pages:
    url = f'http://127.0.0.1:9911{p}'
    try:
        r = requests.get(url, cookies=cookies, timeout=5)
        print(f'{p:<20} -> {r.status_code} ({len(r.content)} bytes)')
        if r.status_code >= 400:
            print('  ERROR BODY:', r.text[:200])
    except Exception as e:
        print(f'{p:<20} -> ERROR: {e}')

