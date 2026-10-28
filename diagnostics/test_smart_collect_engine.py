import os
import sys
import sqlite3
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def test_smart_collect_engine():
    print("=== Testing Smart Collect Customer Payment Engine ===")
    
    # 1. Test against customer #158 (Ovi) or create a dedicated mock customer
    with database.get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Create a temporary mock customer for testing
        cur.execute("""
            INSERT INTO customers (name, phone, notes, billing_type, package_name, monthly_fee, due_day, due_date, expiry_date, status, credit_balance, created_at, updated_at, billing_start_date)
            VALUES ('__TEST_SMART_COLLECT__', '0500000099', 'Room Test99', 'postpaid', 'Standard 30M', 30.0, 1, '2026-10-01', '2026-10-01', 'expired', -15.0, '2026-10-01 00:00:00', '2026-10-01 00:00:00', '2026-10-01')
        """)
        test_cid = cur.lastrowid
        conn.commit()
        print(f"Created temporary mock customer #{test_cid}")

    try:
        # Check initial breakdown
        bd_initial = database.get_customer_billing_breakdown(test_cid)
        print(f"Initial: credit_balance={bd_initial['credit_balance']}, total_due={bd_initial['total_due']}, unpaid_cycles={[c['month'] for c in bd_initial['unpaid_cycles']]}")
        assert bd_initial["total_due"] >= 14.0, "Mock customer should owe at least 14 SAR for elapsed days"

        # Execute Smart Collection: Collect 30.00 SAR
        res1 = database.smart_collect_customer_payment(
            customer_id=test_cid,
            amount=30.0,
            payment_type="cash",
            collector="Test Collector",
            notes="Smart collection test 1"
        )
        print("Smart Collect Result 1:", res1["message"])
        assert res1["success"] is True
        assert len(res1["settled_cycles"]) >= 1, "Should have settled at least 1 cycle"
        assert res1["new_credit_balance"] >= 0.0, f"Balance should be >= 0 after settlement, got {res1['new_credit_balance']}"

        # Verify in database
        bd_after1 = database.get_customer_billing_breakdown(test_cid)
        print(f"After Step 1: credit_balance={bd_after1['credit_balance']}, total_due={bd_after1['total_due']}, expiry={bd_after1['expiry_date']}")
        assert bd_after1["total_due"] == 0.0, f"Expected total_due == 0, got {bd_after1['total_due']}"

        # Execute Advance Smart Collection: Collect 60.00 SAR (2 advance months)
        res2 = database.smart_collect_customer_payment(
            customer_id=test_cid,
            amount=60.0,
            payment_type="stc_pay",
            collector="Test Collector",
            notes="Smart collection advance test 2"
        )
        print("Smart Collect Result 2:", res2["message"])
        assert res2["success"] is True
        assert len(res2["settled_cycles"]) == 2, f"Should have covered 2 advance cycles, got {res2['settled_cycles']}"

        # Verify expiry date extended into the future
        bd_after2 = database.get_customer_billing_breakdown(test_cid)
        print(f"After Step 2: credit_balance={bd_after2['credit_balance']}, total_due={bd_after2['total_due']}, expiry={bd_after2['expiry_date']}")
        assert bd_after2["total_due"] == 0.0
        assert bd_after2["expiry_date"] > bd_after1["expiry_date"], "Expiry date should have advanced"

        print("SUCCESS: All smart collect engine assertions passed with flying colors!")

    finally:
        # Clean up temporary test data completely
        with database.get_db() as conn:
            conn.execute("DELETE FROM collections WHERE customer_id = ?", (test_cid,))
            conn.execute("DELETE FROM customers WHERE id = ?", (test_cid,))
            conn.commit()
            print(f"Cleanly purged mock customer #{test_cid} and all test collections.")

if __name__ == "__main__":
    test_smart_collect_engine()
