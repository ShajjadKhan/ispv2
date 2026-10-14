import subprocess
import time

cmd = [
    "ssh",
    "-i", "/home/tserver/.ssh/id_hetzner_tunnel",
    "-o", "ConnectTimeout=5",
    "-o", "ServerAliveInterval=5",
    "-o", "StrictHostKeyChecking=accept-new",
    "shajjad@135.181.39.96",
    "uptime; top -b -n 1 | head -n 15; sudo systemctl status nginx --no-pager; sudo netstat -tlpn | grep 9911"
]

for attempt in range(1, 10):
    print(f"Attempt {attempt}...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("SUCCESS!")
        print(res.stdout)
        break
    else:
        print(f"Failed (code {res.returncode}): {res.stderr.strip()[:100]}")
        time.sleep(2)
