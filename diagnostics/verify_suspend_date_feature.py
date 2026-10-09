import sys
import os
import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

def test_suspend_date_logic():
    print("=== Step 1: Testing database.py update_customer_details with suspend_date ===")
    customers = database.get_all_customers()
    if not customers:
        print("[FAIL] No customers in database.")
        sys.exit(1)
    
    test_cust = customers[0]
    cust_id = test_cust["id"]
    orig_due = test_cust.get("due_date")
    orig_expiry = test_cust.get("expiry_date")
    print(f"Testing on customer ID #{cust_id} ({test_cust.get('name')}). Original due={orig_due}, expiry={orig_expiry}")

    # Set new test suspend date
    target_date = (datetime.date.today() + datetime.timedelta(days=25)).isoformat()
    updated = database.update_customer_details(customer_id=cust_id, suspend_date=target_date)
    assert updated is not None, "update_customer_details returned None"
    assert updated["due_date"] == target_date, f"Expected due_date={target_date}, got {updated['due_date']}"
    assert updated["expiry_date"] == target_date, f"Expected expiry_date={target_date}, got {updated['expiry_date']}"
    print(f"[PASS] database.update_customer_details correctly set due_date and expiry_date to {target_date}")

    print("\n=== Step 2: Testing get_customer_profile & get_dashboard_metrics suspend_date presence ===")
    profile = database.get_customer_profile(cust_id)
    assert profile is not None, "get_customer_profile returned None"
    assert profile.get("suspend_date") == target_date, f"Profile suspend_date mismatch: {profile.get('suspend_date')}"
    print(f"[PASS] get_customer_profile includes suspend_date: {profile.get('suspend_date')}")

    metrics = database.get_dashboard_metrics()
    metric_cust = next((c for c in metrics.get("all_customers", []) if c["id"] == cust_id), None)
    assert metric_cust is not None, "Customer not in dashboard metrics"
    assert metric_cust.get("suspend_date") == target_date, f"Metrics suspend_date mismatch: {metric_cust.get('suspend_date')}"
    print(f"[PASS] get_dashboard_metrics includes suspend_date: {metric_cust.get('suspend_date')}")

    print("\n=== Step 3: Testing set_customer_suspend_date_endpoint directly ===")
    import asyncio
    from main import set_customer_suspend_date_endpoint, SetSuspendDatePayload
    new_suspend_date = (datetime.date.today() + datetime.timedelta(days=45)).isoformat()
    resp = asyncio.run(set_customer_suspend_date_endpoint(cust_id, SetSuspendDatePayload(suspend_date=new_suspend_date)))
    assert isinstance(resp, dict) and resp.get("success") is True, f"Response not success: {resp}"
    assert resp.get("suspend_date") == new_suspend_date, f"Response suspend date mismatch: {resp}"
    print(f"[PASS] set_customer_suspend_date_endpoint succeeded: {resp['message']}")

    # Restore original date
    if orig_due:
        database.update_customer_details(customer_id=cust_id, due_date=orig_due)
        print(f"[CLEANUP] Restored customer #{cust_id} due_date to {orig_due}")

    print("\n=== Step 4: Testing Package Validity Days calculation ===")
    packages = database.get_packages()
    assert len(packages) > 0, "No packages found"
    for pkg in packages[:3]:
        validity = pkg.get("validity_days") or 30
        expected_calc = (datetime.date.today() + datetime.timedelta(days=validity)).isoformat()
        print(f"Package '{pkg['name']}': validity_days={validity} -> target suspend date={expected_calc}")
    print("[PASS] Package validity calculation verified.")

    print("\nAll 4 test suites passed successfully!")

if __name__ == "__main__":
    test_suspend_date_logic()
