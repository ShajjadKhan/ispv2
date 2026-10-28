#!/usr/bin/env python3
"""
Sets Jisan's secondary device (MAC: AC:51:2C:A6:F1:99, TECNO KM8n) as a 2-day Guest Pass.
Updates:
1. SQLite isp_v2.db:
   - customer_devices: is_guest = 1, guest_days = 2, guest_expires_at = (now + 2 days), status = 'approved'
   - connection_requests (#262): note updated to reflect Guest Pass (2 Days)
2. MikroTik fleet (Router-10, Router-20, Router-30):
   - IP-binding updated with comment showing Guest Pass and expiration date.
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, '/home/tserver/isp_v2')
import database
import mikrotik_client

def main():
    mac = "AC:51:2C:A6:F1:99"
    cust_id = 78  # Jisan
    days = 2

    print("=" * 70)
    print(f"APPLYING 2-DAY GUEST PASS: Jisan ({mac})")
    print("=" * 70)

    now = datetime.now()
    exp_dt = now + timedelta(days=days)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    exp_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")

    print(f"[*] Current Server Time: {now_str}")
    print(f"[*] Guest Expiration Time (2 Days): {exp_str}")

    # 1. Update database customer_devices
    with database.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, customer_id, mac_address, device_name, status FROM customer_devices WHERE UPPER(mac_address) = ?", (mac,))
        row = cur.fetchone()
        if not row:
            print(f"[!] Device with MAC {mac} not found in customer_devices!")
            return 1

        dev_id = row["id"]
        dev_name = "TECNO KM8n (Guest 2d)"
        print(f"[*] Found device record #{dev_id} under customer #{row['customer_id']}")

        cur.execute("""
            UPDATE customer_devices
            SET is_guest = 1,
                guest_days = ?,
                guest_expires_at = ?,
                device_name = ?,
                status = 'approved',
                approved_at = ?
            WHERE id = ?
        """, (days, exp_str, dev_name, now_str, dev_id))

        # Update connection request #262 if present
        cur.execute("""
            UPDATE connection_requests
            SET notes = ?
            WHERE mac_address = ? AND status = 'approved'
        """, (f"Guest Pass (2 Days until {exp_str})", mac))

        conn.commit()
        print(f"[✓] Database updated: device #{dev_id} set to is_guest=1, guest_days=2, guest_expires_at='{exp_str}'")

    # 2. Update MikroTik fleet
    comment = f"CyberNet: 0508584766 - Jisan [B1F5C] (Guest Pass 2d until {exp_str})"
    print(f"[*] Broadcasting IP-binding to fleet with comment:\n    '{comment}'")
    fleet_res = mikrotik_client.broadcast_bind_device(
        mac_address=mac,
        comment=comment,
        rate_limit="Unlimited"
    )
    print(f"[✓] Fleet binding result: {fleet_res}")

    # 3. Verify in database
    with database.get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, customer_id, mac_address, device_name, status, is_guest, guest_days, guest_expires_at FROM customer_devices WHERE id = ?", (dev_id,))
        updated = dict(cur.fetchone())
        print("[✓] Verified customer_devices record:")
        for k, v in updated.items():
            print(f"    - {k}: {v}")

    print("=" * 70)
    print("GUEST PASS (2 DAYS) SUCCESSFULLY APPLIED!")
    print("=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
