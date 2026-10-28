import urllib.request
import auth_service
import database

# Create valid session token
session_id, csrf_token = auth_service.create_session(user_id=1)
req = urllib.request.Request("http://127.0.0.1:9911/olt", headers={"Cookie": f"{auth_service.COOKIE_NAME}={session_id}"})

with urllib.request.urlopen(req) as resp:
    status_code = resp.status
    html = resp.read().decode("utf-8")

print(f"HTTP Status: {status_code}")
print(f"HTML size: {len(html)} bytes")
import re
print("TITLE:", re.findall(r'<title>.*?</title>', html, re.I))
print("H1/H2:", re.findall(r'<h[12].*?</h[12]>', html, re.I))
print("BODY SNIPPET:", re.findall(r'<body.*?>.*?</body>', html, re.I | re.S)[:500])

print("\n--- AUTHENTIC OLT VERIFICATION CHECKS ---")
checks = [
    ("Real OLT Name: 'Core Hub OLT (VSOL 1-Port GPON)'", "Core Hub OLT (VSOL 1-Port GPON)" in html),
    ("Real Management IP: '192.168.200.200:161'", "192.168.200.200:161" in html),
    ("Real Connected ONUs count: '66 Connected ONUs'", "66 Connected ONUs" in html),
    ("PON 1 Port visualizer: '66 / 128 ONUs'", "66 / 128 ONUs" in html),
    ("Real ONU 1: 'EnamulUncleSupervisor'", "EnamulUncleSupervisor" in html),
    ("Real ONU 4: '16.B2S15 Corridor'", "16.B2S15" in html),
    ("Real ONU 66: '66.B1R3 FathyAPT'", "66.B1R3" in html),
    ("No fake OLT: 'Core Hub OLT 1'", "Core Hub OLT 1" not in html),
    ("No fake ONU serial: 'VSOL1A2B3C4D'", "VSOL1A2B3C4D" not in html),
    ("No fake ONU serial: 'FHTT4D3C2B1A'", "FHTT4D3C2B1A" not in html),
    ("No fake ONU serial: 'ZTEG9C8B7A6F'", "ZTEG9C8B7A6F" not in html),
    ("Real optical loss alarms present", "CRITICAL" in html or "HIGH LOSS" in html or "Active Optical" in html),
]

all_passed = True
for name, passed in checks:
    status = "✅ PASS" if passed else "❌ FAIL"
    if not passed:
        all_passed = False
    print(f"{status} - {name}")

print(f"\nOVERALL RESULT: {'ALL 12 CHECKS PASSED SUCCESSFULLY!' if all_passed else 'SOME CHECKS FAILED'}")
