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

s.sendall(b"show ?\n")
print("SHOW HELP IN INTERFACE GPON 0/1:")
print(recv_until("#", timeout=4.0))

s.sendall(b"show onu running-config 62\n")
print("\n--- ONU 62 RUNNING CONFIG ---")
print(recv_until("#", timeout=4.0))

s.sendall(b"show onu running-config 70\n")
print("\n--- ONU 70 RUNNING CONFIG ---")
print(recv_until("#", timeout=4.0))

s.close()
