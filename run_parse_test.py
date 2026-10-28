import json, re

with open('/home/tserver/isp_v2/olt_live_raw.json', 'r', encoding='utf-8-sig') as f:
    raw = json.load(f)

def clean(s):
    if not s: return ''
    s = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', ' ', s)
    s = re.sub(r'[\r\t]', ' ', s)
    return s

state = clean(raw.get('state', ''))
states = re.findall(r'(?:GPON0/1:|1:)(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)', state)
for s in states:
    idx = int(s[0])
    admin = s[1]
    omcc = s[2]
    phase = s[3]
    sn = s[4]
    if phase.lower() != 'working':
        print(f"OFFLINE ONU {idx:02d}: Phase={phase}, Admin={admin}, OMCC={omcc}, SN={sn}")
