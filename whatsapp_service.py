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

# OpenWA Dedicated Container Configuration for ISPv2
OPENWA_URL = os.getenv("OPENWA_URL", "http://127.0.0.1:2790")
OPENWA_API_KEY = os.getenv("OPENWA_API_KEY", "dev-admin-key")
OPENWA_SESSION_ID = os.getenv("OPENWA_SESSION_ID", "abba0f1a-573b-4107-8fc4-3e8000668e92")

DEFAULT_SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "0597595059")
DEFAULT_MOVIE_SERVER = os.getenv("MOVIE_SERVER", "http://10.12.14.16:8082")
DEFAULT_FOOTBALL_SERVER = os.getenv("FOOTBALL_SERVER", "http://10.12.14.16:8080")

# STRICT TEST SANDBOX SAFETY SHIELD
# Only this authorized phone number may receive test messages during sandbox mode.
ALLOWED_TEST_PHONE = "966597595059"


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


def is_sandbox_active() -> bool:
    """
    Checks whether the safety sandbox mode is active.
    Defaults to True (active) unless WHATSAPP_SANDBOX_MODE is explicitly set to false/0.
    """
    env_val = os.getenv("WHATSAPP_SANDBOX_MODE", "true").lower().strip()
    return env_val not in ("false", "0", "no", "disabled")


def get_whatsapp_gateway_status() -> Dict[str, Any]:
    """Queries the dedicated OpenWA container for live session state."""
    sandbox = is_sandbox_active()
    try:
        url = f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            data = r.json()
            status_val = data.get("status", "unknown")
            is_connected = status_val in ("ready", "CONNECTED")
            needs_qr = status_val in ("scan_qr_code", "SCAN_QR_CODE", "initializing", "created", "qr_ready")
            return {
                "connected": is_connected,
                "needs_qr": needs_qr,
                "status": status_val,
                "phone": data.get("phone"),
                "name": data.get("pushName") or data.get("name") or "CyberNet Bot",
                "session_id": OPENWA_SESSION_ID,
                "connected_at": data.get("connectedAt"),
                "last_active": data.get("lastActive") or data.get("lastActiveAt"),
                "openwa_url": OPENWA_URL,
                "sandbox_mode": sandbox,
                "allowed_test_phone": ALLOWED_TEST_PHONE,
                "error": None
            }
        return {
            "connected": False,
            "needs_qr": False,
            "status": f"HTTP {r.status_code}",
            "phone": None,
            "name": "CyberNet Bot",
            "session_id": OPENWA_SESSION_ID,
            "openwa_url": OPENWA_URL,
            "sandbox_mode": sandbox,
            "allowed_test_phone": ALLOWED_TEST_PHONE,
            "error": r.text
        }
    except Exception as e:
        logger.warning(f"Failed to query OpenWA status: {e}")
        return {
            "connected": False,
            "needs_qr": False,
            "status": "offline",
            "phone": None,
            "name": "CyberNet Bot",
            "session_id": OPENWA_SESSION_ID,
            "openwa_url": OPENWA_URL,
            "sandbox_mode": sandbox,
            "allowed_test_phone": ALLOWED_TEST_PHONE,
            "error": str(e)
        }


def get_whatsapp_qr_code() -> Dict[str, Any]:
    """Fetches the active pairing QR code for the dedicated ISPv2 session."""
    try:
        url = f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}/qr"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            return {
                "success": True,
                "qr": data.get("qrCode"),
                "status": data.get("status", "scan_qr_code"),
                "already_authenticated": False
            }

        # Check if session is already authenticated (no QR required)
        if r.status_code == 400 and "already authenticated" in r.text.lower():
            status_data = get_whatsapp_gateway_status()
            return {
                "success": True,
                "already_authenticated": True,
                "status": "ready",
                "phone": status_data.get("phone"),
                "name": status_data.get("name"),
                "qr": None,
                "message": "Session is already authenticated. No QR code needed."
            }

        # If session is not found or not initialized, try starting it
        if r.status_code in (404, 400):
            try:
                start_whatsapp_session()
                r2 = requests.get(url, headers=headers, timeout=5)
                if r2.status_code == 200:
                    d2 = r2.json()
                    return {
                        "success": True,
                        "qr": d2.get("qrCode"),
                        "status": d2.get("status", "scan_qr_code"),
                        "already_authenticated": False
                    }
            except Exception:
                pass

        return {
            "success": False,
            "error": f"HTTP {r.status_code}: {r.text}",
            "qr": None,
            "already_authenticated": False
        }
    except Exception as e:
        logger.warning(f"Failed to fetch QR code: {e}")
        return {
            "success": False,
            "error": str(e),
            "qr": None,
            "already_authenticated": False
        }


def start_whatsapp_session() -> Dict[str, Any]:
    """Requests OpenWA to start or re-initialize the ispv2-bot session."""
    try:
        url = f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}/start"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.post(url, headers=headers, timeout=10)
        return {
            "success": r.status_code in (200, 201),
            "status_code": r.status_code,
            "response": r.json() if r.status_code in (200, 201) else r.text
        }
    except Exception as e:
        logger.exception(f"Error starting WhatsApp session: {e}")
        return {"success": False, "error": str(e)}


def restart_whatsapp_session() -> Dict[str, Any]:
    """
    Phase 5: Restarts the dedicated OpenWA session: terminates existing instance
    and launches a fresh session so a new pairing QR code can be generated.
    """
    try:
        headers = {"X-API-Key": OPENWA_API_KEY}
        # 1. Stop existing session
        try:
            requests.post(f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}/stop", headers=headers, timeout=6)
        except Exception as se:
            logger.warning(f"Notice while stopping session before restart: {se}")

        # 2. Start session
        r = requests.post(f"{OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}/start", headers=headers, timeout=12)
        return {
            "success": r.status_code in (200, 201),
            "status_code": r.status_code,
            "response": r.json() if r.status_code in (200, 201) else r.text
        }
    except Exception as e:
        logger.exception(f"Error restarting WhatsApp session: {e}")
        return {"success": False, "error": str(e)}


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
    football_server: str = DEFAULT_FOOTBALL_SERVER,
    collector_name: str = "",
    payment_method: str = ""
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
        "[COLLECTOR]": collector_name or "Admin",
        "[PAYMENT_METHOD]": payment_method or "Cash",
        "[COMPANY_NAME]": "CyberNet ISP"
    }
    for tag, val in replacements.items():
        msg = msg.replace(tag, str(val))
    return msg


def send_whatsapp_raw(phone: str, text: str) -> Tuple[bool, Optional[str]]:
    """
    Dispatches raw text message directly to OpenWA container with strict safety gates.
    ENFORCES HARDCODED TEST SANDBOX SHIELD:
    If sandbox mode is active, only ALLOWED_TEST_PHONE (0597595059) is permitted.
    All other phone numbers are strictly blocked and forbidden from receiving messages.
    """
    clean_phone = format_phone(phone)
    if not clean_phone:
        return False, "Invalid phone number format"

    # =========================================================================
    # STRICT SAFETY SHIELD: TEST NUMBER RESTRICTION (0597595059 ONLY)
    # =========================================================================
    if is_sandbox_active():
        allowed_clean = format_phone(ALLOWED_TEST_PHONE)
        if clean_phone != allowed_clean:
            shield_err = (
                f"🛡️ SANDBOX SHIELD ACTIVE: Outgoing message to {phone} ({clean_phone}) "
                f"was BLOCKED. During testing, messaging client numbers is strictly prohibited. "
                f"Only authorized test number 0597595059 is permitted."
            )
            logger.warning(shield_err)
            return False, shield_err

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
