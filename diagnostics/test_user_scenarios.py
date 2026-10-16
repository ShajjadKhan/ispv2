import sys
import os
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def test_partial_payment_preserves_admin_date():
    print("=== Testing Scenario 1: Partial payment preserves admin date ===")
    with database.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, expiry_date, due_date, monthly_fee, credit_balance FROM customers WHERE name LIKE '%Shajjad%' OR id = 29 LIMIT 1")
        row = cur.fetchone()
        cid = row["id"]
        original_exp = row["expiry_date"]
        original_due = row["due_date"]
        print(f"Customer #{cid} ({row['name']}): current due={original_due}, exp={original_exp}")

        # Set authority date to Oct 31, 2026
        target_admin_date = "2026-10-31"
        cur.execute("UPDATE customers SET due_date = ?, expiry_date = ?, monthly_fee = 100.0 WHERE id = ?", (target_admin_date, target_admin_date, cid))
        conn.commit()

        # Simulate collecting partial payment of 30 SAR (out of 100 SAR monthly fee)
        res = database.smart_collect_customer_payment(
            customer_id=cid,
            amount=30.0,
            payment_type="cash",
            collector="Admin Test",
            notes="Partial payment test 30 SAR"
        )
        print("Smart Collect Result:", res["message"])

        # Check customer record
        cur.execute("SELECT id, due_date, expiry_date, status, credit_balance FROM customers WHERE id = ?", (cid,))
        updated = dict(cur.fetchone())
        print(f"Customer #{cid} after 30 SAR partial payment:")
        print(f"  Due Date:    {updated['due_date']} (Expected: >= 2026-10-31)")
        print(f"  Expiry Date: {updated['expiry_date']} (Expected: >= 2026-10-31)")
        print(f"  Status:      {updated['status']} (Expected: active)")

        assert updated["due_date"] >= target_admin_date, f"Due date regressed! Got {updated['due_date']}"
        assert updated["expiry_date"] >= target_admin_date, f"Expiry date regressed! Got {updated['expiry_date']}"
        assert updated["status"] == "active", "Status should be active"
        print("--> Scenario 1 PASSED: Expiry date NEVER moved backward! It remained consistent with admin setting.")

        # Restore original dates
        cur.execute("UPDATE customers SET due_date = ?, expiry_date = ? WHERE id = ?", (original_due, original_exp, cid))
        conn.commit()

def test_mac_saved_when_suspended():
    print("\n=== Testing Scenario 2: MAC address retained in software when suspended ===")
    with database.get_db() as conn:
        cur = conn.cursor()
        # Find customer with at least one device
        cur.execute("""
            SELECT c.id, c.name, cd.mac_address 
            FROM customers c 
            JOIN customer_devices cd ON cd.customer_id = c.id 
            LIMIT 1
        """)
        row = cur.fetchone()
        cid = row["id"]
        mac = row["mac_address"]
        print(f"Testing Customer #{cid} ({row['name']}) with MAC {mac}")

        # Simulate customer being suspended & device blocked
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE customers SET status = 'suspended', updated_at = ? WHERE id = ?", (now_str, cid))
        cur.execute("UPDATE customer_devices SET status = 'blocked' WHERE customer_id = ?", (cid,))
        conn.commit()
        
        # Verify in get_all_customers
        all_custs = database.get_all_customers()
        cust_match = next((c for c in all_custs if c["id"] == cid), None)
        assert cust_match is not None, "Customer not found in get_all_customers"
        dev_macs = [d["mac_address"].upper() for d in cust_match.get("devices", [])]
        print(f"Suspended Customer in get_all_customers: devices={len(dev_macs)}, MACs={dev_macs}")
        assert mac.upper() in dev_macs, f"MAC {mac} was missing from get_all_customers when customer was suspended!"

        # Verify in get_dashboard_metrics
        dash = database.get_dashboard_metrics()
        dash_custs = dash.get("all_customers", [])
        dash_match = next((c for c in dash_custs if c["id"] == cid), None)
        assert dash_match is not None, "Customer not found in dashboard metrics"
        assert dash_match.get("primary_mac") is not None, f"primary_mac was None for suspended customer!"
        print(f"Suspended Customer in dashboard metrics: primary_mac={dash_match.get('primary_mac')}")

        # Verify in get_customer_by_mac
        lookup = database.get_customer_by_mac(mac)
        assert lookup is not None, f"get_customer_by_mac returned None for registered MAC {mac}!"
        print(f"get_customer_by_mac({mac}): found Customer #{lookup['id']} ({lookup['name']})")

        # Restore customer status to active
        cur.execute("UPDATE customers SET status = 'active', updated_at = ? WHERE id = ?", (now_str, cid))
        cur.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (cid,))
        conn.commit()
        print("--> Scenario 2 PASSED: MAC address was 100% saved and retained in our software while suspended!")

if __name__ == "__main__":
    test_partial_payment_preserves_admin_date()
    test_mac_saved_when_suspended()
