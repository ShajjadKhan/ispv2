import requests
import database
import auth_service

def test_dynamic_collectors():
    print("=== Testing Dynamic Multi-User / Manager Collector Recording ===")

    # 1. Test Admin (User 1)
    sess_admin, _ = auth_service.create_session(1)
    cookies_admin = {auth_service.COOKIE_NAME: sess_admin}
    
    r_admin = requests.get('http://127.0.0.1:9911/balance', cookies=cookies_admin)
    assert 'Collector: <strong style="color:#f1f5f9;">System Administrator</strong>' in r_admin.text
    print("✓ Admin view renders 'Collector: System Administrator'")

    cust = database.get_all_customers()[0]
    payload1 = {'customer_id': cust['id'], 'amount': 1.0, 'payment_type': 'cash', 'notes': 'Test admin collect'}
    resp1 = requests.post('http://127.0.0.1:9911/api/balance/collect', json=payload1, cookies=cookies_admin).json()
    assert resp1['success'] is True
    col1_id = resp1['collection_id']
    
    with database.get_db() as conn:
        c1 = conn.execute("SELECT collected_by FROM collections WHERE id = ?", (col1_id,)).fetchone()
        assert c1[0] == "System Administrator", f"Expected System Administrator, got {c1[0]}"
        print(f"✓ Admin collection registered under: '{c1[0]}'")
        conn.execute("DELETE FROM collections WHERE id = ?", (col1_id,))
        conn.commit()

    # 2. Test Existing Manager: Riyad Hossain (User 14)
    sess_mgr, _ = auth_service.create_session(14)
    cookies_mgr = {auth_service.COOKIE_NAME: sess_mgr}
    
    r_mgr = requests.get('http://127.0.0.1:9911/balance', cookies=cookies_mgr)
    assert 'Collector: <strong style="color:#f1f5f9;">Riyad Hossain</strong>' in r_mgr.text
    print("✓ Manager view renders 'Collector: Riyad Hossain'")

    payload2 = {'customer_id': cust['id'], 'amount': 1.0, 'payment_type': 'stc_pay', 'notes': 'Test manager collect'}
    resp2 = requests.post('http://127.0.0.1:9911/api/balance/collect', json=payload2, cookies=cookies_mgr).json()
    assert resp2['success'] is True
    col2_id = resp2['collection_id']
    
    with database.get_db() as conn:
        c2 = conn.execute("SELECT collected_by FROM collections WHERE id = ?", (col2_id,)).fetchone()
        assert c2[0] == "Riyad Hossain", f"Expected Riyad Hossain, got {c2[0]}"
        print(f"✓ Manager collection registered under: '{c2[0]}'")
        conn.execute("DELETE FROM collections WHERE id = ?", (col2_id,))
        conn.commit()

    # 3. Test Any Future Manager created by Admin
    # Simulate creating a brand-new manager: "Fahad Al-Otaibi"
    new_user_id = None
    with database.get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO admin_users (username, password_hash, salt, full_name, role, is_active, created_at, updated_at)
            VALUES ('fahad_mgr', 'dummy_hash', 'dummy_salt', 'Fahad Al-Otaibi', 'manager', 1, datetime('now'), datetime('now'))
        """)
        new_user_id = cur.lastrowid
        conn.commit()

    print(f"\nSimulated newly created manager (ID: {new_user_id}, Name: 'Fahad Al-Otaibi')...")
    sess_new, _ = auth_service.create_session(new_user_id)
    cookies_new = {auth_service.COOKIE_NAME: sess_new}

    r_new = requests.get('http://127.0.0.1:9911/balance', cookies=cookies_new)
    assert 'Collector: <strong style="color:#f1f5f9;">Fahad Al-Otaibi</strong>' in r_new.text
    print("✓ Future manager view dynamically renders 'Collector: Fahad Al-Otaibi'")

    payload3 = {'customer_id': cust['id'], 'amount': 1.0, 'payment_type': 'bank_transfer', 'notes': 'Test future manager collect'}
    resp3 = requests.post('http://127.0.0.1:9911/api/balance/collect', json=payload3, cookies=cookies_new).json()
    assert resp3['success'] is True
    col3_id = resp3['collection_id']

    with database.get_db() as conn:
        c3 = conn.execute("SELECT collected_by FROM collections WHERE id = ?", (col3_id,)).fetchone()
        assert c3[0] == "Fahad Al-Otaibi", f"Expected Fahad Al-Otaibi, got {c3[0]}"
        print(f"✓ Future manager collection registered under: '{c3[0]}'")
        
        # Clean up test rows
        conn.execute("DELETE FROM collections WHERE id = ?", (col3_id,))
        conn.execute("DELETE FROM admin_sessions WHERE user_id = ?", (new_user_id,))
        conn.execute("DELETE FROM admin_users WHERE id = ?", (new_user_id,))
        conn.commit()
    print("✓ Cleaned up test data.")

    print("\nALL DYNAMIC MULTI-USER TESTS PASSED 100%! It is 100% dynamic for any current or future manager/admin.")

if __name__ == '__main__':
    test_dynamic_collectors()
