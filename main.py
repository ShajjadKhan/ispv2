try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

"""
CyberNet OS v2 - Clean ISP Management System
Entry Point & Gateway Operations Dashboard (Port 9911)
Includes Step 2: Hotspot Approvals, Onboarding Modal, and Real-Time RouterOS Sync.
"""

import os
import time
import asyncio
import logging
import base64
import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastapi import FastAPI, Request, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
import uvicorn
import qrcode
import urllib.parse

import mikrotik_client
from mikrotik_client import RouterClient, format_bytes, clean_device_friendly_name
import database
import whatsapp_service
import auth_service

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cybernet_v2")

# Base directory & Templates
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="CyberNet OS v2",
    description="Clean, Step-by-Step Reality-Based ISP Operations Engine",
    version="2.0.0"
)

# Enable CORS for all origins (needed for captive portal from MikroTik hotspot)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Initialize database schema and auth engine
database.init_db()
auth_service.init_auth_schema()

# Global router client instance
router_client = RouterClient(
    host=os.getenv("MIKROTIK_HOST", "10.20.30.1"),
    username=os.getenv("MIKROTIK_USER", "admin"),
    password=os.getenv("MIKROTIK_PASS", "admin"),
    port=int(os.getenv("MIKROTIK_PORT", "8728"))
)

# Background Traffic Accounting & 90-Day Delta Collector
_last_host_traffic_snapshot: Dict[str, Dict[str, Any]] = {}
_last_daily_prune_time: float = 0.0

def collect_router_traffic_snapshot():
    """Polls live hotspot hosts from MikroTik, computes delta traffic, and writes to database."""
    global _last_host_traffic_snapshot, _last_daily_prune_time
    now = time.time()
    try:
        hosts = router_client.get_hotspot_hosts_raw()
    except Exception as e:
        logger.debug(f"Traffic collector read error: {e}")
        return

    current_macs = set()
    for h in hosts:
        mac = (h.get("mac-address") or "").strip().upper()
        if not mac:
            continue
        current_macs.add(mac)

        raw_in = int(h.get("bytes-in", 0) or 0)   # Upload from client
        raw_out = int(h.get("bytes-out", 0) or 0) # Download to client
        ip_addr = h.get("address")

        prev = _last_host_traffic_snapshot.get(mac)
        if prev is not None:
            delta_up = (raw_in - prev["bytes_in"]) if raw_in >= prev["bytes_in"] else raw_in
            delta_down = (raw_out - prev["bytes_out"]) if raw_out >= prev["bytes_out"] else raw_out
            delta_sec = int(now - prev["timestamp"])
            if delta_sec > 300:
                delta_sec = 60
        else:
            delta_up = 0
            delta_down = 0
            delta_sec = 0

        _last_host_traffic_snapshot[mac] = {
            "bytes_in": raw_in,
            "bytes_out": raw_out,
            "timestamp": now,
            "ip": ip_addr
        }

        database.record_device_traffic_delta(
            mac_address=mac,
            download_bytes=delta_down,
            upload_bytes=delta_up,
            active_seconds=delta_sec,
            ip_address=ip_addr
        )

    # Disconnected devices
    disconnected_macs = set(_last_host_traffic_snapshot.keys()) - current_macs
    for d_mac in disconnected_macs:
        database.close_device_session(d_mac)
        _last_host_traffic_snapshot.pop(d_mac, None)

    # Daily prune (> 90 days)
    if (now - _last_daily_prune_time) > 86400:
        database.purge_old_traffic_logs(days_to_keep=90)
        _last_daily_prune_time = now


