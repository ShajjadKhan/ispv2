import sys
sys.path.insert(0, '/home/tserver/isp_v2')
import sqlite3
import database

def main():
    print("=" * 80)
    print("1. BALANCE SHEET (/balance) CALCULATIONS")
    print("=" * 80)
    bs = database.get_balance_sheet_data()
    summary = bs["summary"]
    for k, v in summary.items():
        print(f"  {k:<25}: {v}")

    print("\n" + "=" * 80)
    print("2. COLLECTIONS & LEDGER (/collections) CALCULATIONS")
    print("=" * 80)
    colls = database.get_collections_hub_data()
    c_bs = colls["balance_sheet"]
    for k, v in c_bs.items():
        print(f"  {k:<25}: {v}")

    print("\n" + "=" * 80)
    print("3. DASHBOARD (/) FINANCIAL KPIS")
    print("=" * 80)
    dash = database.get_dashboard_metrics()
    for k in [
        "target_month", "month_label", "total_subscribers", "active_subscribers",
        "collected_month_sar", "collections_count", "outstanding_sar",
        "due_customers_count", "target_revenue_sar", "collection_rate"
    ]:
        print(f"  {k:<25}: {dash.get(k)}")

    print("\n" + "=" * 80)
    print("4. DATABASE RAW AUDIT (customers vs collections)")
    print("=" * 80)
    with database.get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check total collections in db
        total_colls = cur.execute("SELECT COALESCE(SUM(amount), 0.0), COUNT(*) FROM collections WHERE amount > 0").fetchone()
        print(f"  Total All-Time Collections in DB: {total_colls[0]} SAR ({total_colls[1]} records)")

        # Check collections this month
        cur_month = cur.execute("SELECT COALESCE(SUM(amount), 0.0), COUNT(*) FROM collections WHERE strftime('%Y-%m', collected_at) = strftime('%Y-%m', 'now') AND amount > 0").fetchone()
        print(f"  Current Month Collections in DB: {cur_month[0]} SAR ({cur_month[1]} records)")

        # Check credit_balance column in customers table
        cust_credits = cur.execute("""
            SELECT 
                COUNT(*) as total_custs,
                SUM(CASE WHEN credit_balance > 0 THEN credit_balance ELSE 0 END) as positive_credit,
                COUNT(CASE WHEN credit_balance > 0 THEN 1 END) as positive_count,
                SUM(CASE WHEN credit_balance < 0 THEN credit_balance ELSE 0 END) as negative_credit,
                COUNT(CASE WHEN credit_balance < 0 THEN 1 END) as negative_count,
                COUNT(CASE WHEN credit_balance = 0 THEN 1 END) as zero_count
            FROM customers WHERE status != 'deleted'
        """).fetchone()
        print(f"  Customers table credit_balance column:")
        print(f"    Positive Wallet Credit: {cust_credits['positive_credit']} SAR ({cust_credits['positive_count']} subscribers)")
        print(f"    Negative Arrears Debt : {cust_credits['negative_credit']} SAR ({cust_credits['negative_count']} subscribers)")
        print(f"    Zero Balance          : {cust_credits['zero_count']} subscribers")

        # Compare credit_balance in customers table vs balance in Balance Sheet
        mismatches = []
        for r in bs["rows"]:
            cid = r["id"]
            db_row = cur.execute("SELECT credit_balance FROM customers WHERE id = ?", (cid,)).fetchone()
            db_cb = round(float(db_row["credit_balance"] or 0.0), 2)
            sheet_bal = round(float(r["balance"]), 2)
            if abs(db_cb - sheet_bal) > 0.05:
                mismatches.append((cid, r["name"], db_cb, sheet_bal, r["total_owed"], r["total_paid"]))

        print(f"\n  Discrepancy Check between `customers.credit_balance` and `Balance Sheet balance`:")
        print(f"    Total mismatches: {len(mismatches)} / {len(bs['rows'])}")
        if mismatches:
            print("    Sample mismatches (first 10):")
            for m in mismatches[:10]:
                print(f"      Customer #{m[0]} ({m[1]}): credit_balance={m[2]} SAR vs Sheet balance={m[3]} SAR (Owed: {m[4]}, Paid: {m[5]})")

if __name__ == "__main__":
    main()
