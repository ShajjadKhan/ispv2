import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def test_will_suspend_and_suspended_behavior():
    print("=== Step 1: Baseline Check ===")
    m = database.get_dashboard_metrics()
    tiers = m["expiring_tiers"]
    print("Baseline expiring_tiers:", tiers)
    print("Baseline suspended_count:", m["suspended_count"])
    assert tiers["will_suspend"] == 0, f"Expected will_suspend=0, got {tiers['will_suspend']}"
    assert tiers["total"] == 0, f"Expected total=0 on will suspend card, got {tiers['total']}"
    print("[PASS] Baseline clean: 0 will suspend accounts.")

    # Find a test customer
    custs = database.get_all_customers()
    assert len(custs) > 0, "No customers found"
    test_cust = custs[0]
    cid = test_cust["id"]
    orig_due = test_cust.get("due_date")
    orig_status = test_cust.get("status", "active")
    print(f"\nUsing test customer #{cid} ({test_cust['name']})")

    try:
        print("\n=== Step 2: Test Active Account Due Today / Overdue (Will Suspend) ===")
        yesterday_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        database.update_customer_details(customer_id=cid, due_date=yesterday_str, status="active")
        m2 = database.get_dashboard_metrics()
        tiers2 = m2["expiring_tiers"]
        print("Updated expiring_tiers:", tiers2)
        assert tiers2["will_suspend"] >= 1, "Expected will_suspend >= 1 for overdue active account"
        assert tiers2["total"] >= 1, "Expected total >= 1 on Will Suspend card"
        assert tiers2["overdue"] >= 1, "Expected overdue >= 1"
        target_cust = next((c for c in m2["all_customers"] if c["id"] == cid), None)
        assert target_cust is not None
        assert target_cust["tier"] == "overdue"
        assert target_cust["status"] == "active"
        print(f"[PASS] Customer #{cid} correctly identified as WILL SUSPEND (overdue to cut).")

        print("\n=== Step 3: Test Suspended Account Isolation ===")
        # Now suspend the customer
        database.update_customer_details(customer_id=cid, status="suspended")
        m3 = database.get_dashboard_metrics()
        tiers3 = m3["expiring_tiers"]
        print("After suspension expiring_tiers:", tiers3)
        print("After suspension suspended_count:", m3["suspended_count"])
        assert tiers3["will_suspend"] == 0, f"Suspended account must NOT be in will_suspend! Got {tiers3['will_suspend']}"
        assert m3["suspended_count"] >= 1, f"Expected suspended_count >= 1, got {m3['suspended_count']}"
        
        target_cust3 = next((c for c in m3["all_customers"] if c["id"] == cid), None)
        assert target_cust3 is not None, "Suspended customer must NOT be removed from customer list!"
        assert target_cust3["status"] == "suspended"
        assert target_cust3["tier"] == "suspended"
        print(f"[PASS] Suspended customer #{cid} is on Suspended list and NOT in Will Suspend count.")

    finally:
        # Cleanup
        print("\n=== Step 4: Cleanup to original state ===")
        database.update_customer_details(customer_id=cid, due_date=orig_due, status=orig_status)
        m_final = database.get_dashboard_metrics()
        print("Restored expiring_tiers:", m_final["expiring_tiers"])
        print("Restored suspended_count:", m_final["suspended_count"])
        print(f"[CLEANUP] Customer #{cid} restored to status='{orig_status}', due='{orig_due}'.")

    print("\nAll Will Suspend & Suspended isolation tests passed 100%!")

if __name__ == "__main__":
    test_will_suspend_and_suspended_behavior()
