import sqlite3
import subprocess
import json
import os
import sys
import shutil
from datetime import datetime, date

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database

BILLS_DB = "/home/tserver/billing_reminder/bills.db"
ISP_DB = "/home/tserver/isp_v2/isp_v2.db"
PHP_SCRIPT = "/home/tserver/billing_reminder/billing_logic.php"

def export_bills_accounting():
    """Executes PHP billing_logic to get 100% accurate accounting calculation for all customers in bills.db"""
    php_code = """
    require_once '/home/tserver/billing_reminder/billing_logic.php';
    $db = new SQLite3('/home/tserver/billing_reminder/bills.db');
    $res = $db->query("SELECT * FROM customers ORDER BY id ASC");
    $summary = [];
    while ($c = $res->fetchArray(SQLITE3_ASSOC)) {
        $cid = $c['id'];
        $acct = getCustomerAccountDetails($db, $cid);
        $bal = getCustomerBalance($db, $cid);
        if (!$acct || !$bal) continue;

        $col_q = $db->query("SELECT month_year FROM collections WHERE customer_id=$cid AND amount > 0 ORDER BY month_year DESC LIMIT 1");
        $last_col = $col_q->fetchArray(SQLITE3_ASSOC);
        $max_month = $last_col ? $last_col['month_year'] : 'none';

        $unpaid_m = array_map(function($u) { return $u['month']; }, $acct['unpaid']);

        $summary[] = [
            'id' => $cid,
            'name' => $c['name'],
            'mobile' => $c['mobile'],
            'join_date' => $c['billing_start_date'],
            'due_day' => $c['due_day'],
            'status' => $c['status'],
            'balance' => $bal['balance'],
            'max_paid_month' => $max_month,
            'unpaid_months' => $unpaid_m
        ];
    }
    echo json_encode($summary);
    """
    proc = subprocess.run(["php", "-r", php_code], capture_output=True, text=True, check=True)
    return json.loads(proc.stdout)

def compute_target_dates(b_info):
    orig_join = (b_info["join_date"] or "").strip() or "2026-05-01"
    due_day_raw = b_info["due_day"]
    try:
        due_day = int(due_day_raw) if due_day_raw is not None else 1
    except Exception:
        due_day = 1
    safe_due_day = max(1, min(28, due_day))

    max_paid = b_info["max_paid_month"]
    unpaid = b_info["unpaid_months"]
    bal = float(b_info["balance"] or 0.0)

    # Check for earlier unpaid months (< 2026-10)
    earlier_unpaid = [m for m in unpaid if m < "2026-10"]

    if earlier_unpaid:
        # Customer owes for earlier months (e.g. Dilshad Ansari owes 2026-08, 2026-09)
        earliest_m = min(earlier_unpaid)
        b_start = f"{earliest_m}-01"
        due_d = f"2026-11-{safe_due_day:02d}"
        exp_d = due_d
        credit_bal = bal
        scenario = f"earlier_unpaid ({earliest_m})"
    elif "2026-10" in unpaid:
        # Previous bills paid up through Sept, active cycle is Oct (e.g. Naseem)
        b_start = "2026-10-01"
        due_d = f"2026-11-{safe_due_day:02d}"
        exp_d = due_d
        credit_bal = bal
        scenario = "paid_through_sep"
    elif max_paid != "none" and max_paid >= "2026-10":
        # Customer paid October and future months in advance (e.g. Mr. Hamid paid through 2026-12)
        dt = datetime.strptime(max_paid + "-01", "%Y-%m-%d").date()
        nm = dt.month + 1
        ny = dt.year
        if nm > 12:
            nm = 1
            ny += 1
        b_start = f"{ny:04d}-{nm:02d}-01"
        due_d = b_start
        exp_d = b_start
        credit_bal = 0.0
        scenario = f"future_credit (paid through {max_paid})"
    else:
        # All months up through Sept paid, Oct settled or not yet due
        b_start = "2026-10-01"
        due_d = f"2026-11-{safe_due_day:02d}"
        exp_d = due_d
        credit_bal = bal
        scenario = "settled_or_other"

    return {
        "join_date": orig_join,
        "billing_start_date": b_start,
        "due_date": due_d,
        "expiry_date": exp_d,
        "credit_balance": round(credit_bal, 2),
        "due_day": safe_due_day,
        "scenario": scenario
    }

