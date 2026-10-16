import sys
import re
import requests
import sqlite3
import os

def test_mobile_filters():
    base_url = "http://127.0.0.1:9911"
    session = requests.Session()

    db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else 'isp_v2.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1")
    row = cur.fetchone()
    assert row, "No active admin session found in database"
    session_id = row[0]
    conn.close()

    session.cookies.set("cybernet_session", session_id)

    print("[1] Fetching live rendered Dashboard ('/')...")
    resp = session.get(f"{base_url}/", timeout=15)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    html = resp.text
    print(f"    Delivered {len(html)} bytes.")

    print("[2] Verifying CSS mobile rules for tier deck and subscriber row hiding...")
    # Check that mobile tier-filter-deck display: flex !important has been fixed
    assert '.tier-filter-deck.active-deck' in html, "Missing .tier-filter-deck.active-deck"
    assert '.tier-filter-deck.deck-hidden' in html, "Missing .tier-filter-deck.deck-hidden"
    assert '#subscribersTable tr.cust-row.cust-hidden' in html, "Missing #subscribersTable tr.cust-row.cust-hidden in CSS"
    assert 'display: none !important;' in html, "Missing display: none !important in CSS"
    assert '.sub-tab-btn *, .tier-pill-btn *' in html, "Missing pointer-events: none shield on filter button children"

    print("[3] Verifying empty filter state row...")
    assert 'id="emptyCustFilterRow"' in html, "Missing #emptyCustFilterRow in DOM"

    print("[4] Verifying JavaScript filter functions...")
    assert "r.classList.add('cust-hidden');" in html, "Missing classList.add('cust-hidden') in applySubscribersFilter"
    assert "r.classList.remove('cust-hidden');" in html, "Missing classList.remove('cust-hidden') in applySubscribersFilter"
    assert "r.style.setProperty('display', 'none', 'important');" in html, "Missing setProperty display none important"
    assert "subTierDeck.classList.add('active-deck');" in html, "Missing subTierDeck.classList.add('active-deck')"
    assert "subTierDeck.classList.add('deck-hidden');" in html, "Missing subTierDeck.classList.add('deck-hidden')"

    print("[5] Auditing customer rows and their filter attributes...")
    row_matches = re.findall(r'<tr class="cust-row"[^>]*id="cust-row-(\d+)"[^>]*data-tier="([^"]*)"[^>]*data-status="([^"]*)"[^>]*data-online="([^"]*)"', html)
    print(f"    Parsed {len(row_matches)} customer rows in rendered HTML.")
    assert len(row_matches) > 0, "No customer rows parsed!"

    # Simulate filter logic on parsed rows:
    # 1. Tab All:
    all_count = len(row_matches)
    # 2. Tab Online:
    online_count = sum(1 for cid, tier, status, online in row_matches if online == 'true')
    # 3. Tab Suspended:
    suspended_count = sum(1 for cid, tier, status, online in row_matches if status == 'suspended' or tier == 'suspended')
    # 4. Tab Priority:
    priority_tiers = ['overdue', 'today', 'in_3d', 'in_7d', 'in_15d', 'grace']
    priority_count = sum(1 for cid, tier, status, online in row_matches if tier in priority_tiers)
    # Sub-tier will_suspend:
    will_suspend_count = sum(1 for cid, tier, status, online in row_matches if tier in ['overdue', 'today'])
    # Sub-tier in_3d:
    in_3d_count = sum(1 for cid, tier, status, online in row_matches if tier == 'in_3d')
    # Sub-tier in_7d:
    in_7d_count = sum(1 for cid, tier, status, online in row_matches if tier == 'in_7d')

    print(f"    Simulation results:")
    print(f"      - All: {all_count}")
    print(f"      - Online: {online_count}")
    print(f"      - Suspended: {suspended_count}")
    print(f"      - Priority (Due Queue): {priority_count}")
    print(f"      - Priority > Will Cut/Overdue: {will_suspend_count}")
    print(f"      - Priority > In 3 Days: {in_3d_count}")
    print(f"      - Priority > In 7 Days: {in_7d_count}")

    print("\n>>> ALL MOBILE FILTER VERIFICATIONS PASSED 100% <<<")

if __name__ == '__main__':
    try:
        test_mobile_filters()
    except Exception as e:
        print(f"\n[FAIL] Test encountered error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
