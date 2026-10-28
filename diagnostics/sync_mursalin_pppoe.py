import sys
sys.path.insert(0, '/home/sk/isp_v2')
import sqlite3
import time
import mikrotik_client

def main():
    conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
    cur = conn.cursor()
    cur.execute('UPDATE customers SET pppoe_remote_ip = "" WHERE id = 9')
    conn.commit()
    conn.close()
    print("Cleaned pppoe_remote_ip for customer #9.")

    res = mikrotik_client.broadcast_sync_pppoe_secret(
        username='B1G7D',
        password='1234',
        profile='pppoe-profile-ether4',
        remote_ip=None,
        rate_limit=None,
        disabled=False,
        comment='CyberNet PPPoE: 0571245716 - Mohammad Mursalin [B1G7D]'
    )
    print("Broadcast sync result:", res)

    print("Waiting 10 seconds to observe connection attempt...")
    time.sleep(10)

    # Check active PPP sessions on Router-20
    import routeros_api
    pool = routeros_api.RouterOsApiPool(
        host="10.20.30.1",
        username="admin",
        password="adminn",
        port=8728,
        use_ssl=False,
        plaintext_login=True
    )
    api = pool.get_api()
    actives = api.get_resource('/ppp/active').get(name='B1G7D')
    print(f"Active session for B1G7D on Router-20: {actives}")

    logs = api.get_resource('/log').get()
    print("\nRecent 10 logs on Router-20:")
    for l in logs[-10:]:
        print(f"  [{l.get('time')}] ({l.get('topics')}) {l.get('message')}")

    pool.disconnect()

if __name__ == '__main__':
    main()
