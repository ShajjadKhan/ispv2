import sys
import os
sys.path.insert(0, '/home/tserver/isp_v2')
import database
import whatsapp_service

phone = '0508584766'
clean_phone = whatsapp_service.format_phone(phone)
text = """✅ *CYBERNET PAYMENT RECEIPT*

Customer : *Jisan*
Receipt #: `COL-60`

💳 *Payment Details:*
  • Amount Paid Today : *10.00 SAR* (Stc Pay)
  • Plan              : Hotspot For 30 Days
  • Service Active To : *2026-11-13*

🌟 *Account Status: Paid in Full (+1.00 SAR Advance Credit) ✅*

🎁 *Free for our customers:*
  🎬 Movies: http://10.12.14.16:8082
  ⚽ Live Football: http://10.12.14.16:8080

📞 Support (24/7): 0597595059

Thank you for your payment! 🙏"""

status = whatsapp_service.get_whatsapp_gateway_status()
print(f"Current status: {status.get('status')}")
if status.get("is_connected"):
    ok, err = whatsapp_service.send_whatsapp_raw(clean_phone, text)
    if ok:
        database.log_whatsapp_message(
            phone=clean_phone,
            message_body=text,
            message_type="receipt",
            status="sent",
            error_message=None,
            customer_id=78,
            customer_name="Jisan",
            sent_by="admin"
        )
        print("SUCCESS: Receipt resent to Jisan!")
    else:
        print(f"FAILED: {err}")
else:
    print("BOT_NOT_CONNECTED: Scan QR code first.")
