import sqlite3
import re
import socket
import json

db_path = "/home/sk/isp_v2/isp_v2.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== 1. CHECKING ONUS FOR 62, 70, OR SERIAL HWTC3c23dca9 ===")
cur.execute("""
    SELECT id, pon_port, onu_id, name, serial_number, mac_address, status, rx_power, distance_m, reg_time, updated_at
    FROM onus
    WHERE onu_id IN (60, 61, 62, 63, 64, 69, 70, 71)
       OR lower(serial_number) LIKE '%3c23dca9%'
    ORDER BY onu_id
""")
rows = cur.fetchall()
for r in rows:
    print(dict(r))

print("\n=== 2. CHECKING ALL ONUS AROUND 50-70 ===")
cur.execute("SELECT onu_id, name, serial_number, rx_power, distance_m, status FROM onus WHERE onu_id >= 50 ORDER BY onu_id")
for r in cur.fetchall():
    print(dict(r))

print("\n=== 3. CHECKING SURVEY LOGS IN BACKUPS OR CODE ===")
import glob
for bfile in glob.glob("/home/sk/isp_v2/backups/*olt*"):
    print("Found backup:", bfile)
    try:
        with open(bfile, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f.readlines() if any(k in l.lower() for k in ["62", "70", "3c23dca9", "hw", "hg8245"])]
            for l in lines[:20]:
                print("  ", l)
    except Exception as e:
        print("  Error reading:", e)

print("\n=== 4. CHECKING RECENT UNCONFIGURED / NEW ONUS ON OLT ===")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    s.connect(("192.168.200.200", 23))
    # telnet read
    import time
    time.sleep(0.5)
    data = s.recv(4096).decode('utf-8', errors='ignore')
    print("OLT Login prompt:", repr(data))
    s.close()
except Exception as e:
    print("OLT socket error:", e)