def main(dry_run=False):
    print("=== STARTING BILLING REMINDER DATE & BALANCE SYNC ===")
    print(f"Dry run mode: {dry_run}")
    
    # 1. Backup isp_v2.db if not dry run
    if not dry_run:
        now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{ISP_DB}.backup_before_sync_dates_{now_ts}"
        shutil.copy2(ISP_DB, backup_path)
        print(f"Created database backup: {backup_path}")

    # 2. Extract accurate billing reminder accounting data
    print("Calculating accounting metrics via billing_logic.php...")
    bills_data = export_bills_accounting()
    print(f"Extracted {len(bills_data)} customer accounts from bills.db")

    # 3. Match against isp_v2 customers
    cisp = sqlite3.connect(ISP_DB)
    cisp.row_factory = sqlite3.Row
    isp_rows = cisp.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    
    isp_by_phone = {}
    for r in isp_rows:
        p = r["phone"]
        if p:
            for v in database.get_phone_lookup_variants(p):
                isp_by_phone[v] = r
            norm = database.normalize_saudi_phone_number(p)
            if norm:
                isp_by_phone[norm] = r

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_count = 0
    scenarios_count = {}

    updates_to_run = []

    for b in bills_data:
        p = b["mobile"]
        match = None
        if p:
            for v in database.get_phone_lookup_variants(p):
                if v in isp_by_phone:
                    match = isp_by_phone[v]
                    break
            if not match:
                norm = database.normalize_saudi_phone_number(p)
                if norm and norm in isp_by_phone:
                    match = isp_by_phone[norm]

        if not match:
            continue

        # NEVER touch manually created original customers (IDs 2-78, e.g. Hamid)
        if match["id"] <= 78:
            continue

        target = compute_target_dates(b)
        sc = target["scenario"].split(" ")[0]
        scenarios_count[sc] = scenarios_count.get(sc, 0) + 1

        # Preserve further future due_date if customer already paid/renewed in isp_v2
        final_due = target["due_date"]
        final_exp = target["expiry_date"]
        curr_due = match["due_date"] or ""
        curr_exp = match["expiry_date"] or ""
        if curr_due > final_due:
            final_due = curr_due
        if curr_exp > final_exp:
            final_exp = curr_exp

        updates_to_run.append({
            "isp_id": match["id"],
            "isp_name": match["name"],
            "bills_name": b["name"],
            "phone": match["phone"],
            "join_date": target["join_date"],
            "billing_start_date": target["billing_start_date"],
            "credit_balance": target["credit_balance"],
            "due_date": final_due,
            "expiry_date": final_exp,
            "due_day": target["due_day"],
            "scenario": target["scenario"]
        })

    print(f"Matched {len(updates_to_run)} customers in isp_v2.db")
    print(f"Scenario breakdown: {scenarios_count}")

    if not dry_run:
        cur = cisp.cursor()
        for u in updates_to_run:
            cur.execute("""
                UPDATE customers SET
                    join_date = ?,
                    billing_start_date = ?,
                    credit_balance = ?,
                    due_date = ?,
                    expiry_date = ?,
                    due_day = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                u["join_date"],
                u["billing_start_date"],
                u["credit_balance"],
                u["due_date"],
                u["expiry_date"],
                u["due_day"],
                now_str,
                u["isp_id"]
            ))
            updated_count += 1
        cisp.commit()
        print(f"Successfully updated {updated_count} customer records in isp_v2.db!")
    else:
        print(f"Dry run complete. Would update {len(updates_to_run)} records.")

    cisp.close()

    # 4. Verify specific key test cases
    print("\n=== VERIFYING KEY CUSTOMERS IN ISP_V2 ===")
    test_phones = ["0554971623", "0559802084", "0507439282", "0552036454", "0563935052"]
    for ph in test_phones:
        cust = database.get_customer_by_phone(ph)
        if cust:
            cid = cust["id"]
            bd = database.get_customer_billing_breakdown(cid)
            print(f"Customer #{cid}: {cust['name']} ({cust['phone']})")
            print(f"  Join Date:          {cust['join_date']}")
            print(f"  Billing Start Date: {cust['billing_start_date']}")
            print(f"  Credit Balance:     {cust['credit_balance']} SAR")
            print(f"  Due Date:           {cust['due_date']}")
            print(f"  Expiry Date:        {cust['expiry_date']}")
            print(f"  Total Due:          {bd['total_due']} SAR")
            print(f"  Unpaid Cycles:      {[u['month'] for u in bd.get('unpaid_cycles', [])]}")
            print(f"  Settled Cycles:     {[s['month'] for s in bd.get('settled_cycles', [])]}")
            print("--------------------------------------------------")

if __name__ == "__main__":
    dry_mode = "--dry-run" in sys.argv
    main(dry_run=dry_mode)
