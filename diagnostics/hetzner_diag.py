import subprocess

ssh_key = '/home/tserver/.ssh/id_hetzner_tunnel'
remote = 'shajjad@135.181.39.96'

def run_remote(cmd):
    res = subprocess.run(['ssh', '-i', ssh_key, remote, cmd], capture_output=True, text=True)
    return res.stdout + res.stderr

print("=== CHECKING sudo -l FOR USER SHAJJAD ===")
print(run_remote("sudo -l 2>&1"))
