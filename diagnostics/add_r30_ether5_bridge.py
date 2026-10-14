import routeros_api
import subprocess

print("=== CONNECTING TO ROUTER-30 (10.20.30.12) ===")
connection = routeros_api.RouterOsApiPool("10.20.30.12", username="admin", password="adminn3", plaintext_login=True)
api = connection.get_api()

bridge_ports = api.get_resource('/interface/bridge/port')
existing = bridge_ports.get(interface='ether5')

if existing:
    print(f"ether5 already in bridge: {existing}")
else:
    print("Adding ether5 to bridge-mgmt on Router-30...")
    bridge_ports.add(bridge='bridge-mgmt', interface='ether5')
    print("Added ether5 successfully!")

print("\n--- CURRENT BRIDGE PORTS ON ROUTER-30 ---")
for p in bridge_ports.get():
    print(f"  Interface: {p.get('interface')} | Bridge: {p.get('bridge')} | Disabled: {p.get('disabled')} | Role: {p.get('role')} | Status: {p.get('status')}")

connection.disconnect()

print("\n=== TESTING REACHABILITY ===")
# Ping from tserver to 10.20.30.10
res = subprocess.run(["ping", "-c", "3", "10.20.30.10"], capture_output=True, text=True)
print(f"Ping tserver -> 10.20.30.10:\n{res.stdout}")
