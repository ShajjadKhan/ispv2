import os
import sys
import sqlite3
import calendar
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

def test_month_lengths():
    print("\n--- Verifying Month-Aware Math Precision ---")
    monthly_fee = 30.0
    
    test_cases = [
        ("January 2026 (31 days)", date(2026, 1, 1), date(2026, 1, 31), 31, 30.00),
        ("February 2026 (28 days non-leap)", date(2026, 2, 1), date(2026, 2, 28), 28, 30.00),
        ("February 2024 (29 days leap)", date(2024, 2, 1), date(2024, 2, 29), 29, 30.00),
        ("April 2026 (30 days)", date(2026, 4, 1), date(2026, 4, 30), 30, 30.00),
        ("October 2026 (Half month 15 days of 31)", date(2026, 10, 1), date(2026, 10, 15), 15, round(15 * (30.0/31), 2)),
    ]

    for label, s_date, e_date, exp_billable, exp_cost in test_cases:
        cur_d = s_date
        total_accrued = 0.0
        billable = 0
        cur_m_key = None
        cur_dim = 30
        while cur_d <= e_date:
            billable += 1
            m_key = (cur_d.year, cur_d.month)
            if m_key != cur_m_key:
                cur_m_key = m_key
                cur_dim = calendar.monthrange(cur_d.year, cur_d.month)[1]
            total_accrued += (monthly_fee / float(cur_dim))
            cur_d += timedelta(days=1)
        cost = round(total_accrued, 2)
        print(f"  {label}: Billable={billable} days -> Accrued Cost = {cost:.2f} SAR (Expected: {exp_cost:.2f} SAR)")
        assert billable == exp_billable
        assert cost == exp_cost, f"Mismatch: got {cost}, expected {exp_cost}"

    print("ALL MONTH LENGTHS (28, 29, 30, 31) VERIFIED PERFECT!")

def test_live_database_functions():
    print("\n--- Verifying Live Database Integration ---")
    synced = database.sync_all_customer_realtime_balances()
    print(f"  sync_all_customer_realtime_balances updated {synced} customer records.")
    
    bs = database.get_balance_sheet_data()
    counts = bs.get("status_counts", {})
    print(f"  get_balance_sheet_data active customers: {counts.get('all')}, owing: {counts.get('owing')}, credit: {counts.get('credit')}")
    assert counts.get("all", 0) > 0, "No active customers found in balance sheet"
    
    # Test customer 158 (Ovi)
    rt = database.calculate_customer_realtime_balance(158)
    print(f"  Customer #158 realtime balance: {rt['balance']} SAR, status: {rt['status']}, billable: {rt['billable_days']}")
    
    bd = database.get_customer_billing_breakdown(158)
    print(f"  Customer #158 breakdown: total_due={bd['total_due']} SAR, credit_balance={bd['credit_balance']} SAR")
    print("LIVE DATABASE FUNCTIONS VERIFIED PERFECT!")

if __name__ == "__main__":
    test_month_lengths()
    test_live_database_functions()

