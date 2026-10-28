#!/usr/bin/env python3
import requests
import auth_service

BASE_URL = "http://127.0.0.1:9911"
session = requests.Session()

print("1. Creating authentic admin session via auth_service...")
session_id, _ = auth_service.create_session(user_id=1, client_ip="127.0.0.1", user_agent="TestRunner/1.0", remember_me=True)
session.cookies.set(auth_service.COOKIE_NAME, session_id)
print(f"  [PASS] Session created with cookie '{auth_service.COOKIE_NAME}'.")

print("\n2. Checking /dashboard template...")
dash = session.get(f"{BASE_URL}/dashboard")
assert dash.status_code == 200, f"Dashboard failed: {dash.status_code}"
assert 'id="custNotes"' in dash.text, "Dashboard missing #custNotes"
assert 'id="secondaryCustNotes"' in dash.text, "Dashboard missing #secondaryCustNotes"
print("  [PASS] /dashboard contains customer room/notes input fields.")

print("\n3. Checking /approvals template...")
appr = session.get(f"{BASE_URL}/approvals")
assert appr.status_code == 200, f"Approvals failed: {appr.status_code}"
assert 'id="custNotes"' in appr.text, "Approvals missing #custNotes"
assert 'id="secondaryCustNotes"' in appr.text, "Approvals missing #secondaryCustNotes"
print("  [PASS] /approvals contains customer room/notes input fields.")

print("\n4. Checking /customers template...")
cust = session.get(f"{BASE_URL}/customers")
assert cust.status_code == 200, f"Customers failed: {cust.status_code}"
assert 'id="newCustNotes"' in cust.text, "Customers missing #newCustNotes"
assert 'id="editCustNotes"' in cust.text, "Customers missing #editCustNotes"
print("  [PASS] /customers contains add & edit room/notes modal input fields.")

print("\n5. Checking /customers/2/edit template...")
cedit = session.get(f"{BASE_URL}/customers/2/edit")
assert cedit.status_code == 200, f"Customer edit page failed: {cedit.status_code}"
assert 'id="custNotes"' in cedit.text, "Customer edit page missing #custNotes"
print("  [PASS] /customers/2/edit contains #custNotes input.")

print("\n6. Testing customer note edit API...")
# Read existing note
orig_cust = session.get(f"{BASE_URL}/api/customers/2").json()
orig_notes = orig_cust.get("notes") or ""

# Update note
test_note = "Room 302 - Test Unit"
edit_resp = session.post(f"{BASE_URL}/api/customers/2/edit", json={"notes": test_note})
assert edit_resp.status_code == 200, f"Edit API failed: {edit_resp.text}"
edit_json = edit_resp.json()
assert edit_json["success"] is True, "Edit response success is False"
assert edit_json["customer"]["notes"] == test_note, f"Notes mismatch: {edit_json['customer']['notes']}"
print(f"  [PASS] Customer 2 notes updated to '{test_note}'.")

# Verify in /customers HTML rendering
cust_page = session.get(f"{BASE_URL}/customers").text
assert "🚪 Room 302 - Test Unit" in cust_page, "Badge missing in /customers page"
print("  [PASS] Badge '🚪 Room 302 - Test Unit' rendered in /customers table.")

# Restore original notes
restore_resp = session.post(f"{BASE_URL}/api/customers/2/edit", json={"notes": orig_notes})
assert restore_resp.status_code == 200
print("  [PASS] Customer 2 notes restored cleanly.")

print("\n=======================================================")
print(" ALL 6 END-TO-END CHECKS PASSED: 100% OPERATIONAL")
print("=======================================================")
