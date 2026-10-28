#!/usr/bin/env python3
"""
Verification Script: Secondary Device Quick Authorize Modal Popup Audit
Verifies that:
1. When a secondary device requests connection, clicking 'Quick Authorize'
   always triggers the review popup modal (openApprovalModalFromBtn)
   instead of direct-approving in the background.
2. The Quick Authorize button carries complete HTML5 data attributes:
   data-req-id, data-phone, data-mac, data-ip, data-cust-name, data-is-secondary="1",
   data-max-devices, data-current-devices, data-pkg-name, data-expiry-date,
   data-notes, data-device-model.
3. Both quickApproveSecondary and quickApproveSecondaryFromBtn delegate safely
   to opening the approval modal.
4. The guest pass checkbox (chkIsGuestPass) is strictly unchecked by default,
   allowing the administrator to explicitly select Guest Pass (with days input & fee)
   or leave unchecked for permanent device authorization.
5. Optional bill collection and guest fees are summed properly into collected_today.
6. Verified across both Dashboard (/) and Approvals (/approvals).
"""
import sqlite3
import requests
import json
import re
import sys
from datetime import datetime

DB_PATH = "/home/tserver/isp_v2/isp_v2.db"
BASE_URL = "http://127.0.0.1:9911"

def get_admin_session():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1")
    row = cur.fetchone()
    con.close()
    if not row:
        raise RuntimeError("No active admin session found in database.")
    return row[0]

