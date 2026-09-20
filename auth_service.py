"""
Authentication and Session Security Engine for CyberNet OS v2.
Hardened with Scrypt KDF, constant-time comparisons, brute-force lockout,
cryptographic session tokens, and security audit logging.
"""

import hashlib
import secrets
import sqlite3
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import database

logger = logging.getLogger("cybernet_auth")

# Security Configuration
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
IP_RATE_LIMIT_MAX = 10
IP_RATE_LIMIT_WINDOW_MIN = 10
DEFAULT_SESSION_HOURS = 24
REMEMBER_ME_DAYS = 30
COOKIE_NAME = "cybernet_session"

# Pre-auth CSRF tokens cache (token -> expiry timestamp)
_LOGIN_CSRF_TOKENS: Dict[str, float] = {}


def hash_password(password: str) -> Tuple[str, str]:
    """
    Derives a hardened password hash using scrypt if available,
    otherwise falling back to PBKDF2-HMAC-SHA256 (120,000 rounds).
    Returns (prefixed_hash_hex, salt_hex).
    """
    salt = secrets.token_hex(16)
    if hasattr(hashlib, "scrypt"):
        try:
            key = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt.encode("utf-8"),
                n=16384,
                r=8,
                p=1,
                maxmem=32 * 1024 * 1024
            )
            return "scrypt$" + key.hex(), salt
        except Exception:
            pass

    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return "pbkdf2$" + key.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """
    Verifies a password against the stored hash using constant-time comparison
    to prevent timing attacks. Supports both scrypt and pbkdf2 schemes.
    """
    try:
        if stored_hash.startswith("scrypt$"):
            expected = stored_hash.split("$", 1)[1]
            if hasattr(hashlib, "scrypt"):
                try:
                    key = hashlib.scrypt(
                        password.encode("utf-8"),
                        salt=salt.encode("utf-8"),
                        n=16384,
                        r=8,
                        p=1,
                        maxmem=32 * 1024 * 1024
                    )
                    return secrets.compare_digest(key.hex(), expected)
                except Exception:
                    return False
            return False
        elif stored_hash.startswith("pbkdf2$"):
            expected = stored_hash.split("$", 1)[1]
            key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
            return secrets.compare_digest(key.hex(), expected)
        else:
            # Fallback for plain hex hashes
            if hasattr(hashlib, "scrypt"):
                try:
                    key = hashlib.scrypt(
                        password.encode("utf-8"),
                        salt=salt.encode("utf-8"),
                        n=16384,
                        r=8,
                        p=1,
                        maxmem=32 * 1024 * 1024
                    )
                    if secrets.compare_digest(key.hex(), stored_hash):
                        return True
                except Exception:
                    pass
            key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
            return secrets.compare_digest(key.hex(), stored_hash)
    except Exception as e:
        logger.error(f"Error during password verification: {e}")
        return False


def init_auth_schema():
    """Initializes authentication, session, and audit tables."""
    with database.get_db() as conn:
        cursor = conn.cursor()

        # 1. Admin Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            full_name TEXT NOT NULL DEFAULT 'Super Administrator',
            role TEXT NOT NULL DEFAULT 'superadmin',
            is_active INTEGER DEFAULT 1,
            is_default_password INTEGER DEFAULT 1,
            failed_attempts INTEGER DEFAULT 0,
            locked_until TEXT DEFAULT NULL,
            last_login TEXT DEFAULT NULL,
            last_ip TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # 2. Cryptographic Sessions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            csrf_token TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_activity TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES admin_users(id) ON DELETE CASCADE
        )
        """)

        # 3. Security Audit Ledger
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_auth_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            ip_address TEXT,
            event_type TEXT NOT NULL, -- 'login_success', 'login_failure', 'account_locked', 'logout', 'password_change', 'ip_throttled'
            details TEXT,
            user_agent TEXT,
            created_at TEXT NOT NULL
        )
        """)

        # Seed initial default admin if table is empty
        cursor.execute("SELECT COUNT(*) FROM admin_users")
        if cursor.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Default root credentials: username=admin, password=admin
            # Flagged with is_default_password=1 so the system encourages changing it
            p_hash, p_salt = hash_password("admin")
            cursor.execute("""
                INSERT INTO admin_users (
                    username, password_hash, salt, full_name, role,
                    is_active, is_default_password, created_at, updated_at
                )
                VALUES (?, ?, ?, 'System Administrator', 'superadmin', 1, 1, ?, ?)
            """, ("admin", p_hash, p_salt, now_str, now_str))
            logger.info("Initialized default administrator account (admin).")

        conn.commit()


