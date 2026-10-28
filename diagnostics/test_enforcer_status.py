import sys
sys.path.insert(0, '/home/sk/isp_v2')
import database

exp = database.check_and_enforce_customer_expirations()
print("Expired customers count:", len(exp))
for c in exp:
    print("  Expired:", c['customer_id'], c['name'], c['expiry_date'])

for cid in [29, 155, 157]:
    cust = database.get_customer_by_id(cid)
    print(f"Customer #{cid} ({cust['name']}): status={cust['status']}, expiry={cust['expiry_date']}, due={cust['due_date']}")
