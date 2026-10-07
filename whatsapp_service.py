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
DEFAULT_OPENWA_SESSION_ID = os.getenv("OPENWA_SESSION_ID", "5d393908-58b1-4d36-93e4-69decc3ed193")

_cached_session_id: Optional[str] = None


def get_openwa_session_id(force_refresh: bool = False) -> str:
    """
    Dynamically discovers the active session ID from OpenWA container.
    If multiple sessions exist, prioritizes 'ispv2-bot'.
    If no sessions exist, automatically creates a new 'ispv2-bot' session.
    Caches the ID in memory to minimize overhead.
    """
    global _cached_session_id
    if _cached_session_id and not force_refresh:
        return _cached_session_id

    try:
        url = f"{OPENWA_URL}/api/sessions"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            sessions = r.json()
            if isinstance(sessions, list) and len(sessions) > 0:
                for s in sessions:
                    if s.get("name") == "ispv2-bot":
                        _cached_session_id = s.get("id")
                        return _cached_session_id
                _cached_session_id = sessions[0].get("id")
                return _cached_session_id
            elif isinstance(sessions, list) and len(sessions) == 0:
                cr = requests.post(url, json={"name": "ispv2-bot"}, headers=headers, timeout=5)
                if cr.status_code in (200, 201):
                    new_session = cr.json()
                    _cached_session_id = new_session.get("id")
                    requests.post(f"{OPENWA_URL}/api/sessions/{_cached_session_id}/start", headers=headers, timeout=5)
                    return _cached_session_id
    except Exception as e:
        logger.warning(f"Failed to auto-discover OpenWA session ID: {e}")

    configured = os.getenv("OPENWA_SESSION_ID", "").strip()
    return configured or DEFAULT_OPENWA_SESSION_ID

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
    Checks SQLite database configuration table 'whatsapp_settings' first.
    Falls back to WHATSAPP_SANDBOX_MODE environment variable if not set in DB.
    Defaults to True (active safety) to strictly protect real subscribers.
    """
    try:
        import database
        db_settings = database.get_whatsapp_settings()
        db_val = db_settings.get("sandbox_mode")
        if db_val is not None:
            return str(db_val).lower().strip() not in ("false", "0", "no", "disabled", "off")
    except Exception as e:
        logger.debug(f"Could not read sandbox_mode from database: {e}")

    env_val = os.getenv("WHATSAPP_SANDBOX_MODE", "true").lower().strip()
    return env_val not in ("false", "0", "no", "disabled", "off")


def get_whatsapp_gateway_status() -> Dict[str, Any]:
    """Queries the dedicated OpenWA container for live session state."""
    sandbox = is_sandbox_active()
    session_id = get_openwa_session_id()
    try:
        url = f"{OPENWA_URL}/api/sessions/{session_id}"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 404:
            session_id = get_openwa_session_id(force_refresh=True)
            url = f"{OPENWA_URL}/api/sessions/{session_id}"
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
                "session_id": session_id,
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
            "session_id": session_id,
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
            "session_id": session_id,
            "openwa_url": OPENWA_URL,
            "sandbox_mode": sandbox,
            "allowed_test_phone": ALLOWED_TEST_PHONE,
            "error": str(e)
        }


def get_whatsapp_qr_code() -> Dict[str, Any]:
    """Fetches the active pairing QR code for the dedicated ISPv2 session."""
    session_id = get_openwa_session_id()
    try:
        url = f"{OPENWA_URL}/api/sessions/{session_id}/qr"
        headers = {"X-API-Key": OPENWA_API_KEY}
        r = requests.get(url, headers=headers, timeout=5)

        if r.status_code == 404:
            session_id = get_openwa_session_id(force_refresh=True)
            url = f"{OPENWA_URL}/api/sessions/{session_id}/qr"
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
    session_id = get_openwa_session_id()
    try:
        url = f"{OPENWA_URL}/api/sessions/{session_id}/start"
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


def reset_and_relink_whatsapp_session() -> Dict[str, Any]:
    """
    Completely purges any existing WhatsApp session from OpenWA,
    creates a brand new ispv2-bot session, and starts it to generate a fresh QR code.
    This guarantees any previous WhatsApp account is logged out and removed.
    """
    global _cached_session_id
    headers = {"X-API-Key": OPENWA_API_KEY}
    current_id = get_openwa_session_id()

    # 1. Stop and Delete old session if it exists
    if current_id:
        try:
            requests.post(f"{OPENWA_URL}/api/sessions/{current_id}/stop", headers=headers, timeout=6)
        except Exception:
            pass
        try:
            requests.delete(f"{OPENWA_URL}/api/sessions/{current_id}", headers=headers, timeout=8)
        except Exception as e:
            logger.warning(f"Could not delete old session {current_id}: {e}")

    _cached_session_id = None

    # 2. Create fresh session
    try:
        cr = requests.post(f"{OPENWA_URL}/api/sessions", json={"name": "ispv2-bot"}, headers=headers, timeout=8)
        if cr.status_code in (200, 201):
            session_data = cr.json()
            new_id = session_data.get("id")
            _cached_session_id = new_id

            # 3. Start fresh session
            requests.post(f"{OPENWA_URL}/api/sessions/{new_id}/start", headers=headers, timeout=8)
            return {
                "success": True,
                "session_id": new_id,
                "message": "Session reset successfully. A new QR code is generating..."
            }
        else:
            return {"success": False, "error": f"Failed to create new session: {cr.text}"}
    except Exception as e:
        logger.exception(f"Error resetting WhatsApp session: {e}")
        return {"success": False, "error": str(e)}


def restart_whatsapp_session() -> Dict[str, Any]:
    """
    Restarts / resets the dedicated OpenWA session to provide a clean QR code.
    """
    return reset_and_relink_whatsapp_session()


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
    payment_method: str = "",
    pending_debt: float = 0.0,
    previous_debt: float = 0.0,
    credit_balance: float = 0.0,
    account_status: str = ""
) -> str:
    """
    Replaces standard dynamic tags in WhatsApp message templates, including
    intelligent accounting ledger breakdown for partial payments, full settlements,
    and advance credits.
    """
    msg = template_str
    clean_paid = float(amount_paid or 0.0)
    clean_pending = float(pending_debt or 0.0)
    clean_prev = float(previous_debt or 0.0)
    clean_credit = float(credit_balance or 0.0)

    # Dynamic Account Status generation if not explicitly provided
    if not account_status:
        if clean_pending > 0.01:
            account_status = (
                f"⚠️ *Account Status: Partial Payment*\n"
                f"  • Total Debt Prior  : *{clean_prev:.2f} SAR*\n"
                f"  • Amount Paid Today : *{clean_paid:.2f} SAR*\n"
                f"  • *Pending Debt Remaining : {clean_pending:.2f} SAR* ⚠️\n"
                f"  _(Please settle remaining balance at your earliest convenience)_"
            )
        elif clean_credit > 0.01:
            account_status = f"🌟 *Account Status: Paid in Full (+{clean_credit:.2f} SAR Advance Credit) ✅*"
        else:
            account_status = "✨ *Account Status: Fully Paid & Settled (0.00 SAR Due) ✅*"

    replacements = {
        "[NAME]": customer_name or "Valued Subscriber",
        "[PHONE]": phone or "",
        "[PACKAGE]": package_name or "High-Speed Fiber",
        "[AMOUNT]": f"{clean_paid:.2f}" if clean_paid > 0 else f"{due_balance:.2f}",
        "[DUE_BALANCE]": f"{due_balance:.2f}",
        "[EXPIRY_DATE]": str(expiry_date or "End of Month"),
        "[PIN]": pin or "N/A",
        "[RECEIPT_NO]": receipt_no or "REC-" + datetime.now().strftime("%Y%m%d%H%M"),
        "[HELPLINE]": support_phone,
        "[MOVIES]": movie_server,
        "[FOOTBALL]": football_server,
        "[COLLECTOR]": collector_name or "Admin",
        "[PAYMENT_METHOD]": payment_method or "Cash",
        "[COMPANY_NAME]": "CyberNet ISP",
        "[ACCOUNT_STATUS]": account_status,
        "[PENDING_DEBT]": f"{clean_pending:.2f}",
        "[REMAINING_DEBT]": f"{clean_pending:.2f}",
        "[PREVIOUS_DEBT]": f"{clean_prev:.2f}",
        "[CREDIT_BALANCE]": f"{clean_credit:.2f}",
        "[DATE]": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    for tag, val in replacements.items():
        msg = msg.replace(tag, str(val))

    # Backward compatibility: Replace legacy hardcoded 'Fully Paid & Settled' in templates
    # if the template didn't use the explicit [ACCOUNT_STATUS] tag
    if "[ACCOUNT_STATUS]" not in template_str:
        legacy_needles = [
            "✨ *Account Status:* Fully Paid & Settled ✅",
            "*Account Status:* Fully Paid & Settled ✅",
            "✨ *Account Status:* Fully Paid & Settled",
            "*Account Status:* Fully Paid & Settled"
        ]
        for needle in legacy_needles:
            if needle in msg:
                msg = msg.replace(needle, account_status)
                break

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

    session_id = get_openwa_session_id()
    chat_id = f"{clean_phone}@c.us"
    url = f"{OPENWA_URL}/api/sessions/{session_id}/messages/send-text"
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
