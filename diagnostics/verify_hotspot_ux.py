import requests
import sqlite3

base = 'http://127.0.0.1:9911'

print('--- Test 1: Captive Portal Template UI Elements ---')
r1 = requests.get(base + '/portal')
assert r1.status_code == 200, 'Status %d' % r1.status_code
assert 'boxRequestConfirmation' in r1.text, 'boxRequestConfirmation missing'
assert 'boxRequestFailed' in r1.text, 'boxRequestFailed missing'
assert 'boxSubscriptionExpired' in r1.text, 'boxSubscriptionExpired missing'
assert 'confDispPhone' in r1.text, 'confDispPhone missing'
assert 'confDispTimer' in r1.text, 'confDispTimer missing'
assert 'btn-wa-direct' in r1.text, 'WhatsApp direct button missing'
print('  [PASS] All UI elements present in /portal template')

print('\n--- Test 2: Randomized MAC Rejection ---')
r2 = requests.post(base + '/api/hotspot/submit', json={
    'phone': '0555555555',
    'mac': '02:00:00:11:22:33',
    'ip': '10.40.0.99'
})
assert r2.status_code == 403, 'Expected 403, got %d' % r2.status_code
assert r2.json().get('status') == 'random_mac_blocked', 'Expected random_mac_blocked'
print('  [PASS] Randomized MAC blocked with 403 status')

print('\n--- Test 3: Phone Number Submission & Confirmation Receipt ---')
test_mac = '00:11:22:33:44:99'
r3 = requests.post(base + '/api/hotspot/submit', json={
    'phone': '0599999999',
    'mac': test_mac,
    'ip': '10.40.0.99'
})
assert r3.status_code == 200, 'Expected 200, got %d' % r3.status_code
d3 = r3.json()
assert d3.get('success') is True
assert d3.get('status') == 'pending'
assert 'request_id' in d3, 'Missing request_id'
assert 'phone' in d3, 'Missing phone'
assert 'mac' in d3, 'Missing mac'
assert 'support_phone' in d3, 'Missing support_phone'
assert 'created_at' in d3, 'Missing created_at'
print('  [PASS] Receipt generated: Request #%s, Phone=%s, Support=%s' % (d3.get('request_id'), d3.get('phone'), d3.get('support_phone')))

print('\n--- Test 4: Polling Status Endpoint Metadata ---')
r4 = requests.get(base + '/api/hotspot/check-status', params={
    'mac': test_mac,
    'phone': '0599999999'
})
assert r4.status_code == 200, 'Expected 200, got %d' % r4.status_code
d4 = r4.json()
assert d4.get('status') == 'pending'
assert 'request_id' in d4
assert 'support_phone' in d4
print('  [PASS] check-status poller returns rich status metadata')

# Clean up test request
conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('DELETE FROM connection_requests WHERE UPPER(mac_address) = ?', (test_mac.upper(),))
conn.commit()
conn.close()
print('  [PASS] Test request cleaned up from database')

print('\n--- ALL HOTSPOT CAPTIVE PORTAL TESTS PASSED (100% SUCCESS) ---')
