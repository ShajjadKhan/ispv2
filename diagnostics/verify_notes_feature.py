#!/usr/bin/env python3
import sys
import os
import sqlite3
import jinja2

print("=== 1. Testing Jinja2 Template Compilation ===")
templates_dir = "/home/tserver/isp_v2/templates"
env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir))
for tmpl in ["dashboard.html", "approvals.html", "customers.html", "customer_edit.html"]:
    try:
        env.get_template(tmpl)
        print(f"  [PASS] Template {tmpl} compiled successfully.")
    except Exception as e:
        print(f"  [FAIL] Template {tmpl} compilation error: {e}")
        sys.exit(1)

print("\n=== 2. Testing Database Schema Migration ===")
import database
database.init_db()

with database.get_db() as conn:
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(customers)")
    cust_cols = [row[1] for row in cursor.fetchall()]
    print(f"  Customers columns count: {len(cust_cols)}")
    assert "notes" in cust_cols, "ERROR: 'notes' column missing from customers table!"
    print("  [PASS] 'notes' column present in customers table.")

    cursor.execute("PRAGMA table_info(connection_requests)")
    req_cols = [row[1] for row in cursor.fetchall()]
    print(f"  Connection requests columns count: {len(req_cols)}")
    assert "notes" in req_cols, "ERROR: 'notes' column missing from connection_requests table!"
    print("  [PASS] 'notes' column present in connection_requests table.")

print("\n=== 3. Testing Customer Creation with Room Number / Note ===")
test_phone = "0590009999"
test_name = "Test Room Note Customer"
test_notes = "Room 401 - Building A"

# Purge any old test record
with database.get_db() as conn:
    conn.execute("DELETE FROM customers WHERE phone = ?", (test_phone,))
    conn.execute("DELETE FROM connection_requests WHERE phone = ?", (test_phone,))
    conn.commit()

created = database.create_customer(
    phone=test_phone,
    name=test_name,
    billing_type="prepaid",
    package_name="Standard (20 Mbps)",
    monthly_fee=75.0,
    due_date="2026-11-04",
    max_devices=2,
    speed_limit="20M/20M",
    initial_payment=75.0,
    notes=test_notes
)

assert created is not None, "Failed to create customer"
assert created["notes"] == test_notes, f"Expected notes '{test_notes}', got '{created.get('notes')}'"
print(f"  [PASS] Customer #{created['id']} created with notes: '{created['notes']}'")

print("\n=== 4. Testing Customer Edit with Modified Room Number / Note ===")
updated_notes = "Room 401 (VIP Suite)"
updated = database.update_customer_details(
    customer_id=created["id"],
    notes=updated_notes
)
assert updated is not None, "Failed to update customer"
assert updated["notes"] == updated_notes, f"Expected notes '{updated_notes}', got '{updated.get('notes')}'"
print(f"  [PASS] Customer #{created['id']} updated with notes: '{updated['notes']}'")

print("\n=== 5. Testing Connection Request Creation and Approval with Note ===")
test_mac = "20:00:00:AA:BB:CC"
req_notes = "Room 505 - Penthouse"
with database.get_db() as conn:
    c = conn.cursor()
    c.execute("""
        INSERT INTO connection_requests (phone, mac_address, ip_address, status, created_at, updated_at)
        VALUES (?, ?, '10.50.1.99', 'pending', datetime('now'), datetime('now'))
    """, ("0590008888", test_mac))
    req_id = c.lastrowid
    conn.commit()

approved = database.approve_connection(
    req_id=req_id,
    name="Penthouse Resident",
    billing_type="prepaid",
    package_name="Standard (20 Mbps)",
    monthly_fee=75.0,
    collected_today=75.0,
    notes=req_notes
)

assert approved is not None, "Failed to approve connection"
assert approved["notes"] == req_notes, f"Expected notes '{req_notes}', got '{approved.get('notes')}'"

# Verify request table also persisted the note
req_check = database.get_request_by_id(req_id)
assert req_check.get("notes") == req_notes, f"Expected req notes '{req_notes}', got '{req_check.get('notes')}'"
print(f"  [PASS] Request #{req_id} approved with notes: '{approved['notes']}' and stored in connection_requests.")

# Clean up test data
with database.get_db() as conn:
    conn.execute("DELETE FROM customers WHERE phone IN (?, ?)", (test_phone, "0590008888"))
    conn.execute("DELETE FROM connection_requests WHERE phone IN (?, ?)", (test_phone, "0590008888"))
    conn.execute("DELETE FROM collections WHERE customer_id IN (?, ?)", (created["id"], approved["id"]))
    conn.commit()
print("  [PASS] Test data cleaned up safely.")

print("\n=======================================================")
print(" ALL CHECKS PASSED: Room Number / Notes Feature 100% OPERATIONAL")
print("=======================================================")
