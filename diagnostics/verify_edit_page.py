import sys
import requests
import auth_service

BASE_URL = "http://127.0.0.1:9911"

# Create a session for master admin (user_id=1)
session_token, expiry = auth_service.create_session(user_id=1, client_ip="127.0.0.1", user_agent="VerificationScript")
print(f"Created admin session token: {session_token[:8]}...")

session = requests.Session()
session.cookies.set(auth_service.COOKIE_NAME, session_token)

# Query /customers/2/edit
edit_resp = session.get(f"{BASE_URL}/customers/2/edit")
print(f"Customer 2 edit status code: {edit_resp.status_code}")

if edit_resp.status_code != 200:
    print(f"ERROR: Expected 200 OK, got {edit_resp.status_code}")
    print(edit_resp.text[:500])
    sys.exit(1)

html = edit_resp.text

# Define checks
checks = [
    ("Title has Customer #2", "Edit Customer #2" in html),
    ("Customer Full Name input (#custName)", 'id="custName"' in html and 'name="name"' in html),
    ("Primary Phone Number input (#custPhone)", 'id="custPhone"' in html and 'name="phone"' in html),
    ("Customer Joining Date (#custJoinDate)", 'id="custJoinDate"' in html and 'name="join_date"' in html),
    ("Billing Cycle Start Date (#custBillingStartDate)", 'id="custBillingStartDate"' in html and 'name="billing_start_date"' in html),
    ("Payment Due Date (#custDueDate)", 'id="custDueDate"' in html and 'name="due_date"' in html),
    ("Quick Due Date presets (.btn-preset +30 Days)", '+30 Days' in html and 'btn-preset' in html),
    ("Max Devices presets (.btn-preset 1 Device Solo)", '1 Device (Solo)' in html and 'btn-preset' in html),
    ("Dark theme color-scheme: dark present", 'color-scheme: dark' in html),
    ("Native input[type=\"date\"] styled in CSS", 'input[type="date"]' in html and '-webkit-calendar-picker-indicator' in html),
    (".btn-preset styled in CSS", '.btn-preset' in html and '#17233a' in html),
    ("Mobile 768px media query with 16px font", '@media (max-width: 768px)' in html and 'font-size: 16px !important' in html),
    ("Danger zone delete customer modal", 'id="deleteCustomerModal"' in html and 'confirmDeleteInput' in html),
    ("JavaScript submit handles join_date and billing_start_date", 'join_date' in html and 'billing_start_date' in html and 'handleFormSubmit' in html)
]

all_passed = True
for label, passed in checks:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {label}")
    if not passed:
        all_passed = False

if all_passed:
    print("\n>>> ALL 14 CUSTOMER EDIT PAGE CHECKS PASSED 100%! <<<")
    sys.exit(0)
else:
    print("\n>>> VERIFICATION FAILED! <<<")
    sys.exit(1)
