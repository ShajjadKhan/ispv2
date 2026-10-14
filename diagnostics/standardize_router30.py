import sys
sys.path.insert(0, '/home/tserver/isp_v2')
import routeros_api
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("router30_clean")

router_ip = "10.20.30.12"
username = "admin"
password = "adminn3"

print("==================================================")
print(f"Connecting to Router-30 at {router_ip}:8728...")
print("==================================================")

pool = routeros_api.RouterOsApiPool(router_ip, username=username, password=password, port=8728, plaintext_login=True)
api = pool.get_api()

print("Connected successfully! Starting cleanup & standardization...")

def safe_remove(resource_path, filter_fn=None, name_field='name'):
    try:
        res = api.get_resource(resource_path)
        items = res.get()
        removed = 0
        for item in items:
            item_id = item.get('id')
            item_name = item.get(name_field, item_id)
            if filter_fn is None or filter_fn(item):
                try:
                    res.remove(id=item_id)
                    removed += 1
                    print(f"  [REMOVED] {resource_path}: {item_name} (id={item_id})")
                except Exception as ex:
                    print(f"  [NOTICE] {resource_path}: {item_name}: {ex}")
        return removed
    except Exception as e:
        print(f"  [ERROR ACCESSING] {resource_path}: {e}")
        return 0

# ----------------------------------------------------------------------
# 1. REMOVE FOREIGN / OBSOLETE COMPONENTS
# ----------------------------------------------------------------------
print("\n--- 1. Removing foreign SSTP and routes ---")
safe_remove('/interface/sstp-client')
safe_remove('/ip/route', filter_fn=lambda r: 'vpn' in r.get('comment', '').lower() or r.get('dst-address') == '100.127.240.0/20')

print("\n--- 2. Removing old Hotspots & Profiles ---")
safe_remove('/ip/hotspot')
safe_remove('/ip/hotspot/profile', filter_fn=lambda p: p.get('name') != 'default')
safe_remove('/ip/hotspot/user/profile', filter_fn=lambda p: p.get('name') != 'default')
safe_remove('/ip/hotspot/user', filter_fn=lambda u: u.get('name') != 'admin')
safe_remove('/ip/hotspot/ip-binding')

print("\n--- 3. Removing old DHCP servers, networks, pools ---")
safe_remove('/ip/dhcp-server')
safe_remove('/ip/dhcp-server/network')
safe_remove('/ip/pool')

print("\n--- 4. Removing old PPPoE servers, secrets, profiles, queues ---")
safe_remove('/interface/pppoe-server/server')
safe_remove('/ppp/secret')
safe_remove('/ppp/profile', filter_fn=lambda p: p.get('name') not in ('default', 'default-encryption'))
safe_remove('/queue/simple')

print("\n--- 5. Removing old Mangles & Firewall rules ---")
safe_remove('/ip/firewall/mangle')
safe_remove('/ip/firewall/nat', filter_fn=lambda n: n.get('chain') in ('srcnat', 'hotspot', 'pre-hotspot', 'hs-unauth', 'hs-auth'))
safe_remove('/ip/firewall/filter', filter_fn=lambda f: f.get('comment') and any(k in f.get('comment', '') for k in ('Allow access to billing server', 'Allow from MT1 hotspot', 'place hotspot rules here')))
safe_remove('/radius')
safe_remove('/snmp/community', filter_fn=lambda c: c.get('name') == 'billing')

print("\n--- 6. Removing old IP addresses (Preserving bridge-mgmt) ---")
safe_remove('/ip/address', filter_fn=lambda a: a.get('interface') != 'bridge-mgmt')

print("\n--- 7. Resetting interface hardware states ---")
try:
    eth_res = api.get_resource('/interface/ethernet')
    # Enable sfp1
    sfp1 = eth_res.get(name='sfp1')
    if sfp1:
        eth_res.set(id=sfp1[0]['id'], disabled='false')
        print("  [ENABLED] sfp1 interface")
    # Reset ether1 MAC if spoofed
    eth1 = eth_res.get(name='ether1')
    if eth1 and eth1[0].get('mac-address') == '04:5A:3D:D5:1A:00':
        eth_res.call('reset-mac-address', {'.id': eth1[0]['id']})
        print("  [RESET] ether1 MAC address to factory default")
except Exception as e:
    print(f"  Interface reset notice: {e}")

# ----------------------------------------------------------------------
# 2. STANDARDIZING FOR CYBERNET OS
# ----------------------------------------------------------------------
print("\n--- 8. Configuring DNS & WAN ---")
try:
    api.get_resource('/ip/dns').set(servers='8.8.8.8,1.1.1.1,8.8.4.4', allow_remote_requests='yes')
    print("  [OK] DNS set to 8.8.8.8, 1.1.1.1")
except Exception as e:
    print(f"  DNS error: {e}")

# WAN DHCP Client on ether1
try:
    dhcp_cli = api.get_resource('/ip/dhcp-client')
    existing = dhcp_cli.get(interface='ether1')
    if not existing:
        dhcp_cli.add(interface='ether1', disabled='false', comment='Zain WAN 2 (DHCP)')
        print("  [ADDED] DHCP Client on ether1")
    else:
        dhcp_cli.set(id=existing[0]['id'], disabled='false', comment='Zain WAN 2 (DHCP)')
        print("  [UPDATED] DHCP Client on ether1 enabled")
except Exception as e:
    print(f"  DHCP Client error: {e}")

# Outbound NAT Masquerade
try:
    nat_res = api.get_resource('/ip/firewall/nat')
    nat_res.add(chain='srcnat', out_interface='ether1', action='masquerade', comment='NAT out Zain WAN 2')
    print("  [ADDED] Clean NAT Masquerade on ether1")
