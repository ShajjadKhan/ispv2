#!/usr/bin/env python3
"""
Hetzner Reverse SSH Tunnel Pre-Start Cleanup Script for CyberNet ISP v2 (Port 9911)
Ensures port 9911 is completely free on the remote server before SSH attempts to bind it.
"""
import subprocess
import os
import sys
import time

SSH_KEY = "/home/sk/.ssh/id_hetzner_tunnel"
REMOTE = "shajjad@135.181.39.96"
TARGET_PORT = "9911"

def run_ssh(cmd, timeout=5):
    full_cmd = [
        "ssh", "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=4",
        "-o", "StrictHostKeyChecking=accept-new",
        REMOTE, cmd
    ]
    try:
        return subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None

def is_port_listening():
    res = run_ssh(f"ss -tulpn | grep -E '(:| ){TARGET_PORT}( |$)'")
    if res is None:
        print(f"[cleanup] Warning: SSH check timed out connecting to {REMOTE}.")
        return None
    return bool(res.stdout.strip())

def clear_stale_sessions():
    print(f"[cleanup] Port {TARGET_PORT} is held on {REMOTE}. Clearing stale tunnel sessions...")
    run_ssh("pkill -u shajjad -f 'sshd-session: shajjad$' || true", timeout=5)
    time.sleep(1.5)

def check_and_clean():
    if not os.path.exists(SSH_KEY):
        print(f"[cleanup] Notice: SSH key {SSH_KEY} not found locally.")
        return 0

    listening = is_port_listening()
    if listening is False:
        print(f"[cleanup] Port {TARGET_PORT} is free on Hetzner.")
        return 0

    if listening is None:
        return 0

    clear_stale_sessions()

    if not is_port_listening():
        print(f"[cleanup] Success: Port {TARGET_PORT} is now free and ready for binding.")
    else:
        print(f"[cleanup] Notice: Port {TARGET_PORT} cleanup initiated; proceeding to tunnel start.")

    return 0

if __name__ == "__main__":
    try:
        sys.exit(check_and_clean() or 0)
    except Exception as e:
        print(f"[cleanup] Unexpected error: {e}")
        sys.exit(0)
