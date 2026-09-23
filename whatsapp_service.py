try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

"""
CyberNet OS v2 - WhatsApp Messaging Engine & Safety Service
Direct integration with OpenWA container running on port 2785.
Includes strict night-time guardrails and audit logging.
"""

import os
import re
import logging
import requests
from datetime import datetime, time as dtime
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("whatsapp_service")

# OpenWA container configuration
OPENWA_URL = os.getenv("OPENWA_URL", "http://127.0.0.1:2785")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY", "dev-admin-key")
OPENWA_SESSION_ID = os.getenv("OPENWA_SESSION_ID", "8cc17322-a9d3-4b88-89ac-d4d95fb57ff4")

DEFAULT_SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "0597595059")
DEFAULT_MOVIE_SERVER = os.getenv("MOVIE_SERVER", "http://10.12.14.16:8082")
DEFAULT_FOOTBALL_SERVER = os.getenv("FOOTBALL_SERVER", "http://10.12.14.16:8080")


def format_phone(raw: str) -> str:
    """
    Normalizes a phone number to standard international E.164 without '+' sign.
    Specifically handles Saudi local mobile numbers (05... -> 9665...).
    """
    if not raw:
        return ""
    p = re.sub(r"[^0-9]", "", str(raw).strip())
    # Handle Saudi local numbers starting with 05
    if p.startswith("0") and len(p) == 10:
        p = "966" + p[1:]
    elif p.startswith("5") and len(p) == 9:
        p = "966" + p
    return p


def get_whatsapp_gateway_status() -> Dict[str, Any]:
    """Queries the local OpenWA container for live session state."""
    try:
        url = f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            data = r.json()
            status_val = data.get("status", "unknown")
            is_connected = status_val in ("ready", "CONNECTED")
            return {
                "connected": is_connected,
                "status": status_val,
                "phone": data.get("phone", "966594266584"),
                "name": data.get("pushName") or data.get("name") or "Cyber Net",
                "session_id": OPENWA_SESSION_ID,
                "connected_at": data.get("connectedAt"),
                "last_active": data.get("lastActive"),
                "openwa_url": OPENWA_URL,
                "error": None
            }
        return {
            "connected": False,
            "status": f"HTTP {r.status_code}",
            "phone": None,
            "name": "Cyber Net",
            "session_id": OPENWA_SESSION_ID,
            "openwa_url": OPENWA_URL,
            "error": r.text
        }
    except Exception as e:
        logger.warning(f"Failed to query OpenWA status: {e}")
        return {
            "connected": False,
            "status": "offline",
            "phone": None,
            "name": "Cyber Net",
            "session_id": OPENWA_SESSION_ID,
            "openwa_url": OPENWA_URL,
            "error": str(e)
        }


def is_night_quiet_hours(start_str: str = "22:00", end_str: str = "09:00") -> Tuple[bool, str]:
    """
    Evaluates whether the current local time falls within night quiet hours.
    Default: 10:00 PM (22:00) to 09:00 AM (09:00).
    """
    now = datetime.now()
    current_time = now.time()

    try:
        sh, sm = [int(x) for x in start_str.split(":")]
        eh, em = [int(x) for x in end_str.split(":")]
        start_t = dtime(sh, sm)
        end_t = dtime(eh, em)
    except Exception:
        start_t = dtime(22, 0)
        end_t = dtime(9, 0)

    # Overnight range check (e.g. 22:00 to 09:00 next day)
    if start_t > end_t:
        is_night = (current_time >= start_t) or (current_time < end_t)
    else:
        is_night = start_t <= current_time < end_t

    desc = f"Current time is {now.strftime('%I:%M %p')} (Quiet hours: {start_t.strftime('%I:%M %p')} - {end_t.strftime('%I:%M %p')})"
    return is_night, desc


def render_message_template(
    template_str: str,
    customer_name: str = "",
    phone: str = "",
    package_name: str = "",
    due_balance: float = 0.0,
    expiry_date: str = "",
    pin: str = "",
    receipt_no: str = "",
    amount_paid: float = 0.0,
    support_phone: str = DEFAULT_SUPPORT_PHONE,
    movie_server: str = DEFAULT_MOVIE_SERVER,
    football_server: str = DEFAULT_FOOTBALL_SERVER
) -> str:
    """Replaces standard dynamic tags in WhatsApp message templates."""
    msg = template_str
    replacements = {
        "[NAME]": customer_name or "Valued Subscriber",
        "[PHONE]": phone or "",
        "[PACKAGE]": package_name or "High-Speed Fiber",
        "[AMOUNT]": f"{amount_paid:.2f}" if amount_paid > 0 else f"{due_balance:.2f}",
        "[DUE_BALANCE]": f"{due_balance:.2f}",
        "[EXPIRY_DATE]": str(expiry_date or "End of Month"),
        "[PIN]": pin or "N/A",
        "[RECEIPT_NO]": receipt_no or "REC-" + datetime.now().strftime("%Y%m%d%H%M"),
        "[HELPLINE]": support_phone,
        "[MOVIES]": movie_server,
        "[FOOTBALL]": football_server,
        "[COMPANY_NAME]": "CyberNet ISP"
    }
    for tag, val in replacements.items():
        msg = msg.replace(tag, str(val))
    return msg


def send_whatsapp_raw(phone: str, text: str) -> Tuple[bool, Optional[str]]:
    """Dispatches raw text message directly to OpenWA container."""
    clean_phone = format_phone(phone)
    if not clean_phone:
        return False, "Invalid phone number format"

    chat_id = f"{clean_phone}@c.us"
    url = f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}/messages/send-text"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": OPENWA_API_KEY
    }
    payload = {
        "chatId": chat_id,
        "text": text
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=8)
        if r.status_code in (200, 201):
            logger.info(f"WhatsApp sent successfully to {clean_phone}")
            return True, None
        else:
            err = f"OpenWA HTTP {r.status_code}: {r.text}"
            logger.warning(err)
            return False, err
    except Exception as e:
        err = f"OpenWA network error: {e}"
        logger.error(err)
        return False, err
