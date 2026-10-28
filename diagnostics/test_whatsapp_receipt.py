import sqlite3
import sys
import os

sys.path.insert(0, '/home/sk/isp_v2')
import whatsapp_service
import database

print("=== WhatsApp Service Status ===")
status = whatsapp_service.get_whatsapp_gateway_status()
print(f"Status: {status}")

print("\n=== WhatsApp Settings ===")
settings = database.get_whatsapp_settings()
for k, v in settings.items():
    if k not in ('template_receipt', 'template_reminder'):
        print(f"  {k}: {v}")

# Check recent logs
conn = sqlite3.connect('/home/sk/isp_v2/isp_v2.db')
c = conn.cursor()
c.execute("SELECT id, phone, customer_name, message_type, status, error_message, created_at FROM whatsapp_logs ORDER BY id DESC LIMIT 5")
rows = c.fetchall()
print("\n=== Recent WhatsApp Logs ===")
for r in rows:
    print(r)

# Test dispatch_payment_receipt_whatsapp directly for Customer #2 (dry run or check)
import main
print("\n=== Testing dispatch_payment_receipt_whatsapp for Customer #2 ===")
res = main.dispatch_payment_receipt_whatsapp(
    customer_id=2,
    amount_paid=1.0,
    receipt_no="TEST-DEMO-001",
    collector="Shajjad Khan",
    payment_type="cash",
    notes="Test Demo Receipt"
)
print("Dispatch result:", res)
