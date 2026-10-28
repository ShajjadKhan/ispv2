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

print("--- TESTING MAC ADDRESS TABLE COMMANDS ---")
s.sendall(b"show mac address-table ?\n")
print("HELP:", recv_until(r"#", timeout=4.0))

s.sendall(b"show mac address-table\n")
out = recv_until(r"#", timeout=10.0)
lines = out.splitlines()
print(f"Total MAC entries returned: {len(lines)}")
for l in lines[:40]:
    print("  ", l)

# Filter for anything matching 62 or 70 or gpon
with open("/tmp/olt_macs.txt", "w") as f:
    f.write(out)

# Check inside interface gpon 0/1 for mac commands
s.sendall(b"configure terminal\n")
recv_until(r"#")
s.sendall(b"interface gpon 0/1\n")
recv_until(r"#")
s.sendall(b"show onu ?\n")
print("SHOW ONU HELP:", recv_until(r"#", timeout=4.0))

s.close()
