#!/usr/bin/env python3
import subprocess
import os

SSH_KEY = "/home/tserver/.ssh/id_hetzner_tunnel"
REMOTE = "shajjad@135.181.39.96"

def check_and_clean():
    if not os.path.exists(SSH_KEY):
        return

    # 1. Check if 9911 is listening on Hetzner
    cmd_ss = [
        "ssh", "-i", SSH_KEY,
        "-o", "ConnectTimeout=4",
        "-o", "StrictHostKeyChecking=accept-new",
        REMOTE, "ss -tulpn | grep 9911"
    ]
    res_ss = subprocess.run(cmd_ss, capture_output=True, text=True)
    if not res_ss.stdout.strip():
        print("[cleanup] Port 9911 is free on Hetzner.")
        return

    # 2. Test if 9911 responds to HTTP GET on Hetzner
    cmd_curl = [
        "ssh", "-i", SSH_KEY,
        "-o", "ConnectTimeout=4",
        REMOTE, "curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:9911/login"
    ]
    res_curl = subprocess.run(cmd_curl, capture_output=True, text=True)
    code = res_curl.stdout.strip()

    if code == "200":
        print(f"[cleanup] Port 9911 is healthy (HTTP {code}).")
    else:
        print(f"[cleanup] Port 9911 returned '{code}' (zombie socket). Clearing stale sessions...")
        cmd_kill = [
            "ssh", "-i", SSH_KEY,
            "-o", "ConnectTimeout=4",
            REMOTE, "pkill -u shajjad -f 'sshd-session: shajjad$' || true"
        ]
        subprocess.run(cmd_kill, capture_output=True, text=True)
        print("[cleanup] Stale sessions cleared on Hetzner.")

if __name__ == "__main__":
    try:
        check_and_clean()
    except Exception as e:
        print(f"[cleanup] Warning: {e}")
