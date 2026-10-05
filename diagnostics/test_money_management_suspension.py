#!/usr/bin/env python3
"""
Automated Verification Suite for CyberNet OS isp_v2 Money Management,
Suspension-Aware Billing Accrual, and Month-End Financial Reconciliation.
"""
import sys
import os
import sqlite3
from datetime import datetime, date, timedelta

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database
import jinja2

def run_tests():
    print("=" * 70)
    print("CYBERNET OS MONEY MANAGEMENT & SUSPENSION BILLING TEST SUITE")
    print("=" * 70)

    # 1. Database Schema & Tables Check
    print("\n[CHECK 1] Database Tables & Indexes...")
    database.init_db()
    with database.get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        tables = [r["name"] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "customer_suspensions" in tables, "customer_suspensions table missing!"
        print("  ✓ customer_suspensions table present")

        indexes = [r["name"] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()]
        assert "idx_suspensions_cust" in indexes, "idx_suspensions_cust index missing!"
        print("  ✓ idx_suspensions_cust index present")

    # 2. Template Compilation Check (Jinja2)
    print("\n[CHECK 2] Jinja2 Templates Compilation...")
    tmpl_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(tmpl_dir))
    
    # Check balance.html
    tmpl_balance = env.get_template("balance.html")
    assert tmpl_balance is not None
    print("  ✓ templates/balance.html compiled cleanly (zero syntax errors)")

    # Check balance_report.html
    tmpl_report = env.get_template("balance_report.html")
    assert tmpl_report is not None
    print("  ✓ templates/balance_report.html compiled cleanly (zero syntax errors)")

    # 3. Balance Sheet Data & Suspension Flag Check
    print("\n[CHECK 3] Balance Sheet Query & Suspension Flag...")
    bs_data = database.get_balance_sheet_data(status_filter="all")
    assert "summary" in bs_data and "rows" in bs_data, "Balance sheet structure invalid!"
    print(f"  ✓ Active subscribers queried: {len(bs_data['rows'])}")
    for r in bs_data["rows"]:
        assert "is_suspended" in r, f"Row #{r['id']} missing is_suspended flag!"
    print(f"  ✓ All {len(bs_data['rows'])} rows have is_suspended property")

    # 4. Month-End Reconciliation Engine Check
    print("\n[CHECK 4] Month-End Reconciliation Calculation...")
    now = datetime.now()
    cur_month = now.strftime("%Y-%m")
    recon = database.get_monthly_reconciliation(cur_month)
    assert recon["month"] == cur_month, f"Recon month mismatch: {recon['month']}"
    assert recon["start_date"] == f"{cur_month}-01", f"Start date not 1st: {recon['start_date']}"
    assert "total_collected" in recon
    assert "staff_breakdown" in recon
    assert "method_breakdown" in recon
    assert "transactions" in recon
    assert "months_available" in recon and len(recon["months_available"]) == 12
    print(f"  ✓ Reconciliation for {recon['month_label']}:")
    print(f"    • Total Collected: {recon['total_collected']:.2f} SAR")
    print(f"    • Total Transactions: {recon['total_transactions']}")
    print(f"    • Paying Subscribers: {recon['paying_subscribers']} / {recon['total_active_subscribers']}")
    print(f"    • Staff Breakdown: {len(recon['staff_breakdown'])} collector(s)")
    for s in recon["staff_breakdown"]:
        print(f"      - {s['collector']}: {s['total']:.2f} SAR ({s['count']} tx, avg: {s['average']:.2f} SAR)")

    # 5. Suspension-Aware Accrual Pause Lifecycle Simulation
    print("\n[CHECK 5] Suspension Lifecycle & Accrual Pause Simulation...")
    # Create temporary subscriber for test
    test_phone = "0599998888"
    with database.get_db() as conn:
        conn.cursor().execute("DELETE FROM customers WHERE phone = ?", (test_phone,))
        conn.commit()

    created = database.create_customer(
        phone=test_phone,
        name="Test Suspension Subscriber",
        billing_type="monthly",
        package_name="15 Mbps Home",
        monthly_fee=30.0,
        due_day=1,
        notes="Room T-101"
    )
    test_cid = created["id"]
    print(f"  ✓ Created test subscriber #{test_cid}")

    try:
        # Step A: Check initial customer history (active)
        hist1 = database.get_balance_customer_history(test_cid)
        assert hist1["customer"]["is_suspended"] is False
        assert len(hist1["suspensions"]) == 0
        print("  ✓ Subscriber #{test_cid} initially Active with 0 suspensions")

        # Step B: Toggle to Suspended (service cut)
        new_st1, _ = database.toggle_customer_status(test_cid)
        assert new_st1 == "suspended"

        hist2 = database.get_balance_customer_history(test_cid)
        assert hist2["customer"]["is_suspended"] is True
        assert len(hist2["suspensions"]) == 1
        open_susp = hist2["suspensions"][0]
        assert open_susp["resumed_at"] is None, "Open suspension must have resumed_at = None!"
        print(f"  ✓ Status toggled to 'suspended': open suspension logged (ID #{open_susp['id']}, resumed_at=None)")

        # Step C: Toggle back to Active (service resumed)
        new_st2, _ = database.toggle_customer_status(test_cid)
        assert new_st2 == "active"

        hist3 = database.get_balance_customer_history(test_cid)
        assert hist3["customer"]["is_suspended"] is False
        assert len(hist3["suspensions"]) == 1
        closed_susp = hist3["suspensions"][0]
        assert closed_susp["resumed_at"] is not None, "Closed suspension must have resumed_at timestamp!"
        print(f"  ✓ Status toggled back to 'active': suspension closed (resumed_at={closed_susp['resumed_at']})")

        # Step D: Test Payment Collection Reactivation Hook
        # Suspend again
        database.toggle_customer_status(test_cid)
        hist4 = database.get_balance_customer_history(test_cid)
        assert hist4["customer"]["is_suspended"] is True
        assert len(hist4["suspensions"]) == 2
        print("  ✓ Re-suspended: second open suspension logged")

        # Record payment collection with collector
        col_res = database.record_balance_collection(
            customer_id=test_cid,
            amount=30.0,
            payment_type="cash",
            collector="Test Manager",
            notes="Reactivation payment"
        )
        assert col_res["success"] is True

        hist5 = database.get_balance_customer_history(test_cid)
        assert hist5["customer"]["is_suspended"] is False
        # All suspensions must be closed now
        for s in hist5["suspensions"]:
            assert s["resumed_at"] is not None, "Collection must close all open suspensions!"
        print("  ✓ Payment collected: customer reactivated and open suspension closed cleanly")

        # Step E: Verify month-end reconciliation includes the test collection
        recon_after = database.get_monthly_reconciliation(cur_month)
        manager_col = [s for s in recon_after["staff_breakdown"] if s["collector"] == "Test Manager"]
        assert len(manager_col) == 1, "Reconciliation must track Test Manager collections!"
        assert manager_col[0]["total"] >= 30.0
        print(f"  ✓ Month-end reconciliation correctly audited Test Manager ({manager_col[0]['total']:.2f} SAR)")

    finally:
        # Cleanup test records
        with database.get_db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM customer_suspensions WHERE customer_id = ?", (test_cid,))
            cur.execute("DELETE FROM collections WHERE customer_id = ?", (test_cid,))
            cur.execute("DELETE FROM customers WHERE id = ?", (test_cid,))
            conn.commit()
        print(f"  ✓ Cleaned up test subscriber #{test_cid} and all test transactions from database")

    # 6. HTTP Endpoints & Session Protection Check
    print("\n[CHECK 6] HTTP Endpoints & Session Protection...")
    import requests
    import auth_service

    # A: Unauthenticated access should redirect to /login
    r_unauth1 = requests.get("http://127.0.0.1:9911/balance", allow_redirects=False)
    assert r_unauth1.status_code == 303, f"Expected 303 for unauth /balance, got {r_unauth1.status_code}"
    r_unauth2 = requests.get("http://127.0.0.1:9911/balance/report", allow_redirects=False)
    assert r_unauth2.status_code == 303, f"Expected 303 for unauth /balance/report, got {r_unauth2.status_code}"
    print("  ✓ Unauthenticated requests strictly redirected to /login (HTTP 303)")

    # B: Authenticated access
    session_id, _ = auth_service.create_session(1)
    cookies = {auth_service.COOKIE_NAME: session_id}

    r_bal = requests.get("http://127.0.0.1:9911/balance", cookies=cookies)
    assert r_bal.status_code == 200, f"/balance returned {r_bal.status_code}"
    assert "Customer Balance Sheet" in r_bal.text
    assert "Month-End Report" in r_bal.text
    assert "monthReconciliationModal" in r_bal.text
    print("  ✓ Authenticated GET /balance -> HTTP 200 OK (Reconciliation modal & report button present)")

    r_rep = requests.get("http://127.0.0.1:9911/balance/report", cookies=cookies)
    assert r_rep.status_code == 200, f"/balance/report returned {r_rep.status_code}"
    assert "Month-End Collection Report" in r_rep.text
    assert "Print / Save PDF" in r_rep.text
    print("  ✓ Authenticated GET /balance/report -> HTTP 200 OK (Printable report ready)")

    r_api = requests.get("http://127.0.0.1:9911/api/balance/reconciliation", cookies=cookies)
    assert r_api.status_code == 200, f"/api/balance/reconciliation returned {r_api.status_code}"
    api_data = r_api.json()
    assert api_data.get("success") is True, "API reconciliation must return success=True"
    print("  ✓ Authenticated GET /api/balance/reconciliation -> HTTP 200 OK (JSON verified)")

    print("\n" + "=" * 70)
    print("ALL 6 VERIFICATION CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()

