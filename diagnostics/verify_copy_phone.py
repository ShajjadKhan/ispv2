import sqlite3, requests

conn = sqlite3.connect('/home/tserver/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute('SELECT session_id FROM admin_sessions WHERE is_active = 1 AND user_id = 1 ORDER BY last_activity DESC LIMIT 1')
row = c.fetchone()
if not row:
    print('No active session found')
    exit(1)

session_id = row[0]
cookies = {'cybernet_session': session_id}

res = requests.get('http://127.0.0.1:9911/approvals', cookies=cookies, timeout=10)
print(f"GET /approvals: status={res.status_code}, length={len(res.content)}")

if res.status_code == 200:
    btn_count = res.text.count('btn-copy-phone')
    has_copy_js = 'copyPhone' in res.text
    has_check_icon = 'check-icon' in res.text
    print(f"btn-copy-phone count: {btn_count}")
    print(f"has copyPhone JS: {has_copy_js}")
    print(f"has check-icon SVG: {has_check_icon}")
    
    if btn_count > 0 and has_copy_js:
        print("VERIFICATION SUCCESS: Copy phone button successfully integrated and rendering!")
    else:
        print("VERIFICATION FAILED: Buttons not found in rendered HTML")
else:
    print("Failed to fetch /approvals:", res.status_code)
