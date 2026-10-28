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
s.sendall(b"configure terminal\n")
recv_until(r"#")
s.sendall(b"interface gpon 0/1\n")
recv_until(r"#")

cmds = [
    "show onu auto-find",
    "show onu detail-info 62",
    "show onu detail-info 70",
    "show onu optical-info 62",
    "show onu optical-info 70",
    "show onu statistics 62",
    "show onu statistics 70",
    "show onu version 62",
    "show onu version 70",
]

for c in cmds:
    s.sendall(c.encode() + b"\n")
    out = recv_until(r"#", timeout=6.0)
    print(f"\n==================== CMD: {c} ====================")
    print(out)

s.close()
