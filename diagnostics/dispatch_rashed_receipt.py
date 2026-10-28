import sys
import os

sys.path.insert(0, '/home/sk/isp_v2')
import main

print("=== Dispatching Missing Receipt for Rashed (Customer #90) ===")
res = main.dispatch_payment_receipt_whatsapp(
    customer_id=90,
    amount_paid=30.0,
    receipt_no="PAY-COL-78",
    collector="Shajjad Khan",
    payment_type="cash",
    notes="Cash Payment on cafeteria (Oct 15)"
)
print("Result:", res)
