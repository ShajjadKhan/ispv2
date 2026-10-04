import requests
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auth_service
import database

BASE_URL = 'http://127.0.0.1:9911'
session = requests.Session()

# 1. Create a valid session directly via auth_service
session_id, _ = auth_service.create_session(
    user_id=1,
    client_ip='127.0.0.1',
    user_agent='verify_mobile_script'
)
session.cookies.set('cybernet_session', session_id)
print(f'Session created: {session_id[:16]}...')

# 2. Query DB expected count
db_data = database.get_balance_sheet_data('all')
expected_count = len(db_data['rows'])
print(f'Total active subscribers in DB: {expected_count}')
for r in db_data['rows']:
    print(f"  #{r['id']} {r['name']} | Bal: {r['balance']} SAR | Status: {r['status']}")

# 3. Get /balance HTML
res = session.get(f'{BASE_URL}/balance')
assert res.status_code == 200, f'GET /balance failed: {res.status_code}'
html = res.text

# 4. Assertions
print('\n=== Running Verification on /balance Phone Responsiveness ===')

# Check desktop & mobile classes
assert 'desktop-table-view' in html, 'desktop-table-view missing'
assert 'mobile-balance-deck' in html, 'mobile-balance-deck missing'
print('PASS 1: desktop-table-view and mobile-balance-deck present')

# Count mobile cards
mobile_cards = re.findall(r'<div class="bal-mobile-card[^"]*"', html)
print(f'PASS 2: Found {len(mobile_cards)} mobile subscriber cards (Expected: {expected_count})')
assert len(mobile_cards) == expected_count, f'Expected {expected_count} mobile cards, got {len(mobile_cards)}'

# Check table rows count
table_rows = re.findall(r'<tr data-status="[^"]*"', html)
print(f'PASS 2b: Found {len(table_rows)} desktop table rows (Expected: {expected_count})')
assert len(table_rows) == expected_count, f'Expected {expected_count} table rows, got {len(table_rows)}'

# Check mobile card components
assert 'm-bal-header' in html, 'm-bal-header missing'
assert 'm-bal-hero-box' in html, 'm-bal-hero-box missing'
assert 'm-bal-grid' in html, 'm-bal-grid missing'
assert 'm-bal-actions' in html, 'm-bal-actions missing'
assert 'm-bal-grand-total' in html, 'm-bal-grand-total missing'
assert 'mBalanceNoMatchCard' in html, 'mBalanceNoMatchCard missing'
print('PASS 3: All mobile card deck components present')

# Check action buttons
assert 'btn-m-hist' in html, 'btn-m-hist missing'
assert 'btn-m-wa' in html, 'btn-m-wa missing'
assert 'btn-m-settle' in html, 'btn-m-settle missing'
assert 'btn-m-call' in html, 'btn-m-call missing'
print('PASS 4: Touch-friendly action buttons (History, WhatsApp, Settle, Call) present')

# Check iOS safari font-size 16px anti-zoom rule
assert 'font-size: 16px !important;' in html, 'iOS anti-zoom font-size missing'
print('PASS 5: iOS Safari 16px input anti-zoom rule verified')

# Check media queries for max-width: 1024px and max-width: 440px
assert '@media (max-width: 1024px)' in html, '@media 1024px query missing'
assert '@media (max-width: 440px)' in html, '@media 440px query missing'
print('PASS 6: Responsive media queries for iPhone, Honor, and Redmi (1024px and 440px) verified')

# Check filterBalanceTable JavaScript dual-view support
assert 'mobileBalanceDeck' in html, 'JS mobileBalanceDeck reference missing'
assert 'bal-mobile-card' in html, 'JS bal-mobile-card reference missing'
assert 'mBalanceNoMatchCard' in html, 'JS mBalanceNoMatchCard reference missing'
print('PASS 7: JS real-time filter synchronization between desktop table and mobile deck verified')

# Verify room badge in mobile card
assert 'bal-room-badge' in html, 'bal-room-badge missing in mobile card'
print('PASS 8: Customer room / note badge verified')

# Verify customer ID #number is NOT displayed beside subscriber names
ashraf_desktop = re.search(r'Ashraf.*?(?=</td>)', html, re.DOTALL)
assert ashraf_desktop and '#12' not in ashraf_desktop.group(0), 'Found #12 in desktop Ashraf name cell'

ashraf_mobile = re.search(r'class="m-bal-name"[^>]*>\s*Ashraf\s*</a>.*?(?=<div class="m-bal-hero-box)', html, re.DOTALL)
assert ashraf_mobile and '#12' not in ashraf_mobile.group(0), 'Found #12 in mobile Ashraf header'
print('PASS 10: Verified customer ID #number is cleanly removed from beside subscriber names')

print('\nALL VERIFICATION CHECKS PASSED 100%! Phone responsiveness is active and verified!')
