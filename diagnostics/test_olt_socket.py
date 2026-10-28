import socket
import time
import re

def run_olt_commands():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(15.0)
    s.connect(("192.168.200.200", 23))

    def recv_until(pattern, timeout=8.0):
        buf = ""
        start = time.time()
        while time.time() - start < timeout:
            try:
                data = s.recv(4096)
                if not data:
                    break
                clean = bytearray()
                i = 0
                while i < len(data):
                    if data[i] == 0xff: # IAC
                        if i + 2 < len(data):
                            cmd = data[i+1]
                            opt = data[i+2]
                            if cmd == 0xfd:
                                s.sendall(bytes([0xff, 0xfc, opt]))
                            elif cmd == 0xfb:
                                s.sendall(bytes([0xff, 0xfe, opt]))
                            i += 3
                        else:
                            i += 1
                    else:
                        clean.append(data[i])
                        i += 1
                text = clean.decode('utf-8', errors='ignore')
                buf += text
                if re.search(pattern, buf):
                    return buf
            except socket.timeout:
                break
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

    commands = [
        "show onu state",
        "show onu info 1-75",
        "show onu desc 1-75",
        "show onu rx-power 1-75",
        "show onu distance 1-75",
        "show unauthen-onu",
        "show auto-find-onu",
    ]

    for c in commands:
        s.sendall(c.encode() + b"\n")
        out = recv_until(r"#", timeout=6.0)
        print(f"\n==================== CMD: {c} ====================")
        print(out)

    s.sendall(b"exit\n")
    recv_until(r"#")
    s.sendall(b"show mac ?\n")
    print("\n==================== CMD: show mac ? ====================")
    print(recv_until(r"#", timeout=3.0))

    s.close()

run_olt_commands()
