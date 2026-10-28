import sqlite3
import re
import socket
import time

print("=== 1. FETCHING ALL DESCRIPTIONS, DISTANCES & RX-POWER FROM DB & OLT ===")
conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT onu_id, name, serial_number, rx_power, distance_m FROM onus ORDER BY onu_id")
onus_db = {r["onu_id"]: dict(r) for r in cur.fetchall()}

# Connect to OLT to get full description list and mac-address-table syntax
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10.0)
s.connect(("192.168.200.200", 23))

def recv_until(pattern, timeout=6.0):
    buf = ""
    start = time.time()
    while time.time() - start < timeout:
        try:
            data = s.recv(4096)
            if not data: break
            clean = bytearray()
            i = 0
            while i < len(data):
                if data[i] == 0xff and i + 2 < len(data):
                    cmd, opt = data[i+1], data[i+2]
                    if cmd == 0xfd: s.sendall(bytes([0xff, 0xfc, opt]))
                    elif cmd == 0xfb: s.sendall(bytes([0xff, 0xfe, opt]))
                    i += 3
                else:
                    if data[i] != 0xff: clean.append(data[i])
                    i += 1
            buf += clean.decode('utf-8', errors='ignore')
            if re.search(pattern, buf): return buf
        except socket.timeout: break
    return buf

recv_until(r"Login:")
s.sendall(b"admin\n")
recv_until(r"Password:")
s.sendall(b"Xpon@Olt9417#\n")
time.sleep(0.5)

recv_until(r">")
s.sendall(b"enable\n")
p = recv_until(r"Password:|#", timeout=2.0)
if "Password:" in p:
    s.sendall(b"Xpon@Olt9417#\n")
    recv_until(r"#")

s.sendall(b"terminal length 0\n")
recv_until(r"#")
s.sendall(b"configure terminal\n")
recv_until(r"#")
s.sendall(b"interface gpon 0/1\n")
recv_until(r"#")

s.sendall(b"show onu desc 1-75\n")
desc_raw = recv_until(r"#", timeout=6.0)

s.sendall(b"show onu distance 1-75\n")
dist_raw = recv_until(r"#", timeout=6.0)

s.sendall(b"show onu rx-power 1-75\n")
pwr_raw = recv_until(r"#", timeout=6.0)

# Check MAC address table on OLT
s.sendall(b"exit\n")
recv_until(r"#")
s.sendall(b"show mac-address-table ?\n")
mac_help = recv_until(r"#", timeout=4.0)

s.sendall(b"show mac-address-table\n")
mac_table = recv_until(r"#", timeout=8.0)

s.close()

# Parse OLT output
olt_data = {}
for line in desc_raw.splitlines():
    m = re.search(r"onu\s+(\d+)\s+Description:\s+(.+)", line)
    if m:
        oid = int(m.group(1))
        olt_data.setdefault(oid, {})["desc"] = m.group(2).strip()

for line in dist_raw.splitlines():
    m = re.search(r"onu\s+(\d+)\s+Distance:\s+(\d+)m", line)
    if m:
        oid = int(m.group(1))
        olt_data.setdefault(oid, {})["distance"] = int(m.group(2))

for line in pwr_raw.splitlines():
    m = re.search(r"^(\d+)\s*([-\d\.]+)\s*([-\d\.]+)", line.strip())
    if m:
        oid = int(m.group(1))
        olt_data.setdefault(oid, {})["rx"] = float(m.group(2))
        olt_data.setdefault(oid, {})["olt_rx"] = float(m.group(3))

print("\n--- COMBINED OLT TOPOLOGY TABLE ---")
print(f"{'ONU':<5} | {'Distance':<8} | {'Rx dBm':<8} | {'Description'}")
print("-" * 65)
for oid in sorted(olt_data.keys()):
    d = olt_data[oid]
    dist = f"{d.get('distance', '?')}m"
    rx = f"{d.get('rx', '?')}"
    desc = d.get('desc', 'None')
    print(f"{oid:<5} | {dist:<8} | {rx:<8} | {desc}")

print("\n--- MAC ADDRESS HELP ---")
print(mac_help)

print("\n--- MAC ADDRESS TABLE SAMPLES (TOTAL LINES: {}) ---".format(len(mac_table.splitlines())))
for l in mac_table.splitlines()[:50]:
    print("  ", l)

# Let's inspect MACs in mac_table matching any ONU or VLAN
with open("/tmp/olt_mac_table.txt", "w") as f:
    f.write(mac_table)
print("Saved full mac table to /tmp/olt_mac_table.txt")

