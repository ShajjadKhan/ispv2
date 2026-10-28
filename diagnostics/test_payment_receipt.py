import sqlite3
import requests
import json

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
s_id = conn.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1').fetchone()[0]

payload = {
    'amount': 1.0,
    'notes': 'Test Receipt Delivery via Express POS',
    'send_whatsapp': True
}

res = requests.post(
    'http://127.0.0.1:9911/api/customers/2/record-payment',
    json=payload,
    cookies={'cybernet_session': s_id}
)

print('HTTP Status:', res.status_code)
print('Response JSON:', json.dumps(res.json(), indent=2))
