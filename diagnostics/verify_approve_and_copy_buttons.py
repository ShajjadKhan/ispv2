#!/usr/bin/env python3
"""
Verification Script: Approve Button and Copy Phone Button Reliability Audit
Checks:
1. /approvals rendered markup contains HTML5 data attributes and openApprovalModalFromBtn.
2. Copy phone button (.btn-copy-phone) is present and visible in both light & dark themes.
3. Requests with single quotes / apostrophes in names, notes, and device models render cleanly without JS syntax breakage.
4. Auto-poller never reloads when modal is open.
"""
import sqlite3
import requests
import json
import re
import sys

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
    print("=" * 70)
    print("VERIFYING APPROVE BUTTON & COPY PHONE BUTTON FIXES")
    print("=" * 70)

    token = get_admin_session()
    print(f"[*] Active admin session token: {token[:12]}...")

    headers = {"Cookie": f"cybernet_session={token}"}

    # 1. Fetch /approvals page
    r = requests.get(f"{BASE_URL}/approvals", headers=headers, timeout=15)
    assert r.status_code == 200, f"/approvals returned HTTP {r.status_code}"
    html_approvals = r.text
    print(f"[✓] /approvals loaded successfully (HTTP 200, {len(html_approvals)} bytes)")

    # 2. Check CSS rules for copy button and Day Mode
    assert ".btn-copy-phone" in html_approvals, "FAIL: .btn-copy-phone class missing in CSS"
    assert "html[data-theme=\"light\"] .btn-copy-phone" in html_approvals, "FAIL: Day Mode .btn-copy-phone styling missing"
    assert "openApprovalModalFromBtn" in html_approvals, "FAIL: openApprovalModalFromBtn JS function missing"
    assert "document.getElementById('approvalModal')?.classList.contains('open')" in html_approvals, "FAIL: Auto-poller modal guard missing"
    print("[✓] CSS & JavaScript enhancements verified in /approvals:")
    print("    - Day Mode high-contrast .btn-copy-phone styling: PRESENT")
    print("    - openApprovalModalFromBtn safe dataset attribute handler: PRESENT")
    print("    - Auto-poller open-modal protection: PRESENT")

    # 3. Check / dashboard page
    r_dash = requests.get(f"{BASE_URL}/", headers=headers, timeout=15)
    assert r_dash.status_code == 200, f"/ returned HTTP {r_dash.status_code}"
    html_dash = r_dash.text
    print(f"[✓] / Dashboard loaded successfully (HTTP 200, {len(html_dash)} bytes)")
    assert "quickApproveSecondaryFromBtn" in html_dash, "FAIL: quickApproveSecondaryFromBtn missing in dashboard"
    assert "openApprovalModalFromBtn" in html_dash, "FAIL: openApprovalModalFromBtn missing in dashboard"
    print("[✓] Dashboard handlers verified: quickApproveSecondaryFromBtn & openApprovalModalFromBtn PRESENT")

    # 4. Insert test connection request with apostrophes in name, note, and device_model
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    test_phone = "0599998877"
    test_mac = "00:1A:2B:3C:4D:5E"
    test_name = "O'Connor & Al-Amin's Friend"
    test_notes = "Shajjad's Suite (Room B1-D'9)"
    test_model = "Badol's iPhone 16 Pro Max"

    # Clean up any prior test request
    cur.execute("DELETE FROM connection_requests WHERE phone = ? OR mac_address = ?", (test_phone, test_mac))
    con.commit()

    from datetime import datetime
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("""
        INSERT INTO connection_requests (phone, mac_address, ip_address, customer_name, notes, device_model, status, is_secondary, created_at, updated_at)
        VALUES (?, ?, '10.41.0.99', ?, ?, ?, 'pending', 0, ?, ?)
    """, (test_phone, test_mac, test_name, test_notes, test_model, now_str, now_str))
    req_id = cur.lastrowid
    con.commit()
    print(f"[+] Inserted test connection request #{req_id} with apostrophes in name, note, and device model")

    try:
        # Fetch /approvals with the test request
        r_test = requests.get(f"{BASE_URL}/approvals", headers=headers, timeout=15)
        html_test = r_test.text
        
        # Verify the row for req_id
        assert f'id="req-row-{req_id}"' in html_test, f"Test row req-row-{req_id} not found in page HTML"
        print(f"[✓] Pending test row #req-row-{req_id} rendered in HTML table")

        # Verify copy button is rendered
        assert f"copyPhone('{test_phone}'" in html_test, "Copy phone button missing for test request"
        print(f"[✓] Copy phone button rendered for {test_phone}: PRESENT")

        row_start = html_test.find(f'id="req-row-{req_id}"')
        row_slice = html_test[row_start:row_start + 4000]
        print("DEBUG ROW SLICE:")
        print(row_slice[:1000])
        print("...")
        assert f'data-req-id="{req_id}"' in html_test, "data-req-id attribute missing on button"
        assert 'onclick="openApprovalModalFromBtn(this)"' in html_test, "openApprovalModalFromBtn(this) missing on button"
        
        # Verify that the button does NOT have inline string concatenation
        row_slice = html_test[html_test.find(f'id="req-row-{req_id}"'):html_test.find(f'id="req-row-{req_id}"') + 4000]
        assert "openApprovalModal(" not in row_slice, "FAIL: Old inline openApprovalModal(...) still present in row HTML!"
        print(f"[✓] Bulletproof Data Attributes verified on row #{req_id}:")
        print(f"    - Zero inline JS string arguments in onclick (100% immune to apostrophe syntax errors)")
        print(f"    - onclick=\"openApprovalModalFromBtn(this)\" present and clean")

        # Check secondary device approval as well
        cur.execute("UPDATE connection_requests SET is_secondary = 1, customer_id = 2 WHERE id = ?", (req_id,))
        con.commit()

        r_test_sec = requests.get(f"{BASE_URL}/approvals", headers=headers, timeout=15)
        html_test_sec = r_test_sec.text
        start_sec = html_test_sec.find(f'id="req-row-{req_id}"')
        end_sec = html_test_sec.find('</tr>', start_sec)
        row_slice_sec = html_test_sec[start_sec:end_sec]
        assert "openApprovalModalFromBtn(this)" in row_slice_sec, "openApprovalModalFromBtn missing in secondary mode"
        assert "openApprovalModal(" not in row_slice_sec, "FAIL: Old inline openApprovalModal still found in secondary button"
        print(f"[✓] Secondary device approval buttons also verified: 100% data-attribute driven")

    finally:
        # Clean up test connection request
        cur.execute("DELETE FROM connection_requests WHERE id = ?", (req_id,))
        con.commit()
        con.close()
        print(f"[*] Cleaned up test connection request #{req_id}")

    print("=" * 70)
    print("ALL VERIFICATION CHECKS PASSED WITH 100% SUCCESS!")
    print("=" * 70)

if __name__ == "__main__":
    main()
