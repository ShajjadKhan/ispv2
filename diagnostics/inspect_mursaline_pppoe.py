import sys
sys.path.insert(0, '/home/sk/isp_v2')
import sqlite3
import routeros_api
import database

def main():
    routers = database.get_all_routers(active_only=True)
    for r in routers:
        host = r.get("host")
        user = r.get("username")
        pwd = r.get("password")
        port = int(r.get("port") or 8728)
        print(f"\n==========================================")
        print(f"Checking Router: {r.get('name')} ({host}:{port})")
        print(f"==========================================")
        try:
            pool = routeros_api.RouterOsApiPool(
                host=host,
                username=user,
                password=pwd,
                port=port,
                use_ssl=False,
                plaintext_login=True
            )
            api = pool.get_api()

            # 1. Check all PPP secrets
            ppp_secret_res = api.get_resource('/ppp/secret')
            secrets = ppp_secret_res.get()
            print(f"PPP Secrets ({len(secrets)}):")
            for s in secrets:
                name = s.get('name', '')
                password = s.get('password', '')
                service = s.get('service', '')
                profile = s.get('profile', '')
                remote_ip = s.get('remote-address', '')
                disabled = s.get('disabled', '')
                comment = s.get('comment', '')
                print(f"  Name: '{name}' | Pass: '{password}' | Service: '{service}' | Profile: '{profile}' | Remote-IP: '{remote_ip}' | Disabled: {disabled} | Comment: '{comment}'")

            # 2. Check all PPP Active sessions
            ppp_active_res = api.get_resource('/ppp/active')
            actives = ppp_active_res.get()
            print(f"\nPPP Active Sessions ({len(actives)}):")
            for a in actives:
                print(f"  Name: '{a.get('name')}' | Service: '{a.get('service')}' | Caller-ID: '{a.get('caller-id')}' | Address: '{a.get('address')}' | Uptime: '{a.get('uptime')}'")

            # 3. Check PPPoE Servers
            try:
                pppoe_srv_res = api.get_resource('/interface/pppoe-server/server')
                servers = pppoe_srv_res.get()
                print(f"\nPPPoE Server Services ({len(servers)}):")
                for srv in servers:
                    print(f"  Service: '{srv.get('service-name')}' | Interface: '{srv.get('interface')}' | Disabled: {srv.get('disabled')} | Profile: '{srv.get('default-profile')}' | One-Session-Per-Host: {srv.get('one-session-per-host')} | Max-Sessions: {srv.get('max-sessions')}")
            except Exception as e:
                print(f"  Error PPPoE servers: {e}")

            # 4. Check PPP Profiles
            try:
                ppp_prof_res = api.get_resource('/ppp/profile')
                profiles = ppp_prof_res.get()
                print(f"\nPPP Profiles ({len(profiles)}):")
                for pr in profiles:
                    print(f"  Profile: '{pr.get('name')}' | Local-IP: '{pr.get('local-address')}' | Remote-Pool: '{pr.get('remote-address')}' | DNS: '{pr.get('dns-server')}' | Rate-Limit: '{pr.get('rate-limit')}'")
            except Exception as e:
                print(f"  Error PPP profiles: {e}")

            # 5. Check PPPoE logs
            logs = api.get_resource('/log').get()
            print(f"\nRecent Logs matching ppp or b1g7d or error (last 30 matches):")
            matched_logs = []
            for lg in logs:
                msg = lg.get('message', '')
                top = lg.get('topics', '')
                t_str = lg.get('time', '')
                if 'ppp' in top or 'ppp' in msg.lower() or 'b1g7d' in msg.lower() or 'mursalin' in msg.lower() or 'auth' in msg.lower():
                    matched_logs.append(f"  [{t_str}] ({top}) {msg}")
            for ml in matched_logs[-30:]:
                print(ml)

            pool.disconnect()
        except Exception as e:
            print(f"Failed to query router {host}: {e}")

if __name__ == '__main__':
    main()
