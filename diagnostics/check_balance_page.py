import sqlite3
import requests
import re
import os

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else 'isp_v2.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit(1)

session_id = row[0]
session = requests.Session()
session.cookies.set('cybernet_session', session_id)

res = session.get('http://127.0.0.1:9911/balance')
html = res.text
print('Page status:', res.status_code)
print('Page length:', len(html))

# Extract all <script> tags
scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
print(f'Found {len(scripts)} script tags')

for idx, s in enumerate(scripts):
    fname = f'/tmp/script_{idx}.js'
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(s)
    print(f'Script {idx}: saved {len(s)} bytes, {len(s.splitlines())} lines to {fname}')

# Check for duplicate declarations in main_script
if len(scripts) > 1:
    main_script = scripts[1]
    lines = main_script.splitlines()
    decls = {}
    for i, l in enumerate(lines):
        m = re.match(r'^\s*(?:let|const)\s+([a-zA-Z0-9_$]+)\s*=', l)
        if m:
            varname = m.group(1)
            decls.setdefault(varname, []).append(i + 1)

    for v, lnums in decls.items():
        if len(lnums) > 1:
            print(f'DUPLICATE DECLARATION: {v} on lines {lnums}')

