import ftplib
import os
import sys

LOGIN_HTML = '/home/tserver/isp_v2/mikrotik_hotspot/login.html'
ROUTER_LOGIN_HTML = '/home/tserver/isp_v2/mikrotik_hotspot/router_login.html'

if not os.path.exists(LOGIN_HTML):
    print(f'Error: {LOGIN_HTML} not found')
    sys.exit(1)

with open(LOGIN_HTML, 'rb') as f:
    login_bytes = f.read()

with open(ROUTER_LOGIN_HTML, 'rb') as f:
    router_login_bytes = f.read()

print(f'Source login.html size: {len(login_bytes)} bytes')
print(f'Source router_login.html size: {len(router_login_bytes)} bytes')

fleet = [
    ('Cybernet Router-20', '10.20.30.1', 'admin', 'adminn', 'hotspot'),
    ('Cybernet Router-30', '10.20.30.12', 'admin', 'adminn3', 'hotspot'),
    ('Cybernet Router-10 (via 10.12.14.1)', '10.12.14.1', 'admin', 'adminn1', 'flash/hotspot'),
    ('Cybernet Router-10 (via 10.20.30.10)', '10.20.30.10', 'admin', 'adminn1', 'flash/hotspot'),
]

for name, host, user, pwd, target_dir in fleet:
    print(f'\n--- Deploying to {name} ({host}) ---')
    try:
        ftp = ftplib.FTP(timeout=5)
        ftp.connect(host, 21)
        ftp.login(user, pwd)
        print(f'  [OK] Authenticated')
        
        # Navigate to target directory
        try:
            ftp.cwd(target_dir)
        except Exception:
            # If flash/hotspot, might need to cwd flash then cwd hotspot
            parts = target_dir.split('/')
            for p in parts:
                if p:
                    try:
                        ftp.cwd(p)
                    except Exception:
                        ftp.mkd(p)
                        ftp.cwd(p)
        print(f'  [OK] Current directory: {ftp.pwd()}')

        # Upload login.html
        from io import BytesIO
        ftp.storbinary('STOR login.html', BytesIO(login_bytes))
        print(f'  [OK] Uploaded login.html ({len(login_bytes)} B)')

        # Upload router_login.html if present
        ftp.storbinary('STOR router_login.html', BytesIO(router_login_bytes))
        print(f'  [OK] Uploaded router_login.html ({len(router_login_bytes)} B)')

        # Verify uploaded sizes
        files = ftp.nlst()
        print(f'  [OK] Remote files verified: {len(files)} files in {target_dir}')
        ftp.quit()
    except Exception as e:
        print(f'  [FAILED] {name} ({host}): {e}')

