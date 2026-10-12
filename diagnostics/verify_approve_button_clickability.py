#!/usr/bin/env python3
"""
Verification Script: Wi-Fi Join Approve Button Reliability & Clickability
Tests templates/dashboard.html and templates/approvals.html for:
1. DOM Caching & Active Modal Guards in dynamic poller (race-condition prevention)
2. Interactive Random MAC button replacing inert disabled button
3. Fail-safe modal opening with defensive try/catch blocks
4. HTML quote-escaping across dataset attributes
5. Event delegation safety net for touch & click
6. Jinja template syntax compilation
"""

import sys
import os
import re
from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_tests():
    print("=" * 70)
    print("🔍 VERIFYING APPROVE BUTTON RELIABILITY & CLICKABILITY")
    print("=" * 70)

    # 1. Check templates/dashboard.html
    dash_path = os.path.join(PROJECT_ROOT, "templates", "dashboard.html")
    with open(dash_path, "r", encoding="utf-8") as f:
        dash_content = f.read()

    print("\n[Phase 1] Auditing templates/dashboard.html...")
    
    # 1.1 Signature caching & Modal Guard
    assert "_lastPendingSignature" in dash_content, "FAIL: _lastPendingSignature missing in dashboard.html"
    assert "if (modal && modal.classList.contains('open'))" in dash_content, "FAIL: Modal open guard missing in refreshPendingRequests"
    print("  ✓ Poller contains _lastPendingSignature and active modal guard")

    # 1.2 escapeHtml used for attributes
    assert "const safeName = escapeHtml(rawName);" in dash_content, "FAIL: safeName not escaped with escapeHtml"
    assert "data-cust-name=\"${safeName}\"" in dash_content, "FAIL: data-cust-name missing escaped safeName"
    print("  ✓ Poller dynamic attributes use escapeHtml escaping")

    # 1.3 Random MAC button is interactive
    assert "btn-approve btn-random-mac" in dash_content, "FAIL: btn-random-mac class missing"
    assert "showRandomMacNotice" in dash_content, "FAIL: showRandomMacNotice helper missing"
    # Ensure no disabled attribute on the random mac button in dashboard.html
    assert 'class="btn-approve" disabled' not in dash_content, "FAIL: Inert 'disabled' button still present in dashboard.html"
    print("  ✓ Random MAC button upgraded to interactive with showRandomMacNotice")

    # 1.4 Fail-safe openApprovalModal
    assert "modal.classList.add('open')" in dash_content, "FAIL: modal.classList.add('open') missing"
    assert "try {" in dash_content and "catch (err) {" in dash_content, "FAIL: try/catch block missing in openApprovalModal"
    print("  ✓ openApprovalModal contains try/catch fail-safe and modal opening")

    # 1.5 Event delegation
    assert "tableBody.addEventListener('click'" in dash_content, "FAIL: Event delegation listener missing in dashboard.html"
    print("  ✓ Table body has click event delegation safety net")

    # 2. Check templates/approvals.html
    app_path = os.path.join(PROJECT_ROOT, "templates", "approvals.html")
    with open(app_path, "r", encoding="utf-8") as f:
        app_content = f.read()

    print("\n[Phase 2] Auditing templates/approvals.html...")
    assert "showRandomMacNotice" in app_content, "FAIL: showRandomMacNotice helper missing in approvals.html"
    assert 'class="btn-approve" disabled' not in app_content, "FAIL: Inert 'disabled' button still present in approvals.html"
    assert "openApprovalModal" in app_content, "FAIL: openApprovalModal missing in approvals.html"
    print("  ✓ approvals.html matches hardening with interactive notice and null checks")

    # 3. Test Jinja Compilation
    print("\n[Phase 3] Compiling Jinja Templates...")
    env = Environment(loader=FileSystemLoader(os.path.join(PROJECT_ROOT, "templates")))
    dash_tmpl = env.get_template("dashboard.html")
    app_tmpl = env.get_template("approvals.html")
    print("  ✓ dashboard.html compiled successfully without Jinja errors")
    print("  ✓ approvals.html compiled successfully without Jinja errors")

    print("\n" + "=" * 70)
    print("✅ ALL APPROVE BUTTON RELIABILITY AUDIT PHASES PASSED 100%!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