def log_audit_event(
    username: Optional[str],
    ip_address: Optional[str],
    event_type: str,
    details: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """Logs a security-critical authentication event."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with database.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admin_auth_audit (username, ip_address, event_type, details, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, ip_address, event_type, details, user_agent, now_str))
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to write auth audit log: {e}")


def is_ip_rate_limited(ip_address: str) -> Tuple[bool, int]:
    """
    Checks if client IP has exceeded max failed attempts within the sliding window.
    Returns (is_limited, remaining_lockout_seconds).
    """
    if not ip_address or ip_address in ("127.0.0.1", "localhost", "::1"):
        return False, 0

    cutoff = (datetime.now() - timedelta(minutes=IP_RATE_LIMIT_WINDOW_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM admin_auth_audit
            WHERE ip_address = ? AND event_type = 'login_failure' AND created_at >= ?
        """, (ip_address, cutoff))
        fail_count = cursor.fetchone()[0]

        if fail_count >= IP_RATE_LIMIT_MAX:
            # Find time of latest failure
            cursor.execute("""
                SELECT created_at FROM admin_auth_audit
                WHERE ip_address = ? AND event_type = 'login_failure'
                ORDER BY id DESC LIMIT 1
            """, (ip_address,))
            row = cursor.fetchone()
            if row:
                last_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                diff = (last_time + timedelta(minutes=IP_RATE_LIMIT_WINDOW_MIN) - datetime.now()).total_seconds()
                if diff > 0:
                    return True, int(diff)
    return False, 0


def generate_login_csrf_token() -> str:
    """Generates a transient CSRF token for the login form valid for 15 minutes."""
    token = secrets.token_hex(24)
    now = time.time()
    # Clean up stale tokens
    to_del = [k for k, exp in _LOGIN_CSRF_TOKENS.items() if exp < now]
    for k in to_del:
        _LOGIN_CSRF_TOKENS.pop(k, None)
    _LOGIN_CSRF_TOKENS[token] = now + 900  # 15 minutes
    return token


def validate_login_csrf_token(token: str) -> bool:
    """Validates and consumes a single-use login CSRF token."""
    if not token:
        return False
    exp = _LOGIN_CSRF_TOKENS.pop(token, None)
    if exp and exp > time.time():
        return True
    return False


