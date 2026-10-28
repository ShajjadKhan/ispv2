import sqlite3
import requests

con = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
cur = con.cursor()
cur.execute("SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1")
row = cur.fetchone()
con.close()

if not row:
    print("No session found")
    exit(1)

session_id = row[0]
r = requests.get('http://127.0.0.1:9911/approvals', headers={'Cookie': f'cybernet_session={session_id}'})
with open('/home/tserver/isp_v2/scratch_approvals.html', 'w', encoding='utf-8') as f:
    f.write(r.text)
print("Saved /home/tserver/isp_v2/scratch_approvals.html, bytes:", len(r.text))
