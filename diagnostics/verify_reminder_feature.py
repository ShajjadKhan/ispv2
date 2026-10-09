import sqlite3
import requests
import json

conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit()

session_id = row[0]

for name in ['MILLAT', 'TAWHID']:
    c_row = c.execute('SELECT id, name, phone, notes, due_date, expiry_date, credit_balance FROM customers WHERE name LIKE ?', (f'%{name}%',)).fetchone()
    if not c_row:
        print(f'Customer {name} not found')
        continue
    cid, cname, phone, notes, due, exp, bal = c_row
    print('===============================================================')
    print(f'Customer: #{cid} {cname} | Phone: {phone} | Due: {due} | Notes: {notes} | Balance: {bal}')
    r = requests.post(
        'http://127.0.0.1:9911/api/balance/send-reminder',
        cookies={'cybernet_session': session_id},
        json={'customer_id': cid, 'send_direct': True}
    )
    print('HTTP Status:', r.status_code)
    data = r.json()
    print('Success:', data.get('success'))
    print('Phone:', data.get('phone'))
    print('WhatsApp Direct URL generated:', bool(data.get('whatsapp_url')))
    print('--- Generated Message Text ---')
    print(data.get('message_text', ''))
    print('------------------------------')