def authenticate_user(
    username: str,
    password: str,
    client_ip: str = "127.0.0.1",
    user_agent: str = ""
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Validates user credentials with full brute-force defense, lockout checking,
    and progressive response delay on failures.
    Returns (success, user_dict_or_none, message).
    """
    username = (username or "").strip()
    if not username or not password:
        return False, None, "Please enter both username and password."

    # 1. IP Rate Limiting Check
    ip_limited, ip_rem = is_ip_rate_limited(client_ip)
    if ip_limited:
        log_audit_event(username, client_ip, "ip_throttled", f"Too many failures from IP. Cooldown {ip_rem}s", user_agent)
        return False, None, f"Too many failed login attempts from this network. Try again in {ip_rem} seconds."

    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
        row = cursor.fetchone()

        if not row:
            # Constant-time dummy delay to prevent username enumeration timing attacks
            verify_password("dummy", "0" * 128, "0" * 32)
            time.sleep(0.4)
            log_audit_event(username, client_ip, "login_failure", "Unknown username", user_agent)
            return False, None, "Invalid username or password."

        user = dict(row)

        if not user.get("is_active", 1):
            log_audit_event(username, client_ip, "login_failure", "Account is deactivated", user_agent)
            return False, None, "This account is disabled. Contact system administrator."

        # 2. Check Account Lockout
        locked_until_str = user.get("locked_until")
        if locked_until_str:
            try:
                locked_until_dt = datetime.strptime(locked_until_str, "%Y-%m-%d %H:%M:%S")
                if now_dt < locked_until_dt:
                    seconds_left = int((locked_until_dt - now_dt).total_seconds())
                    mins = max(1, seconds_left // 60)
                    log_audit_event(username, client_ip, "login_failure", f"Attempt while account locked. {seconds_left}s left", user_agent)
                    return False, None, f"Account is temporarily locked due to failed attempts. Try again in {mins} minute(s)."
                else:
                    # Lock has expired, reset
                    cursor.execute("UPDATE admin_users SET locked_until = NULL, failed_attempts = 0 WHERE id = ?", (user["id"],))
                    conn.commit()
                    user["failed_attempts"] = 0
            except Exception:
                pass

        # 3. Verify Password
        is_valid = verify_password(password, user["password_hash"], user["salt"])

        if not is_valid:
            failed = user.get("failed_attempts", 0) + 1
            # Artificial progressive delay
            time.sleep(min(1.2, 0.3 * failed))

            if failed >= MAX_FAILED_ATTEMPTS:
                lock_time = (now_dt + timedelta(minutes=LOCKOUT_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("""
                    UPDATE admin_users SET failed_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?
                """, (failed, lock_time, now_str, user["id"]))
                conn.commit()
                log_audit_event(username, client_ip, "account_locked", f"Account locked for {LOCKOUT_MINUTES} mins after {failed} failures", user_agent)
                return False, None, f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes."
            else:
                cursor.execute("""
                    UPDATE admin_users SET failed_attempts = ?, updated_at = ? WHERE id = ?
                """, (failed, now_str, user["id"]))
                conn.commit()
                remaining = MAX_FAILED_ATTEMPTS - failed
                log_audit_event(username, client_ip, "login_failure", f"Failed attempt {failed}/{MAX_FAILED_ATTEMPTS}", user_agent)
                return False, None, f"Invalid username or password. ({remaining} attempts remaining before lockout)"

        # 4. Successful Authentication
        cursor.execute("""
            UPDATE admin_users SET
                failed_attempts = 0,
                locked_until = NULL,
                last_login = ?,
                last_ip = ?,
                updated_at = ?
            WHERE id = ?
        """, (now_str, client_ip, now_str, user["id"]))
        conn.commit()

        log_audit_event(username, client_ip, "login_success", "User authenticated successfully", user_agent)
        return True, user, "Success"


def create_session(
    user_id: int,
    client_ip: str = "127.0.0.1",
    user_agent: str = "",
    remember_me: bool = False
) -> Tuple[str, str]:
    """
    Generates a 256-bit cryptographically secure session ID and CSRF token.
    Persists session in database with expiration.
    Returns (session_id, csrf_token).
    """
    session_id = secrets.token_hex(32)
    csrf_token = secrets.token_hex(16)
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    if remember_me:
        exp_dt = now_dt + timedelta(days=REMEMBER_ME_DAYS)
    else:
        exp_dt = now_dt + timedelta(hours=DEFAULT_SESSION_HOURS)

    exp_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")

    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin_sessions (
                session_id, user_id, csrf_token, ip_address, user_agent,
                expires_at, created_at, last_activity, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (session_id, user_id, csrf_token, client_ip, user_agent[:255], exp_str, now_str, now_str))
        conn.commit()

    return session_id, csrf_token


def validate_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Validates session token, verifies expiration and active flag,
    and updates last activity timestamp.
    Returns combined user & session record or None.
    """
    if not session_id or len(session_id) < 32:
        return None

    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                s.session_id, s.csrf_token, s.expires_at, s.is_active as session_active,
                u.id as user_id, u.username, u.full_name, u.role, u.is_active as user_active,
                u.is_default_password, u.last_login
            FROM admin_sessions s
            JOIN admin_users u ON s.user_id = u.id
            WHERE s.session_id = ? AND s.is_active = 1
        """, (session_id,))
        row = cursor.fetchone()

        if not row:
            return None

        record = dict(row)

        if not record.get("user_active", 1) or not record.get("session_active", 1):
            return None

        # Check expiration
        exp_str = record.get("expires_at")
        try:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            if now_dt > exp_dt:
                cursor.execute("UPDATE admin_sessions SET is_active = 0 WHERE session_id = ?", (session_id,))
                conn.commit()
                return None
        except Exception:
            return None

        # Update activity timestamp (throttled)
        cursor.execute("UPDATE admin_sessions SET last_activity = ? WHERE session_id = ?", (now_str, session_id))
        conn.commit()

        return record


def revoke_session(session_id: str) -> bool:
    """Terminates an active session."""
    if not session_id:
        return False
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE admin_sessions SET is_active = 0 WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0


def revoke_all_user_sessions(user_id: int) -> bool:
    """Revokes all active sessions for a given user (e.g., after password change)."""
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE admin_sessions SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0


def change_password(
    user_id: int,
    current_password: str,
    new_password: str,
    client_ip: str = "127.0.0.1"
) -> Tuple[bool, str]:
    """
    Changes user password after validating the current password and ensuring
    new password meets security strength standards.
    """
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters long."

    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admin_users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "User not found."

        user = dict(row)
        if not verify_password(current_password, user["password_hash"], user["salt"]):
            return False, "Current password is incorrect."

        new_hash, new_salt = hash_password(new_password)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            UPDATE admin_users SET
                password_hash = ?,
                salt = ?,
                is_default_password = 0,
                updated_at = ?
            WHERE id = ?
        """, (new_hash, new_salt, now_str, user_id))
        conn.commit()

        log_audit_event(user["username"], client_ip, "password_change", "Password successfully changed", None)
        return True, "Password updated successfully."


def get_all_admins() -> List[Dict[str, Any]]:
    """Returns list of admin users for management."""
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, full_name, role, is_active, is_default_password, last_login, last_ip, created_at
            FROM admin_users ORDER BY id ASC
        """)
        return [dict(r) for r in cursor.fetchall()]


def get_recent_auth_logs(limit: int = 20) -> List[Dict[str, Any]]:
    """Returns recent security audit logs."""
    with database.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM admin_auth_audit ORDER BY id DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]
