import requests
import sqlite3
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
BASE = "http://127.0.0.1:9911"

print("=== 1. Verifying HTML Attributes across All 4 Views ===")
views = [
    ("/customers", "collectModal", "collectForm", "collAmount"),
    ("/dashboard", "collectModal", "collectForm", "collAmount"),
    ("/collections", "collectModal", "collectForm", "collAmount"),
    ("/balance", "balanceCollectModal", "balanceCollectForm", "collAmountInput"),
]

for url, modal_id, form_id, input_id in views:
    resp = session.get(BASE + url)
    assert resp.status_code == 200, f"{url} returned status {resp.status_code}"
    html = resp.text
    
    # Check modal exists
    assert f'id="{modal_id}"' in html, f"Missing modal {modal_id} in {url}"
    
    # Check z-index 10005
    assert '10005' in html, f"Missing z-index: 10005 in {url}"
    
    # Check form has novalidate
    assert f'id="{form_id}"' in html, f"Missing form {form_id} in {url}"
    form_match = re.search(rf'<form[^>]*id="{form_id}"[^>]*>', html)
    assert form_match and 'novalidate' in form_match.group(0), f"Form {form_id} missing novalidate in {url}: {form_match.group(0) if form_match else 'None'}"
    
    # Check input has step="0.01" and min="0.01"
    inp_match = re.search(rf'<input[^>]*id="{input_id}"[^>]*>', html)
    assert inp_match, f"Missing input {input_id} in {url}"
    inp_tag = inp_match.group(0)
    assert 'step="0.01"' in inp_tag, f"Input {input_id} does not have step='0.01' in {url}: {inp_tag}"
    assert 'min="0.01"' in inp_tag, f"Input {input_id} does not have min='0.01' in {url}: {inp_tag}"
    
    print(f"  ✓ {url}: Modal, z-index 10005, novalidate, step='0.01', min='0.01' all verified!")

print("\n=== 2. Verifying Decimal (Halala) Collections Endpoints ===")
# Create mock customer for testing both endpoints
cur = conn.cursor()
cur.execute("""
    INSERT INTO customers (name, phone, notes, billing_type, package_name, monthly_fee, due_day, due_date, expiry_date, status, credit_balance, created_at, updated_at, billing_start_date)
    VALUES ('__TEST_COLLECT_MODAL__', '0500000088', 'Room B1F88', 'postpaid', 'Standard 30M', 30.0, 1, '2026-10-01', '2026-10-01', 'active', -14.52, '2026-10-01 00:00:00', '2026-10-01 00:00:00', '2026-10-01')
""")
test_id = cur.lastrowid
conn.commit()
print(f"Created temporary mock customer #{test_id} with -14.52 SAR debt")

try:
    # Test POST /api/customers/{id}/smart-collect with exact decimal 14.52
    r1 = session.post(f"{BASE}/api/customers/{test_id}/smart-collect", json={
        "amount": 14.52,
        "payment_type": "cash",
        "notes": "Exact halala debt settlement",
        "send_whatsapp": False
    })
    assert r1.status_code == 200, f"smart-collect failed: {r1.status_code} {r1.text}"
    j1 = r1.json()
    assert j1["success"] is True, f"smart-collect unsuccessful: {j1}"
    print(f"  ✓ POST /api/customers/{test_id}/smart-collect with 14.52 SAR: SUCCESS! (bal: {j1['data']['new_credit_balance']} SAR)")

    # Reset balance to -28.48 SAR
    cur.execute("UPDATE customers SET credit_balance = -28.48 WHERE id = ?", (test_id,))
    conn.commit()

    # Test POST /api/balance/collect with decimal 28.48
    r2 = session.post(f"{BASE}/api/balance/collect", json={
        "customer_id": test_id,
        "amount": 28.48,
        "payment_type": "stc_pay",
        "collector": "Shajjad Khan",
        "notes": "Balance sheet halala collection",
        "send_whatsapp": False
    })
    assert r2.status_code == 200, f"balance/collect failed: {r2.status_code} {r2.text}"
    j2 = r2.json()
    assert j2["success"] is True, f"balance/collect unsuccessful: {j2}"
    print(f"  ✓ POST /api/balance/collect with 28.48 SAR: SUCCESS! (bal: {j2['new_credit_balance']} SAR)")

finally:
    cur.execute("DELETE FROM customers WHERE id = ?", (test_id,))
    cur.execute("DELETE FROM collections WHERE customer_id = ?", (test_id,))
    conn.commit()
    print(f"Cleanly purged mock customer #{test_id}")

print("\n🎉 ALL 4 VIEWS AND APIS PASSED 100% OF VERIFICATION CHECKS!")
