import requests
import sqlite3
import re

conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
sid = c.fetchone()[0]
s = requests.Session()
s.cookies.set('cybernet_session', sid)

pages = ['/customers', '/dashboard', '/collections', '/balance']

for p in pages:
    r = s.get('http://127.0.0.1:9911' + p)
    html = r.text
    print(f"=== Testing {p} (status: {r.status_code}) ===")
    
    # Check for unquoted None or undefined syntax errors in scripts
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
    for idx, sc in enumerate(scripts):
        for line in sc.splitlines():
            if re.search(r'(:|,|=|\()\s*None\b', line):
                print(f"  [POTENTIAL PYTHON None LEAK] script {idx}: {line.strip()[:120]}")
            if re.search(r'(:|,|=|\()\s*False\b', line) and 'false' not in line.lower():
                print(f"  [POTENTIAL PYTHON False LEAK] script {idx}: {line.strip()[:120]}")
            if re.search(r'(:|,|=|\()\s*True\b', line) and 'true' not in line.lower():
                print(f"  [POTENTIAL PYTHON True LEAK] script {idx}: {line.strip()[:120]}")

    # Check for buttons with onclick
    collect_btns = re.findall(r'<button[^>]*onclick="([^"]*collect[^"]*)"[^>]*>(.*?)</button>', html, re.IGNORECASE | re.DOTALL)
    print(f"  Found {len(collect_btns)} collect buttons with onclick:")
    for oc, inner in collect_btns[:5]:
        clean_inner = re.sub(r'\s+', ' ', inner).strip()
        print(f"    onclick: {oc[:70]} | label: {clean_inner[:40]}")

print("\nDone inspect_js_syntax.py")
