import os
import sqlite3
import re
import requests

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else 'isp_v2.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit()

session_id = row[0]
session = requests.Session()
session.cookies.set('cybernet_session', session_id)
print('Using session:', session_id[:8] + '...')

# Check special characters in customers
cur = conn.cursor()
c_rows = cur.execute("SELECT id, name, notes FROM customers WHERE status != 'deleted'").fetchall()
special_custs = [r for r in c_rows if any(ch in str(r[1]) or ch in str(r[2]) for ch in ["'", '"', '\\', '\n', '\r'])]
print(f"\nSubscribers with quotes/special chars in name/room: {len(special_custs)}")
for sc in special_custs[:10]:
    print("  ", sc)

BASE = "http://127.0.0.1:9911"
pages = ["/customers", "/dashboard", "/collections", "/balance"]

for p in pages:
    resp = session.get(f"{BASE}{p}")
    html = resp.text
    print(f"\n==========================================")
    print(f"Page {p} (status {resp.status_code}, len {len(html)})")
    print(f"==========================================")

    # 1. Check onclick attributes with openCollectModal
    onclicks = re.findall(r'onclick=["\'](openCollectModal[^"\']*)["\']', html)
    print(f"Found {len(onclicks)} openCollectModal onclick attributes.")
    syntax_issues = []
    for oc in onclicks:
        # Check if parenthesis or quotes are mismatched
        if oc.count("'") % 2 != 0 or oc.count('"') % 2 != 0:
            syntax_issues.append(oc)
    print(f"Broken onclick syntax attributes: {len(syntax_issues)}")
    if syntax_issues:
        for si in syntax_issues[:5]:
            print("  BROKEN ONCLICK:", si)

    # 2. Check modal element IDs referenced in JS
    js_ids = set(re.findall(r"document\.getElementById\(['\"]([a-zA-Z0-9_\-]+)['\"]\)", html))
    print(f"Total getElementById targets in scripts: {len(js_ids)}")
    missing_ids = []
    for jid in js_ids:
        # Check if id="jid" exists in HTML
        if f'id="{jid}"' not in html and f"id='{jid}'" not in html:
            # Check if this id belongs to collect modal
            if 'coll' in jid.lower() or 'modal' in jid.lower():
                missing_ids.append(jid)
    print(f"Missing collect/modal IDs in DOM: {len(missing_ids)}")
    if missing_ids:
        print("  MISSING IDs:", missing_ids)

print("\n--- Testing /api/customers/{id}/billing-breakdown across all customers ---")
all_cids = [r[0] for r in c_rows]
failed_breakdowns = []
for cid in all_cids:
    r = session.get(f"{BASE}/api/customers/{cid}/billing-breakdown")
    if r.status_code != 200:
        failed_breakdowns.append((cid, r.status_code, r.text[:100]))
    else:
        try:
            d = r.json()
            if not d.get("success") and "customer_id" not in d:
                failed_breakdowns.append((cid, 200, "success is false"))
        except Exception as e:
            failed_breakdowns.append((cid, 200, str(e)))

print(f"Tested {len(all_cids)} customers. Failed: {len(failed_breakdowns)}")
if failed_breakdowns:
    for fb in failed_breakdowns[:10]:
        print("  FAIL:", fb)


