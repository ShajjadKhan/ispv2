import telnetlib
import time
import re

HOST = "192.168.200.200"
USER = "admin"
PASS = "Xpon@Olt9417#"

print(f"Connecting to OLT {HOST}...")
tn = telnetlib.Telnet(HOST, 23, timeout=10)

def cmd(c, wait=1.0):
    tn.write(c.encode() + b"\n")
    time.sleep(wait)
    res = tn.read_very_eager().decode('utf-8', errors='ignore')
    return res

tn.read_until(b"Login:", timeout=5)
tn.write(USER.encode() + b"\n")
tn.read_until(b"Password:", timeout=5)
tn.write(PASS.encode() + b"\n")
time.sleep(0.5)

tn.read_until(b">", timeout=5)
tn.write(b"enable\n")
time.sleep(0.3)
prompt = tn.read_until(b"Password:", timeout=2)
if b"Password:" in prompt:
    tn.write(PASS.encode() + b"\n")
    time.sleep(0.5)

cmd("terminal length 0")
cmd("configure terminal")

print("--- 1. SHOW ONU INFO / STATUS ---")
out_info = cmd("show onu info 1 60-70", wait=1.5)
print(out_info)

print("--- 2. SHOW ONU STATUS ALL ---")
out_status = cmd("show onu status 1 60-70", wait=1.5)
print(out_status)

print("--- 3. SHOW ONU DESC ---")
out_desc = cmd("show onu desc 1 60-70", wait=1.5)
print(out_desc)

print("--- 4. SEARCH FOR 3c23dca9 IN ALL ONUS ---")
out_all = cmd("show onu info 1 1-75", wait=3.0)
for line in out_all.splitlines():
    if any(k in line.lower() for k in ["3c23", "dca9", "62", "70", "hg8245x6"]):
        print("  [MATCH]", line)

print("--- 5. SHOW ONU 62 & 70 DETAIL ---")
print("ONU 62 DETAIL:")
print(cmd("show onu 1 62 detail", wait=1.5))
print("ONU 70 DETAIL:")
print(cmd("show onu 1 70 detail", wait=1.5))

print("--- 6. SHOW MAC ON GPON 0/1 ---")
out_mac = cmd("show mac-address-table", wait=2.0)
print("Total MAC lines:", len(out_mac.splitlines()))
for line in out_mac.splitlines():
    if any(k in line.lower() for k in ["62", "70", "0/1"]):
        print("  [MAC]", line)

tn.close()
