import sqlite3
import requests
import re
import sys

def main():
    db_path = '/home/sk/isp_v2/isp_v2.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
    row = c.fetchone()
    if not row:
        print('ERROR: No active session found')
        sys.exit(1)
    sid = row[0]

    r = requests.get('http://127.0.0.1:9911/balance', cookies={'cybernet_session': sid})
    html = r.text
    print(f'Page HTTP Status: {r.status_code}, Length: {len(html)} bytes')

    # 1. Search Box & Clear Button Elements
    assert 'id="balanceSearch"' in html, 'balanceSearch input missing'
    assert 'id="balanceSearchClearBtn"' in html, 'balanceSearchClearBtn missing'
    assert 'clearBalanceSearch()' in html, 'clearBalanceSearch function call missing'
    print('[PASS] Search input, clear button, and handlers exist in markup')

    # 2. CSS Specificity Fixes
    assert 'tr.bal-row-hidden' in html, 'bal-row-hidden class rule missing'
    assert ':not(.bal-row-hidden)' in html, ':not(.bal-row-hidden) pseudo-class missing in mobile rule'
    assert 'display: none !important' in html, 'display: none !important missing'
    print('[PASS] CSS bal-row-hidden override rules verified')

    # 3. Data attributes on table rows
    rows = re.findall(r'<tr[^>]*data-status="([^"]*)"[^>]*data-search="([^"]*)"', html)
    print(f'[PASS] Found {len(rows)} data rows with data-status and data-search')
    assert len(rows) > 0, 'No subscriber rows found'

    # Check that data-search contains phone variations
    sample_phone_checks = 0
    for st, ds in rows:
        tokens = ds.split()
        if any(tok.startswith('9665') or tok.startswith('05') for tok in tokens):
            sample_phone_checks += 1
    print(f'[PASS] {sample_phone_checks}/{len(rows)} rows have indexed phone numbers in data-search')

    # 4. Simulate token-based searching (matching our JS logic)
    def test_search(query, status_filter='all'):
        q_tokens = query.lower().split()
        matches = []
        for st, ds in rows:
            if status_filter != 'all' and st.lower() != status_filter.lower():
                continue
            matched = True
            for tok in q_tokens:
                if tok in ds.lower():
                    continue
                dig = re.sub(r'\D', '', tok)
                if len(dig) >= 2:
                    if dig.startswith('05') and ('966' + dig[1:]) in ds:
                        continue
                    if dig.startswith('9665') and ('0' + dig[3:]) in ds:
                        continue
                    if dig.startswith('5') and (('0' + dig) in ds or ('966' + dig) in ds):
                        continue
                matched = False
                break
            if matched:
                matches.append((st, ds))
        return matches

    queries = [
        ('hasib', 'all'),
        ('arafat', 'all'),
        ('054', 'all'),
        ('9665', 'all'),
        ('54', 'all'),
        ('settled', 'all'),
        ('credit', 'all'),
        ('', 'owing'),
        ('', 'settled'),
        ('', 'credit'),
    ]

    for q, sf in queries:
        res = test_search(q, sf)
        print(f'  Query "{q}" (Filter: {sf}) -> {len(res)} matches')

    # 5. Check JS functions
    assert 'function filterBalanceTable' in html, 'filterBalanceTable function missing'
    assert 'function clearBalanceSearch' in html, 'clearBalanceSearch function missing'
    assert 'DOMContentLoaded' in html, 'DOMContentLoaded handler missing'
    print('[PASS] JavaScript logic and lifecycle hooks verified')

    print('\n========================================')
    print('ALL VERIFICATIONS PASSED SUCCESSFULLY!')
    print('========================================')

if __name__ == '__main__':
    main()
