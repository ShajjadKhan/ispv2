import sqlite3

customers_backup = [
    (2, '2026-09-01', '2026-11-01', 1, '2026-11-01'),
    (7, '2026-10-03', '2026-11-02', 2, '2026-11-02'),
    (8, '2027-04-30', '2026-11-02', 2, '2026-11-02'),
    (9, '2026-10-04', '2026-11-03', 3, '2026-11-03'),
    (10, '2026-10-04', '2026-11-03', 3, '2026-11-03'),
    (11, '2026-10-04', '2026-11-03', 3, '2026-11-03'),
    (12, '2026-09-29', '2026-11-03', 3, '2026-11-03'),
    (15, '2026-10-04', '2026-11-03', 3, '2026-11-03'),
    (16, '2026-10-04', '2026-11-10', 10, '2026-11-10'),
    (17, '2026-10-04', '2026-11-10', 10, '2026-11-10'),
    (18, '2026-10-04', '2026-11-03', 3, '2026-11-03')
]

def restore():
    conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
    cur = conn.cursor()
    for cid, bstart, ddate, dday, exp in customers_backup:
        cur.execute(
            "UPDATE customers SET billing_start_date = ?, due_date = ?, due_day = ?, expiry_date = ? WHERE id = ?",
            (bstart, ddate, dday, exp, cid)
        )
    conn.commit()
    print("Restored exact previous dates for all 11 customers.")
    
    # Verify
    rows = cur.execute("SELECT id, name, billing_start_date, due_date, due_day, expiry_date FROM customers WHERE status != 'deleted'").fetchall()
    for r in rows:
        print(f"#{r[0]} {r[1]}: start={r[2]}, due_date={r[3]}, due_day={r[4]}, expiry={r[5]}")

    conn.close()

if __name__ == '__main__':
    restore()
