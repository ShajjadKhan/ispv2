import sqlite3, requests, re

conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
s_id = c.fetchone()[0]

r = requests.get('http://127.0.0.1:9911/gateway', cookies={'cybernet_session': s_id})
matches = re.findall(r'Status:[\s\S]*?(ONLINE|OFFLINE)', r.text)
print("Router statuses found on /gateway:", matches)
