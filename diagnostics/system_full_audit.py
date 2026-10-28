import sys
import os
import sqlite3
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def audit_database():
    print("=== 1. DATABASE INTEGRITY & CORE STATS ===")
    with database.get_db() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        integrity = cur.fetchone()[0]
        print(f"Database Integrity: {integrity}")

        cur.execute("SELECT COUNT(*) FROM customers")
        total_cust = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM customers WHERE status = 'active'")
        active_cust = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM customers WHERE status = 'suspended'")
        susp_cust = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM customer_devices")
        total_dev = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM customer_devices WHERE status = 'approved'")
        appr_dev = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM connection_requests WHERE status = 'pending'")
        pending_req = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0.0) FROM collections")
        col_cnt, col_amt = cur.fetchone()

        print(f"Total Subscribers:    {total_cust} (Active: {active_cust}, Suspended: {susp_cust})")
        print(f"Total Devices in DB:  {total_dev} (Approved: {appr_dev})")
        print(f"Pending Requests:     {pending_req}")
        print(f"Total Collections:    {col_cnt} transactions ({col_amt:,.2f} SAR)")

def audit_enforcer_and_subscribers():
    print("\n=== 2. EXPIRATION ENFORCER & TARGET SUBSCRIBERS ===")
    expired_list = database.check_and_enforce_customer_expirations()
    print(f"Enforcer Run Triggered Cutoffs: {len(expired_list)}")
    if expired_list:
        for e in expired_list:
            print(f"  - Cutoff: #{e['customer_id']} {e['name']} (exp: {e['expiry_date']})")
    else:
        print("  ✓ Zero unexpected suspensions triggered.")

    target_ids = [29, 155, 157]
    for cid in target_ids:
        c = database.get_customer_by_id(cid)
        if c:
            is_exp, reason, exp_d = database.is_customer_expired(c)
            with database.get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM customer_devices WHERE customer_id = ?", (cid,))
                d_cnt = cur.fetchone()[0]
                cur.execute("SELECT mac_address FROM customer_devices WHERE customer_id = ? LIMIT 1", (cid,))
                m_row = cur.fetchone()
                m_str = m_row[0] if m_row else "None"
            print(f"Subscriber #{cid} ({c['name']}): Status={c['status']}, Due={c['due_date']}, Exp={c['expiry_date']}, Devices={d_cnt}, Primary MAC={m_str}, Expired={is_exp} ({reason})")

def audit_routers():
    print("\n=== 3. MIKROTIK ROUTER FLEET CONNECTIVITY & BINDINGS ===")
    import routeros_api
    routers = database.get_all_routers(active_only=True)
    target_macs = ["F4:2B:8C:0E:BB:5C", "E0:4C:12:1F:17:DF", "C4:D4:D0:8F:78:CA"]

    for r in routers:
        r_name = r["name"]
        r_host = r["host"]
        print(f"\nRouter {r_name} ({r_host}):")
        try:
            pool = routeros_api.RouterOsApiPool(
                r_host,
                username=r["username"],
                password=r["password"],
                port=r.get("port", 8728),
                use_ssl=bool(r.get("use_ssl", False)),
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            
            # System resource
            res = api.get_resource("/system/resource").get()
            if res:
                cpu = res[0].get("cpu-load", "?")
                uptime = res[0].get("uptime", "?")
                mem_free = int(res[0].get("free-memory", 0)) / (1024 * 1024)
                print(f"  ✓ Connected! Uptime: {uptime}, CPU: {cpu}%, Free Mem: {mem_free:.1f} MB")

            # Hotspot bindings
            bindings = api.get_resource("/ip/hotspot/ip-binding").get()
            total_binds = len(bindings)
            found_macs = [b for b in bindings if b.get("mac-address", "").upper() in target_macs]
            print(f"  Total IP Bindings: {total_binds}")
            print(f"  Target Subscribers Bound ({len(found_macs)} / {len(target_macs)}):")
            for f in found_macs:
                print(f"    - MAC: {f.get('mac-address')} | Type: {f.get('type')} | Disabled: {f.get('disabled')}")
            
            pool.disconnect()
        except Exception as e:
            print(f"  ✗ Connection Error: {e}")

def audit_web_routes():
    print("\n=== 4. WEB ENDPOINTS HEALTH CHECK ===")
    with database.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT session_id FROM admin_sessions WHERE is_active = 1 ORDER BY last_activity DESC LIMIT 1")
        row = cur.fetchone()
        session_id = row[0] if row else None

    if not session_id:
        print("No active session found for authenticated test. Testing public paths.")
        cookies = {}
    else:
        cookies = {"cybernet_session": session_id}

    test_routes = [
        "/",
        "/customers",
        "/balance",
        "/balance/report",
        "/approvals",
        "/collections",
        "/gateway",
        "/packages",
        "/api/router/telemetry"
    ]

    for p in test_routes:
        url = f"http://127.0.0.1:9911{p}"
        t0 = time.time()
        try:
            r = requests.get(url, cookies=cookies, timeout=10)
            elapsed = time.time() - t0
            print(f"  {p:<24} -> HTTP {r.status_code} ({len(r.content):,} bytes) in {elapsed:.2f}s")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  {p:<24} -> ERROR: {e} after {elapsed:.2f}s")

if __name__ == "__main__":
    audit_database()
    audit_enforcer_and_subscribers()
    audit_routers()
    audit_web_routes()