async def traffic_collector_loop():
    """Background worker that continuously tracks internet traffic every 60 seconds."""
    logger.info("Background 90-Day Traffic Accounting Collector initialized.")
    while True:
        try:
            await asyncio.sleep(60)
            await asyncio.to_thread(collect_router_traffic_snapshot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Traffic collector worker loop error: {e}")
            await asyncio.sleep(15)


async def expiration_enforcement_loop():
    """
    Background worker that continuously audits customer expiry dates and cuts expired
    connections across the MikroTik router fleet every 60 seconds.
    Subscription validity is strictly customer-centric: when a customer expires,
    all of their registered devices are disconnected immediately.
    """
    logger.info("Background Customer Expiration Enforcement Loop initialized.")
    await asyncio.sleep(10)
    while True:
        try:
            expired_customers = await asyncio.to_thread(database.check_and_enforce_customer_expirations)
            if expired_customers:
                for cust in expired_customers:
                    cid = cust["customer_id"]
                    macs = cust.get("macs", [])
                    exp_date = cust.get("expiry_date", "")
                    logger.warning(
                        f"[Expiration Enforcer] Customer #{cid} ({cust.get('name')} - {cust.get('phone')}) "
                        f"has expired on {exp_date}. Cutting connection across MikroTik fleet for {len(macs)} device(s)."
                    )
                    for mac in macs:
                        try:
                            mikrotik_client.broadcast_unbind_device(mac)
                        except Exception as mt_err:
                            logger.error(f"Error cutting expired MAC {mac} for customer #{cid}: {mt_err}")
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Expiration enforcer worker loop error: {e}")
            await asyncio.sleep(30)


@app.on_event("startup")
async def startup_event():
    # Real live data from MikroTik traffic collector only
    asyncio.create_task(traffic_collector_loop())
    # Customer subscription expiration enforcement loop across MikroTik fleet
    asyncio.create_task(expiration_enforcement_loop())


# =========================================================
# Pydantic Request Models
# =========================================================
class HotspotSubmitRequest(BaseModel):
    phone: str
    mac: str
    ip: Optional[str] = None
    device_model: Optional[str] = None


class ApproveConnectionPayload(BaseModel):
    name: str
    billing_type: Optional[str] = "prepaid"  # 'prepaid' or 'postpaid'
    package_name: Optional[str] = None
    monthly_fee: Optional[float] = 0.0
    collected_today: Optional[float] = 0.0
    due_day: Optional[int] = 1
    due_date: Optional[str] = None
    max_devices: Optional[int] = 1
    speed_limit: Optional[str] = None
    advance_mode: Optional[str] = "credit"  # "credit" or "months"
    is_secondary: Optional[bool] = False
    join_date: Optional[str] = None
    billing_start_date: Optional[str] = None
    notes: Optional[str] = None


class RevokeDevicePayload(BaseModel):
    mac: str


class CreateCustomerPayload(BaseModel):
    name: str
    phone: str
    billing_type: str  # 'prepaid' or 'postpaid'
    package_name: str
    monthly_fee: float
    due_date: Optional[str] = None
    due_day: int = 1
    mac_address: Optional[str] = None
    max_devices: int = 1
    speed_limit: Optional[str] = None
    initial_payment: Optional[float] = 0.0
    advance_mode: Optional[str] = "credit"
    reseller_id: Optional[int] = None
    join_date: Optional[str] = None
    billing_start_date: Optional[str] = None
    notes: Optional[str] = None


class EditCustomerPayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    billing_type: Optional[str] = None
    package_name: Optional[str] = None
    monthly_fee: Optional[float] = None
    due_date: Optional[str] = None
    speed_limit: Optional[str] = None
    max_devices: Optional[int] = None
    status: Optional[str] = None
    credit_balance: Optional[float] = None
    reseller_id: Optional[int] = -1
    billing_start_date: Optional[str] = None
    join_date: Optional[str] = None
    suspension_held_until: Optional[str] = -1
    suspension_hold_reason: Optional[str] = -1
    notes: Optional[str] = -1


class RecordPromisePayload(BaseModel):
    days: Optional[int] = 0
    promise_date: Optional[str] = None
    note: Optional[str] = ""


class SettleCycleItem(BaseModel):
    month: str
    amount: float = 0.0
    settle: bool = True


class SettleCyclesPayload(BaseModel):
    items: List[SettleCycleItem]
    notes: Optional[str] = ""
    send_whatsapp: Optional[bool] = False


class CreateResellerPayload(BaseModel):
    username: str
    password: str
    full_name: str
    shop_name: Optional[str] = ""
    phone: Optional[str] = ""
    commission_rate: Optional[float] = 0.0
    initial_wallet: Optional[float] = 0.0


class TopupResellerPayload(BaseModel):
    amount: float
    notes: Optional[str] = ""


class UpdateResellerPayload(BaseModel):
    full_name: Optional[str] = None
    shop_name: Optional[str] = None
    phone: Optional[str] = None
    commission_rate: Optional[float] = None
    is_active: Optional[int] = None
    username: Optional[str] = None
    new_password: Optional[str] = None


class CreateManagerPayload(BaseModel):
    username: str
    password: str
    full_name: str
    phone: Optional[str] = ""


class UpdateManagerPayload(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    new_password: Optional[str] = None
    is_active: Optional[int] = None


class UpdateSelfProfilePayload(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    confirm_password: Optional[str] = None


class ResellerRechargePayload(BaseModel):
    customer_id: int
    months: Optional[int] = 1
    notes: Optional[str] = ""


class UpdateDeviceLimitPayload(BaseModel):
    max_devices: int


class AddDevicePayload(BaseModel):
    mac: str
    device_name: Optional[str] = "Client Device"


class RecordPaymentPayload(BaseModel):
    amount: float
    extend_days: int = 30
    notes: Optional[str] = "Manual Service Renewal"
    advance_mode: Optional[str] = "credit"  # "credit" or "months"


class ApplyCreditPayload(BaseModel):
    amount: Optional[float] = None
    extend_days: int = 30


class UpdateCollectionPayload(BaseModel):
    amount: float
    notes: Optional[str] = "Payment entry"
    collected_at: Optional[str] = None
    collected_by: Optional[str] = "Admin"
    billing_type: Optional[str] = "cash"


class BalanceCollectPayload(BaseModel):
    customer_id: int
    amount: float
    source: Optional[str] = "building"
    payment_type: Optional[str] = "cash"
    notes: Optional[str] = ""
    collector: Optional[str] = None
    month_year: Optional[str] = None


class BalanceReminderPayload(BaseModel):
    customer_id: int
    source: Optional[str] = "building"
    send_direct: Optional[bool] = False


class PackagePayload(BaseModel):
    name: str
    price: float
    rate_limit: Optional[str] = "0"
    package_type: Optional[str] = "hotspot"
    cost_price: Optional[float] = 0.0
    validity_days: Optional[int] = 30
    shared_users: Optional[int] = 1
    mikrotik_profile: Optional[str] = None
    description: Optional[str] = ""
    is_active: Optional[int] = 1
    sync_router: Optional[bool] = True


class RegisterOnuPayload(BaseModel):
    olt_id: int
    pon_port: int
    serial_number: str
    name: str
    customer_id: Optional[int] = None
    onu_model: Optional[str] = "1GE+1FE+WiFi GPON ONT"
    mode: Optional[str] = "Routing"
    vlan_id: Optional[int] = 100
    mac_address: Optional[str] = None


class UpdateOnuPayload(BaseModel):
    name: Optional[str] = None
    customer_id: Optional[int] = None
    vlan_id: Optional[int] = None
    mode: Optional[str] = None
    status: Optional[str] = None


class RenameOnuPayload(BaseModel):
    name: str


class OltTelemetrySyncPayload(BaseModel):
    olt_id: int = 1
    onus: List[Dict[str, Any]]
    chassis: Optional[Dict[str, Any]] = None


class WhatsAppSendRequest(BaseModel):
    phone: str
    message: str
    message_type: Optional[str] = "manual"
    customer_id: Optional[int] = None
    force_night: Optional[bool] = False
    simulate: Optional[bool] = False


class WhatsAppSettingsRequest(BaseModel):
    auto_dispatch_enabled: Optional[str] = None
    quiet_hours_enabled: Optional[str] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    support_phone: Optional[str] = None
    movie_server: Optional[str] = None
    football_server: Optional[str] = None
    template_reminder: Optional[str] = None
    template_receipt: Optional[str] = None
    template_voucher: Optional[str] = None
    template_expiry: Optional[str] = None
    template_maintenance: Optional[str] = None


class CreateOltPayload(BaseModel):
    name: str
    ip_address: str
    brand: Optional[str] = "VSOL"
    model: Optional[str] = "GPON-4P"
    pon_type: Optional[str] = "GPON"
    pon_ports_count: Optional[int] = 4
    uplink_ports_count: Optional[int] = 4
    port: Optional[int] = 161
    snmp_community: Optional[str] = "public"
    notes: Optional[str] = None


class CreateRouterPayload(BaseModel):
    name: str
    host: str
    port: Optional[int] = 8728
    username: Optional[str] = "admin"
    password: Optional[str] = ""
    vlan_id: Optional[int] = 10
    ssid_name: Optional[str] = "CyberNet-WiFi"
    uplink_type: Optional[str] = "Zain SIM"
    is_active: Optional[int] = 1


class UpdateRouterPayload(BaseModel):
    name: str
    host: str
    port: Optional[int] = 8728
    username: Optional[str] = "admin"
    password: Optional[str] = None
    vlan_id: Optional[int] = None
    ssid_name: Optional[str] = None
    uplink_type: Optional[str] = None
    is_active: Optional[int] = None


class TestRouterPayload(BaseModel):
    host: str
    port: Optional[int] = 8728
    username: Optional[str] = "admin"
    password: Optional[str] = ""


class LoginPayload(BaseModel):
    username: str
    password: str
    remember_me: Optional[bool] = False


class ChangePasswordPayload(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class TotpEnablePayload(BaseModel):
    code: str


class TotpDisablePayload(BaseModel):
    current_password: str
    code: Optional[str] = ""


# =========================================================
# Security & Authentication Engine
# =========================================================

def get_client_ip(request: Request) -> str:
    """Extracts client IP behind reverse proxy or direct LAN."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


PUBLIC_EXACT_PATHS = {
    "/login",
    "/logout",
    "/api/auth/login",
    "/api/auth/logout",
    "/favicon.ico",
    "/portal",
    "/hotspot",
    "/hotspot/login",
    "/get_unpaid.php"
}

PUBLIC_PREFIXES = (
    "/static/",
    "/api/hotspot/submit",
    "/api/hotspot/check-status",
    "/api/hotspot/detect-mac",
    "/api/hotspot/validate-mac",
    "/api/customer/lookup",
    "/api/olt/sync-telemetry",
    "/downloads/",
    "/portal",
    "/hotspot"
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Allow public endpoints and customer captive portal registration
    if path in PUBLIC_EXACT_PATHS or any(path.startswith(pfx) for pfx in PUBLIC_PREFIXES):
        session_id = request.cookies.get(auth_service.COOKIE_NAME)
        if session_id:
            request.state.user = auth_service.validate_session(session_id)
        else:
            request.state.user = None
        return await call_next(request)

    # Check session cookie or Authorization header
    session_id = request.cookies.get(auth_service.COOKIE_NAME)
    if not session_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header.split(" ", 1)[1].strip()

    user_session = auth_service.validate_session(session_id) if session_id else None

    if not user_session:
        # If calling an API route, return 401 Unauthorized
        if path.startswith("/api/"):
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Authentication required. Please sign in."}
            )
        # For browser UI pages, redirect to /login with next target
        next_target = path
        if request.url.query:
            next_target += f"?{request.url.query}"
        return RedirectResponse(url=f"/login?next={next_target}", status_code=303)

    request.state.user = user_session
    return await call_next(request)


# =========================================================
# Authentication Web & API Routes
# =========================================================

@app.api_route("/login", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: Optional[str] = "/",
    error: Optional[str] = None,
    msg: Optional[str] = None
):
    """Renders the executive secured login portal."""
    if getattr(request.state, "user", None):
        return RedirectResponse(url=next or "/", status_code=303)

    csrf_token = auth_service.generate_login_csrf_token()
    success_msg = None
    if msg == "logged_out":
        success_msg = "You have been securely signed out."
    elif msg == "pw_changed":
        success_msg = "Password changed successfully. Please sign in with your new password."
    elif msg == "session_expired":
        error = "Your session has expired. Please sign in again."

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "request": request,
            "csrf_token": csrf_token,
            "next_url": next or "/",
            "error_msg": error,
            "success_msg": success_msg,
            "username": ""
        }
    )


@app.post("/login")
async def login_post(request: Request):
    """Processes operator credentials with Scrypt verification and lockout defense."""
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    otp_code = str(form.get("otp_code", ""))
    preauth_token = str(form.get("preauth_token", ""))
    csrf_token = str(form.get("csrf_token", ""))
    remember_me = bool(form.get("remember_me"))
    next_url = str(form.get("next", "/")).strip() or "/"

    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    if preauth_token:
        ok, user, message = auth_service.consume_totp_pending_login(preauth_token, otp_code)
        if not ok:
            new_csrf = auth_service.generate_login_csrf_token()
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "request": request,
                    "csrf_token": new_csrf,
                    "next_url": next_url,
                    "error_msg": message,
                    "success_msg": None,
                    "username": username,
                    "requires_totp": True,
                    "preauth_token": preauth_token
                },
                status_code=401
            )

        session_id, _ = auth_service.create_session(
            user_id=user["id"],
            client_ip=client_ip,
            user_agent=user_agent,
            remember_me=bool(user.get("remember_me"))
        )
        next_url = user.get("next_url") or next_url or "/"
        if not next_url.startswith("/") or next_url.startswith("//"):
            next_url = "/"
        if user.get("role") == "reseller" and (next_url == "/" or next_url == "/dashboard"):
            next_url = "/reseller"
        response = RedirectResponse(url=next_url, status_code=303)
        max_age = 30 * 86400 if user.get("remember_me") else 24 * 3600
        is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        response.set_cookie(
            key=auth_service.COOKIE_NAME,
            value=session_id,
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=is_https,
            path="/"
        )
        return response

    # Verify form CSRF token
    if not auth_service.validate_login_csrf_token(csrf_token):
        new_csrf = auth_service.generate_login_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "csrf_token": new_csrf,
                "next_url": next_url,
                "error_msg": "Security token expired. Please re-enter credentials.",
                "success_msg": None,
                "username": username
            },
            status_code=400
        )

    success, user, message = auth_service.authenticate_user(
        username=username,
        password=password,
        client_ip=client_ip,
        user_agent=user_agent
    )

    if not success:
        new_csrf = auth_service.generate_login_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "csrf_token": new_csrf,
                "next_url": next_url,
                "error_msg": message,
                "success_msg": None,
                "username": username
            },
            status_code=401
        )

    if user.get("totp_enabled") and user.get("totp_secret"):
        preauth = auth_service.create_totp_pending_login(
            user=user,
            client_ip=client_ip,
            user_agent=user_agent,
            remember_me=remember_me,
            next_url=next_url
        )
        new_csrf = auth_service.generate_login_csrf_token()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "request": request,
                "csrf_token": new_csrf,
                "next_url": next_url,
                "error_msg": None,
                "success_msg": "Password accepted. Enter your 6-digit authenticator code.",
                "username": username,
                "requires_totp": True,
                "preauth_token": preauth
            }
        )

    # Issue cryptographic session
    session_id, _ = auth_service.create_session(
        user_id=user["id"],
        client_ip=client_ip,
        user_agent=user_agent,
        remember_me=remember_me
    )

    # Prevent open redirect
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/"

    # Route resellers to Reseller Portal if logging in without a specific target
    if user.get("role") == "reseller" and (next_url == "/" or next_url == "/dashboard"):
        next_url = "/reseller"

    response = RedirectResponse(url=next_url, status_code=303)
    max_age = 30 * 86400 if remember_me else 24 * 3600
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"

    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=session_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/"
    )
    return response


@app.api_route("/logout", methods=["GET", "POST"])
async def logout_view(request: Request):
    """Terminates active session and clears auth cookies."""
    session_id = request.cookies.get(auth_service.COOKIE_NAME)
    if session_id:
        auth_service.revoke_session(session_id)
    response = RedirectResponse(url="/login?msg=logged_out", status_code=303)
    response.delete_cookie(key=auth_service.COOKIE_NAME, path="/")
    return response


@app.post("/api/auth/login")
async def api_login(payload: LoginPayload, request: Request):
    """JSON login API for programmatic clients."""
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    success, user, message = auth_service.authenticate_user(
        username=payload.username,
        password=payload.password,
        client_ip=client_ip,
        user_agent=user_agent
    )
    if not success:
        return JSONResponse(status_code=401, content={"success": False, "error": message})

    if user.get("totp_enabled") and user.get("totp_secret"):
        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "requires_2fa": True,
                "error": "Two-factor authentication is enabled. Please use the web login flow."
            }
        )

    session_id, csrf_token = auth_service.create_session(
        user_id=user["id"],
        client_ip=client_ip,
        user_agent=user_agent,
        remember_me=bool(payload.remember_me)
    )
    response = JSONResponse(content={
        "success": True,
        "token": session_id,
        "csrf_token": csrf_token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "is_default_password": bool(user.get("is_default_password", 0))
        },
        "redirect_url": "/reseller" if user.get("role") == "reseller" else "/"
    })
    max_age = 30 * 86400 if payload.remember_me else 24 * 3600
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=session_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_https,
        path="/"
    )
    return response


@app.post("/api/auth/logout")
async def api_logout(request: Request):
    """Terminates session via API."""
    session_id = request.cookies.get(auth_service.COOKIE_NAME)
    if session_id:
        auth_service.revoke_session(session_id)
    response = JSONResponse(content={"success": True, "message": "Session revoked."})
    response.delete_cookie(key=auth_service.COOKIE_NAME, path="/")
    return response


@app.get("/api/auth/me")
async def api_me(request: Request):
    """Returns currently authenticated operator profile."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return {"success": True, "user": user}


@app.post("/api/auth/profile")
async def api_update_profile(payload: UpdateSelfProfilePayload, request: Request):
    """Allows any logged-in operator, manager, or admin to change their username, display name, phone, or password."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})

    target_user_id = user.get("user_id") or user.get("id")
    if not target_user_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid session user ID."})

    if payload.new_password:
        if payload.new_password != payload.confirm_password:
            return JSONResponse(status_code=400, content={"success": False, "error": "New passwords do not match."})

    client_ip = get_client_ip(request)
    ok, msg, updated_user = auth_service.update_self_profile(
        user_id=target_user_id,
        username=payload.username,
        full_name=payload.full_name,
        phone=payload.phone,
        current_password=payload.current_password,
        new_password=payload.new_password,
        client_ip=client_ip
    )
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg, "user": updated_user}


@app.post("/api/auth/change-password")
async def api_change_password(payload: ChangePasswordPayload, request: Request):
    """Changes password for the currently logged-in operator."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})

    if payload.new_password != payload.confirm_password:
        return JSONResponse(status_code=400, content={"success": False, "error": "New passwords do not match."})

    client_ip = get_client_ip(request)
    ok, msg = auth_service.change_password(
        user_id=user["user_id"],
        current_password=payload.current_password,
        new_password=payload.new_password,
        client_ip=client_ip
    )
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg}


@app.get("/api/auth/2fa/setup")
async def api_totp_setup(request: Request):
    """Starts Google Authenticator compatible TOTP setup for the logged-in user."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    user_id = user.get("user_id") or user.get("id")
    ok, secret, msg = auth_service.ensure_totp_secret(user_id)
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    uri = auth_service.build_totp_uri(user.get("username", "admin"), secret)
    img = qrcode.make(uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_data = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    return {
        "success": True,
        "secret": secret,
        "qr_data": qr_data,
        "enabled": bool(user.get("totp_enabled", 0))
    }


@app.post("/api/auth/2fa/enable")
async def api_totp_enable(payload: TotpEnablePayload, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    user_id = user.get("user_id") or user.get("id")
    ok, msg = auth_service.enable_totp(user_id, payload.code, client_ip=get_client_ip(request))
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg}


@app.post("/api/auth/2fa/disable")
async def api_totp_disable(payload: TotpDisablePayload, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Unauthorized"})
    user_id = user.get("user_id") or user.get("id")
    ok, msg = auth_service.disable_totp(user_id, payload.current_password, payload.code or "", client_ip=get_client_ip(request))
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg}


@app.get("/api/auth/audit")
async def api_auth_audit(request: Request):
    """Returns security audit ledger (superadmin only)."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "superadmin":
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    logs = auth_service.get_recent_auth_logs(limit=30)
    return {"success": True, "logs": logs}



# =========================================================
# Web UI Routes
# =========================================================

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/dashboard", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def dashboard_view(request: Request, month: Optional[str] = None):
    """
    Unified Operations & Financial Command Center.
    Merges live MikroTik connectivity metrics, capacity utilization,
    will-suspend expiration tiers, billing collection analytics,
    staff performance breakdown, and 1-click collections.
    """
    live_status = router_client.get_live_status()
    online_macs = []
    if live_status.get("connected"):
        try:
            online_macs = router_client.get_online_mac_addresses()
        except Exception as e:
            logger.warning(f"Could not retrieve online MACs: {e}")

    metrics = database.get_dashboard_metrics(month_str=month, online_macs=online_macs)
    pending_requests = database.get_pending_requests()
    packages = database.get_packages()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "router": live_status,
            "active_page": "dashboard",
            "metrics": metrics,
            "pending_requests": pending_requests,
            "pending_count": len(pending_requests),
            "packages": packages
        }
    )


@app.api_route("/gateway", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def gateway_view(request: Request, router_id: Optional[int] = None):
    """
    Dedicated MikroTik Gateway Operations & Fleet Management Visualizer.
    Supports multi-MikroTik fleet (1 by 1 expansion for VLAN 10, 20, 30).
    """
    all_routers = database.get_all_routers()
    if not all_routers:
        database.init_db()
        all_routers = database.get_all_routers()

    # Determine selected router
    selected_router_record = None
    if router_id:
        for r in all_routers:
            if r["id"] == router_id:
                selected_router_record = r
                break
    if not selected_router_record and all_routers:
        selected_router_record = all_routers[0]

    # Gather live status for the selected router
    if selected_router_record:
        client = mikrotik_client.get_client_for_router(selected_router_record)
        selected_live_status = client.get_live_status()
        # Cache telemetry in DB
        database.update_router_telemetry(
            router_id=selected_router_record["id"],
            identity=selected_live_status.get("identity"),
            model=selected_live_status.get("model"),
            ros_version=selected_live_status.get("version"),
            cpu_usage=selected_live_status.get("cpu_load", 0),
            memory_usage=int(selected_live_status.get("memory_percent", 0)),
            uptime=selected_live_status.get("uptime"),
            last_status="online" if selected_live_status.get("connected") else "offline"
        )
    else:
        selected_live_status = router_client.get_live_status()

    # Refresh fleet list with cached or live indicators
    fleet_list = database.get_all_routers()
    if selected_router_record and fleet_list:
        for r in fleet_list:
            if r["id"] == selected_router_record["id"]:
                r["cpu_usage"] = selected_live_status.get("cpu_load", r.get("cpu_usage", 0))
                r["uptime"] = selected_live_status.get("uptime", r.get("uptime"))
                r["last_status"] = "online" if selected_live_status.get("connected") else "offline"
    pending_requests = database.get_pending_requests()

    return templates.TemplateResponse(
        request=request,
        name="gateway.html",
        context={
            "router": selected_live_status,
            "selected_router": selected_router_record,
            "routers": fleet_list,
            "active_page": "gateway",
            "pending_count": len(pending_requests)
        }
    )


@app.api_route("/olt", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def olt_view(
    request: Request,
    olt_id: Optional[int] = None,
    port: Optional[int] = None,
    filter: Optional[str] = "all"
):
    """
    Step 5: OLT & Fiber PON Plant Monitoring.
    Clean read-only optical console providing:
    - Details about connected ONUs, their names, and optical signal levels.
    - Optical Link Errors & Diagnostics (Loss of Signal / Fiber Break, Dying Gasp, High Attenuation).
    - ONU Uptime & Outage History Ledger.
    No setup/settings forms or VLAN assignment.
    """
    live_status = router_client.get_live_status()
    olts = database.get_all_olts()

    selected_olt_id = olt_id
    if not selected_olt_id and olts:
        selected_olt_id = olts[0]["id"]

    olt_details = database.get_olt_details(selected_olt_id) if selected_olt_id else None
    onus = database.get_onus(olt_id=selected_olt_id, pon_port=port, status_filter=filter) if selected_olt_id else []
    active_errors = database.get_olt_active_errors(olt_id=selected_olt_id) if selected_olt_id else []
    uptime_ledger = database.get_onu_uptime_ledger(olt_id=selected_olt_id) if selected_olt_id else []
    kpis = database.get_olt_kpis(olt_id=selected_olt_id) if selected_olt_id else {}
    pending_requests = database.get_pending_requests()

    return templates.TemplateResponse(
        request=request,
        name="olt.html",
        context={
            "router": live_status,
            "active_page": "olt",
            "olts": olts,
            "selected_olt": olt_details,
            "selected_olt_id": selected_olt_id,
            "selected_port": port,
            "current_filter": filter,
            "onus": onus,
            "active_errors": active_errors,
            "uptime_ledger": uptime_ledger,
            "kpis": kpis,
            "pending_count": len(pending_requests)
        }
    )



@app.api_route("/approvals", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def approvals_view(request: Request):
    """
    Step 2: Hotspot Connection Approvals & Device Management.
    """
    live_status = router_client.get_live_status()
    pending_requests = database.get_pending_requests()
    approved_devices = database.get_approved_devices()
    packages = database.get_packages()

    # Group approved devices by customer subscription
    customers_map = {}
    for dev in approved_devices:
        cid = dev["customer_id"]
        if cid not in customers_map:
            customers_map[cid] = {
                "customer_id": cid,
                "customer_name": dev.get("customer_name") or "Unknown",
                "phone": dev.get("phone") or "—",
                "billing_type": dev.get("billing_type") or "prepaid",
                "package_name": dev.get("package_name") or "—",
                "monthly_fee": dev.get("monthly_fee") or 0.0,
                "customer_status": dev.get("customer_status") or "active",
                "expiry_date": dev.get("expiry_date"),
                "max_devices": dev.get("max_devices") or 1,
                "notes": dev.get("notes") or "",
                "devices": []
            }
        customers_map[cid]["devices"].append(dev)
    approved_customers = list(customers_map.values())

    return templates.TemplateResponse(
        request=request,
        name="approvals.html",
        context={
            "router": live_status,
            "active_page": "approvals",
            "pending_requests": pending_requests,
            "approved_devices": approved_devices,
            "approved_customers": approved_customers,
            "packages": packages
        }
    )


def enrich_customer_devices_telemetry(customers_list: list, telemetry_map: dict):
    """
    Enriches each customer's devices list with live connection telemetry (online/recent/offline),
    calculates online_devices_count, and formats friendly device labels.
    """
    for cust in customers_list:
        online_count = 0
        devices = cust.get("devices", [])
        for dev in devices:
            mac_clean = (dev.get("mac_address") or "").strip().upper()
            telem = telemetry_map.get(mac_clean)
            if telem:
                dev["state"] = telem.get("state", "offline")
                dev["status_label"] = telem.get("status_label", "Offline")
                dev["is_online"] = telem.get("is_online", False)
                dev["live_ip"] = telem.get("live_ip") or dev.get("ip_address")
                dev["uptime"] = telem.get("uptime")
                dev["last_seen"] = telem.get("last_seen")
                dev["idle_time"] = telem.get("idle_time")
                dev["detail"] = telem.get("detail", "Offline")
                dev["friendly_name"] = clean_device_friendly_name(dev.get("device_name"), telem.get("dhcp_host_name"))
            else:
                dev["state"] = "offline"
                dev["status_label"] = "Offline"
                dev["is_online"] = False
                dev["live_ip"] = dev.get("ip_address")
                dev["uptime"] = None
                dev["last_seen"] = None
                dev["idle_time"] = None
                dev["detail"] = "Offline"
                dev["friendly_name"] = clean_device_friendly_name(dev.get("device_name"))

            if dev["state"] == "online":
                online_count += 1
        cust["online_devices_count"] = online_count


@app.api_route("/customers", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def customers_view(request: Request):
    """
    Step 3: Customer Directory & Subscription Operations.
    """
    user = getattr(request.state, "user", None)
    if user and user.get("role") == "reseller":
        return RedirectResponse(url="/reseller", status_code=303)

    live_status = router_client.get_live_status()
    customers = database.get_all_customers()
    packages = database.get_packages()
    resellers = auth_service.get_resellers_list()

    # Live device telemetry (green/yellow/red status indicators)
    telemetry_map = router_client.get_devices_telemetry_map()
    enrich_customer_devices_telemetry(customers, telemetry_map)

    return templates.TemplateResponse(
        request=request,
        name="customers.html",
        context={
            "router": live_status,
            "active_page": "customers",
            "customers": customers,
            "packages": packages,
            "resellers": resellers
        }
    )


@app.api_route("/customers/{customer_id}/edit", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def customer_edit_view(request: Request, customer_id: int):
    """
    Dedicated Customer Edit & MikroTik Provisioning Page.
    """
    live_status = router_client.get_live_status()
    cust = database.get_customer_profile(customer_id)
    if not cust:
        return RedirectResponse(url="/customers", status_code=303)
    packages = database.get_packages()
    resellers = auth_service.get_resellers_list()

    # Live device telemetry for customer devices
    telemetry_map = router_client.get_devices_telemetry_map()
    enrich_customer_devices_telemetry([cust], telemetry_map)

    return templates.TemplateResponse(
        request=request,
        name="customer_edit.html",
        context={
            "router": live_status,
            "active_page": "customers",
            "c": cust,
            "packages": packages,
            "resellers": resellers
        }
    )


@app.api_route("/customers/{customer_id}/usage", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def customer_usage_view(
    request: Request,
    customer_id: int,
    range: Optional[str] = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Dedicated 90-Day Internet Usage & Bandwidth Audit View for a Customer.
    Answers customer disputes with exact timestamped hardware proof.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    range_preset = range or "30d"

    if range_preset == "today":
        start_d = today_str
        end_d = today_str
    elif range_preset == "yesterday":
        yest = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_d = yest
        end_d = yest
    elif range_preset == "7d":
        start_d = (now.date() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_d = today_str
    elif range_preset == "30d":
        start_d = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_d = today_str
    elif range_preset == "90d":
        start_d = (now.date() - timedelta(days=90)).strftime("%Y-%m-%d")
        end_d = today_str
    elif range_preset == "custom" and start_date and end_date:
        start_d = start_date
        end_d = end_date
    else:
        start_d = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_d = today_str
        range_preset = "30d"

    analytics = database.get_customer_usage_analytics(customer_id, start_d, end_d)
    if not analytics or not analytics.get("customer"):
        return RedirectResponse(url="/customers", status_code=303)

    live_status = router_client.get_live_status()

    try:
        telemetry_map = router_client.get_devices_telemetry_map()
        enrich_customer_devices_telemetry([analytics["customer"]], telemetry_map)
    except Exception:
        pass

    return templates.TemplateResponse(
        request=request,
        name="customer_usage.html",
        context={
            "router": live_status,
            "active_page": "customers",
            "c": analytics["customer"],
            "analytics": analytics,
            "range_preset": range_preset,
            "start_date": start_d,
            "end_date": end_d
        }
    )


@app.api_route("/collections", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/billing", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def collections_view(
    request: Request,
    period: Optional[str] = "month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    q: Optional[str] = None
):
    """
    Step 4: Collections, Balance Sheet & Financial Ledger Hub.
    """
    live_status = router_client.get_live_status()
    data = database.get_collections_hub_data(
        period=period or "month",
        start_date=start_date,
        end_date=end_date,
        search_query=q
    )

    return templates.TemplateResponse(
        request=request,
        name="collections.html",
        context={
            "router": live_status,
            "active_page": "collections",
            "bs": data["balance_sheet"],
            "due_queue": data["due_queue"],
            "ledger": data["ledger"],
            "filtered_total": data["filtered_total"],
            "filtered_tx_count": data["filtered_tx_count"],
            "period": period or "month",
            "start_date": start_date or "",
            "end_date": end_date or "",
            "search_q": q or "",
            "customers_dropdown": data["customers_dropdown"]
        }
    )


@app.api_route("/balance", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/billing/balance", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def balance_sheet_view(
    request: Request,
    status: Optional[str] = "all",
    q: Optional[str] = None
):
    """
    Dedicated Customer Balance Sheet & Financial Ledger Desk.
    Replicates and modernizes portal.php?page=balance with CyberNet OS styling.
    Strictly for CyberNet OS existing subscribers.
    """
    live_status = router_client.get_live_status()
    data = database.get_balance_sheet_data(
        status_filter=status or "all",
        search_query=q
    )

    return templates.TemplateResponse(
        request=request,
        name="balance.html",
        context={
            "router": live_status,
            "active_page": "balance",
            "bs": data["summary"],
            "rows": data["rows"],
            "status_counts": data["status_counts"],
            "status_filter": data["status_filter"],
            "search_q": data["search_query"]
        }
    )



@app.api_route("/packages", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def packages_view(request: Request):
    """
    Step 4: Bandwidth Packages & Speed Limits Management.
    """
    live_status = router_client.get_live_status()
    packages = database.get_packages()

    return templates.TemplateResponse(
        request=request,
        name="packages.html",
        context={
            "router": live_status,
            "active_page": "packages",
            "packages": packages
        }
    )


@app.api_route("/resellers", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def resellers_view(request: Request):
    """
    Owner Side: Reseller Partners & Internal Staff Hub.
    Accessible only by Admins / Superadmins.
    """
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        if user and user.get("role") == "reseller":
            return RedirectResponse(url="/reseller", status_code=303)
        if user and user.get("role") == "manager":
            return RedirectResponse(url="/customers", status_code=303)
        return RedirectResponse(url="/login?next=/resellers", status_code=303)

    live_status = router_client.get_live_status()
    resellers = auth_service.get_resellers_list()
    managers = auth_service.get_managers_list()
    ledger = database.get_reseller_wallet_ledger(limit=50)

    total_wallet_pool = sum(float(r.get("wallet_balance") or 0.0) for r in resellers)
    total_partner_sales = sum(float(r.get("month_sales") or 0.0) for r in resellers)
    active_resellers_count = sum(1 for r in resellers if r.get("is_active", 1))

    return templates.TemplateResponse(
        request=request,
        name="resellers.html",
        context={
            "router": live_status,
            "active_page": "resellers",
            "resellers": resellers,
            "managers": managers,
            "ledger": ledger,
            "stats": {
                "total_resellers": len(resellers),
                "active_resellers": active_resellers_count,
                "total_wallet_pool": total_wallet_pool,
                "total_partner_sales": total_partner_sales
            }
        }
    )


@app.api_route("/reseller", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def reseller_portal_view(request: Request, as_reseller_id: Optional[int] = None):
    """
    Reseller Side: Dedicated External Partner Portal.
    Fast Recharge POS, Subscriber Worklist, Wallet Balance & Ledger.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return RedirectResponse(url="/login?next=/reseller", status_code=303)

    target_reseller_id = user.get("id") or user.get("user_id")
    # If Admin/Superadmin is previewing another reseller's portal:
    if user.get("role") in ("admin", "superadmin") and as_reseller_id:
        target_reseller_id = as_reseller_id

    live_status = router_client.get_live_status()
    stats = database.get_reseller_stats(target_reseller_id)
    my_customers = database.get_all_customers(reseller_id=target_reseller_id)
    packages = database.get_packages()
    ledger = database.get_reseller_wallet_ledger(reseller_id=target_reseller_id, limit=30)

    # Live device telemetry
    telemetry_map = router_client.get_devices_telemetry_map()
    enrich_customer_devices_telemetry(my_customers, telemetry_map)

    return templates.TemplateResponse(
        request=request,
        name="reseller_portal.html",
        context={
            "router": live_status,
            "active_page": "reseller_portal",
            "stats": stats,
            "customers": my_customers,
            "packages": packages,
            "ledger": ledger,
            "current_user": user
        }
    )


# =========================================================
# Reseller & Partner API Endpoints
# =========================================================

@app.post("/api/resellers/create")
async def api_create_reseller(payload: CreateResellerPayload, request: Request):
    """Admin creates a new Reseller Partner account."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    success, created_user, msg = auth_service.create_user(
        username=payload.username,
        password=payload.password,
        full_name=payload.full_name,
        role="reseller",
        shop_name=payload.shop_name,
        phone=payload.phone,
        commission_rate=payload.commission_rate or 0.0,
        initial_wallet=payload.initial_wallet or 0.0,
        created_by=user.get("username", "admin")
    )
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg, "user": created_user}


@app.post("/api/resellers/{reseller_id}/topup")
async def api_topup_reseller(reseller_id: int, payload: TopupResellerPayload, request: Request):
    """Admin credits / tops up reseller prepaid wallet."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    success, msg, new_bal = database.topup_reseller_wallet(
        reseller_id=reseller_id,
        amount=payload.amount,
        notes=payload.notes,
        created_by=user.get("username", "admin")
    )
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg, "new_balance": new_bal}


@app.get("/api/resellers/{reseller_id}")
async def api_get_reseller(reseller_id: int, request: Request):
    """Fetches details for a specific reseller partner."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    r = auth_service.get_reseller_by_id(reseller_id)
    if not r:
        return JSONResponse(status_code=404, content={"success": False, "error": "Reseller partner not found."})
    return {"success": True, "reseller": r}


@app.post("/api/resellers/{reseller_id}/update")
async def api_update_reseller(reseller_id: int, payload: UpdateResellerPayload, request: Request):
    """Admin updates reseller commission, shop name, username, password, or account details."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    success, msg = auth_service.update_reseller_profile(
        reseller_id=reseller_id,
        full_name=payload.full_name,
        shop_name=payload.shop_name,
        phone=payload.phone,
        commission_rate=payload.commission_rate,
        is_active=payload.is_active,
        username=payload.username,
        new_password=payload.new_password
    )
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg}


@app.delete("/api/resellers/{reseller_id}")
@app.post("/api/resellers/{reseller_id}/delete")
async def api_delete_reseller(reseller_id: int, request: Request):
    """Admin permanently deletes a reseller partner."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    requesting_id = user.get("id") or user.get("user_id")
    success, msg = auth_service.delete_user(reseller_id, requesting_user_id=requesting_id)
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg}


@app.get("/api/resellers/{reseller_id}/ledger")
async def api_reseller_ledger(reseller_id: int, request: Request):
    """Returns wallet ledger for a specific reseller."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    # Allowed if admin/superadmin OR if reseller looking at their own ledger
    if user.get("role") not in ("admin", "superadmin") and user.get("id") != reseller_id:
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    records = database.get_reseller_wallet_ledger(reseller_id=reseller_id, limit=50)
    return {"success": True, "ledger": records}


@app.post("/api/managers/create")
async def api_create_manager(payload: CreateManagerPayload, request: Request):
    """Admin creates an internal operations manager account."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    success, created_user, msg = auth_service.create_user(
        username=payload.username,
        password=payload.password,
        full_name=payload.full_name,
        role="manager",
        phone=payload.phone,
        created_by=user.get("username", "admin")
    )
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg, "user": created_user}


@app.get("/api/managers/{manager_id}")
async def api_get_manager(manager_id: int, request: Request):
    """Fetches details for an operations manager or admin user."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    target_user = auth_service.get_user_by_id(manager_id)
    if not target_user:
        return JSONResponse(status_code=404, content={"success": False, "error": "Manager not found."})
    return {"success": True, "manager": target_user}


@app.post("/api/managers/{manager_id}/update")
async def api_update_manager(manager_id: int, payload: UpdateManagerPayload, request: Request):
    """Admin updates an operations manager or admin user's username, role, phone, or resets password."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    client_ip = get_client_ip(request)
    ok, msg, updated_user = auth_service.admin_update_manager(
        target_user_id=manager_id,
        username=payload.username,
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
        new_password=payload.new_password,
        is_active=payload.is_active,
        client_ip=client_ip
    )
    if not ok:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg, "manager": updated_user}


@app.delete("/api/managers/{manager_id}")
@app.post("/api/managers/{manager_id}/delete")
async def api_delete_manager(manager_id: int, request: Request):
    """Admin permanently deletes an operations manager account."""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") not in ("admin", "superadmin"):
        return JSONResponse(status_code=403, content={"success": False, "error": "Admin access required."})

    requesting_id = user.get("id") or user.get("user_id")
    success, msg = auth_service.delete_user(manager_id, requesting_user_id=requesting_id)
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg})
    return {"success": True, "message": msg}


@app.post("/api/reseller/recharge")
async def api_reseller_recharge(payload: ResellerRechargePayload, request: Request):
    """
    Reseller Fast POS Recharge:
    Deducts net fee from reseller wallet, renews customer line on MikroTik router.
    """
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Authentication required."})

    target_reseller_id = user.get("id") or user.get("user_id")

    success, msg, data = database.reseller_recharge_customer(
        reseller_id=target_reseller_id,
        customer_id=payload.customer_id,
        months=payload.months or 1,
        notes=payload.notes or "",
        operator_username=user.get("username", "Reseller")
    )
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "error": msg, "details": data})

    # Trigger MikroTik synchronization to ensure line is active
    try:
        cust = database.get_customer_profile(payload.customer_id)
        if cust and cust.get("devices"):
            for dev in cust["devices"]:
                if dev.get("status") == "approved":
                    router_client.bind_device(
                        mac_address=dev["mac_address"],
                        ip_address=dev.get("ip_address"),
                        comment=f"CyberNet: {cust['phone']} - {cust['name']} (RENEWED)",
                        rate_limit=cust.get("effective_speed")
                    )
    except Exception as e:
        logger.warning(f"Post-recharge router sync notice: {e}")

    return {"success": True, "message": msg, "data": data}


@app.post("/api/reseller/customers/create")
async def api_reseller_create_customer(payload: CreateCustomerPayload, request: Request):
    """Reseller registers a new subscriber attributed to their agency."""
    user = getattr(request.state, "user", None)
    if not user:
        return JSONResponse(status_code=401, content={"success": False, "error": "Authentication required."})

    target_reseller_id = user.get("id") or user.get("user_id")
    if payload.mac_address and payload.mac_address.strip():
        if database.is_randomized_mac(payload.mac_address):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Randomized MAC address '{payload.mac_address}' is not permitted. CyberNet strictly requires physical Device MAC."
                }
            )

    try:
        cust = database.create_customer(
            phone=payload.phone,
            name=payload.name,
            billing_type="prepaid",
            package_name=payload.package_name,
            monthly_fee=payload.monthly_fee,
            due_date=payload.due_date,
            due_day=payload.due_day,
            mac_address=payload.mac_address,
            max_devices=payload.max_devices,
            speed_limit=payload.speed_limit,
            initial_payment=payload.initial_payment or 0.0,
            advance_mode=payload.advance_mode or "credit",
            reseller_id=target_reseller_id,
            join_date=payload.join_date,
            billing_start_date=payload.billing_start_date,
            notes=payload.notes
        )

        # Bind on MikroTik if MAC was supplied
        mt_ok = True
        if payload.mac_address and payload.mac_address.strip():
            notes_str = f" [{cust['notes'].strip()}]" if cust.get("notes") and cust["notes"].strip() else ""
            mt_ok = router_client.bind_device(
                mac_address=payload.mac_address,
                comment=f"CyberNet Partner [{user.get('username')}]: {cust['phone']} - {cust['name']}{notes_str}"
            )

        return {
            "success": True,
            "message": f"Subscriber '{payload.name}' registered under your partner agency.",
            "customer": cust,
            "mikrotik_synced": mt_ok
        }
    except Exception as e:
        logger.exception(f"Reseller customer registration failed: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


# =========================================================
# Hotspot Captive Portal API Endpoints
# =========================================================

@app.post("/api/hotspot/submit")
async def hotspot_submit(payload: HotspotSubmitRequest):
    """
    Called by captive portal popup (login.html) when client enters phone number.
    Returns status: 'approved' (if device is already authorized) or 'pending' (waiting for admin).
    Blocks and rejects any device connecting with a Randomized / Private MAC address.
    """
    mac_clean = payload.mac.strip().upper() if payload.mac else ""
    phone_clean = payload.phone.strip() if payload.phone else ""
    logger.info(f"Incoming hotspot submit: Phone={phone_clean}, MAC={mac_clean}, IP={payload.ip}")

    # Enforce Device MAC - Strictly forbid Randomized MACs
    if database.is_randomized_mac(mac_clean):
        logger.warning(f"Blocked hotspot submit: Randomized MAC detected {mac_clean} for Phone {phone_clean}")

        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "status": "random_mac_blocked",
                "error": "RANDOM_MAC_BLOCKED",
                "is_random_mac": True,
                "mac": mac_clean,
                "message": (
                    f"Please change your MAC type! Randomized MAC address detected ({mac_clean}). "
                    "CyberNet Wi-Fi strictly requires your physical Device MAC to connect. "
                    "Please go to your phone's Wi-Fi Settings -> tap this Wi-Fi network -> "
                    "switch MAC Address to 'Use Device MAC' (or turn OFF 'Private Wi-Fi Address'), then reconnect."
                ),
                "instructions": {
                    "ios": "Settings -> Wi-Fi -> (i) icon -> Turn OFF 'Private Wi-Fi Address'",
                    "android": "Settings -> Wi-Fi -> Gear icon -> Advanced -> MAC address type -> Select 'Use Device MAC'",
                    "windows": "Settings -> Network & Internet -> Wi-Fi -> Turn OFF 'Random hardware addresses'"
                }
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            }
        )

    # Process through database
    try:
        req_dict, is_approved, is_secondary = database.create_or_update_request(
            phone=phone_clean,
            mac=mac_clean,
            ip=payload.ip,
            device_model=payload.device_model
        )
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "status": "error", "message": str(e)},
            headers={"Access-Control-Allow-Origin": "*"}
        )

    # Check if this customer or device is expired
    if req_dict.get("is_expired") or req_dict.get("status") == "expired" or req_dict.get("is_customer_expired"):
        exp_date = req_dict.get("expiry_date") or req_dict.get("customer_expiry_date") or "N/A"
        try:
            mikrotik_client.broadcast_unbind_device(mac_clean)
        except Exception:
            pass
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "status": "expired",
                "expiry_date": exp_date,
                "is_secondary_device": bool(is_secondary),
                "message": f"Subscription expired on {exp_date}. Please contact administrator to renew your plan."
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    if is_approved:
        # Re-ensure pure MAC-only MikroTik binding is active across the fleet
        comment_str = f"CyberNet: {phone_clean} (Existing Active)"
        mikrotik_client.broadcast_bind_device(
            mac_address=mac_clean,
            comment=comment_str
        )
        return JSONResponse(
            content={
                "success": True,
                "status": "approved",
                "is_secondary_device": False,
                "message": "Welcome back! Your device is authorized."
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    return JSONResponse(
        content={
            "success": True,
            "status": "pending",
            "is_secondary_device": is_secondary,
            "message": "Waiting for Administrator approval..."
        },
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.options("/api/hotspot/submit")
async def hotspot_submit_options():
    return JSONResponse(
        content="OK",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


@app.get("/api/hotspot/check-status")
async def check_connection_status(request: Request, mac: str, phone: Optional[str] = ""):
    """
    Called by captive portal polling loop every 4s to check if admin approved the connection.
    Guarantees that any device actively polling with a phone number is registered as pending.
    Blocks polling and rejects any device connecting with a randomized MAC.
    """
    mac_clean = mac.strip().upper() if mac else ""
    phone_clean = phone.strip() if phone else ""

    if database.is_randomized_mac(mac_clean):
        return JSONResponse(
            status_code=403,
            content={
                "status": "random_mac_blocked",
                "error": "RANDOM_MAC_BLOCKED",
                "can_connect": False,
                "is_random_mac": True,
                "mac": mac_clean,
                "message": "Connection blocked: Randomized MAC detected. Please change your MAC type to 'Device MAC' to connect."
            },
            headers={"Access-Control-Allow-Origin": "*"}
        )

    # If phone is provided and device is not yet registered, auto-register pending request!
    if phone_clean and mac_clean:
        client_ip = request.client.host if request.client else None
        if client_ip and (client_ip.startswith("10.20.30.") or client_ip == "127.0.0.1"):
            client_ip = None
        existing_status = database.get_request_status_by_mac_and_phone(mac=mac_clean, phone=phone_clean)
        if existing_status.get("status") in ("none", None):
            logger.info(f"Auto-registering pending request from check-status: Phone={phone_clean}, MAC={mac_clean}, IP={client_ip}")
            try:
                database.create_or_update_request(
                    phone=phone_clean,
                    mac=mac_clean,
                    ip=client_ip,
                    device_model="Mobile Hotspot Client"
                )
            except ValueError:
                pass

    result = database.get_request_status_by_mac_and_phone(mac=mac_clean, phone=phone_clean)
    if result.get("status") == "approved":
        # Validate that device is genuinely active in customer_devices and NOT expired before re-binding
        cust = database.get_customer_by_mac(mac_clean)
        if cust and cust.get("status") == "active" and not cust.get("is_expired"):
            try:
                mikrotik_client.broadcast_bind_device(
                    mac_address=mac_clean,
                    comment=f"CyberNet: {cust.get('phone', '')} - {cust.get('name', 'Active Subscriber')}"
                )
            except Exception:
                pass
        else:
            # Device or customer is expired / inactive! Cut connection immediately
            try:
                mikrotik_client.broadcast_unbind_device(mac_clean)
            except Exception:
                pass
            exp_date = (cust.get("expiry_date") or cust.get("due_date")) if cust else ""
            return JSONResponse(
                status_code=403,
                content={
                    "status": "expired",
                    "expiry_date": exp_date,
                    "phone": cust.get("phone") if cust else phone_clean,
                    "name": cust.get("name") if cust else "Subscriber",
                    "message": f"Your internet subscription has expired. Please renew your plan to restore internet access."
                },
                headers={"Access-Control-Allow-Origin": "*"}
            )
    elif result.get("status") == "expired":
        # Expired customer or device: cut connection immediately
        try:
            mikrotik_client.broadcast_unbind_device(mac_clean)
        except Exception:
            pass
        return JSONResponse(
            status_code=403,
            content=result,
            headers={"Access-Control-Allow-Origin": "*"}
        )
    elif result.get("status") in ("revoked", "rejected", "blocked"):
        # Explicitly ensure MikroTik fleet unbinds and drops traffic for revoked/rejected devices
        try:
            mikrotik_client.broadcast_unbind_device(mac_clean)
        except Exception:
            pass

    return JSONResponse(
        content=result,
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/api/hotspot/detect-mac")
async def detect_mac_endpoint(mac: str):
    """
    Utility endpoint for captive portal clients to verify their MAC address type.
    Returns whether the MAC is a physical Device MAC or a blocked Randomized MAC.
    """
    mac_clean = mac.strip().upper() if mac else ""
    is_valid, msg, norm_mac = database.validate_mac_address(mac_clean, allow_random=True)
    if not is_valid:
        return JSONResponse(
            status_code=400,
            content={"success": False, "mac": mac_clean, "is_valid": False, "error": msg},
            headers={"Access-Control-Allow-Origin": "*"}
        )
    is_rand = database.is_randomized_mac(norm_mac)
    return JSONResponse(
        content={
            "success": True,
            "mac": norm_mac,
            "is_valid": True,
            "is_random_mac": is_rand,
            "mac_type": "randomized" if is_rand else "device",
            "allowed": not is_rand,
            "message": (
                "Randomized MAC detected! Switch to Device MAC in your Wi-Fi settings to connect."
                if is_rand else "Device MAC verified. You may proceed."
            )
        },
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/api/customer/lookup")
async def api_customer_lookup(phone: str):
    """Allows subscriber to look up their current account plan and expiry status in captive portal."""
    clean_phone = phone.strip()
    cust = database.get_customer_by_phone(clean_phone)
    if not cust:
        return JSONResponse(
            content={"found": False, "message": "No subscriber account found with this mobile number."},
            headers={"Access-Control-Allow-Origin": "*"}
        )
    return JSONResponse(
        content={
            "found": True,
            "name": cust.get("name", "Subscriber"),
            "package": cust.get("package_name", "Standard"),
            "expiry_date": cust.get("due_date") or cust.get("expiry_date") or "Active",
            "zone": cust.get("zone", ""),
            "room": cust.get("room", ""),
            "status": cust.get("status", "active"),
            "is_active": cust.get("status") == "active"
        },
        headers={"Access-Control-Allow-Origin": "*"}
    )


@app.get("/portal", response_class=HTMLResponse)
@app.get("/hotspot", response_class=HTMLResponse)
@app.get("/hotspot/login", response_class=HTMLResponse)
async def captive_portal_page(
    request: Request,
    mac: Optional[str] = "",
    ip: Optional[str] = "",
    username: Optional[str] = "",
    link_login_only: Optional[str] = ""
):
    """
    Renders the customer captive portal Wi-Fi login screen.
    Enforces physical Device MAC policy with step-by-step mobile guides.
    """
    client_ip = ip or (request.client.host if request.client else "")
    mac_clean = database.normalize_mac(mac) or (mac.strip().upper() if mac else "")
    is_rand = database.is_randomized_mac(mac_clean) if mac_clean else False

    return templates.TemplateResponse(
        request=request,
        name="captive_portal.html",
        context={
            "mac": mac_clean,
            "ip": client_ip,
            "is_random_mac": is_rand,
            "link_login_only": link_login_only,
            "username": username
        }
    )


@app.get("/api/hotspot/pending-count")
async def get_pending_count():
    """
    Returns pending count for real-time sidebar & dashboard notifications.
    """
    pending = database.get_pending_requests()
    return {"count": len(pending)}


@app.get("/api/hotspot/requests/pending")
async def get_pending_requests_api():
    """
    Returns list of all pending connection requests for live dashboard polling.
    """
    pending = database.get_pending_requests()
    return {"success": True, "count": len(pending), "requests": pending}


# =========================================================
# Admin Approval Actions
# =========================================================

@app.post("/api/hotspot/requests/{req_id}/approve")
async def approve_request(req_id: int, payload: ApproveConnectionPayload):
    """
    Approves pending connection request, registers customer, records payment,
    and pushes bypass rule & rate-limit to MikroTik RouterOS!
    Strictly forbids approving requests with Randomized MAC addresses.
    """
    logger.info(f"Admin approving request #{req_id} with payload: {payload}")
    req = database.get_request_by_id(req_id)
    if not req:
        return JSONResponse(status_code=404, content={"success": False, "error": f"Request #{req_id} not found."})

    req_mac = req.get("mac_address", "").strip().upper()
    if database.is_randomized_mac(req_mac):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Cannot approve request #{req_id}: Device MAC '{req_mac}' is a randomized MAC address. Customer must connect using their physical Device MAC."
            }
        )

    try:
        # 1. Update database
        customer = database.approve_connection(
            req_id=req_id,
            name=payload.name,
            billing_type=payload.billing_type or "prepaid",
            package_name=payload.package_name,
            monthly_fee=payload.monthly_fee or 0.0,
            collected_today=payload.collected_today or 0.0,
            due_day=payload.due_day or 1,
            due_date=payload.due_date,
            max_devices=payload.max_devices or 1,
            speed_limit=payload.speed_limit,
            advance_mode=payload.advance_mode or "credit",
            is_secondary=payload.is_secondary or False,
            join_date=payload.join_date,
            billing_start_date=payload.billing_start_date,
            notes=payload.notes
        )

        # 2. Determine effective rate limit (custom or package default)
        effective_package = customer.get("package_name") or payload.package_name
        effective_speed = customer.get("speed_limit") or payload.speed_limit
        packages = database.get_packages()
        pkg_match = next((p for p in packages if p["name"] == effective_package), None)
        default_rate = pkg_match["rate_limit"] if pkg_match else None
        effective_rate = effective_speed if (effective_speed and effective_speed.strip()) else default_rate

        # 3. Apply to MikroTik fleet
        is_active = (customer.get("status") == "active") and not customer.get("is_expired")
        if is_active:
            cust_billing_label = customer.get("billing_type", "POSTPAID").upper()
            notes_str = f" [{customer['notes'].strip()}]" if customer.get("notes") and customer["notes"].strip() else ""
            comment_str = f"CyberNet: {customer['phone']} - {customer['name']}{notes_str} ({cust_billing_label})"
            fleet_res = mikrotik_client.broadcast_bind_device(
                mac_address=customer["mac_address"],
                ip_address=customer.get("ip_address"),
                comment=comment_str,
                rate_limit=effective_rate
            )
            mt_ok = any(fleet_res.values()) if fleet_res else False
            if not mt_ok:
                logger.warning(f"Device bound in DB but MikroTik API reported an issue: {fleet_res}")
            return {
                "success": True,
                "message": f"Customer '{payload.name}' approved! Internet activated across MikroTik fleet.",
                "customer": customer,
                "mikrotik_synced": mt_ok,
                "fleet_results": fleet_res
            }
        else:
            try:
                mikrotik_client.broadcast_unbind_device(customer["mac_address"])
            except Exception:
                pass
            return {
                "success": True,
                "message": f"Device registered for '{payload.name}', but subscriber subscription is EXPIRED. Internet access will remain cut until renewed.",
                "customer": customer,
                "mikrotik_synced": False,
                "fleet_results": {}
            }

    except Exception as e:
        logger.exception(f"Error approving request #{req_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/api/hotspot/requests/{req_id}/reject")
async def reject_request(req_id: int):
    """Rejects pending request."""
    success = database.reject_connection(req_id)
    return {"success": success, "message": "Request marked as rejected."}


@app.post("/api/hotspot/devices/revoke")
async def revoke_device(payload: RevokeDevicePayload):
    """Revokes device access from MikroTik and local DB with instant connection drop across the fleet."""
    logger.info(f"Admin revoking device MAC {payload.mac}")

    # 1. Update database
    info = database.revoke_customer_device(payload.mac)
    client_ip = info.get("ip_address") if info else None

    # 2. Instantly drop all traffic and remove bindings across MikroTik fleet
    fleet_res = mikrotik_client.broadcast_unbind_device(payload.mac, ip_address=client_ip)
    mt_ok = any(fleet_res.values()) if fleet_res else False

    return {
        "success": True,
        "message": f"Device {payload.mac} revoked and disconnected immediately from MikroTik fleet.",
        "mikrotik_synced": mt_ok,
        "fleet_results": fleet_res
    }


# =========================================================
# Step 3: Customer Directory API Endpoints
# =========================================================

@app.get("/api/customers/live-devices")
async def get_customers_live_devices(request: Request):
    """
    Returns live connection telemetry (green/yellow/red) for all customer devices,
    enabling real-time status dots and connected counters on the customer directory.
    """
    telemetry_map = router_client.get_devices_telemetry_map()
    customers = database.get_all_customers()
    enrich_customer_devices_telemetry(customers, telemetry_map)

    result_customers = {}
    for cust in customers:
        cid = cust["id"]
        dev_list = []
        for dev in cust.get("devices", []):
            dev_list.append({
                "id": dev.get("id"),
                "mac": dev.get("mac_address", ""),
                "state": dev.get("state", "offline"),
                "status_label": dev.get("status_label", "Offline"),
                "detail": dev.get("detail", "Offline"),
                "live_ip": dev.get("live_ip"),
                "friendly_name": dev.get("friendly_name", "Device")
            })
        result_customers[str(cid)] = {
            "online_count": cust.get("online_devices_count", 0),
            "total_devices": len(dev_list),
            "max_devices": cust.get("max_devices", 1),
            "devices": dev_list
        }
    return {
        "success": True,
        "customers": result_customers,
        "timestamp": time.strftime("%H:%M:%S")
    }


@app.get("/api/customers")
async def list_customers():
    """Returns list of all customers with computed validity."""
    return database.get_all_customers()


@app.get("/api/customers/{customer_id}")
async def get_customer_details(customer_id: int):
    """Returns complete customer profile, devices, and payment records."""
    prof = database.get_customer_profile(customer_id)
    if not prof:
        raise HTTPException(status_code=404, detail="Customer not found")
    return prof


@app.get("/api/customers/{customer_id}/usage")
async def api_customer_usage(
    customer_id: int,
    range: Optional[str] = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Returns JSON analytics of 90-day internet traffic usage for a customer.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    range_preset = range or "30d"

    if range_preset == "today":
        start_d = today_str
        end_d = today_str
    elif range_preset == "yesterday":
        yest = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_d = yest
        end_d = yest
    elif range_preset == "7d":
        start_d = (now.date() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_d = today_str
    elif range_preset == "30d":
        start_d = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_d = today_str
    elif range_preset == "90d":
        start_d = (now.date() - timedelta(days=90)).strftime("%Y-%m-%d")
        end_d = today_str
    elif range_preset == "custom" and start_date and end_date:
        start_d = start_date
        end_d = end_date
    else:
        start_d = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_d = today_str

    analytics = database.get_customer_usage_analytics(customer_id, start_d, end_d)
    if not analytics:
        raise HTTPException(status_code=404, detail="Customer not found or no usage data available")

    summ = analytics.get("summary", {})
    cust = analytics.get("customer", {})
    devs = analytics.get("device_breakdown", [])
    active_count = len([d for d in devs if d.get("total_bytes", 0) > 0])

    return {
        "success": True,
        "customer_id": customer_id,
        "customer_name": cust.get("name"),
        "is_online": (summ.get("total_active_seconds", 0) > 0),
        "active_devices_count": active_count,
        "total_download": summ.get("formatted_down", "0 B"),
        "total_upload": summ.get("formatted_up", "0 B"),
        "total_traffic": summ.get("formatted_total", "0 B"),
        "devices": devs,
        "analytics": analytics
    }


@app.get("/api/customers/{customer_id}/usage/whatsapp")
async def api_customer_usage_whatsapp(
    customer_id: int,
    range: Optional[str] = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Generates a clear, professional dispute proof message for WhatsApp.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    range_preset = range or "30d"

    if range_preset == "today":
        start_d = today_str
        end_d = today_str
        period_label = f"Today ({today_str})"
    elif range_preset == "yesterday":
        yest = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
        start_d = yest
        end_d = yest
        period_label = f"Yesterday ({yest})"
    elif range_preset == "7d":
        start_d = (now.date() - timedelta(days=7)).strftime("%Y-%m-%d")
        end_d = today_str
        period_label = f"Last 7 Days ({start_d} to {end_d})"
    elif range_preset == "30d":
        start_d = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_d = today_str
        period_label = f"Last 30 Days ({start_d} to {end_d})"
    elif range_preset == "90d":
        start_d = (now.date() - timedelta(days=90)).strftime("%Y-%m-%d")
        end_d = today_str
        period_label = f"Last 90 Days Archive ({start_d} to {end_d})"
    elif range_preset == "custom" and start_date and end_date:
        start_d = start_date
        end_d = end_date
        period_label = f"Period ({start_d} to {end_d})"
    else:
        start_d = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_d = today_str
        period_label = f"Last 30 Days ({start_d} to {end_d})"

    analytics = database.get_customer_usage_analytics(customer_id, start_d, end_d)
    if not analytics:
        raise HTTPException(status_code=404, detail="Customer not found")

    cust = analytics["customer"]
    summ = analytics["summary"]
    devs = analytics.get("device_breakdown", [])

    lines = [
        "🌐 *CyberNet Internet Usage Verification*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"👤 *Subscriber:* {cust.get('name')}",
        f"📱 *Account ID:* #{cust.get('id')} | Phone: {cust.get('phone')}",
        f"📅 *Audited Period:* {period_label}",
        f"⚡ *Package:* {cust.get('package_name', 'Active Plan')}",
        "",
        "📊 *Total Data Transferred:*",
        f"  • 📥 Download: {summ.get('formatted_down')}",
        f"  • 📤 Upload: {summ.get('formatted_up')}",
        f"  • 🌐 Total Consumed: {summ.get('formatted_total')} (Daily Avg: {summ.get('formatted_daily_avg')})",
        f"  • ⏱️ Online Active Time: {summ.get('formatted_active_time')}",
        ""
    ]

    if devs:
        lines.append("📱 *Consumption by Authorized Device:*")
        for d in devs[:5]:
            lines.append(f"  • {d.get('friendly_name')} ({d.get('mac_address')}): {d.get('formatted_total')} ({d.get('share_percent')}%)")
        lines.append("")

    peak_h = summ.get("peak_hour", {})
    peak_d = summ.get("peak_day", {})
    lines.append("⏰ *Peak Bandwidth Activity:*")
    lines.append(f"  • Busiest Hour: {peak_h.get('label')} ({peak_h.get('formatted_total')} transferred)")
    lines.append(f"  • Highest Day: {peak_d.get('formatted_name')} ({peak_d.get('formatted_total')} transferred)")
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("ℹ️ *Audit Guarantee:* All traffic counters and connection timestamps are recorded directly by the MikroTik hardware gateway.")

    text_msg = "\n".join(lines)
    return {
        "success": True,
        "phone": cust.get("phone", ""),
        "message": text_msg
    }


@app.post("/api/traffic/clear")
async def api_clear_traffic_history(request: Request):
    """Admin endpoint to clear historical traffic entries to start testing with fresh real data."""
    session_id = request.cookies.get(auth_service.COOKIE_NAME)
    user = auth_service.validate_session(session_id)
    if not user or user.get("role") not in ("superadmin", "admin", "manager"):
        raise HTTPException(status_code=403, detail="Permission denied")
    global _PREV_ROUTER_COUNTERS
    _PREV_ROUTER_COUNTERS.clear()
    res = database.clear_all_traffic_history()
    return {
        "success": True,
        "message": "All traffic entries cleared. System is now recording fresh live MikroTik traffic.",
        "details": res
    }


@app.post("/api/customers")
async def create_new_customer(payload: CreateCustomerPayload):
    """Manually registers a customer and optionally binds their MAC on MikroTik."""
    logger.info(f"Creating new customer: {payload.name} ({payload.phone})")
    if payload.mac_address and payload.mac_address.strip():
        if database.is_randomized_mac(payload.mac_address):
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"Randomized MAC address '{payload.mac_address}' is not permitted. CyberNet strictly requires physical Device MAC."
                }
            )

    try:
        cust = database.create_customer(
            phone=payload.phone,
            name=payload.name,
            billing_type=payload.billing_type,
            package_name=payload.package_name,
            monthly_fee=payload.monthly_fee,
            due_date=payload.due_date,
            due_day=payload.due_day,
            mac_address=payload.mac_address,
            max_devices=payload.max_devices,
            speed_limit=payload.speed_limit,
            initial_payment=payload.initial_payment or 0.0,
            advance_mode=payload.advance_mode or "credit",
            reseller_id=payload.reseller_id,
            join_date=payload.join_date,
            billing_start_date=payload.billing_start_date,
            notes=payload.notes
        )

        mt_ok = True
        if payload.mac_address and payload.mac_address.strip():
            packages = database.get_packages()
            pkg_match = next((p for p in packages if p["name"] == payload.package_name), None)
            default_rate = pkg_match["rate_limit"] if pkg_match else None
            effective_rate = payload.speed_limit if (payload.speed_limit and payload.speed_limit.strip()) else default_rate

            notes_str = f" [{cust['notes'].strip()}]" if cust.get("notes") and cust["notes"].strip() else ""
            comment = f"CyberNet: {cust['phone']} - {cust['name']}{notes_str} ({cust['billing_type'].upper()})"
            mt_ok = router_client.bind_device(
                mac_address=payload.mac_address,
                comment=comment,
                rate_limit=effective_rate
            )

        return {
            "success": True,
            "message": f"Customer '{payload.name}' registered successfully.",
            "customer": cust,
            "mikrotik_synced": mt_ok
        }
    except Exception as e:
        logger.exception(f"Error creating customer: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.post("/api/customers/{customer_id}/edit")
async def edit_customer_details(customer_id: int, payload: EditCustomerPayload):
    """
    Manually edits customer parameters from Customer Directory:
    Monthly fee, payment due date, custom speed limit, speed package, billing type, device limit, reseller.
    Immediately synchronizes the new speed limit to MikroTik for all the customer's active devices!
    """
    logger.info(f"Admin editing customer #{customer_id} with payload: {payload}")
    try:
        updated = database.update_customer_details(
            customer_id=customer_id,
            name=payload.name,
            phone=payload.phone,
            billing_type=payload.billing_type,
            package_name=payload.package_name,
            monthly_fee=payload.monthly_fee,
            due_date=payload.due_date,
            speed_limit=payload.speed_limit,
            max_devices=payload.max_devices,
            status=payload.status,
            credit_balance=payload.credit_balance,
            reseller_id=payload.reseller_id,
            billing_start_date=payload.billing_start_date,
            join_date=payload.join_date,
            suspension_held_until=payload.suspension_held_until,
            suspension_hold_reason=payload.suspension_hold_reason,
            notes=payload.notes
        )
        if not updated:
            return JSONResponse(status_code=404, content={"success": False, "message": "Customer not found."})

        # Sync updated speed to MikroTik for all approved devices of this customer
        effective_speed = updated.get("effective_speed")
        devices = updated.get("devices", [])
        notes_str = f" [{updated['notes'].strip()}]" if updated.get("notes") and updated["notes"].strip() else ""
        comment_str = f"CyberNet: {updated['phone']} - {updated['name']}{notes_str} ({updated['billing_type']})"

        fleet_res = mikrotik_client.broadcast_sync_customer_devices_speed(
            devices=devices,
            rate_limit=effective_speed,
            comment=comment_str
        )
        mt_ok = any(fleet_res.values()) if fleet_res else False

        return {
            "success": True,
            "message": f"Customer '{updated['name']}' updated and speed synced across MikroTik fleet!",
            "customer": updated,
            "mikrotik_synced": mt_ok,
            "fleet_results": fleet_res
        }
    except Exception as e:
        logger.exception(f"Error editing customer #{customer_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/customers/{customer_id}/toggle-status")
async def toggle_customer_status(customer_id: int):
    """
    Toggles customer between active and suspended.
    If suspended, immediately drops all active connections and bindings from MikroTik fleet.
    If activated, restores bypassed bindings on MikroTik fleet.
    """
    logger.info(f"Toggling status for customer #{customer_id}")
    try:
        new_status, macs = database.toggle_customer_status(customer_id)
        cust = database.get_customer_profile(customer_id)

        if new_status == "suspended":
            for mac in macs:
                mikrotik_client.broadcast_unbind_device(mac)
            logger.info(f"Customer #{customer_id} suspended. Unbound {len(macs)} MACs from MikroTik fleet.")
        else:
            pkg_name = cust.get("package_name") if cust else ""
            packages = database.get_packages()
            pkg_match = next((p for p in packages if p["name"] == pkg_name), None)
            rate_limit = cust.get("speed_limit") or (pkg_match["rate_limit"] if pkg_match else None)
            cust_devices = cust.get("devices", []) if cust else []
            dev_map = {d["mac_address"]: d.get("ip_address") for d in cust_devices if "mac_address" in d}

            notes_str = f" [{cust.get('notes', '').strip()}]" if cust and cust.get("notes") and cust.get("notes").strip() else ""
            for mac in macs:
                comment = f"CyberNet: {cust.get('phone')} - {cust.get('name')}{notes_str} (Restored)"
                mikrotik_client.broadcast_bind_device(
                    mac_address=mac,
                    ip_address=dev_map.get(mac),
                    comment=comment,
                    rate_limit=rate_limit
                )
            logger.info(f"Customer #{customer_id} activated. Rebound {len(macs)} MACs to MikroTik fleet.")

        return {
            "success": True,
            "new_status": new_status,
            "macs_affected": macs,
            "message": f"Customer is now {new_status.upper()} across MikroTik fleet."
        }
    except Exception as e:
        logger.exception(f"Error toggling customer #{customer_id} status: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/customers/enforce-expirations")
async def enforce_expirations_endpoint():
    """
    Manually triggers customer expiration audit and cuts connections for any expired accounts across MikroTik fleet.
    """
    logger.info("Manual expiration enforcement audit triggered.")
    try:
        expired_customers = await asyncio.to_thread(database.check_and_enforce_customer_expirations)
        total_cut = 0
        for cust in expired_customers:
            for mac in cust.get("macs", []):
                try:
                    mikrotik_client.broadcast_unbind_device(mac)
                    total_cut += 1
                except Exception as mt_err:
                    logger.error(f"Error unbinding expired MAC {mac}: {mt_err}")

        return {
            "success": True,
            "expired_customers_count": len(expired_customers),
            "devices_cut_count": total_cut,
            "expired_customers": expired_customers,
            "message": f"Expiration audit complete: {len(expired_customers)} customer(s) expired, {total_cut} device(s) cut across MikroTik fleet."
        }
    except Exception as e:
        logger.exception(f"Error in manual expiration enforcement: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/customers/{customer_id}/devices")
async def add_device(customer_id: int, payload: AddDevicePayload):
    """Adds a new MAC device to customer and authorizes it across MikroTik fleet."""
    logger.info(f"Adding device {payload.mac} to customer #{customer_id}")
    if database.is_randomized_mac(payload.mac):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": f"Randomized MAC address '{payload.mac}' is not permitted. CyberNet strictly requires physical Device MAC."
            }
        )

    try:
        dev = database.add_customer_device(
            customer_id=customer_id,
            mac_address=payload.mac,
            device_name=payload.device_name or "Secondary Device"
        )
        cust = database.get_customer_profile(customer_id)

        pkg_name = cust.get("package_name") if cust else ""
        packages = database.get_packages()
        pkg_match = next((p for p in packages if p["name"] == pkg_name), None)
        rate_limit = cust.get("speed_limit") or (pkg_match["rate_limit"] if pkg_match else None)

        comment = f"CyberNet: {cust.get('phone', '')} - {cust.get('name', '')} ({payload.device_name})"
        fleet_res = mikrotik_client.broadcast_bind_device(
            mac_address=payload.mac,
            comment=comment,
            rate_limit=rate_limit
        )
        mt_ok = any(fleet_res.values()) if fleet_res else False

        return {
            "success": True,
            "message": f"Device {payload.mac} added and authorized across fleet.",
            "device": dev,
            "mikrotik_synced": mt_ok,
            "fleet_results": fleet_res
        }
    except Exception as e:
        logger.exception(f"Error adding device to customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.delete("/api/customers/{customer_id}/devices/{device_id}")
async def remove_device(customer_id: int, device_id: int):
    """Removes a device from customer and revokes it immediately from MikroTik fleet."""
    logger.info(f"Removing device #{device_id} from customer #{customer_id}")
    try:
        mac, ip = database.remove_customer_device(device_id)
        if not mac:
            raise HTTPException(status_code=404, detail="Device not found")

        fleet_res = mikrotik_client.broadcast_unbind_device(mac, ip_address=ip)
        mt_ok = any(fleet_res.values()) if fleet_res else False
        return {
            "success": True,
            "message": f"Device {mac} removed and revoked from MikroTik fleet.",
            "mac": mac,
            "mikrotik_synced": mt_ok,
            "fleet_results": fleet_res
        }
    except Exception as e:
        logger.exception(f"Error removing device #{device_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.delete("/api/customers/{customer_id}")
@app.post("/api/customers/{customer_id}/delete")
async def delete_customer_endpoint(customer_id: int):
    """
    Permanently deletes a customer, wipes their devices and collections,
    and removes all associated bindings, queues, and active sessions from MikroTik fleet.
    """
    logger.warning(f"Initiating permanent deletion for customer #{customer_id}")
    try:
        success, macs, name, phone = database.delete_customer_permanently(customer_id)
        if not success:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Clean up MikroTik bindings, hosts, queues, and active connections across fleet
        unbound_count = 0
        for mac in macs:
            try:
                mikrotik_client.broadcast_unbind_device(mac)
                unbound_count += 1
            except Exception as mt_err:
                logger.error(f"Error unbinding device {mac} during customer #{customer_id} deletion: {mt_err}")

        logger.info(f"Customer #{customer_id} ({name} - {phone}) permanently deleted. Unbound {unbound_count}/{len(macs)} devices from MikroTik fleet.")

        return {
            "success": True,
            "message": f"Subscriber '{name}' ({phone}) permanently deleted. {unbound_count} device(s) revoked from MikroTik fleet.",
            "customer_id": customer_id,
            "unbound_macs": macs
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to permanently delete customer #{customer_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/customers/{customer_id}/record-payment")
async def record_payment(customer_id: int, payload: RecordPaymentPayload):
    """Records a payment, extends expiry date, handles advance credit, and re-activates service on MikroTik."""
    logger.info(f"Recording payment for customer #{customer_id}: {payload.amount} SAR (mode: {payload.advance_mode})")
    try:
        result = database.record_customer_payment(
            customer_id=customer_id,
            amount=payload.amount,
            notes=payload.notes or "Manual Service Renewal",
            extend_days=payload.extend_days,
            advance_mode=payload.advance_mode or "credit"
        )

        # Ensure devices are active on MikroTik with appropriate speed limit & updated billing type in comment
        cust = database.get_customer_profile(customer_id)
        if cust and cust.get("devices"):
            btype_label = (cust.get("billing_type") or "PREPAID").upper()
            for d in cust["devices"]:
                if d.get("status") == "approved":
                    mikrotik_client.broadcast_bind_device(
                        mac_address=d["mac_address"],
                        ip_address=d.get("ip_address"),
                        comment=f"CyberNet: {cust.get('phone')} - {cust.get('name')} ({btype_label})",
                        rate_limit=cust.get("effective_speed")
                    )

        switch_msg = ""
        if result.get("switched"):
            switch_msg = f" Billing type auto-switched to {result['billing_type'].upper()}."

        msg = f"Payment of {payload.amount:.2f} SAR recorded.{switch_msg} Validity extended to {result['new_expiry_date']}."
        if result.get("new_credit_balance", 0) > 0:
            msg += f" Current Credit Balance: {result['new_credit_balance']:.2f} SAR."

        return {
            "success": True,
            "message": msg,
            **result
        }
    except Exception as e:
        logger.exception(f"Error recording payment for customer #{customer_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/customers/{customer_id}/apply-credit")
async def apply_credit(customer_id: int, payload: ApplyCreditPayload):
    """
    Applies existing customer credit balance to renew service/settle bill.
    Deducts from credit_balance and extends due date.
    Automatically sets/keeps customer as PREPAID.
    """
    logger.info(f"Applying credit for customer #{customer_id}: amount={payload.amount}, days={payload.extend_days}")
    try:
        result = database.apply_customer_credit(
            customer_id=customer_id,
            amount=payload.amount,
            extend_days=payload.extend_days
        )

        # Ensure devices are active on MikroTik
        cust = database.get_customer_profile(customer_id)
        if cust and cust.get("devices"):
            for d in cust["devices"]:
                if d.get("status") == "approved":
                    mikrotik_client.broadcast_bind_device(
                        mac_address=d["mac_address"],
                        ip_address=d.get("ip_address"),
                        comment=f"CyberNet: {cust.get('phone')} - {cust.get('name')} (PREPAID)",
                        rate_limit=cust.get("effective_speed")
                    )

        return {
            "success": True,
            "message": f"Successfully applied {result['applied_credit']:.2f} SAR from credit balance! Validity extended to {result['new_expiry_date']}. Remaining Credit: {result['remaining_credit']:.2f} SAR.",
            **result
        }
    except Exception as e:
        logger.exception(f"Error applying credit for customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.post("/api/customers/{customer_id}/device-limit")
async def update_device_limit(customer_id: int, payload: UpdateDeviceLimitPayload):
    """Updates the allowed maximum device limit for a customer."""
    logger.info(f"Updating device limit for customer #{customer_id} to {payload.max_devices}")
    try:
        success = database.update_customer_device_limit(customer_id, payload.max_devices)
        return {"success": success, "max_devices": payload.max_devices}
    except Exception as e:
        logger.exception(f"Error updating device limit: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =========================================================
# Dashboard & Financial Reports API Endpoints
# =========================================================

@app.get("/api/dashboard/metrics")
async def api_dashboard_metrics(month: Optional[str] = None):
    """Returns real-time dashboard metrics and online status in JSON."""
    live_status = router_client.get_live_status()
    online_macs = []
    if live_status.get("connected"):
        try:
            online_macs = router_client.get_online_mac_addresses()
        except Exception as e:
            logger.warning(f"Could not retrieve online MACs: {e}")
    metrics = database.get_dashboard_metrics(month_str=month, online_macs=online_macs)
    return JSONResponse({
        "success": True,
        "metrics": metrics,
        "router_connected": live_status.get("connected", False)
    })


@app.get("/api/reports/collections")
async def api_collections_report(start_date: str, end_date: str):
    """Generates custom date range collection report for financial auditing and export."""
    if not start_date or not end_date:
        raise HTTPException(status_code=400, detail="start_date and end_date required")
    report = database.get_date_range_report(start_date=start_date, end_date=end_date)
    return JSONResponse({"success": True, "report": report})


@app.post("/api/customers/{customer_id}/quick-collect")
async def api_quick_collect(customer_id: int, payload: RecordPaymentPayload):
    """1-click bill collection directly from dashboard priority queue."""
    try:
        res = database.record_customer_payment(
            customer_id=customer_id,
            amount=payload.amount,
            notes=payload.notes or "Direct Cycle Bill Collection",
            extend_days=payload.extend_days or 30,
            advance_mode=payload.advance_mode or "credit"
        )
        # Re-bind customer devices to ensure internet access is active
        cust_profile = database.get_customer_profile(customer_id)
        if cust_profile and cust_profile.get("status") == "active":
            for dev in cust_profile.get("devices", []):
                if dev.get("status") == "approved":
                    mikrotik_client.broadcast_bind_device(
                        mac_address=dev["mac_address"],
                        ip_address=dev.get("ip_address"),
                        comment=f"CyberNet: {cust_profile.get('phone')} ({cust_profile.get('name')})",
                        rate_limit=cust_profile.get("effective_speed")
                    )
        return {"success": True, "result": res}
    except Exception as e:
        logger.exception(f"Error recording quick collect for customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


# =========================================================
# Collection & Financial Ledger Modification Endpoints
# =========================================================

@app.get("/api/collections/{collection_id}")
async def get_collection_endpoint(collection_id: int):
    """Fetches details of a single collection transaction."""
    col = database.get_collection_by_id(collection_id)
    if not col:
        raise HTTPException(status_code=404, detail="Collection record not found")
    return {"success": True, "collection": col}


@app.put("/api/collections/{collection_id}")
@app.post("/api/collections/{collection_id}/edit")
async def update_collection_endpoint(collection_id: int, payload: UpdateCollectionPayload):
    """Updates amount, notes, timestamp, collector, or billing type of a collection record."""
    logger.info(f"Admin updating collection #{collection_id} with amount={payload.amount}, notes={payload.notes}")
    try:
        updated = database.update_collection(
            collection_id=collection_id,
            amount=payload.amount,
            notes=payload.notes or "",
            collected_at=payload.collected_at,
            collected_by=payload.collected_by,
            billing_type=payload.billing_type
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Collection record not found")
        return {
            "success": True,
            "message": f"Payment record #COL-{collection_id} updated successfully.",
            "collection": updated
        }
    except Exception as e:
        logger.exception(f"Error updating collection #{collection_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.delete("/api/collections/{collection_id}")
@app.post("/api/collections/{collection_id}/delete")
async def delete_collection_endpoint(collection_id: int):
    """Permanently deletes a collection entry from the financial ledger and balance sheet."""
    logger.info(f"Admin deleting collection record #{collection_id}")
    try:
        success, deleted = database.delete_collection(collection_id)
        if not success:
            raise HTTPException(status_code=404, detail="Collection record not found")
        return {
            "success": True,
            "message": f"Payment record #COL-{collection_id} deleted successfully.",
            "deleted": deleted
        }
    except Exception as e:
        logger.exception(f"Error deleting collection #{collection_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =========================================================
# Dedicated Balance Sheet & Ledger API Endpoints
# =========================================================

@app.get("/api/balance/history/{customer_id}")
async def api_balance_customer_history(customer_id: int, source: Optional[str] = None):
    """Returns detailed history, statement breakdown, and receipts for CyberNet customer."""
    try:
        data = database.get_balance_customer_history(customer_id=customer_id)
        return {"success": True, "data": data}
    except Exception as e:
        logger.exception(f"Error fetching balance history for #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.post("/api/balance/collect")
async def api_balance_collect(payload: BalanceCollectPayload, request: Request):
    """Records quick collection directly from the Balance Sheet ledger."""
    user = getattr(request.state, "user", None)
    admin_name = "Admin"
    if user:
        if isinstance(user, dict):
            admin_name = user.get("full_name") or user.get("username") or "Admin"
        else:
            admin_name = getattr(user, "full_name", None) or getattr(user, "username", None) or "Admin"
    collector = admin_name if admin_name != "Admin" else (payload.collector or "Admin")
    try:
        res = database.record_balance_collection(
            customer_id=payload.customer_id,
            amount=payload.amount,
            payment_type=payload.payment_type or "cash",
            collector=collector,
            notes=payload.notes or "",
            month_year=payload.month_year
        )
        # Re-bind customer devices on MikroTik to restore/guarantee active internet access
        try:
            cust_profile = database.get_customer_profile(payload.customer_id)
            if cust_profile and cust_profile.get("status") == "active":
                for dev in cust_profile.get("devices", []):
                    if dev.get("status") == "approved":
                        mikrotik_client.broadcast_bind_device(
                            mac_address=dev["mac_address"],
                            ip_address=dev.get("ip_address"),
                            comment=f"CyberNet: {cust_profile.get('phone')} - {cust_profile.get('name')} [{cust_profile.get('notes') or ''}]",
                            rate_limit=cust_profile.get("effective_speed")
                        )
        except Exception as me:
            logger.warning(f"Could not rebind device after balance collection for #{payload.customer_id}: {me}")

        return res
    except Exception as e:
        logger.exception(f"Error in api_balance_collect for #{payload.customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.post("/api/balance/send-reminder")
async def api_balance_send_reminder(payload: BalanceReminderPayload, request: Request):
    """
    Builds the authentic CyberNet account status reminder and sends via OpenWA
    or returns WhatsApp direct click URL.
    """
    try:
        hist = database.get_balance_customer_history(customer_id=payload.customer_id)
        cust = hist["customer"]
        metrics = hist["metrics"]

        cust_name = cust["name"]
        norm_phone = cust["norm_phone"] or database.normalize_saudi_phone_number(cust["mobile"])
        balance_val = metrics["balance"]
        owed_amount = abs(balance_val) if balance_val < 0 else 0.0
        start_date_str = cust["billing_start_date"]

        # Build message matching billing_reminder
        msg = f"📶 *CYBERNET ACCOUNT STATUS*\n"
        msg += f"Assalamu Alaikum {cust_name}!\n\n"
        if start_date_str:
            msg += f"📅 Connected since: {start_date_str}\n"

        if balance_val < 0:
            msg += f"⚠️ *Outstanding Balance: {owed_amount:.2f} SAR*\n\n"
            msg += f"💰 Please recharge to continue enjoying uninterrupted internet service.\n\n"
        elif balance_val > 0:
            msg += f"✅ *Your account has an advance credit of +{balance_val:.2f} SAR.*\n\n"
        else:
            msg += f"✅ *Your account is fully settled (0.00 SAR).* Thank you!\n\n"

        msg += f"💳 *Payment Accounts / طرق الدفع:*\n\n"
        msg += f"1️⃣ *Shajjad Khan:*\n"
        msg += f"📱 +966597595059 (STC Pay, Barq, AlinmaPay)\n"
        msg += f"🏦 Alinma Bank IBAN: `SA3305000068206538133000`\n\n"
        msg += f"2️⃣ *Riyad Hossain:*\n"
        msg += f"📱 +966552036454 (STC Pay, Barq)\n"
        msg += f"🏦 Alinma Bank IBAN: `SA5805000068207720354000`\n\n"
        msg += f"🎬 Free Movies: http://10.12.14.16:8082\n"
        msg += f"⚽ Live Football: http://10.12.14.16:8086\n\n"
        msg += f"📞 Support (24/7): 0597595059 / 0552036454\n"
        msg += f"Please recharge on time to avoid service interruption. 🙏"

        wa_web_url = f"https://wa.me/{norm_phone}?text={urllib.parse.quote(msg)}" if norm_phone else None

        sent_via_openwa = False
        error_msg = None
        if not payload.send_direct and norm_phone:
            try:
                import whatsapp_service
                success, err = whatsapp_service.send_whatsapp_raw(norm_phone, msg)
                if success:
                    sent_via_openwa = True
                else:
                    error_msg = err
            except Exception as wex:
                error_msg = str(wex)

        return {
            "success": True,
            "sent_via_openwa": sent_via_openwa,
            "whatsapp_url": wa_web_url,
            "phone": norm_phone,
            "customer_name": cust_name,
            "balance": balance_val,
            "message_text": msg,
            "error": error_msg
        }
    except Exception as e:
        logger.exception(f"Error in api_balance_send_reminder for #{payload.customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.get("/api/balance/export")
async def api_balance_export_csv(
    status: str = "all",
    q: Optional[str] = None,
    source: Optional[str] = None
):
    """Exports the CyberNet OS balance sheet ledger to CSV."""
    import csv, io
    data = database.get_balance_sheet_data(status_filter=status, search_query=q)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Customer ID", "Name", "Mobile", "Room/Notes",
        "Monthly Fee (SAR)", "Daily Rate (SAR)", "Since Date",
        "Billable Days", "Total Owed (SAR)", "Total Paid (SAR)",
        "Balance (SAR)", "Status"
    ])
    for idx, r in enumerate(data["rows"], start=1):
        writer.writerow([
            idx,
            r["id"],
            r["name"],
            r["mobile"],
            r["room"],
            f"{r['monthly_fee']:.2f}",
            f"{r['daily_rate']:.4f}",
            r["billing_start_date"],
            r["billable_days"],
            f"{r['total_owed']:.2f}",
            f"{r['total_paid']:.2f}",
            f"{r['balance']:.2f}",
            r["status"]
        ])
    csv_text = output.getvalue()
    filename = f"CyberNet_Balance_Sheet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )



# =========================================================
# Grace Period, Daily Accrual & Month Settlement API Endpoints
# =========================================================


@app.get("/api/customers/{customer_id}/billing-breakdown")
async def get_customer_billing_breakdown_endpoint(customer_id: int):
    """
    Returns complete month-by-month billing breakdown, unpaid cycles,
    active suspension hold (grace period) accrual, and settled history.
    """
    try:
        breakdown = database.get_customer_billing_breakdown(customer_id)
        return {"success": True, "breakdown": breakdown}
    except Exception as e:
        logger.exception(f"Error fetching billing breakdown for #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


@app.get("/api/customers/{customer_id}/unpaid")
async def get_customer_unpaid_endpoint(customer_id: int):
    """
    Returns unpaid billing cycles in billing_reminder format:
    [{ "month": "2026-09", "month_name": "September 2026", "due": 30.0, "fee": 30.0, "paid": 0.0 }]
    """
    try:
        data = database.get_customer_unpaid_months(customer_id)
        return JSONResponse(content=data)
    except Exception as e:
        logger.exception(f"Error fetching unpaid cycles for customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/get_unpaid.php")
async def get_unpaid_php_endpoint(cid: int = Query(...)):
    """PHP-compatible endpoint matching billing_reminder get_unpaid.php?cid=..."""
    try:
        data = database.get_customer_unpaid_months(cid)
        return JSONResponse(content=data)
    except Exception as e:
        logger.exception(f"Error fetching unpaid cycles (PHP compat) for customer #{cid}: {e}")
        return JSONResponse(status_code=400, content=[])


@app.post("/api/customers/{customer_id}/promise")
async def record_customer_promise_endpoint(customer_id: int, payload: RecordPromisePayload, request: Request):
    """
    Records a suspension grace hold.
    Prevents MikroTik auto-suspension while daily debt accrues continuously.
    """
    try:
        session_id = request.cookies.get(auth_service.COOKIE_NAME)
        user = auth_service.validate_session(session_id) if session_id else None
        session_user = user.get("username", "Admin") if user else "Admin"
        res = database.record_customer_promise(
            customer_id=customer_id,
            days=payload.days or 0,
            promise_date=payload.promise_date,
            note=payload.note or "",
            created_by=session_user
        )

        # Unblock and re-bind customer devices on MikroTik to guarantee active service
        cust = database.get_customer_profile(customer_id)
        if cust and cust.get("devices"):
            for dev in cust["devices"]:
                mac = dev.get("mac_address")
                if mac:
                    try:
                        mikrotik_client.broadcast_bind_device(
                            mac_address=mac,
                            ip_address=dev.get("ip_address"),
                            comment=f"CyberNet: {cust.get('phone')} ({cust.get('name')}) [Grace Hold]",
                            rate_limit=cust.get("effective_speed")
                        )
                    except Exception as me:
                        logger.warning(f"Could not bind MAC {mac} for grace customer #{customer_id}: {me}")

        return JSONResponse(content={
            "success": True,
            "message": f"Suspension hold active until {res['promise_date']}. Daily debt will continue accruing.",
            "data": res
        })
    except Exception as e:
        logger.exception(f"Error recording promise for customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


@app.post("/api/customers/{customer_id}/promise/cancel")
async def cancel_customer_promise_endpoint(customer_id: int):
    """
    Cancels an active suspension hold / promise.
    Reverts customer to normal due/expiry date status.
    If customer is expired, instantly cuts connection across MikroTik fleet.
    """
    try:
        res = database.cancel_customer_promise(customer_id)
        cust = database.get_customer_profile(customer_id)
        if cust:
            is_exp, reason, exp_date = database.is_customer_expired(cust)
            if is_exp:
                database.toggle_customer_status(customer_id)
                for dev in cust.get("devices", []):
                    try:
                        mikrotik_client.broadcast_unbind_device(dev["mac_address"])
                    except Exception:
                        pass
                logger.warning(f"Suspension hold cancelled for customer #{customer_id}. Customer is expired: Cut connection for {len(cust.get('devices', []))} device(s).")
        return JSONResponse(content={"success": True, "message": "Suspension hold cancelled successfully."})
    except Exception as e:
        logger.exception(f"Error cancelling promise for customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


@app.post("/api/customers/{customer_id}/settle-cycles")
async def settle_customer_cycles_endpoint(customer_id: int, payload: SettleCyclesPayload, request: Request):
    """
    Records month-by-month settlement.
    When a month is marked settle=True, the remaining difference is waived as a discount
    and that month is permanently marked is_settled=1 (solved).
    """
    try:
        session_id = request.cookies.get(auth_service.COOKIE_NAME)
        user = auth_service.validate_session(session_id) if session_id else None
        session_user = user.get("username", "Admin") if user else "Admin"
        items_dicts = [item.dict() for item in payload.items]

        res = database.settle_customer_cycles(
            customer_id=customer_id,
            settlement_items=items_dicts,
            collected_by=session_user,
            notes=payload.notes or ""
        )

        # Restore/ensure active bindings on MikroTik
        cust = database.get_customer_profile(customer_id)
        if cust and cust.get("devices"):
            for dev in cust["devices"]:
                mac = dev.get("mac_address")
                if mac:
                    try:
                        mikrotik_client.broadcast_bind_device(
                            mac_address=mac,
                            ip_address=dev.get("ip_address"),
                            comment=f"CyberNet: {cust.get('phone')} ({cust.get('name')})",
                            rate_limit=cust.get("effective_speed")
                        )
                    except Exception as me:
                        logger.warning(f"Could not bind MAC {mac} after settlement: {me}")

        # Dispatch WhatsApp receipt if requested
        if payload.send_whatsapp and cust and cust.get("phone"):
            try:
                wa_text = f"✅ *PAYMENT RECEIPT*\n\n"
                wa_text += f"Customer: {cust['name']}\n"
                wa_text += f"Collected Amount: {res['total_collected']:.2f} SAR\n"
                if res['total_waived'] > 0:
                    wa_text += f"Waived Discount: {res['total_waived']:.2f} SAR\n"
                if res.get("settled_months"):
                    wa_text += f"Settled Period(s): {', '.join(res['settled_months'])}\n"
                wa_text += f"Status: Active (Due: {cust.get('due_date') or 'Settled'})\n\n"
                wa_text += "Thank you for your business!"
                whatsapp_service.send_whatsapp_raw(cust["phone"], wa_text)
            except Exception as we:
                logger.warning(f"WhatsApp receipt failed: {we}")

        return JSONResponse(content={
            "success": True,
            "message": f"Settlement recorded: {res['total_collected']:.2f} SAR collected, {res['total_waived']:.2f} SAR waived.",
            "data": res
        })
    except Exception as e:
        logger.exception(f"Error settling cycles for customer #{customer_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "message": str(e)})


# =========================================================
# Step 4: Packages & Rate Limits API Endpoints
# =========================================================

@app.get("/api/packages")
async def list_packages(active_only: bool = False):
    """Returns list of packages with live subscriber counts."""
    return database.get_packages(active_only=active_only)


@app.get("/api/packages/{pkg_id}")
async def get_package_details(pkg_id: int):
    """Returns details for a single package."""
    pkg = database.get_package_by_id(pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@app.post("/api/packages")
async def create_new_package(payload: PackagePayload):
    """Creates a new speed package and optionally provisions it on MikroTik."""
    logger.info(f"Creating package: {payload.name}, Rate: {payload.rate_limit}, Price: {payload.price}")
    try:
        pkg = database.create_package(
            name=payload.name,
            price=payload.price,
            rate_limit=payload.rate_limit,
            package_type=payload.package_type or "hotspot",
            cost_price=payload.cost_price or 0.0,
            validity_days=payload.validity_days or 30,
            shared_users=payload.shared_users or 1,
            mikrotik_profile=payload.mikrotik_profile,
            description=payload.description or "",
            is_active=payload.is_active if payload.is_active is not None else 1
        )

        mt_ok = False
        if payload.sync_router:
            mt_ok = router_client.sync_package_profile(
                profile_name=pkg["mikrotik_profile"],
                rate_limit=pkg["rate_limit"],
                shared_users=pkg["shared_users"],
                package_type=pkg["type"]
            )

        return {
            "success": True,
            "message": f"Package '{payload.name}' created successfully.",
            "package": pkg,
            "mikrotik_synced": mt_ok
        }
    except Exception as e:
        logger.exception(f"Error creating package: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.put("/api/packages/{pkg_id}")
async def update_existing_package(pkg_id: int, payload: PackagePayload):
    """Updates an existing speed package and updates its MikroTik profile."""
    logger.info(f"Updating package #{pkg_id}: {payload.name}, Rate: {payload.rate_limit}")
    try:
        pkg = database.update_package(
            pkg_id=pkg_id,
            name=payload.name,
            price=payload.price,
            rate_limit=payload.rate_limit,
            package_type=payload.package_type or "hotspot",
            cost_price=payload.cost_price or 0.0,
            validity_days=payload.validity_days or 30,
            shared_users=payload.shared_users or 1,
            mikrotik_profile=payload.mikrotik_profile,
            description=payload.description or "",
            is_active=payload.is_active if payload.is_active is not None else 1
        )
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        mt_ok = False
        if payload.sync_router:
            mt_ok = router_client.sync_package_profile(
                profile_name=pkg["mikrotik_profile"],
                rate_limit=pkg["rate_limit"],
                shared_users=pkg["shared_users"],
                package_type=pkg["type"]
            )

        return {
            "success": True,
            "message": f"Package '{payload.name}' updated successfully.",
            "package": pkg,
            "mikrotik_synced": mt_ok
        }
    except Exception as e:
        logger.exception(f"Error updating package #{pkg_id}: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.delete("/api/packages/{pkg_id}")
async def delete_existing_package(pkg_id: int):
    """Deletes package if no active subscribers are using it."""
    logger.info(f"Attempting to delete package #{pkg_id}")
    try:
        success, msg, pkg = database.delete_package(pkg_id)
        if not success:
            return JSONResponse(status_code=400, content={"success": False, "message": msg})

        # Remove profile from MikroTik if present
        if pkg and pkg.get("mikrotik_profile"):
            router_client.delete_package_profile(
                profile_name=pkg["mikrotik_profile"],
                package_type=pkg.get("type", "hotspot")
            )

        return {"success": True, "message": msg}
    except Exception as e:
        logger.exception(f"Error deleting package #{pkg_id}: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/packages/{pkg_id}/sync-router")
async def sync_package_to_router(pkg_id: int):
    """Pushes and provisions package profile directly to the active MikroTik router."""
    pkg = database.get_package_by_id(pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    mt_ok = router_client.sync_package_profile(
        profile_name=pkg["mikrotik_profile"],
        rate_limit=pkg["rate_limit"],
        shared_users=pkg["shared_users"],
        package_type=pkg["type"]
    )

    if mt_ok:
        return {"success": True, "message": f"Profile '{pkg['mikrotik_profile']}' successfully synced to MikroTik."}
    else:
        return JSONResponse(status_code=500, content={"success": False, "message": "Failed to sync profile to MikroTik."})


@app.post("/api/packages/{pkg_id}/toggle-active")
async def toggle_package_active(pkg_id: int):
    """Toggles active state of a package."""
    try:
        success, new_state = database.toggle_package_active(pkg_id)
        return {"success": True, "is_active": new_state}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# =========================================================
# Step 5: OLT & Fiber PON API Endpoints
# =========================================================

@app.get("/api/olt/list")
async def api_get_all_olts():
    """Returns all registered OLTs with ONU counts."""
    return database.get_all_olts()


@app.get("/api/olt/{olt_id}/details")
async def api_get_olt_details(olt_id: int):
    """Returns OLT chassis telemetry and PON port utilization."""
    details = database.get_olt_details(olt_id)
    if not details:
        raise HTTPException(status_code=404, detail="OLT not found")
    return details


@app.get("/api/olt/{olt_id}/onus")
async def api_get_onus(olt_id: int, port: Optional[int] = None, filter: Optional[str] = "all"):
    """Returns optical ONUs/ONTs for an OLT."""
    return database.get_onus(olt_id=olt_id, pon_port=port, status_filter=filter)


@app.post("/api/olt/onus")
async def api_register_onu(payload: RegisterOnuPayload):
    """Registers and activates an ONU on a PON port."""
    try:
        onu = database.register_onu(
            olt_id=payload.olt_id,
            pon_port=payload.pon_port,
            serial_number=payload.serial_number,
            name=payload.name,
            customer_id=payload.customer_id,
            onu_model=payload.onu_model or "1GE+1FE+WiFi GPON ONT",
            mode=payload.mode or "Routing",
            vlan_id=payload.vlan_id or 100,
            mac_address=payload.mac_address
        )
        return {"success": True, "onu": onu}
    except Exception as e:
        logger.exception(f"Error registering ONU: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.put("/api/olt/onus/{onu_id}")
async def api_update_onu(onu_id: int, payload: UpdateOnuPayload):
    """Updates ONU settings or customer link."""
    try:
        updated = database.update_onu(
            onu_id=onu_id,
            name=payload.name,
            customer_id=payload.customer_id,
            vlan_id=payload.vlan_id,
            mode=payload.mode,
            status=payload.status
        )
        if not updated:
            raise HTTPException(status_code=404, detail="ONU not found")
        return {"success": True, "onu": updated}
    except Exception as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.delete("/api/olt/onus/{onu_id}")
async def api_delete_onu(onu_id: int):
    """Removes an ONU from inventory."""
    ok = database.delete_onu(onu_id)
    return {"success": ok}


@app.post("/api/olt/onus/{onu_id}/reboot")
async def api_reboot_onu(onu_id: int):
    """Simulates OMCI restart for an ONU."""
    res = database.reboot_onu(onu_id)
    return res


@app.post("/api/olt/create")
async def api_create_olt(payload: CreateOltPayload):
    """Adds a new OLT device."""
    try:
        olt = database.create_olt(
            name=payload.name,
            ip_address=payload.ip_address,
            brand=payload.brand or "VSOL",
            model=payload.model or "GPON-4P",
            pon_type=payload.pon_type or "GPON",
            pon_ports_count=payload.pon_ports_count or 4,
            uplink_ports_count=payload.uplink_ports_count or 4,
            port=payload.port or 161,
            snmp_community=payload.snmp_community or "public",
            notes=payload.notes
        )
        return {"success": True, "olt": olt}
    except Exception as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.put("/api/olt/onus/{onu_id}/name")
async def api_rename_onu(onu_id: int, payload: RenameOnuPayload):
    """Simple rename of an ONU."""
    updated = database.update_onu_name(onu_id, payload.name)
    if not updated:
        raise HTTPException(status_code=404, detail="ONU not found")
    return {"success": True, "onu": updated}


@app.get("/api/olt/{olt_id}/uptime-ledger")
async def api_get_uptime_ledger(olt_id: int):
    """Returns uptime and outage history ledger for an OLT."""
    return database.get_onu_uptime_ledger(olt_id=olt_id)


@app.get("/api/olt/{olt_id}/errors")
async def api_get_olt_errors(olt_id: int):
    """Returns active optical errors and alerts."""
    return database.get_olt_active_errors(olt_id=olt_id)


@app.post("/api/olt/sync-telemetry")
async def api_sync_olt_telemetry(payload: OltTelemetrySyncPayload):
    """
    Ingests live telemetry from background poller agent or manual sync.
    Updates ONUs, link states, optical errors, and uptime ledger.
    """
    try:
        res = database.sync_olt_live_telemetry(
            olt_id=payload.olt_id,
            onus_data=payload.onus,
            chassis_info=payload.chassis
        )
        return res
    except Exception as e:
        logger.exception(f"Error syncing OLT telemetry: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/olt/{olt_id}/sync")
async def api_trigger_olt_sync(olt_id: int):
    """
    Triggers an on-demand OLT sync.
    Returns latest telemetry stats, active errors, and ONU states.
    """
    try:
        # Write trigger timestamp file for any listening sync daemon
        trigger_path = "/home/tserver/isp_v2/olt_sync.trigger"
        try:
            with open(trigger_path, "w") as f:
                f.write(datetime.now().isoformat())
        except Exception:
            pass

        # Retrieve current live state from database
        olt = database.get_olt_details(olt_id)
        if not olt:
            raise HTTPException(status_code=404, detail="OLT not found")

        onus = database.get_onus(olt_id=olt_id)
        errors = database.get_olt_active_errors(olt_id=olt_id)

        online_count = sum(1 for o in onus if o.get("status") == "online")

        return {
            "success": True,
            "message": f"OLT Telemetry Synced: {online_count}/{len(onus)} ONUs online",
            "olt": olt,
            "total_onus": len(onus),
            "online_onus": online_count,
            "offline_onus": len(onus) - online_count,
            "active_errors_count": len(errors),
            "updated_at": olt.get("updated_at")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in api_trigger_olt_sync: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/api/olt/{olt_id}/telemetry")
async def api_get_olt_live_telemetry(olt_id: int):
    """
    Returns complete live telemetry snapshot for real-time GUI auto-refresh without page reloads.
    """
    olt = database.get_olt_details(olt_id)
    if not olt:
        raise HTTPException(status_code=404, detail="OLT not found")
    onus = database.get_onus(olt_id=olt_id)
    errors = database.get_olt_active_errors(olt_id=olt_id)
    ledger = database.get_onu_uptime_ledger(olt_id=olt_id)
    return {
        "olt": olt,
        "onus": onus,
        "errors": errors,
        "ledger": ledger[:20],
        "stats": {
            "total": len(onus),
            "online": sum(1 for o in onus if o.get("status") == "online"),
            "offline": sum(1 for o in onus if o.get("status") != "online"),
            "errors_count": len(errors)
        }
    }


# =========================================================
# WhatsApp Operations & Messaging Hub
# =========================================================

@app.api_route("/whatsapp", methods=["GET", "HEAD", "POST"], response_class=HTMLResponse)
async def whatsapp_hub_page(request: Request, filter: str = "all", search: str = ""):
    """Renders the comprehensive WhatsApp Operations & Messaging Hub."""
    live_status = router_client.get_live_status()
    pending_requests = database.get_pending_requests()
    wa_status = whatsapp_service.get_whatsapp_gateway_status()
    wa_settings = database.get_whatsapp_settings()
    is_night, quiet_desc = whatsapp_service.is_night_quiet_hours(
        wa_settings.get("quiet_hours_start", "22:00"),
        wa_settings.get("quiet_hours_end", "09:00")
    )
    logs = database.get_whatsapp_logs(limit=100, status_filter=filter, search=search)
    due_customers = database.get_due_customers_for_whatsapp()
    all_customers = database.get_customers()

    # Pre-calculated stats
    stats = {
        "total_logs": len(logs),
        "sent_count": sum(1 for l in logs if l.get("status") == "sent"),
        "blocked_count": sum(1 for l in logs if l.get("status") == "blocked_night"),
        "failed_count": sum(1 for l in logs if l.get("status") == "failed"),
        "simulated_count": sum(1 for l in logs if l.get("status") == "simulated"),
        "due_count": len(due_customers)
    }

    return templates.TemplateResponse(
        request=request,
        name="whatsapp.html",
        context={
            "router": live_status,
            "active_page": "whatsapp",
            "pending_count": len(pending_requests),
            "wa_status": wa_status,
            "wa_settings": wa_settings,
            "is_night": is_night,
            "quiet_desc": quiet_desc,
            "logs": logs,
            "current_filter": filter,
            "search": search,
            "due_customers": due_customers,
            "customers": all_customers,
            "stats": stats
        }
    )


@app.get("/api/whatsapp/status")
async def api_whatsapp_status():
    """Returns real-time session state of the OpenWA container."""
    status = whatsapp_service.get_whatsapp_gateway_status()
    return JSONResponse(status)


@app.post("/api/whatsapp/send")
async def api_whatsapp_send(req: WhatsAppSendRequest):
    """
    Dispatches a manual or automated WhatsApp message with safety guardrails.
    Checks quiet night hours to prevent waking customers unless explicitly overridden.
    """
    clean_p = whatsapp_service.format_phone(req.phone)
    if not clean_p:
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid phone number."})

    wa_settings = database.get_whatsapp_settings()
    quiet_enabled = wa_settings.get("quiet_hours_enabled", "1") == "1"
    is_night, quiet_desc = whatsapp_service.is_night_quiet_hours(
        wa_settings.get("quiet_hours_start", "22:00"),
        wa_settings.get("quiet_hours_end", "09:00")
    )

    # Resolve customer name if customer_id supplied
    resolved_name = None
    if req.customer_id:
        cust = database.get_customer_by_id(req.customer_id)
        if cust:
            resolved_name = cust.get("name")

    # Safety Guard: Night Quiet Hours protection
    if quiet_enabled and is_night and not req.force_night and not req.simulate:
        database.log_whatsapp_message(
            phone=clean_p,
            message_body=req.message,
            message_type=req.message_type or "manual",
            status="blocked_night",
            error_message=f"Dispatch blocked by Night Quiet Hours shield ({quiet_desc})",
            customer_id=req.customer_id,
            customer_name=resolved_name,
            sent_by="admin"
        )
        return JSONResponse(status_code=403, content={
            "success": False,
            "status": "blocked_night",
            "error": f"Night Quiet Hours Shield is ACTIVE: {quiet_desc}. Enable 'Confirm Night Send' if this is an authorized emergency."
        })

    # Simulation / Test mode
    if req.simulate:
        log_id = database.log_whatsapp_message(
            phone=clean_p,
            message_body=req.message,
            message_type=req.message_type or "manual",
            status="simulated",
            error_message=None,
            customer_id=req.customer_id,
            customer_name=resolved_name,
            sent_by="admin"
        )
        return {
            "success": True,
            "status": "simulated",
            "message": "Message preview simulated & logged. No WhatsApp network message dispatched.",
            "log_id": log_id
        }

    # Live dispatch via OpenWA container
    ok, err = whatsapp_service.send_whatsapp_raw(clean_p, req.message)
    status_str = "sent" if ok else "failed"

    log_id = database.log_whatsapp_message(
        phone=clean_p,
        message_body=req.message,
        message_type=req.message_type or "manual",
        status=status_str,
        error_message=err,
        customer_id=req.customer_id,
        customer_name=resolved_name,
        sent_by="admin"
    )

    if ok:
        return {"success": True, "status": "sent", "log_id": log_id, "phone": clean_p}
    else:
        return JSONResponse(status_code=502, content={
            "success": False,
            "status": "failed",
            "error": err or "Failed to dispatch via OpenWA container.",
            "log_id": log_id
        })


@app.post("/api/whatsapp/settings")
async def api_whatsapp_save_settings(req: WhatsAppSettingsRequest):
    """Updates WhatsApp configuration, quiet hours, and message templates."""
    updates = {}
    for k, v in req.dict().items():
        if v is not None:
            updates[k] = str(v)
    saved = database.update_whatsapp_settings(updates)
    return {"success": True, "settings": saved}


@app.get("/api/whatsapp/logs")
async def api_whatsapp_logs(limit: int = 100, filter: str = "all", search: str = ""):
    """Returns outbox dispatch ledger entries."""
    logs = database.get_whatsapp_logs(limit=limit, status_filter=filter, search=search)
    return logs


# =========================================================
# MikroTik Router Fleet Management Endpoints
# =========================================================

@app.get("/api/routers")
async def api_get_routers(active_only: bool = False):
    """Returns all registered MikroTik routers in the fleet."""
    routers = database.get_all_routers(active_only=active_only)
    return routers


@app.post("/api/routers")
async def api_create_router(payload: CreateRouterPayload):
    """Adds a new MikroTik hardware router to the fleet one-by-one."""
    logger.info(f"Adding new MikroTik router to fleet: {payload.name} ({payload.host}:{payload.port})")
    try:
        r = database.create_router(
            name=payload.name,
            host=payload.host,
            port=payload.port or 8728,
            username=payload.username or "admin",
            password=payload.password or "",
            vlan_id=payload.vlan_id or 10,
            ssid_name=payload.ssid_name,
            uplink_type=payload.uplink_type,
            is_active=payload.is_active if payload.is_active is not None else 1
        )

        sync_result = {}
        try:
            test_res = mikrotik_client.test_router_connection(
                host=payload.host,
                username=payload.username or "admin",
                password=payload.password or "",
                port=payload.port or 8728
            )
            if test_res.get("success"):
                database.update_router_telemetry(
                    router_id=r["id"],
                    identity=test_res.get("identity"),
                    model=test_res.get("model"),
                    ros_version=test_res.get("version"),
                    cpu_usage=test_res.get("cpu_usage"),
                    uptime=test_res.get("uptime"),
                    last_status="online"
                )
                # Auto-sync fleet devices & packages to this new router!
                sync_result = mikrotik_client.sync_all_to_new_router(r["id"])
            else:
                database.update_router_telemetry(
                    router_id=r["id"],
                    last_status="offline"
                )
        except Exception as te:
            logger.warning(f"Could not complete initial sync to new router {payload.host}: {te}")

        return {
            "success": True,
            "message": f"MikroTik '{payload.name}' added to fleet successfully!",
            "router": r,
            "sync": sync_result
        }
    except Exception as e:
        logger.exception(f"Error creating router: {e}")
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.get("/api/routers/{router_id}")
async def api_get_router(router_id: int):
    """Fetches details and live status for a specific router."""
    r = database.get_router_by_id(router_id)
    if not r:
        raise HTTPException(status_code=404, detail="Router not found")
    client = mikrotik_client.get_client_for_router(r)
    live = client.get_live_status()
    return {"router": r, "live": live}


@app.put("/api/routers/{router_id}")
async def api_update_router(router_id: int, payload: UpdateRouterPayload):
    """Updates router configuration and credentials."""
    logger.info(f"Updating router #{router_id}: {payload.name}")
    try:
        updated = database.update_router(
            router_id=router_id,
            name=payload.name,
            host=payload.host,
            port=payload.port or 8728,
            username=payload.username or "admin",
            password=payload.password,
            vlan_id=payload.vlan_id,
            ssid_name=payload.ssid_name,
            uplink_type=payload.uplink_type,
            is_active=payload.is_active
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Router not found")
        return {"success": True, "router": updated}
    except Exception as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})


@app.delete("/api/routers/{router_id}")
async def api_delete_router(router_id: int):
    """Deletes a router from the fleet."""
    ok = database.delete_router(router_id)
    return {"success": ok}


@app.post("/api/routers/test-connection")
async def api_test_router_connection(payload: TestRouterPayload):
    """Tests live connection to a MikroTik IP without saving."""
    res = mikrotik_client.test_router_connection(
        host=payload.host,
        username=payload.username or "admin",
        password=payload.password or "",
        port=payload.port or 8728
    )
    return res


@app.post("/api/routers/{router_id}/sync")
async def api_sync_fleet_router(router_id: int):
    """Manually broadcasts and syncs all approved subscribers and packages to this router."""
    res = mikrotik_client.sync_all_to_new_router(router_id)
    return res


@app.get("/api/routers/{router_id}/queues")
async def api_get_router_queues(router_id: int):
    """Fetches live simple queues (/queue/simple) with bandwidth limits and real-time rates from a router."""
    r = database.get_router_by_id(router_id)
    if not r:
        raise HTTPException(status_code=404, detail="Router not found")
    client = mikrotik_client.get_client_for_router(r)
    queues = client.get_simple_queues()
    return {
        "success": True,
        "router": r["name"],
        "router_id": router_id,
        "count": len(queues),
        "queues": queues
    }



# =========================================================
# Telemetry & Health Endpoints
# =========================================================

@app.get("/api/router/telemetry")
async def get_telemetry():
    """Returns live router metrics JSON for auto-polling frontend."""
    status = router_client.get_live_status()
    return JSONResponse(status)


@app.post("/api/router/ping")
async def trigger_ping():
    start = time.time()
    status = router_client.get_live_status()
    duration_ms = round((time.time() - start) * 1000, 1)
    return {
        "success": status.get("connected", False),
        "latency_ms": duration_ms,
        "checked_at": status.get("checked_at")
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "CyberNet OS v2", "port": 9911}


@app.get("/downloads/audit-pdf")
async def download_audit_pdf():
    pdf_path = Path("/home/tserver/isp_v2/UI_UX_ACCESSIBILITY_AUDIT_REPORT.pdf")
    if not pdf_path.exists():
        pdf_path = Path("UI_UX_ACCESSIBILITY_AUDIT_REPORT.pdf")
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Audit PDF not found")
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename="CyberNet_OS_v2_UI_UX_Audit_Report.pdf"
    )


@app.get("/downloads/audit-md")
async def download_audit_md():
    md_path = Path("/home/tserver/isp_v2/UI_UX_ACCESSIBILITY_AUDIT_REPORT.md")
    if not md_path.exists():
        md_path = Path("UI_UX_ACCESSIBILITY_AUDIT_REPORT.md")
    if not md_path.exists():
        raise HTTPException(status_code=404, detail="Audit MD not found")
    return FileResponse(
        str(md_path),
        media_type="text/markdown",
        filename="CyberNet_OS_v2_UI_UX_Audit_Report.md"
    )


@app.get("/downloads/{filename}")
async def download_any_file(filename: str):
    file_path = Path("/home/tserver/isp_v2") / filename
    if not file_path.exists():
        file_path = Path(filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    mimetype = "application/octet-stream"
    if filename.endswith(".pdf"):
        mimetype = "application/pdf"
    elif filename.endswith(".md"):
        mimetype = "text/markdown"
    elif filename.endswith(".txt"):
        mimetype = "text/plain"
    return FileResponse(
        str(file_path),
        media_type=mimetype,
        filename=filename
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9911, reload=False)
