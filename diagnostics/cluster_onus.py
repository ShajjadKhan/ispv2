import socket
import time
import re

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(15.0)
s.connect(("192.168.200.200", 23))

def recv_until(pattern, timeout=8.0):
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
            if pattern in buf: return buf
        except socket.timeout: break
    return buf

recv_until("Login:")
s.sendall(b"admin\n")
recv_until("Password:")
s.sendall(b"Xpon@Olt9417#\n")
time.sleep(0.5)

recv_until(">")
s.sendall(b"enable\n")
p = recv_until("#", timeout=2.0)
if "Password:" in p:
    s.sendall(b"Xpon@Olt9417#\n")
    recv_until("#")

s.sendall(b"terminal length 0\n")
recv_until("#")
s.sendall(b"configure terminal\n")
recv_until("#")
s.sendall(b"interface gpon 0/1\n")
recv_until("#")

s.sendall(b"show onu desc 1-75\n")
desc_txt = recv_until("#", timeout=6.0)

s.sendall(b"show onu distance 1-75\n")
dist_txt = recv_until("#", timeout=6.0)

s.sendall(b"show onu rx-power 1-75\n")
pwr_txt = recv_until("#", timeout=6.0)

s.sendall(b"show onu info 1-75\n")
info_txt = recv_until("#", timeout=6.0)

s.close()

onus = {}

for l in desc_txt.splitlines():
    m = re.search(r"onu\s+(\d+)\s+Description:\s+(.+)", l)
    if m:
        onus.setdefault(int(m.group(1)), {})["desc"] = m.group(2).strip()

for l in dist_txt.splitlines():
    m = re.search(r"onu\s+(\d+)\s+Distance:\s+(\d+)m", l)
    if m:
        onus.setdefault(int(m.group(1)), {})["dist"] = int(m.group(2))

for l in pwr_txt.splitlines():
    m = re.search(r"^(\d+)\s+([-\d\.]+)\s+([-\d\.]+)", l.strip())
    if m:
        onus.setdefault(int(m.group(1)), {})["rx"] = float(m.group(2))
        onus.setdefault(int(m.group(1)), {})["olt_rx"] = float(m.group(3))

for l in info_txt.splitlines():
    m = re.search(r"GPON0/1:(\d+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+sn\s+([^\s]+)", l)
    if m:
        oid = int(m.group(1))
        onus.setdefault(oid, {})["model"] = m.group(2)
        onus.setdefault(oid, {})["sn"] = m.group(5)

print("\n==================== ALL ONUS SORTED BY DISTANCE ====================")
sorted_by_dist = sorted(onus.items(), key=lambda x: x[1].get("dist", 999))
for oid, d in sorted_by_dist:
    desc = d.get('desc', 'UNLABELED')
    sn = d.get('sn', '?')
    dist = d.get('dist', '?')
    rx = d.get('rx', '?')
    model = d.get('model', '?')
    print(f"ONU {oid:02d} | Dist: {dist:>3}m | Rx: {rx:>6} dBm | SN: {sn:<12} | Model: {model:<12} | Desc: {desc}")

print("\n==================== CLUSTERING AROUND ONU 70 (49m) ====================")
for oid, d in sorted_by_dist:
    if 20 <= d.get("dist", 0) <= 95:
        print(f"  ONU {oid:02d} | {d.get('dist'):>3}m | Rx: {d.get('rx')} dBm | {d.get('desc')} (SN: {d.get('sn')})")

print("\n==================== CLUSTERING AROUND ONU 62 (197m) ====================")
for oid, d in sorted_by_dist:
    if 170 <= d.get("dist", 0) <= 220:
        print(f"  ONU {oid:02d} | {d.get('dist'):>3}m | Rx: {d.get('rx')} dBm | {d.get('desc')} (SN: {d.get('sn')})")

