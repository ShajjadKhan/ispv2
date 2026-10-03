#!/usr/bin/env python3
"""
Comprehensive verification test suite for Customer-Centric Expiration,
Fleet-wide Device Cut, and Joining/Billing Start Date Billing Cycles.
"""

import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, '/home/tserver/isp_v2')
import database

def run_tests():
    print("==================================================")
    print(" CYBERNET OS v2 - CUSTOMER-CENTRIC VERIFICATION")
    print("==================================================")

    # 1. Test is_customer_expired
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Active customer
    active_cust = {"id": 999, "status": "active", "expiry_date": tomorrow, "suspension_held_until": None}
    is_exp, reason, exp_d = database.is_customer_expired(active_cust)
    assert not is_exp, f"Expected active, got expired: {reason}"
    print("✓ Test 1: Active customer detected correctly (not expired).")

    # Expired customer
    exp_cust = {"id": 998, "status": "active", "expiry_date": yesterday, "suspension_held_until": None}
    is_exp, reason, exp_d = database.is_customer_expired(exp_cust)
    assert is_exp, "Expected expired customer to be detected as expired"
    print(f"✓ Test 2: Expired customer detected correctly ({reason}).")

    # Expired customer with active grace hold
    grace_cust = {"id": 997, "status": "active", "expiry_date": yesterday, "suspension_held_until": tomorrow}
    is_exp, reason, exp_d = database.is_customer_expired(grace_cust)
    assert not is_exp, f"Expected grace hold to protect customer, but got: {is_exp}, {reason}"
    print(f"✓ Test 3: Grace hold correctly protects customer ({reason}).")

    # 2. Test Customer Creation with join_date & billing_start_date
    test_phone = "0590000099"
    # Clean up test customer if exists
    existing = database.get_customer_by_phone(test_phone)
    if existing:
        database.delete_customer_permanently(existing["id"])

    res = database.create_customer(
        phone=test_phone,
        name="Verification Test User",
        billing_type="postpaid",
        package_name="Silver (20 Mbps)",
        monthly_fee=100.0,
        due_day=15,
        mac_address="00:1A:2B:3C:4D:5E",
        join_date="2025-05-15",
        billing_start_date="2025-05-15"
    )
    cust = res
    assert cust.get("id"), f"Failed to create customer: {res}"
    cid = cust["id"]
    print(f"✓ Test 4: Created test customer #{cid} with join_date=2025-05-15.")

    # Verify fields in database
    retrieved = database.get_customer_profile(cid)
    assert retrieved["join_date"] == "2025-05-15", f"join_date mismatch: {retrieved.get('join_date')}"
    assert retrieved["billing_start_date"] == "2025-05-15", f"billing_start_date mismatch: {retrieved.get('billing_start_date')}"
    assert retrieved["due_day"] == 15, f"due_day mismatch: {retrieved.get('due_day')}"
    print("✓ Test 5: Retrieved customer profile confirms join_date and anniversary due_day=15.")

    # 3. Test update_customer_details with updated join_date
    upd = database.update_customer_details(
        customer_id=cid,
        name="Verification Test User (Updated)",
        join_date="2024-11-20",
        billing_start_date="2024-11-20"
    )
    retrieved_upd = database.get_customer_profile(cid)
    assert retrieved_upd["join_date"] == "2024-11-20"
    assert retrieved_upd["due_day"] == 20, f"Expected due_day 20 derived from join_date, got {retrieved_upd.get('due_day')}"
    print("✓ Test 6: Updated join_date to 2024-11-20, anniversary due_day auto-updated to 20.")

    # 4. Test Billing Breakdown
    breakdown = database.get_customer_billing_breakdown(cid)
    assert breakdown["join_date"] == "2024-11-20"
    assert breakdown["billing_start_date"] == "2024-11-20"
    print(f"✓ Test 7: Billing breakdown calculates cycles originating from {breakdown['billing_start_date']}.")

    # 5. Test Secondary Device Expiration Inheritance
    sec_mac = "00:1A:2B:3C:4D:5F"
    add_dev_res = database.add_customer_device(
        customer_id=cid,
        mac_address=sec_mac,
        device_name="Test Secondary Device"
    )
    assert add_dev_res.get("id"), f"Failed to add secondary device: {add_dev_res}"
    print("✓ Test 8: Secondary device registered under customer account.")

    # Simulate expiration by backdating expiry_date to yesterday
    database.update_customer_details(
        customer_id=cid,
        due_date=yesterday
    )
    retrieved_exp = database.get_customer_profile(cid)
    is_exp, reason, _ = database.is_customer_expired(retrieved_exp)
    assert is_exp, "Customer should be expired after backdating due_date"
    print(f"✓ Test 9: Customer backdated to {yesterday}, confirmed expired.")

    # Check connection status for secondary device MAC
    stat_sec = database.get_request_status_by_mac_and_phone(mac=sec_mac, phone=test_phone)
    assert stat_sec.get("status") == "expired", f"Expected secondary device status 'expired', got {stat_sec.get('status')}"
    print("✓ Test 10: Secondary device inherits expired status from customer (Device join date does not grant extra days).")

    # Run check_and_enforce_customer_expirations
    expired_list = database.check_and_enforce_customer_expirations()
    exp_cids = [c["customer_id"] for c in expired_list]
    assert cid in exp_cids, f"Customer {cid} should be in expired list, got {exp_cids}"
    
    # Check that devices were blocked
    prof_after_cut = database.get_customer_profile(cid)
    assert prof_after_cut["status"] == "suspended"
    dev_statuses = [d["status"] for d in prof_after_cut["devices"]]
    assert all(s == "blocked" for s in dev_statuses), f"All devices should be blocked, got {dev_statuses}"
    print(f"✓ Test 11: check_and_enforce_customer_expirations suspended customer and blocked all {len(dev_statuses)} devices.")

    # Clean up test user
    database.delete_customer_permanently(cid)
    print("✓ Test 12: Test customer cleanly deleted.")

    print("\n==================================================")
    print(" ALL 12 VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
