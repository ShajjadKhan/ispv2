import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def main():
    print("--- Verifying subscribers status ---")
    for cid in [29, 155, 157]:
        cust = database.get_customer_by_id(cid)
        is_exp, reason, d = database.is_customer_expired(cust)
        print(f"#{cid} {cust['name']}: status={cust['status']}, due={cust['due_date']}, exp={cust['expiry_date']}, is_expired={is_exp}, reason='{reason}'")

    print("\n--- Running check_and_enforce_customer_expirations() ---")
    expired = database.check_and_enforce_customer_expirations()
    print(f"Expired count triggered by enforcer: {len(expired)}")
    for e in expired:
        print(f"  - Expired customer #{e['customer_id']} {e['name']} (exp: {e['expiry_date']})")

    print("\n--- Checking MikroTik Fleet Bindings ---")
    import routeros_api
    routers = database.get_all_routers(active_only=True)
    macs = ["F4:2B:8C:0E:BB:5C", "E0:4C:12:1F:17:DF", "C4:D4:D0:8F:78:CA"]
    for r in routers:
        print(f"Router {r['name']} ({r['host']}):")
        try:
            pool = routeros_api.RouterOsApiPool(
                r['host'],
                username=r['username'],
                password=r['password'],
                port=r.get('port', 8728),
                use_ssl=bool(r.get('use_ssl', False)),
                ssl_verify=False,
                plaintext_login=True
            )
            api = pool.get_api()
            bindings = api.get_resource("/ip/hotspot/ip-binding").get()
            found = [b for b in bindings if b.get("mac-address", "").upper() in macs]
            for f in found:
                print(f"  MAC: {f.get('mac-address')} | IP: {f.get('address')} | Type: {f.get('type')} | Disabled: {f.get('disabled')} | Comment: {f.get('comment')}")
            pool.disconnect()
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    main()