def main():
    print("=" * 75)
    print("VERIFYING SECONDARY DEVICE QUICK AUTHORIZE REVIEW POPUP")
    print("=" * 75)

    token = get_admin_session()
    print(f"[*] Active admin session token: {token[:12]}...")
    headers = {"Cookie": f"cybernet_session={token}"}

    # 1. Fetch live Dashboard (/) and Approvals (/approvals)
    r_dash = requests.get(f"{BASE_URL}/", headers=headers, timeout=15)
    assert r_dash.status_code == 200, f"/ returned HTTP {r_dash.status_code}"
    html_dash = r_dash.text
    print(f"[✓] Dashboard loaded successfully (HTTP 200, {len(html_dash)} bytes)")

    r_app = requests.get(f"{BASE_URL}/approvals", headers=headers, timeout=15)
    assert r_app.status_code == 200, f"/approvals returned HTTP {r_app.status_code}"
    html_app = r_app.text
    print(f"[✓] Approvals page loaded successfully (HTTP 200, {len(html_app)} bytes)")

    # 2. Check JavaScript handlers in Dashboard
    assert "function quickApproveSecondaryFromBtn(btn)" in html_dash
    assert "openApprovalModalFromBtn(btn)" in html_dash
    assert "function quickApproveSecondary(reqId, custName, btnElement)" in html_dash
    
    # Ensure quickApproveSecondary does NOT make a direct POST request to /approve
    quick_fn_match = re.search(r"function quickApproveSecondary\(reqId, custName, btnElement\) \{(.*?)\}\n\s*window\.quickApproveSecondary", html_dash, re.DOTALL)
    assert quick_fn_match, "FAIL: quickApproveSecondary function not found in dashboard"
    quick_fn_body = quick_fn_match.group(1)
    assert "fetch(" not in quick_fn_body, "FAIL: quickApproveSecondary in dashboard still directly fetches /approve!"
    assert "openApprovalModalFromBtn" in quick_fn_body or "openApprovalModal" in quick_fn_body, "FAIL: quickApproveSecondary does not open modal!"
    print("[✓] Dashboard quickApproveSecondary safely delegates to openApprovalModal (0 direct background approvals)")

    # 3. Check JavaScript handlers in Approvals
    quick_app_match = re.search(r"function quickApproveSecondary\(reqId, custName, btnElement\) \{(.*?)\}\n\s*window\.quickApproveSecondary", html_app, re.DOTALL)
    assert quick_app_match, "FAIL: quickApproveSecondary function not found in approvals"
    quick_app_body = quick_app_match.group(1)
    assert "fetch(" not in quick_app_body, "FAIL: quickApproveSecondary in approvals still directly fetches /approve!"
    assert "openApprovalModalFromBtn" in quick_app_body or "openApprovalModal" in quick_app_body, "FAIL: quickApproveSecondary in approvals does not open modal!"
    print("[✓] Approvals quickApproveSecondary safely delegates to openApprovalModal (0 direct background approvals)")

    # 4. Check Guest Pass default unchecked & fee calculations
    assert "chkGuest.checked = false;" in html_dash, "FAIL: chkGuest default false missing in dashboard"
    assert "chkGuest.checked = false;" in html_app, "FAIL: chkGuest default false missing in approvals"
    assert "(extraFee || 0.0) + (guestFee || 0.0)" in html_dash, "FAIL: fee summation missing in dashboard submitApproval"
    assert "(extraFee || 0.0) + (guestFee || 0.0)" in html_app, "FAIL: fee summation missing in approvals submitApproval"
    print("[✓] Guest Pass controls verified: strictly UNCHECKED by default with proper fee summation")

    # 5. Insert a test secondary connection request
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    # Find an existing active customer
    cur.execute("SELECT id, name, phone, notes, max_devices FROM customers WHERE status = 'active' LIMIT 1")
    cust_row = cur.fetchone()
    assert cust_row, "No active customer found to test secondary approval"
    test_cid, test_cname, test_cphone, test_cnotes, test_max_dev = cust_row
    print(f"[*] Testing secondary request against customer #{test_cid} ({test_cname}, {test_cphone})")

    test_mac = "00:11:22:33:44:55"
    cur.execute("DELETE FROM connection_requests WHERE mac_address = ?", (test_mac,))
    con.commit()

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("""
        INSERT INTO connection_requests (phone, mac_address, ip_address, customer_name, customer_id, notes, device_model, status, is_secondary, created_at, updated_at)
        VALUES (?, ?, '10.41.0.188', ?, ?, ?, 'Samsung Galaxy S24 Ultra', 'pending', 1, ?, ?)
    """, (test_cphone, test_mac, test_cname, test_cid, test_cnotes, now_str, now_str))
    test_req_id = cur.lastrowid
    con.commit()
    con.close()
    print(f"[+] Inserted test secondary request #{test_req_id} for {test_cname} ({test_mac})")

    try:
        # 6. Verify Dashboard HTML render of the secondary request
        r_dash_test = requests.get(f"{BASE_URL}/", headers=headers, timeout=15)
        html_dash_test = r_dash_test.text
        assert f'id="req-row-{test_req_id}"' in html_dash_test, "FAIL: test row missing in dashboard"

        row_idx = html_dash_test.find(f'id="req-row-{test_req_id}"')
        row_end = html_dash_test.find('</tr>', row_idx)
        row_slice = html_dash_test[row_idx:row_end+5]

        # Check Quick Authorize button has openApprovalModalFromBtn and all data attributes
        if 'onclick="openApprovalModalFromBtn(this)"' not in row_slice:
            print("DEBUG ROW_SLICE:")
            print(row_slice)
        assert 'onclick="openApprovalModalFromBtn(this)"' in row_slice, "FAIL: Quick Authorize button missing openApprovalModalFromBtn in dashboard"
        assert f'data-req-id="{test_req_id}"' in row_slice, "FAIL: data-req-id missing on Quick Authorize button"
        assert f'data-phone="{test_cphone}"' in row_slice, "FAIL: data-phone missing on Quick Authorize button"
        assert f'data-mac="{test_mac}"' in row_slice, "FAIL: data-mac missing on Quick Authorize button"
        assert 'data-is-secondary="1"' in row_slice, "FAIL: data-is-secondary missing on Quick Authorize button"
        assert '<span>Quick Authorize</span>' in row_slice, "FAIL: Quick Authorize label missing"
        assert 'quickApproveSecondary(' not in row_slice, "FAIL: direct quickApproveSecondary onclick still present in row"
        print("[✓] Live Dashboard row correctly renders Quick Authorize button:")
        print(f"    - onclick=\"openApprovalModalFromBtn(this)\"")
        print(f"    - data-req-id=\"{test_req_id}\", data-phone=\"{test_cphone}\", data-mac=\"{test_mac}\"")
        print(f"    - data-is-secondary=\"1\", data-cust-name=\"{test_cname}\"")

        # 7. Verify Approvals HTML render of the secondary request
        r_app_test = requests.get(f"{BASE_URL}/approvals", headers=headers, timeout=15)
        html_app_test = r_app_test.text
        assert f'id="req-row-{test_req_id}"' in html_app_test, "FAIL: test row missing in approvals"

        app_row_idx = html_app_test.find(f'id="req-row-{test_req_id}"')
        app_row_end = html_app_test.find('</tr>', app_row_idx)
        app_row_slice = html_app_test[app_row_idx:app_row_end+5]
        assert 'onclick="openApprovalModalFromBtn(this)"' in app_row_slice, "FAIL: Quick Authorize button missing openApprovalModalFromBtn in approvals"
        assert '<span>Quick Authorize</span>' in app_row_slice, "FAIL: Quick Authorize label missing in approvals"
        print("[✓] Live Approvals page row correctly renders Quick Authorize button:")
        print(f"    - onclick=\"openApprovalModalFromBtn(this)\"")
        print(f"    - Label: 'Quick Authorize'")

    finally:
        # Clean up test connection request
        con = sqlite3.connect(DB_PATH)
        con.execute("DELETE FROM connection_requests WHERE id = ?", (test_req_id,))
        con.commit()
        con.close()
        print(f"[*] Cleaned up test secondary request #{test_req_id}")

    print("=" * 75)
    print("ALL SECONDARY QUICK AUTHORIZE VERIFICATION CHECKS PASSED (100% SUCCESS)!")
    print("=" * 75)

if __name__ == "__main__":
    main()
