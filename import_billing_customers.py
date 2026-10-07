import sqlite3
import subprocess
import json
import sys
import os
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database

BILLS_DB = "/home/tserver/billing_reminder/bills.db"
PHP_SCRIPT = "/home/tserver/billing_reminder/billing_logic.php"

def clean_phone_for_storage(raw):
    if not raw:
        return ""
    digits = "".join(c for c in str(raw) if c.isdigit())
    if digits.startswith("966") and len(digits) == 12:
        return "0" + digits[3:]
    if digits.startswith("5") and len(digits) == 9:
        return "0" + digits
    return digits

def export_bills_accounting(bills_db_path=BILLS_DB):
    """Executes PHP billing_logic to get 100% accurate accounting calculation for all customers in bills.db"""
    php_code = f"""
    require_once '{PHP_SCRIPT}';
    $db = new SQLite3('{bills_db_path}');
    $res = $db->query("SELECT * FROM customers ORDER BY id ASC");
    $summary = [];
    while ($c = $res->fetchArray(SQLITE3_ASSOC)) {{
        $cid = $c['id'];
        $acct = getCustomerAccountDetails($db, $cid);
        $bal = getCustomerBalance($db, $cid);
        if (!$acct || !$bal) continue;

        $col_q = $db->query("SELECT month_year FROM collections WHERE customer_id=$cid AND amount > 0 ORDER BY month_year DESC LIMIT 1");
        $last_col = $col_q->fetchArray(SQLITE3_ASSOC);
        $max_month = $last_col ? $last_col['month_year'] : 'none';

        $unpaid_m = array_map(function($u) {{ return $u['month']; }}, $acct['unpaid']);

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
    }}
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

def run_import(bills_db_path=BILLS_DB):
    print("=== STARTING BILLING REMINDER CUSTOMER IMPORT & SYNC ===")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cbills = sqlite3.connect(bills_db_path)
    cbills.row_factory = sqlite3.Row
    bills_rows = cbills.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    print(f"Read {len(bills_rows)} records from {bills_db_path}")

    # Compute accurate accounting details
    accounting_data = export_bills_accounting(bills_db_path)
    accounting_by_id = {a["id"]: a for a in accounting_data}

    with database.get_db() as conn:
        cursor = conn.cursor()

        # Load existing ISP customers
        isp_rows = cursor.execute("SELECT id, phone, name, due_date, expiry_date FROM customers").fetchall()
        print(f"Current isp_v2 customer count: {len(isp_rows)}")

        isp_by_phone = {}
        for r in isp_rows:
            p = r["phone"]
            if p:
                for variant in database.get_phone_lookup_variants(p):
                    isp_by_phone[variant] = r
                norm = database.normalize_saudi_phone_number(p)
                if norm:
                    isp_by_phone[norm] = r
                cleaned = clean_phone_for_storage(p)
                if cleaned:
                    isp_by_phone[cleaned] = r

        inserted_count = 0
        updated_count = 0
        empty_count = 0

        for b in bills_rows:
            raw_phone = b["mobile"]
            phone_clean = clean_phone_for_storage(raw_phone)

            if not phone_clean:
                empty_count += 1
                continue

            # Check if any variant exists
            existing_match = None
            for v in database.get_phone_lookup_variants(phone_clean):
                if v in isp_by_phone:
                    existing_match = isp_by_phone[v]
                    break
            if not existing_match:
                norm = database.normalize_saudi_phone_number(phone_clean)
                if norm and norm in isp_by_phone:
                    existing_match = isp_by_phone[norm]

            # Accounting details for this customer
            b_acct = accounting_by_id.get(b["id"])
            if b_acct:
                target = compute_target_dates(b_acct)
            else:
                target = {
                    "join_date": (b["billing_start_date"] or "").strip() or "2026-05-01",
                    "billing_start_date": "2026-10-01",
                    "due_date": "2026-11-01",
                    "expiry_date": "2026-11-01",
                    "credit_balance": 0.0,
                    "due_day": max(1, min(28, int(b["due_day"] or 1))),
                    "scenario": "default"
                }

            if existing_match:
                # Never touch manually created original customers (IDs <= 78, e.g. Hamid)
                if existing_match["id"] <= 78:
                    continue

                # Update existing imported customer to ensure exact date alignment
                final_due = target["due_date"]
                final_exp = target["expiry_date"]
                curr_due = existing_match["due_date"] or ""
                curr_exp = existing_match["expiry_date"] or ""
                if curr_due > final_due:
                    final_due = curr_due
                if curr_exp > final_exp:
                    final_exp = curr_exp

                cursor.execute("""
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
                    target["join_date"],
                    target["billing_start_date"],
                    target["credit_balance"],
                    final_due,
                    final_exp,
                    target["due_day"],
                    now_str,
                    existing_match["id"]
                ))
                updated_count += 1
                continue

            # Build new customer fields
            cust_name = (b["name"] or "").strip()
            billing_type = "postpaid"
            package_name = "Hotspot For 30 Days"
            monthly_fee = float(b["monthly_fee"] or 30.0)
            collected_today = 0.0

            parts = [str(b[k]).strip() for k in ["building", "apartment", "room"] if b[k] and str(b[k]).strip()]
            notes = " ".join(parts)

            reminders = int(b["reminders_enabled"]) if b["reminders_enabled"] is not None else 1
            created_at = (b["created_at"] or "").strip() or now_str

            cursor.execute("""
                INSERT INTO customers (
                    phone, name, billing_type, package_name, monthly_fee,
                    collected_today, due_day, status, expiry_date,
                    created_at, updated_at, due_date, max_devices,
                    speed_limit, credit_balance, reseller_id, billing_start_date,
                    suspension_held_until, suspension_hold_reason, join_date, notes,
                    connection_type, pppoe_username, pppoe_password, pppoe_profile,
                    pppoe_remote_ip, reminders_enabled
                )
                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, 'active', ?,
                    ?, ?, ?, 1,
                    'Unlimited', ?, NULL, ?,
                    NULL, NULL, ?, ?,
                    'hotspot', '', '', '',
                    '', ?
                )
            """, (
                phone_clean, cust_name, billing_type, package_name, monthly_fee,
                collected_today, target["due_day"], target["expiry_date"],
                created_at, now_str, target["due_date"],
                target["credit_balance"], target["billing_start_date"],
                target["join_date"], notes, reminders
            ))
            new_id = cursor.lastrowid
            inserted_count += 1

            for v in database.get_phone_lookup_variants(phone_clean):
                isp_by_phone[v] = {"id": new_id, "due_date": target["due_date"], "expiry_date": target["expiry_date"]}
            isp_by_phone[phone_clean] = {"id": new_id, "due_date": target["due_date"], "expiry_date": target["expiry_date"]}

        conn.commit()
        print("--------------------------------------------------")
        print(f"Total inserted: {inserted_count}")
        print(f"Total updated: {updated_count}")
        print(f"Total skipped (empty phone): {empty_count}")

        total_now = cursor.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        print(f"Total customers in isp_v2: {total_now}")

    # Re-evaluate pending connection requests
    print("\n=== RE-EVALUATING PENDING REQUESTS ===")
    pending = database.get_pending_requests()
    print(f"Total pending requests: {len(pending)}")
    for p in pending:
        c_name = p.get("existing_customer_name") or "NEW CUSTOMER (Unrecognized)"
        c_notes = p.get("existing_customer_notes") or ""
        print(f"Request #{p['id']} - Phone: {p.get('phone')} - Name: {c_name} - Notes: {c_notes} - Secondary: {p.get('is_secondary')}")

if __name__ == "__main__":
    db_arg = sys.argv[1] if len(sys.argv) > 1 else BILLS_DB
    run_import(db_arg)
