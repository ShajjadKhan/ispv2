import requests
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auth_service
import database

BASE_URL = 'http://127.0.0.1:9911'
session = requests.Session()
sid, _ = auth_service.create_session(1, '127.0.0.1', 'test_collect_api')
session.cookies.set('cybernet_session', sid)

# Check customer 2 initial balance
b_before = database.get_balance_sheet_data('all')
c2_before = next(r for r in b_before['rows'] if r['id'] == 2)
print(f"Before: paid={c2_before['total_paid']} bal={c2_before['balance']}")

# Post 1.00 SAR collection
payload = {
    'customer_id': 2,
    'amount': 1.0,
    'payment_type': 'cash',
    'collector': 'Test Script',
    'notes': 'Automated API Verification'
}
res = session.post(f'{BASE_URL}/api/balance/collect', json=payload)
assert res.status_code == 200, f'Collect failed: {res.text}'
json_data = res.json()
print('Collect response:', json_data)
assert json_data.get('success') is True
col_id = json_data.get('collection_id')

# Verify in balance sheet
b_after = database.get_balance_sheet_data('all')
c2_after = next(r for r in b_after['rows'] if r['id'] == 2)
print(f"After: paid={c2_after['total_paid']} bal={c2_after['balance']}")
assert c2_after['total_paid'] == round(c2_before['total_paid'] + 1.0, 2)
print('Assertion passed: Total paid increased by exactly 1.00 SAR!')

# Clean up test collection
with database.get_db() as conn:
    conn.execute('DELETE FROM collections WHERE id = ?', (col_id,))
    conn.commit()

# Verify balance restored
b_clean = database.get_balance_sheet_data('all')
c2_clean = next(r for r in b_clean['rows'] if r['id'] == 2)
assert c2_clean['total_paid'] == c2_before['total_paid']
print('Test collection cleanly purged. Verification 100% COMPLETE & CLEAN!')
