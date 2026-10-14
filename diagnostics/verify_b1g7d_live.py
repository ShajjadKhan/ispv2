import sys
sys.path.insert(0, '/home/sk/isp_v2')
import database, mikrotik_client

cust = database.get_customer_profile(9)
pppoe_sessions = mikrotik_client.broadcast_get_active_pppoe_sessions()
print('Customer #9 Name:', cust.get('name'))
print('Connection Type:', cust.get('connection_type'))
print('PPPoE Username:', cust.get('pppoe_username'))
print('PPPoE Profile:', cust.get('pppoe_profile'))
print('Active PPPoE Session in Fleet:', pppoe_sessions.get('B1G7D'))

# Also verify get_all_pppoe_customers includes customer #9
all_pp = database.get_all_pppoe_customers()
found = any(c['id'] == 9 for c in all_pp)
print(f'Found customer #9 in get_all_pppoe_customers: {found} (Total PPPoE customers: {len(all_pp)})')
