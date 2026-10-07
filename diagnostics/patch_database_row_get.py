import os
import sys

db_file = '/home/tserver/isp_v2/database.py' if os.path.exists('/home/tserver/isp_v2/database.py') else 'database.py'

with open(db_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

patched = False
for i, line in enumerate(lines):
    if 'SELECT id, name, phone, pppoe_username FROM customers WHERE id = ?' in line:
        # Check next lines
        if i + 1 < len(lines) and 'cust = cursor.fetchone()' in lines[i+1]:
            lines[i+1] = '        row = cursor.fetchone()\n'
            lines[i+2] = '        if not row:\n'
            lines[i+3] = '            return False, [], "", "", ""\n\n'
            lines[i+4] = '        cust = dict(row)\n'
            lines[i+5] = '        cust_name = cust.get("name") or ""\n'
            lines[i+6] = '        cust_phone = cust.get("phone") or ""\n'
            lines[i+7] = '        cust_pppoe_user = cust.get("pppoe_username") or ""\n'
            patched = True
            print(f'Patched lines {i+2} to {i+8}')
            break

if patched:
    with open(db_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print('Successfully updated database.py!')
else:
    print('Target pattern not found or already patched.')
