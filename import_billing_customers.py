import sqlite3
import sys
import os
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database

BILLS_DB = "/home/tserver/billing_reminder/bills.db"

def clean_phone_for_storage(raw):
    if not raw:
        return ""
    digits = "".join(c for c in str(raw) if c.isdigit())
    if digits.startswith("966") and len(digits) == 12:
        return "0" + digits[3:]
    if digits.startswith("5") and len(digits) == 9:
        return "0" + digits
    return digits

def run_import(bills_db_path=BILLS_DB):
    print("=== STARTING BILLING REMINDER CUSTOMER IMPORT ===")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cbills = sqlite3.connect(bills_db_path)
    cbills.row_factory = sqlite3.Row
    bills_rows = cbills.execute("SELECT * FROM customers ORDER BY id ASC").fetchall()
    print(f"Read {len(bills_rows)} records from {bills_db_path}")
    
    with database.get_db() as conn:
        cursor = conn.cursor()
        
        # Load existing ISP customers to prevent any duplicate insertion
        isp_rows = cursor.execute("SELECT id, phone, name FROM customers").fetchall()
        print(f"Current isp_v2 customer count: {len(isp_rows)}")
        
        existing_phone_set = set()
        for r in isp_rows:
            p = r["phone"]
            if p:
                for variant in database.get_phone_lookup_variants(p):
                    existing_phone_set.add(variant)
                cleaned = clean_phone_for_storage(p)
                if cleaned:
                    existing_phone_set.add(cleaned)
                    
        inserted_count = 0
        skipped_count = 0
        empty_count = 0
        
        for b in bills_rows:
            raw_phone = b["mobile"]
            phone_clean = clean_phone_for_storage(raw_phone)
            
            if not phone_clean:
                print(f"Skipping empty phone: ID {b['id']} - Name: {b['name']}")
                empty_count += 1
                continue
                
            # Check if any variant exists
            has_match = False
            for v in database.get_phone_lookup_variants(phone_clean):
                if v in existing_phone_set:
                    has_match = True
                    break
            if phone_clean in existing_phone_set:
                has_match = True
                
            if has_match:
                skipped_count += 1
                continue
                
            # Build customer fields
            cust_name = (b["name"] or "").strip()
            billing_type = "postpaid"
            package_name = "Hotspot For 30 Days"
            monthly_fee = float(b["monthly_fee"] or 30.0)
            collected_today = 0.0
            
            due_day_val = b["due_day"]
            try:
                due_day = int(due_day_val) if due_day_val is not None else 1
            except Exception:
                due_day = 1
            due_day = max(1, min(30, due_day))
            
            # Format due date and expiry date: November 2026 cycle
            due_date = f"2026-11-{due_day:02d}"
            expiry_date = due_date
            
            billing_start = (b["billing_start_date"] or "").strip() or "2026-05-01"
            join_date = billing_start
            
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
                    'Unlimited', 0.0, NULL, ?,
                    NULL, NULL, ?, ?,
                    'hotspot', '', '', '',
                    '', ?
                )
            """, (
                phone_clean, cust_name, billing_type, package_name, monthly_fee,
                collected_today, due_day, expiry_date,
                created_at, now_str, due_date, billing_start,
                join_date, notes, reminders
            ))
            new_id = cursor.lastrowid
            inserted_count += 1
            
            # Add to local existing set so subsequent duplicates within bills are prevented
            for v in database.get_phone_lookup_variants(phone_clean):
                existing_phone_set.add(v)
            existing_phone_set.add(phone_clean)
            
            print(f"Inserted customer #{new_id}: {cust_name} ({phone_clean}) - Due Day: {due_day} - Notes: {notes}")
            
        conn.commit()
        print("--------------------------------------------------")
        print(f"Total inserted: {inserted_count}")
        print(f"Total skipped (already existed): {skipped_count}")
        print(f"Total skipped (empty phone): {empty_count}")
        
        # Verify new customer count
        total_now = cursor.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        print(f"New total customers in isp_v2: {total_now}")

    # Now refresh and auto-resolve pending requests
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
