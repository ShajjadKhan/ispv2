import socket
import time

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

s.sendall(b"show running-config\n")
out = recv_until("#", timeout=12.0)
with open("/tmp/gpon_running_config.txt", "w") as f:
    f.write(out)

# Print lines matching 62 or 70
lines = out.splitlines()
print(f"Total lines in gpon running-config: {len(lines)}")
for i, l in enumerate(lines):
    if any(k in l for k in ["onu 62 ", "onu 70 ", "onu 62\n", "onu 70\n", "3c23dca9", "1969d8a9"]):
        # print context around it
        start = max(0, i - 2)
        end = min(len(lines), i + 8)
        print("--- MATCH AT LINE", i, "---")
        for j in range(start, end):
            print(f"  {lines[j]}")

s.close()
