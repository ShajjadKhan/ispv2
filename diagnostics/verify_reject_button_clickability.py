#!/usr/bin/env python3
"""
Verification Script: Wi-Fi Join Reject Button Reliability & Mobile Clickability
Audits templates/base.html, templates/dashboard.html, and templates/approvals.html
Verifies Inline 2-Step Confirmation Engine, Touch Handling, and Cache-Control Headers
"""

import sys
import os
import re
from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_tests():
    print("=" * 75)
    print("?? AUDITING WI-FI JOIN REJECT BUTTON RELIABILITY & MOBILE CLICKABILITY")
    print("=" * 75)

    # 1. Audit templates/base.html
    base_path = os.path.join(PROJECT_ROOT, "templates", "base.html")
    with open(base_path, "r", encoding="utf-8") as f:
        base_content = f.read()

    print("\n[Phase 1] Auditing templates/base.html...")
    assert "openedAt = Date.now()" in base_content, "FAIL: Ghost click guard openedAt missing in cyberConfirm"
    assert "Date.now() - openedAt < 350" in base_content, "FAIL: 350ms ghost-click guard missing in cyberConfirm overlay.onclick"
    assert "ok.ontouchend" in base_content and "cancel.ontouchend" in base_content, "FAIL: ontouchend handlers missing in cyberConfirm"
    assert "window.isCyberConfirmOpen" in base_content, "FAIL: isCyberConfirmOpen missing in base.html"
    assert "touch-action: manipulation" in base_content, "FAIL: touch-action manipulation missing in cyber-confirm-btn"
    assert "min-height: 48px" in base_content, "FAIL: Mobile 48px min-height missing in cyber-confirm-btn"
    print("  ? cyberConfirm ghost-click prevention, mobile ontouchend, and 48px touch targets verified")

    # 2. Audit templates/dashboard.html
    dash_path = os.path.join(PROJECT_ROOT, "templates", "dashboard.html")
    with open(dash_path, "r", encoding="utf-8") as f:
        dash_content = f.read()

    print("\n[Phase 2] Auditing templates/dashboard.html...")
    assert "handleRejectClick" in dash_content, "FAIL: handleRejectClick missing in dashboard.html"
    assert "btn-reject-confirming" in dash_content, "FAIL: btn-reject-confirming styling missing in dashboard.html"
    assert "Rejecting..." in dash_content, "FAIL: Visual Rejecting spinner state missing in rejectRequest"
    assert "window.rejectRequest = rejectRequest" in dash_content, "FAIL: window.rejectRequest not exposed globally"
    assert 'data-action="reject"' in dash_content, "FAIL: data-action=reject missing from reject buttons"
    assert "rejectBtn = e.target.closest('.btn-reject')" in dash_content, "FAIL: Fail-safe reject click delegation missing in dashboard.html"
    assert "min-height: 46px !important;" in dash_content, "FAIL: Mobile 46px min-height missing in .btn-reject"
    assert "user-select: none !important;" not in dash_content[dash_content.find("td.td-actions button.btn-reject"):dash_content.find("td.td-actions button.btn-reject") + 500], "FAIL: user-select none still present on mobile button.btn-reject"
    print("  ? dashboard.html inline 2-step confirmation engine, pulse styling, and touch optimization verified")

    # 3. Audit templates/approvals.html
    app_path = os.path.join(PROJECT_ROOT, "templates", "approvals.html")
    with open(app_path, "r", encoding="utf-8") as f:
        app_content = f.read()

    print("\n[Phase 3] Auditing templates/approvals.html...")
    assert "handleRejectClick" in app_content, "FAIL: handleRejectClick missing in approvals.html"
    assert "btn-reject-confirming" in app_content, "FAIL: btn-reject-confirming styling missing in approvals.html"
    assert "window.rejectRequest = rejectRequest" in app_content, "FAIL: window.rejectRequest missing in approvals.html"
    assert "rejectBtn = e.target.closest('.btn-reject')" in app_content, "FAIL: Click delegation missing in approvals.html"
    assert "min-height: 46px !important;" in app_content, "FAIL: Mobile 46px min-height missing in approvals.html .btn-reject"
    assert "pending-actions-wrap" in app_content, "FAIL: pending-actions-wrap class missing in approvals.html"
    print("  ? approvals.html inline 2-step confirmation engine, pulse styling, and touch optimization verified")

    # 4. Jinja2 Compilation Test
    print("\n[Phase 4] Testing Jinja2 Template Compilation...")
    env = Environment(loader=FileSystemLoader(os.path.join(PROJECT_ROOT, "templates")))
    env.get_template("base.html")
    env.get_template("dashboard.html")
    env.get_template("approvals.html")
    print("  ? base.html, dashboard.html, and approvals.html compile cleanly with Jinja2")

    print("\n" + "=" * 75)
    print("? ALL WI-FI JOIN REJECT BUTTON AUDIT PHASES PASSED 100%!")
    print("=" * 75)
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
