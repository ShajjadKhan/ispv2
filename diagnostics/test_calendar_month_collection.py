import requests
import database
import auth_service
from datetime import datetime

def test_calendar_month_collection():
    print("=== Testing Strict 1st-to-End-of-Month Calendar Collection Rules ===")

    session_id, _ = auth_service.create_session(1)
    cookies = {auth_service.COOKIE_NAME: session_id}

    # Pick test customer
    cust = database.get_customer_profile(9) # Mohammad Mursalin (fee: 30 SAR)
    assert cust is not None, "Customer 9 not found"
    cid = cust['id']
    fee = float(cust.get('monthly_fee') or 30.0)

    # 1. Verify customer baseline dates
    print(f"Customer #{cid} ({cust['name']}): Fee={fee} SAR")
    print(f"  Baseline: start={cust.get('billing_start_date')}, due_date={cust.get('due_date')}, due_day={cust.get('due_day')}")
    assert cust.get('due_day') == 1, f"Expected due_day=1, got {cust.get('due_day')}"
    assert str(cust.get('due_date')) == '2026-11-01', f"Expected due_date=2026-11-01, got {cust.get('due_date')}"

    # 2. Test 1-Month Collection (30 SAR) -> Covers October
    payload1 = {
        'customer_id': cid,
        'amount': fee,
        'payment_type': 'cash',
        'notes': 'Test October monthly collection'
    }
    r1 = requests.post('http://127.0.0.1:9911/api/balance/collect', json=payload1, cookies=cookies)
    assert r1.status_code == 200, f"Error: {r1.text}"
    col1 = r1.json()
    assert col1['success'] is True
    col1_id = col1['collection_id']

    # Audit DB customer after 1-month collection
    with database.get_db() as conn:
        c_row = conn.execute("SELECT expiry_date, due_date, due_day FROM customers WHERE id = ?", (cid,)).fetchone()
        exp1, due1, day1 = c_row[0], c_row[1], c_row[2]
        print(f"✓ 1-Month Collection Applied:")
        print(f"  Expiry (Last day of month): {exp1}")
        print(f"  Next Due Date (1st of next month): {due1}")
        print(f"  Due Day: {day1}")
        assert exp1 == '2026-10-31', f"Expected expiry 2026-10-31, got {exp1}"
        assert due1 == '2026-11-01', f"Expected due_date 2026-11-01, got {due1}"
        assert day1 == 1, f"Expected due_day 1, got {day1}"

        # Check collection record
        coll_row = conn.execute("SELECT amount, month_year, collected_by FROM collections WHERE id = ?", (col1_id,)).fetchone()
        print(f"  Recorded Collection: Amount={coll_row[0]} SAR, Month={coll_row[1]}, By={coll_row[2]}")
        assert coll_row[1] == '2026-10', f"Expected month_year 2026-10, got {coll_row[1]}"

        # Clean up test collection
        conn.execute("DELETE FROM collections WHERE id = ?", (col1_id,))
        # Restore customer 9
        conn.execute("UPDATE customers SET due_date = '2026-11-01', expiry_date = '2026-10-31', due_day = 1 WHERE id = ?", (cid,))
        conn.commit()

    # 3. Test 2-Months Collection (60 SAR) -> Covers through November
    payload2 = {
        'customer_id': cid,
        'amount': fee * 2,
        'payment_type': 'stc_pay',
        'notes': 'Test 2-Months advance collection'
    }
    r2 = requests.post('http://127.0.0.1:9911/api/balance/collect', json=payload2, cookies=cookies)
    assert r2.status_code == 200, f"Error: {r2.text}"
    col2 = r2.json()
    assert col2['success'] is True
    col2_id = col2['collection_id']

    with database.get_db() as conn:
        c_row = conn.execute("SELECT expiry_date, due_date, due_day FROM customers WHERE id = ?", (cid,)).fetchone()
        exp2, due2, day2 = c_row[0], c_row[1], c_row[2]
        print(f"\n✓ 2-Month Collection Applied:")
        print(f"  Expiry (Last day of 2nd month): {exp2}")
        print(f"  Next Due Date (1st of 3rd month): {due2}")
        print(f"  Due Day: {day2}")
        assert exp2 == '2026-11-30', f"Expected expiry 2026-11-30, got {exp2}"
        assert due2 == '2026-12-01', f"Expected due_date 2026-12-01, got {due2}"
        assert day2 == 1, f"Expected due_day 1, got {day2}"

        # Clean up test collection and restore
        conn.execute("DELETE FROM collections WHERE id = ?", (col2_id,))
        conn.execute("UPDATE customers SET due_date = '2026-11-01', expiry_date = '2026-10-31', due_day = 1 WHERE id = ?", (cid,))
        conn.commit()

    # 4. Check Balance Sheet data
    bs = database.get_balance_sheet_data()
    for row in bs['rows']:
        assert row['billing_start_date'].endswith('-01'), f"Customer {row['id']} start date does not begin on 1st: {row['billing_start_date']}"
    print("\n✓ Verified ALL active subscribers in Balance Sheet start strictly on 1st of the month.")

    print("\nALL CALENDAR MONTH CHECKS PASSED 100%! Subscription and collections strictly adhere to 1st-to-end-of-month.")

if __name__ == '__main__':
    test_calendar_month_collection()
