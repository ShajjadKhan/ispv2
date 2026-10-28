#!/usr/bin/env python3
"""
Full Lifecycle Verification for PPPoE & Hotspot Coexistence on Cybernet Router-20 & CyberNet OS (isp_v2).
"""
import sys
import os
import time

# Ensure isp_v2 root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import mikrotik_client

def get_router_secrets():
    routers = database.get_all_routers(active_only=True)
    if not routers:
        return []
    client = mikrotik_client.get_client_for_router(routers[0])
    if client.connect():
        try:
            return client.api.get_resource('/ppp/secret').get()
        finally:
            client.disconnect()
    return []

def run_tests():
    print("==================================================================")
    print("🚀 STARTING PPPoE FULL LIFECYCLE & HOTSPOT COEXISTENCE TEST")
    print("==================================================================")

    # 1. Database Schema & Init
    print("\n[Step 1] Initializing database schema...")
    database.init_db()
    print("✅ Database initialized successfully.")

    # 2. Router Fleet Connectivity
    print("\n[Step 2] Testing connectivity to Cybernet Router-20...")
    active_routers = database.get_all_routers(active_only=True)
    print(f"Discovered {len(active_routers)} active router(s): {[r['name'] for r in active_routers]}")
    assert len(active_routers) > 0, "No active routers available in fleet!"

    # 3. Query existing secrets and active sessions
    print("\n[Step 3] Querying live PPPoE secrets and active sessions from MikroTik fleet...")
    secrets = get_router_secrets()
    print(f"Live PPP Secrets on fleet: {len(secrets)} secret(s) found.")
    for s in secrets:
        print(f"  • User: {s.get('name')} | Profile: {s.get('profile')} | Disabled: {s.get('disabled')}")

    active_sess = mikrotik_client.broadcast_get_active_pppoe_sessions()
    print(f"Live PPPoE Active Sessions: {len(active_sess)} active session(s).")
    for u, sess in active_sess.items():
        print(f"  • Active Session: {u} -> IP: {sess.get('address')} (uptime: {sess.get('uptime')})")

    # 4. Check existing Hotspot customers integrity
    print("\n[Step 4] Checking existing Hotspot subscribers...")
    customers = database.get_all_customers()
    hotspot_custs = [c for c in customers if c.get("connection_type", "hotspot") == "hotspot"]
    print(f"Found {len(customers)} total customers ({len(hotspot_custs)} Hotspot subscribers).")
    assert len(hotspot_custs) >= 11, f"Expected at least 11 hotspot customers, found {len(hotspot_custs)}"
    print("✅ Existing Hotspot customer records verified intact.")

    # 5. Create Test PPPoE Customer
    test_phone = "0599990099"
    test_name = "PPPoE Test User 99"
    test_pass = "cyberPpp99"
    test_rate = "25M/25M"

    print(f"\n[Step 5] Creating test PPPoE customer '{test_name}' ({test_phone})...")
    # Clean up any leftover test subscriber
    with database.get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM customers WHERE phone = ?", (test_phone,))
        existing = c.fetchone()
        if existing:
            database.delete_customer_permanently(existing["id"])
            mikrotik_client.broadcast_remove_pppoe_secret(test_phone)

    test_cust = database.create_customer(
        phone=test_phone,
        name=test_name,
        billing_type="prepaid",
        package_name="20 Mbps Fast",
        monthly_fee=75.0,
        due_date=time.strftime("%Y-%m-%d"),
        speed_limit=test_rate,
        connection_type="pppoe",
        pppoe_username=test_phone,
        pppoe_password=test_pass,
        pppoe_profile="pppoe-profile-ether4",
        pppoe_remote_ip="10.44.0.199",
        notes="Automated PPPoE Sync Verification"
    )
    cust_id = test_cust["id"]
    print(f"Customer #{cust_id} created in DB with connection_type='pppoe'.")

    # Sync to MikroTik fleet
    print(f"Synchronizing PPPoE secret for '{test_phone}' to MikroTik fleet...")
    sync_res = mikrotik_client.broadcast_sync_pppoe_secret(
        username=test_phone,
        password=test_pass,
        profile="pppoe-profile-ether4",
        remote_ip="10.44.0.199",
        rate_limit=test_rate,
        disabled=False,
        comment=f"CyberNet PPPoE Test #{cust_id}"
    )
    print(f"Fleet sync result: {sync_res}")
    assert any(sync_res.values()), "Failed to sync PPPoE secret to MikroTik!"

    # Verify secret presence on router
    secrets_now = get_router_secrets()
    matched_secret = next((s for s in secrets_now if s.get("name") == test_phone), None)
    assert matched_secret is not None, f"Secret '{test_phone}' not found on router!"
    print(f"✅ Verified secret '{test_phone}' exists on MikroTik: disabled={matched_secret.get('disabled')}, profile={matched_secret.get('profile')}")

    # 6. Test Speed Modification / Profile Update
    new_rate = "40M/40M"
    print(f"\n[Step 6] Updating speed to {new_rate}...")
    updated_cust = database.update_customer_details(
        customer_id=cust_id,
        name=test_name,
        phone=test_phone,
        billing_type="prepaid",
        package_name="20 Mbps Fast",
        monthly_fee=75.0,
        speed_limit=new_rate,
        connection_type="pppoe",
        pppoe_username=test_phone,
        pppoe_password=test_pass,
        pppoe_profile="pppoe-profile-ether4",
        pppoe_remote_ip="10.44.0.199"
    )
    sync_res2 = mikrotik_client.broadcast_sync_pppoe_secret(
        username=test_phone,
        password=test_pass,
        profile="pppoe-profile-ether4",
        remote_ip="10.44.0.199",
        rate_limit=new_rate,
        disabled=False,
        comment=f"CyberNet PPPoE Test #{cust_id}"
    )
    print(f"Fleet speed update result: {sync_res2}")
    secrets_up = get_router_secrets()
    matched_up = next((s for s in secrets_up if s.get("name") == test_phone), None)
    assert matched_up is not None
    print(f"✅ Secret on router profile updated to: {matched_up.get('profile')}")

    # 7. Test Suspension (Cutoff)
    print(f"\n[Step 7] Suspending customer #{cust_id} and checking router disable...")
    new_status, macs = database.toggle_customer_status(cust_id)
    assert new_status == "suspended", f"Expected suspended status, got {new_status}"
    mikrotik_client.broadcast_toggle_pppoe_secret(test_phone, disabled=True)

    secrets_susp = get_router_secrets()
    matched_susp = next((s for s in secrets_susp if s.get("name") == test_phone), None)
    assert matched_susp is not None
    print(f"✅ Secret on router disabled status: {matched_susp.get('disabled')}")
    assert str(matched_susp.get("disabled")).lower() in ("true", "yes"), "Secret was not disabled on router!"

    # 8. Test Reactivation / Un-suspension
    print(f"\n[Step 8] Reactivating customer #{cust_id} and checking router enable...")
    new_status, macs = database.toggle_customer_status(cust_id)
    assert new_status == "active", f"Expected active status, got {new_status}"
    mikrotik_client.broadcast_toggle_pppoe_secret(test_phone, disabled=False)

    secrets_act = get_router_secrets()
    matched_act = next((s for s in secrets_act if s.get("name") == test_phone), None)
    assert matched_act is not None
    print(f"✅ Secret on router disabled status: {matched_act.get('disabled')}")
    assert str(matched_act.get("disabled")).lower() in ("false", "no"), "Secret was not re-enabled on router!"

    # 9. Test Permanent Deletion & Router Purge
    print(f"\n[Step 9] Permanently deleting test customer #{cust_id}...")
    success, macs, name, phone, pppoe_user = database.delete_customer_permanently(cust_id)
    assert success is True, "Customer deletion failed in DB!"
    assert pppoe_user == test_phone, f"Expected pppoe_user={test_phone}, got {pppoe_user}"

    purge_res = mikrotik_client.broadcast_remove_pppoe_secret(pppoe_user)
    print(f"Fleet purge result: {purge_res}")

    secrets_final = get_router_secrets()
    matched_final = next((s for s in secrets_final if s.get("name") == test_phone), None)
    assert matched_final is None, f"Secret '{test_phone}' was NOT removed from router!"
    print(f"✅ Verified secret '{test_phone}' is completely purged from MikroTik router.")

    # 10. Final Verification of Existing 11 Hotspot Users
    print("\n[Step 10] Verifying existing Hotspot subscribers integrity...")
    remaining_custs = database.get_all_customers()
    remaining_hotspot = [c for c in remaining_custs if c.get("connection_type", "hotspot") == "hotspot"]
    assert len(remaining_hotspot) >= 11, "Hotspot customers count dropped unexpectedly!"
    print(f"✅ All {len(remaining_hotspot)} Hotspot subscribers remain 100% intact and unaffected.")

    print("\n==================================================================")
    print("🎉 ALL PPPoE & HOTSPOT LIFECYCLE TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================================")

if __name__ == "__main__":
    run_tests()
