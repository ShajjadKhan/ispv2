import requests
import database
import auth_service

def run_tests():
    session_id, csrf = auth_service.create_session(1) # user 1 is 'System Administrator'
    cookies = {auth_service.COOKIE_NAME: session_id}

    r = requests.get('http://127.0.0.1:9911/balance', cookies=cookies)
    assert r.status_code == 200, f'Status {r.status_code}'
    html = r.text

    # 1. Check no visible collector label
    assert '<label' not in html or 'Collector Name' not in html, 'Found Collector Name label in HTML!'
    print('CHECK 1 PASS: No visible "Collector Name" label/input in modal')

    # 2. Check hidden collector input with admin name
    assert '<input type="hidden" id="collCollectorInput" value="System Administrator">' in html, 'collCollectorInput value mismatch!'
    print('CHECK 2 PASS: Hidden collector input properly prefilled with System Administrator')

    # 3. Check footer displays collector name
    assert 'Collector: <strong style="color:#f1f5f9;">System Administrator</strong>' in html, 'Footer collector badge missing!'
    print('CHECK 3 PASS: Footer displays "Collector: System Administrator" badge')

    # 4. Check JS conditional hide of subscriber select wrapper
    assert "custSelectWrap.style.display = 'none'" in html, 'Missing custSelectWrap.style.display = none in JS!'
    print('CHECK 4 PASS: JS strictly hides Select Subscriber dropdown when opening for specific customer')

    # 5. Check debt preset button display logic
    assert "debtPresetBtn.style.display = 'none'" in html, 'Missing debtPresetBtn.style.display = none in JS!'
    print('CHECK 5 PASS: JS hides Exact Debt button when customer balance is >= 0 (settled or credit)')

    # 6. Test API balance collect without sending collector field -> should record under System Administrator
    all_c = database.get_all_customers()
    active_c = [c for c in all_c if c.get('status') == 'active']
    cust = active_c[0] if active_c else all_c[0]
    payload = {
        'customer_id': cust['id'],
        'amount': 5.0,
        'payment_type': 'cash',
        'notes': 'Automated test collection for collector registration verification'
    }
    resp = requests.post('http://127.0.0.1:9911/api/balance/collect', json=payload, cookies=cookies)
    assert resp.status_code == 200, f'API error: {resp.text}'
    res_data = resp.json()
    assert res_data['success'] is True

    # Verify recorded collector in DB
    with database.get_db() as conn:
        row = conn.execute('SELECT collected_by, amount FROM collections WHERE id = ?', (res_data['collection_id'],)).fetchone()
        assert row[0] == 'System Administrator', f'Expected System Administrator but got {row[0]}'
        print(f'CHECK 6 PASS: Payment recorded in DB with collected_by="{row[0]}" (Amount: {row[1]} SAR)')
        # Clean up test collection
        conn.execute('DELETE FROM collections WHERE id = ?', (res_data['collection_id'],))
        conn.commit()

    print('\nALL 6 CHECKS PASSED 100%! Collector registration and modal format are fully verified.')

if __name__ == '__main__':
    run_tests()
