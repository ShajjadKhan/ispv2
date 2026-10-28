import glob
import sqlite3

print("Scanning for collections tables with > 24 rows...")
for p in sorted(glob.glob('/home/sk/isp_v2/**/*.db*', recursive=True) + glob.glob('/home/sk/**/*.db*', recursive=True)):
    try:
        conn = sqlite3.connect(p)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='collections' OR name='payments' OR name='bills')")
        tables = [r[0] for r in cur.fetchall()]
        if 'collections' in tables:
            cur.execute("SELECT count(*), coalesce(sum(amount), 0) FROM collections")
            cnt, sm = cur.fetchone()
            print(f"  [collections] {p} -> {cnt} rows, sum = {sm:.2f} SAR")
        if 'payments' in tables:
            cur.execute("SELECT count(*), coalesce(sum(amount), 0) FROM payments")
            cnt, sm = cur.fetchone()
            print(f"  [payments]    {p} -> {cnt} rows, sum = {sm:.2f} SAR")
        if 'bills' in tables:
            cur.execute("SELECT count(*) FROM bills")
            cnt = cur.fetchone()[0]
            print(f"  [bills]       {p} -> {cnt} rows")
        conn.close()
    except Exception as e:
        pass
print("Scan complete.")
