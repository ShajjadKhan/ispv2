import routeros_api, ftplib, urllib.request, json

print('====================================================')
print('CYBERNET OS v2 - CAPTIVE PORTAL INTEGRATION AUDIT')
print('====================================================')

pool = routeros_api.RouterOsApiPool('10.20.30.1', username='admin', password='adminn', port=8728, plaintext_login=True)
api = pool.get_api()

# 1. Hotspot Profiles
profs = api.get_resource('/ip/hotspot/profile').get()
for p in profs:
    name = p.get('name')
    if name in ('hsprof-ether4', 'hsprof-sfp1'):
        dns = p.get('dns-name', '')
        addr = p.get('hotspot-address', '')
        html = p.get('html-directory', '')
        print('CHECK 1 - Profile:', name, 'address:', addr, 'dns-name:', dns, 'html-dir:', html)
        assert dns in ('cyber.net', 'sfp.cyber.net', ''), f'Profile dns-name unexpected: {dns}'
        assert html == 'hotspot', 'Profile html-directory must be hotspot!'

# 2. Walled Garden L7
wgs = api.get_resource('/ip/hotspot/walled-garden').get()
for w in wgs:
    host = w.get('dst-host', '')
    dis = w.get('disabled', 'false')
    if host in ('login.cybernet.local', 'sfp.cybernet.local'):
        print('CHECK 2 - Walled Garden L7 host:', host, 'disabled:', dis)
        assert dis == 'true', 'host must be disabled in walled-garden to prevent bypass!'

# 3. Walled Garden L3 IP
wg_ips = api.get_resource('/ip/hotspot/walled-garden/ip').get()
tserver_allowed = any(r.get('dst-address') == '10.20.30.40' and r.get('action') == 'accept' for r in wg_ips)
print('CHECK 3 - Walled Garden L3 IP: 10.20.30.40 accepted =', tserver_allowed)
assert tserver_allowed, '10.20.30.40 must be accepted in walled-garden/ip!'

# 4. Check Hotspot Files via FTP
ftp = ftplib.FTP('10.20.30.1')
ftp.login('admin', 'adminn')
ftp.cwd('hotspot')
files = ftp.nlst()
print('CHECK 4 - Files in MikroTik /hotspot:', files)
assert 'login.html' in files, 'login.html missing from MikroTik /hotspot!'
assert 'alogin.html' in files, 'alogin.html missing!'
assert 'error.html' in files, 'error.html missing!'
ftp.quit()

# 5. Check FastAPI Endpoints
req = urllib.request.Request('http://127.0.0.1:9911/portal')
with urllib.request.urlopen(req) as resp:
    code = resp.getcode()
    body_len = len(resp.read())
    print('CHECK 5 - FastAPI /portal endpoint: HTTP', code, 'length', body_len, 'bytes')
    assert code == 200, 'Expected HTTP 200'

# 6. Check submit API options
post_data = json.dumps({'phone': '0597595059', 'mac': '00:22:33:44:55:66', 'ip': '10.40.2.200'}).encode()
req2 = urllib.request.Request('http://127.0.0.1:9911/api/hotspot/submit', data=post_data, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req2) as resp2:
    code2 = resp2.getcode()
    res_json = json.loads(resp2.read().decode())
    status_val = res_json.get('status')
    print('CHECK 6 - FastAPI /api/hotspot/submit: HTTP', code2, 'status:', status_val)
    assert code2 == 200, 'Expected HTTP 200'

# Clean up check 6 MAC
import sqlite3
c_db = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c_db.execute("DELETE FROM connection_requests WHERE mac_address='00:22:33:44:55:66'")
c_db.commit()
c_db.close()

pool.disconnect()
print('====================================================')
print('RESULT: ALL 6 CAPTIVE PORTAL CHECKS PASSED (100% OK)')
print('====================================================')
