import sqlite3
import requests
import re

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('ERROR: No active session')
    exit(1)
sid = row[0]

r = requests.get('http://127.0.0.1:9911/balance', cookies={'cybernet_session': sid})
print(f'HTTP Status: {r.status_code}, Length: {len(r.text)} bytes')

terms = ['mobile-balance-deck', 'm-bal-hero-box', 'm-bal-grid', 'bal-room-badge', 'bal-cust-sub', 'bal-cust-cell', 'balanceTable']
for t in terms:
    print(f'  "{t}": {t in r.text}')

cust_cells = re.findall(r'<td class="bal-cust-cell">[\s\S]*?</td>', r.text)
print(f'Total Customer Cells in Table: {len(cust_cells)}')
if cust_cells:
    print('\n--- Sample Customer Cell 1 ---')
    print(cust_cells[0])
    print('\n--- Sample Customer Cell 2 ---')
    if len(cust_cells) > 1:
        print(cust_cells[1])

# Check for Hasib (rank 1 debt)
if 'Hasib' in r.text:
    print('\nPASS: Hasib found in balance sheet!')
if 'Mohammad Arafat' in r.text:
    print('PASS: Mohammad Arafat found in balance sheet!')