except Exception as e:
    print(f"  NAT error: {e}")

print("\n--- 9. Provisioning Standardized Customer Pools & Gateways ---")
pool_res = api.get_resource('/ip/pool')
addr_res = api.get_resource('/ip/address')
dhcp_srv_res = api.get_resource('/ip/dhcp-server')
dhcp_net_res = api.get_resource('/ip/dhcp-server/network')

# ether4: Hotspot Distribution (VLAN 10 / Area A) - 10.42.0.1/22
pool_res.add(name='pool-hotspot-ether4', ranges='10.42.0.10-10.42.3.254')
addr_res.add(address='10.42.0.1/22', interface='ether4', network='10.42.0.0', comment='Hotspot Gateway - ether4')
dhcp_net_res.add(address='10.42.0.0/22', gateway='10.42.0.1', dns_server='8.8.8.8,1.1.1.1', comment='CyberNet Hotspot ether4')
dhcp_srv_res.add(name='dhcp-ether4', interface='ether4', address_pool='pool-hotspot-ether4', lease_time='1h', disabled='false')
print("  [OK] ether4 customer pool (10.42.0.1/22) provisioned")

# sfp1: SFP Customer Distribution - 10.52.0.1/22
pool_res.add(name='pool-hotspot-sfp1', ranges='10.52.0.10-10.52.3.254')
addr_res.add(address='10.52.0.1/22', interface='sfp1', network='10.52.0.0', comment='Hotspot Gateway - sfp1')
dhcp_net_res.add(address='10.52.0.0/22', gateway='10.52.0.1', dns_server='8.8.8.8,1.1.1.1', comment='CyberNet Hotspot sfp1')
dhcp_srv_res.add(name='dhcp-sfp1', interface='sfp1', address_pool='pool-hotspot-sfp1', lease_time='1h', disabled='false')
print("  [OK] sfp1 customer pool (10.52.0.1/22) provisioned")

# ether3: Local AP / PC Port - 10.32.30.1/24
pool_res.add(name='pool-ether3-pc', ranges='10.32.30.100-10.32.30.250')
addr_res.add(address='10.32.30.1/24', interface='ether3', network='10.32.30.0', comment='Local PC / AP Port - ether3')
dhcp_net_res.add(address='10.32.30.0/24', gateway='10.32.30.1', dns_server='8.8.8.8,1.1.1.1', comment='Local Management ether3')
dhcp_srv_res.add(name='dhcp-ether3', interface='ether3', address_pool='pool-ether3-pc', lease_time='12h', disabled='false')
print("  [OK] ether3 local PC pool (10.32.30.1/24) provisioned")

print("\n--- 10. Provisioning Hotspot Profiles & Servers ---")
hs_prof_res = api.get_resource('/ip/hotspot/profile')
hs_srv_res = api.get_resource('/ip/hotspot')

# Profile ether4
hs_prof_res.add(
    name='hsprof-ether4',
    html_directory='hotspot',
    dns_name='',
    login_by='mac,http-chap,http-pap',
    mac_auth_mode='mac-as-username-and-password',
    use_radius='yes',
    radius_accounting='yes',
    radius_interim_update='1m'
)
hs_srv_res.add(
    name='hotspot-ether4',
    interface='ether4',
    profile='hsprof-ether4',
    address_pool='pool-hotspot-ether4',
    addresses_per_mac='1',
    disabled='false'
)
print("  [OK] Hotspot server 'hotspot-ether4' configured")

# Profile sfp1
hs_prof_res.add(
    name='hsprof-sfp1',
    html_directory='hotspot',
    dns_name='',
    login_by='mac,http-chap,http-pap',
    mac_auth_mode='mac-as-username-and-password',
    use_radius='yes',
    radius_accounting='yes',
    radius_interim_update='1m'
)
hs_srv_res.add(
    name='hotspot-sfp1',
    interface='sfp1',
    profile='hsprof-sfp1',
    address_pool='pool-hotspot-sfp1',
    addresses_per_mac='1',
    disabled='false'
)
print("  [OK] Hotspot server 'hotspot-sfp1' configured")

print("\n--- 11. Walled Garden Rules for Billing Server & Gateways ---")
wg_ip_res = api.get_resource('/ip/hotspot/walled-garden/ip')
safe_remove('/ip/hotspot/walled-garden/ip')
wg_ip_res.add(action='accept', dst_address='10.20.30.40', comment='Allow TServer Billing Portal')
wg_ip_res.add(action='accept', dst_address='10.20.30.1', comment='Allow Router-20 Gateway')
wg_ip_res.add(action='accept', dst_address='10.20.30.12', comment='Allow Self Gateway')
print("  [OK] Walled-garden Layer-3 IP rules configured")

print("\n--- 12. Central FreeRADIUS Client Configuration ---")
rad_res = api.get_resource('/radius')
rad_res.add(
    address='10.20.30.40',
    secret='cybernet2026',
    service='hotspot,ppp',
    authentication_port='1812',
    accounting_port='1813',
    timeout='3s',
    comment='Central Ubuntu Billing Server'
)
try:
    api.get_resource('/radius/incoming').set(accept='yes', port='3799')
    api.get_resource('/ppp/aaa').set(use_radius='yes', accounting='yes', interim_update='1m')
    print("  [OK] RADIUS client & CoA configured for 10.20.30.40")
except Exception as e:
    print(f"  RADIUS incoming error: {e}")

print("\n==================================================")
print("Router-30 cleanup & standardization completed!")
print("==================================================")

pool.disconnect()
