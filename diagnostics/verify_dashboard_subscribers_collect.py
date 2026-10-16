import sys
import re
import requests

def test_dashboard_collect_workflow():
    session = requests.Session()
    base_url = "http://127.0.0.1:9911"

    import sqlite3
    import os

    db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else 'isp_v2.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1")
    row = cur.fetchone()
    assert row, "No active admin session found in database"
    session_id = row[0]
    conn.close()

    # Step 1: Set Session Cookie
    print(f"[1] Setting session cookie (id: {session_id[:8]}...)...")
    session.cookies.set("cybernet_session", session_id)
    print("    Session cookie attached.")

    # Step 2: Fetch Dashboard HTML
    print("[2] Fetching Dashboard ('/')...")
    dash_resp = session.get(f"{base_url}/", timeout=15)
    assert dash_resp.status_code == 200, f"Dashboard route returned {dash_resp.status_code}"
    html = dash_resp.text
    print(f"    Dashboard delivered {len(html)} bytes.")

    # Step 3: Verify Subscribers Hub table & Collect buttons
    print("[3] Auditing Subscribers Hub in rendered DOM...")
    assert 'id="subscribersTable"' in html, "Missing #subscribersTable in dashboard DOM"
    assert 'id="subscribersTableBody"' in html, "Missing #subscribersTableBody in dashboard DOM"
    assert 'class="btn-quick-collect"' in html, "Missing .btn-quick-collect in dashboard DOM"
    assert 'id="collectModal"' in html, "Missing #collectModal in dashboard DOM"
    assert 'function openCollectModal(' in html or 'async function openCollectModal(' in html, "Missing openCollectModal function definition"
    
    # Extract customer IDs from the rendered Subscribers Hub table
    # Pattern: data-cid="(\d+)"
    collect_buttons = re.findall(r'btn-quick-collect"[^>]*data-cid="(\d+)"[^>]*data-cname="([^"]*)"', html)
    print(f"    Found {len(collect_buttons)} Quick Collect button(s) in rendered dashboard.")
    assert len(collect_buttons) > 0, "No collect buttons found in Subscribers Hub"

    # Step 4: Test API billing-breakdown endpoint for first 3 subscribers
    sample_subscribers = collect_buttons[:3]
    print(f"[4] Testing /api/customers/{'{cid}'}/billing-breakdown for sample subscribers...")
    for cid, name in sample_subscribers:
        api_url = f"{base_url}/api/customers/{cid}/billing-breakdown"
        api_resp = session.get(api_url, timeout=10)
        assert api_resp.status_code == 200, f"Breakdown API for cid {cid} returned {api_resp.status_code}"
        data = api_resp.json()
        b = data.get("breakdown", data)
        assert "credit_balance" in b or "balance" in b, f"Missing credit_balance in breakdown for cid {cid}"
        print(f"    CID #{cid} ({name}): Wallet Balance = {b.get('credit_balance')} SAR | Total Due = {b.get('total_due')} SAR")

    print("[5] Checking JavaScript syntax integrity...")
    # Verify no duplicate let activeCollCustId
    active_coll_decls = re.findall(r'\blet\s+activeCollCustId\b', html)
    print(f"    Occurrences of 'let activeCollCustId' in rendered page: {len(active_coll_decls)}")
    assert len(active_coll_decls) == 1, f"Expected exactly 1 declaration of activeCollCustId, found {len(active_coll_decls)}"

    print("\n>>> ALL DASHBOARD SUBSCRIBERS HUB COLLECT AUDITS PASSED 100% <<<")

if __name__ == '__main__':
    try:
        test_dashboard_collect_workflow()
    except Exception as e:
        print(f"\n[FAIL] Test encountered error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
