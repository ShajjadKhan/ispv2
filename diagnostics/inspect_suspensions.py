import os
import sys
import sqlite3
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def inspect_suspensions():
    print("=== SUSPENSION & BILLING AUDIT ===")
    conn = database.get_raw_connection()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Suspensions in DB
    susp_rows = cur.execute("SELECT * FROM customer_suspensions ORDER BY id ASC").fetchall()
    print(f"Total entries in customer_suspensions: {len(susp_rows)}")
    for s in susp_rows:
        print(f"  Suspension #{s['id']}: Cust #{s['customer_id']} suspended_at={s['suspended_at']}, resumed_at={s['resumed_at']}, reason={s['reason']}")

    # 2. Customers with status = 'suspended'
    susp_custs = cur.execute("SELECT id, name, phone, status, monthly_fee, billing_start_date, due_date, expiry_date, credit_balance FROM customers WHERE status = 'suspended'").fetchall()
    print(f"\nCustomers with status='suspended' ({len(susp_custs)}):")
    for c in susp_custs:
        rt = database.calculate_customer_realtime_balance(c["id"], conn)
        bd = database.get_customer_billing_breakdown(c["id"])
        print(f"  Cust #{c['id']} {c['name']} (Fee={c['monthly_fee']}):")
        print(f"    Table credit_balance={c['credit_balance']}, RT balance={rt['balance']} (Billable days={rt['billable_days']}, owed={rt['total_owed']})")
        print(f"    Billing breakdown total_due={bd['total_due']}, unpaid_cycles={[u['month'] for u in bd['unpaid_cycles']]}")

    # 3. Simulate a customer suspended for 20 days to verify math
    print("\n--- Simulating suspension math test ---")
    today = date.today()
    start_d = today - timedelta(days=30)
    susp_d = today - timedelta(days=20)
    
    cur.execute("""
        INSERT INTO customers (name, phone, notes, billing_type, package_name, monthly_fee, due_day, due_date, expiry_date, status, credit_balance, created_at, updated_at, billing_start_date)
        VALUES ('__TEST_SUSP_SIM__', '0500000088', 'Room Susp', 'postpaid', 'Standard 30M', 30.0, 1, ?, ?, 'suspended', 0.0, ?, ?, ?)
    """, (start_d.strftime("%Y-%m-%d"), start_d.strftime("%Y-%m-%d"), start_d.strftime("%Y-%m-%d 00:00:00"), start_d.strftime("%Y-%m-%d 00:00:00"), start_d.strftime("%Y-%m-%d")))
    sim_cid = cur.lastrowid
    
    cur.execute("""
        INSERT INTO customer_suspensions (customer_id, suspended_at, reason, created_at)
        VALUES (?, ?, 'Test suspension', ?)
    """, (sim_cid, susp_d.strftime("%Y-%m-%d 00:00:00"), susp_d.strftime("%Y-%m-%d 00:00:00")))
    conn.commit()

    try:
        rt_sim = database.calculate_customer_realtime_balance(sim_cid, conn)
        bd_sim = database.get_customer_billing_breakdown(sim_cid)
        print(f"Customer #{sim_cid} started {start_d} (30 days ago), suspended {susp_d} (20 days ago):")
        print(f"  -> Real-Time Engine (daily balance): Billable days = {rt_sim['billable_days']} (expected ~10 days), Total Owed = {rt_sim['total_owed']} SAR, Balance = {rt_sim['balance']} SAR")
        print(f"  -> Billing Breakdown (monthly cycles): Total Due = {bd_sim['total_due']} SAR, Unpaid Cycles = {[c['month'] + ': ' + str(c['rem_due']) + ' SAR' for c in bd_sim['unpaid_cycles']]}")
        assert bd_sim["total_due"] == 10.0, f"Expected total_due 10.0, got {bd_sim['total_due']}"
        assert rt_sim["total_owed"] == 10.0, f"Expected total_owed 10.0, got {rt_sim['total_owed']}"

        # Test collecting 40 SAR (10 SAR debt + 30 SAR advance renewal)
        col_res = database.smart_collect_customer_payment(
            customer_id=sim_cid,
            amount=40.0,
            payment_type="cash",
            collector="Test Collector",
            notes="Testing collection on suspended customer"
        )
        print(f"  -> Smart Collect Result: {col_res['message']}")
        assert col_res["success"] is True

        bd_after = database.get_customer_billing_breakdown(sim_cid)
        rt_after = database.calculate_customer_realtime_balance(sim_cid, conn)
        print(f"  -> After Collection: Status = {bd_after['status']}, Expiry = {bd_after['expiry_date']}, Credit Balance = {bd_after['credit_balance']} SAR, Total Due = {bd_after['total_due']} SAR, Unpaid Cycles = {bd_after['unpaid_cycles']}")
        assert bd_after["total_due"] == 0.0, "Total due should be 0.0 after clearing debt and renewing"
        assert bd_after["status"] == "active", "Customer should be active after payment"
        print("  -> ALL SUSPENSION BILLING LOGIC CHECKS PASSED 100%!")
    finally:
        cur.execute("DELETE FROM collections WHERE customer_id = ?", (sim_cid,))
        cur.execute("DELETE FROM customer_suspensions WHERE customer_id = ?", (sim_cid,))
        cur.execute("DELETE FROM customers WHERE id = ?", (sim_cid,))
        conn.commit()
        print(f"Cleaned up test customer #{sim_cid}")

if __name__ == "__main__":
    inspect_suspensions()
