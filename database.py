try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

"""
Database module for CyberNet OS v2.
Manages customers, devices, connection requests, and billing records using SQLite.
"""

import sqlite3
import os
import re
import calendar
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any

DB_PATH = os.getenv("DB_PATH", "/home/tserver/isp_v2/isp_v2.db")

def is_randomized_mac(mac: Optional[str]) -> bool:
    """
    Checks if a MAC address is locally administered (randomized / private MAC).
    Under IEEE 802 MAC standard:
    - Octet 0, Bit 0 (LSB): 0 = Unicast, 1 = Multicast.
    - Octet 0, Bit 1: 0 = Universally Administered Address (UAA, real factory hardware / Device MAC).
                      1 = Locally Administered Address (LAA, randomized / private MAC).
    For unicast MAC addresses, if the second hex digit of the first octet is
    2, 6, A, or E (case-insensitive), it is a locally administered (randomized) MAC.
    """
    if not mac:
        return False
    clean = re.sub(r'[^0-9A-Fa-f]', '', str(mac).strip())
    if len(clean) < 2:
        return False
    try:
        first_byte = int(clean[:2], 16)
        # Bit 1 (mask 0x02) indicates Locally Administered Address (LAA)
        return bool(first_byte & 0x02)
    except ValueError:
        return False

def normalize_mac(mac: Optional[str]) -> Optional[str]:
    """Formats a MAC string into standard uppercase colon-delimited notation (XX:XX:XX:XX:XX:XX)."""
    if not mac:
        return None
    clean = re.sub(r'[^0-9A-Fa-f]', '', str(mac).strip()).upper()
    if len(clean) != 12:
        return None
    return ":".join(clean[i:i+2] for i in range(0, 12, 2))

def validate_mac_address(mac: Optional[str], allow_random: bool = False) -> Tuple[bool, str, Optional[str]]:
    """
    Validates a MAC address:
    Returns (is_valid, error_message_or_description, normalized_mac).
    If allow_random is False and the MAC is randomized, returns is_valid=False.
    """
    if not mac or not str(mac).strip():
        return False, "MAC address is required.", None
    norm = normalize_mac(mac)
    if not norm:
        return False, "Invalid MAC address format. Expected 12 hexadecimal characters (e.g. 3C:38:24:0F:69:74).", None
    if not allow_random and is_randomized_mac(norm):
        return False, f"Randomized MAC address detected ({norm}). Only real physical Device MAC addresses are allowed on this network. Please disable Private Wi-Fi / Randomized MAC in your phone settings.", norm
    return True, "Valid Device MAC address.", norm

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    """Initializes the database schema."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Customers Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            billing_type TEXT NOT NULL, -- 'prepaid' or 'postpaid'
            package_name TEXT NOT NULL,
            monthly_fee REAL NOT NULL DEFAULT 0.0,
            collected_today REAL NOT NULL DEFAULT 0.0,
            due_day INTEGER NOT NULL DEFAULT 1,
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'active', -- 'active', 'suspended'
            expiry_date TEXT, -- YYYY-MM-DD for prepaid
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # Migration check for existing DB
        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN due_date TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN max_devices INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN speed_limit TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN credit_balance REAL NOT NULL DEFAULT 0.0")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN reseller_id INTEGER REFERENCES admin_users(id)")
        except Exception:
            pass

        # Migration: Suspension grace period & daily billing accrual
        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN billing_start_date TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN join_date TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN suspension_held_until TEXT")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN suspension_hold_reason TEXT")
        except Exception:
            pass

        # Backfill billing_start_date for existing customers
        try:
            cursor.execute("UPDATE customers SET billing_start_date = substr(created_at, 1, 10) WHERE billing_start_date IS NULL")
        except Exception:
            pass

        # Backfill join_date for existing customers
        try:
            cursor.execute("UPDATE customers SET join_date = COALESCE(billing_start_date, substr(created_at, 1, 10)) WHERE join_date IS NULL")
        except Exception:
            pass

        # Migration: Customer notes / room number identification
        try:
            cursor.execute("ALTER TABLE customers ADD COLUMN notes TEXT DEFAULT ''")
        except Exception:
            pass

        try:
            cursor.execute("ALTER TABLE connection_requests ADD COLUMN notes TEXT DEFAULT ''")
        except Exception:
            pass

        # Migration: PPPoE connection technology support
        customer_pppoe_cols = [
            ("connection_type", "TEXT NOT NULL DEFAULT 'hotspot'"),
            ("pppoe_username", "TEXT DEFAULT ''"),
            ("pppoe_password", "TEXT DEFAULT ''"),
            ("pppoe_profile", "TEXT DEFAULT ''"),
            ("pppoe_remote_ip", "TEXT DEFAULT ''")
        ]
        for col_name, col_type in customer_pppoe_cols:
            try:
                cursor.execute(f"ALTER TABLE customers ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        conn_req_pppoe_cols = [
            ("connection_type", "TEXT DEFAULT 'hotspot'"),
            ("pppoe_username", "TEXT DEFAULT ''"),
            ("pppoe_password", "TEXT DEFAULT ''")
        ]
        for col_name, col_type in conn_req_pppoe_cols:
            try:
                cursor.execute(f"ALTER TABLE connection_requests ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # 2. Customer Devices Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            mac_address TEXT UNIQUE NOT NULL,
            ip_address TEXT,
            device_name TEXT,
            status TEXT NOT NULL DEFAULT 'approved', -- 'approved', 'blocked'
            approved_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
        """)

        # 3. Connection Requests Table (Pending Popups)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS connection_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            mac_address TEXT NOT NULL,
            ip_address TEXT,
            device_model TEXT,
            status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
            customer_id INTEGER,
            is_secondary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # 4. Collections / Payment Ledger
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            billing_type TEXT NOT NULL,
            notes TEXT,
            collected_at TEXT NOT NULL,
            collected_by TEXT NOT NULL DEFAULT 'Admin',
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
        """)

        # Migration check for collections table
        collection_new_cols = [
            ("month_year", "TEXT"),
            ("is_settled", "INTEGER NOT NULL DEFAULT 0"),
            ("waived_amount", "REAL NOT NULL DEFAULT 0.0")
        ]
        for col_name, col_type in collection_new_cols:
            try:
                cursor.execute(f"ALTER TABLE collections ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # Backfill month_year for existing collection records
        try:
            cursor.execute("UPDATE collections SET month_year = substr(collected_at, 1, 7) WHERE month_year IS NULL AND collected_at IS NOT NULL")
        except Exception:
            pass

        # 4c. Customer Promises & Suspension Hold Ledger Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_promises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            month_year TEXT,
            days INTEGER NOT NULL DEFAULT 0,
            promise_date TEXT NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'fulfilled', 'cancelled', 'expired'
            created_by TEXT NOT NULL DEFAULT 'Admin',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
        """)

        # 4d. Customer Suspensions & Pause Ledger Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_suspensions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            suspended_at TEXT NOT NULL,
            resumed_at TEXT,
            reason TEXT DEFAULT 'Administration suspension',
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_suspensions_cust ON customer_suspensions(customer_id)")

        # 4b. Reseller Partner Wallet & Transaction Ledger
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reseller_wallet_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reseller_id INTEGER NOT NULL,
            type TEXT NOT NULL, -- 'topup', 'recharge_deduction', 'commission', 'adjustment'
            amount REAL NOT NULL,
            balance_before REAL NOT NULL,
            balance_after REAL NOT NULL,
            customer_id INTEGER NULL,
            description TEXT,
            created_by TEXT NOT NULL DEFAULT 'Admin',
            created_at TEXT NOT NULL,
            FOREIGN KEY (reseller_id) REFERENCES admin_users(id) ON DELETE CASCADE
        )
        """)

        # 5. Speed Packages Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            rate_limit TEXT NOT NULL,
            default_price REAL NOT NULL,
            description TEXT
        )
        """)

        # Migration check for packages table
        package_cols = [
            ("type", "TEXT NOT NULL DEFAULT 'hotspot'"),
            ("price", "REAL NOT NULL DEFAULT 0.0"),
            ("cost_price", "REAL NOT NULL DEFAULT 0.0"),
            ("validity_days", "INTEGER NOT NULL DEFAULT 30"),
            ("shared_users", "INTEGER NOT NULL DEFAULT 1"),
            ("mikrotik_profile", "TEXT"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT")
        ]
        for col_name, col_type in package_cols:
            try:
                cursor.execute(f"ALTER TABLE packages ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # Backfill price and mikrotik_profile for existing rows
        try:
            cursor.execute("UPDATE packages SET price = default_price WHERE price = 0.0 OR price IS NULL")
            cursor.execute("UPDATE packages SET validity_days = 30 WHERE validity_days IS NULL")
            cursor.execute("UPDATE packages SET shared_users = 1 WHERE shared_users IS NULL")
            cursor.execute("UPDATE packages SET is_active = 1 WHERE is_active IS NULL")
            cursor.execute("UPDATE packages SET type = 'hotspot' WHERE type IS NULL")
        except Exception:
            pass

        # Default standard packages
        cursor.execute("SELECT COUNT(*) FROM packages")
        if cursor.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            default_pkgs = [
                ("Starter (10 Mbps)", "10M/10M", 50.0, "Suitable for browsing and social media", "hotspot", 50.0, 0.0, 30, 1, "starter-10m", 1, now_str, now_str),
                ("Standard (20 Mbps)", "20M/20M", 75.0, "Fast streaming and daily use", "hotspot", 75.0, 0.0, 30, 2, "standard-20m", 1, now_str, now_str),
                ("Ultra (50 Mbps)", "50M/50M", 100.0, "High speed 4K streaming and gaming", "hotspot", 100.0, 0.0, 30, 5, "ultra-50m", 1, now_str, now_str),
                ("VIP (100 Mbps)", "100M/100M", 150.0, "Unrestricted maximum speed", "hotspot", 150.0, 0.0, 30, 5, "vip-100m", 1, now_str, now_str),
                ("Unlimited (No Limit)", "0", 120.0, "Full unmetered wire speed without throttling", "hotspot", 120.0, 0.0, 30, 5, "unlimited-wire", 1, now_str, now_str)
            ]
        # 6. OLT (Optical Line Terminals) Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS olts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT 'GPON-4P',
            brand TEXT NOT NULL DEFAULT 'VSOL',
            ip_address TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 161,
            pon_type TEXT NOT NULL DEFAULT 'GPON', -- 'GPON', 'EPON', 'XGS-PON'
            pon_ports_count INTEGER NOT NULL DEFAULT 4,
            uplink_ports_count INTEGER NOT NULL DEFAULT 4,
            status TEXT NOT NULL DEFAULT 'online', -- 'online', 'offline', 'warning'
            uptime TEXT DEFAULT '18d 4h 12m',
            cpu_usage INTEGER DEFAULT 16,
            memory_usage INTEGER DEFAULT 38,
            temperature INTEGER DEFAULT 39,
            snmp_community TEXT DEFAULT 'public',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # 7. ONUs (Optical Network Units / Customer Fiber Terminals) Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS onus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            olt_id INTEGER NOT NULL,
            pon_port INTEGER NOT NULL DEFAULT 1,
            onu_id INTEGER NOT NULL DEFAULT 1,
            customer_id INTEGER,
            serial_number TEXT UNIQUE NOT NULL,
            mac_address TEXT,
            name TEXT NOT NULL,
            onu_model TEXT DEFAULT '1GE+1FE+WiFi GPON ONT',
            mode TEXT DEFAULT 'Routing', -- 'Routing', 'Bridge'
            status TEXT NOT NULL DEFAULT 'online', -- 'online', 'offline', 'los', 'power_off'
            rx_power REAL DEFAULT -19.4,
            tx_power REAL DEFAULT 2.1,
            distance_m INTEGER DEFAULT 840,
            vlan_id INTEGER DEFAULT 100,
            last_status_change TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (olt_id) REFERENCES olts(id) ON DELETE CASCADE,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        )
        """)

        # 8. Unconfigured Discovered ONUs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS unconfigured_onus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            olt_id INTEGER NOT NULL,
            pon_port INTEGER NOT NULL DEFAULT 1,
            serial_number TEXT NOT NULL,
            vendor TEXT DEFAULT 'Huawei',
            rx_power REAL DEFAULT -18.2,
            discovered_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unassigned',
            FOREIGN KEY (olt_id) REFERENCES olts(id) ON DELETE CASCADE
        )
        """)

        # Ensure default Core Hub OLT exists
        cursor.execute("SELECT COUNT(*) FROM olts")
        if cursor.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO olts (id, name, model, brand, ip_address, port, pon_type, pon_ports_count, uplink_ports_count, status, uptime, cpu_usage, memory_usage, temperature, snmp_community, notes, created_at, updated_at)
                VALUES (1, 'Core Hub OLT (VSOL 1-Port GPON)', 'V1600G-series', 'VSOL', '192.168.200.200', 161, 'GPON', 1, 3, 'online', '18d 4h 12m', 14, 38, 39, 'public', 'CyberNet Core GPON Plant on MikroTik ether4 (192.168.200.200:161)', ?, ?)
            """, (now_str, now_str))

        # Migration: Add uptime and error diagnostic columns to onus
        onu_cols = [
            ("uptime", "TEXT DEFAULT '18d 4h 12m'"),
            ("last_error", "TEXT DEFAULT 'None (Normal Operation)'"),
            ("error_severity", "TEXT DEFAULT 'normal'"),
            ("flaps_count", "INTEGER DEFAULT 0"),
            ("availability_pct", "REAL DEFAULT 99.8"),
            ("last_online_at", "TEXT"),
            ("last_offline_at", "TEXT")
        ]
        for col_name, col_type in onu_cols:
            try:
                cursor.execute(f"ALTER TABLE onus ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # 9. ONU Uptime & Outage Ledger Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS onu_uptime_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            onu_id INTEGER NOT NULL,
            event_type TEXT NOT NULL, -- 'online', 'offline', 'los', 'dying_gasp', 'warning', 'recovered'
            event_time TEXT NOT NULL,
            duration_str TEXT,
            reason TEXT NOT NULL,
            rx_power REAL,
            FOREIGN KEY (onu_id) REFERENCES onus(id) ON DELETE CASCADE
        )
        """)

        # 10. WhatsApp Outbox & Delivery Ledger Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            customer_name TEXT,
            phone TEXT NOT NULL,
            message_type TEXT NOT NULL, -- 'reminder', 'receipt', 'voucher', 'expiry', 'maintenance', 'manual'
            message_body TEXT NOT NULL,
            status TEXT NOT NULL, -- 'sent', 'failed', 'blocked_night', 'simulated'
            error_message TEXT,
            sent_by TEXT DEFAULT 'admin',
            created_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        )
        """)

        # 11. WhatsApp System Settings & Templates Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS whatsapp_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)

        # Seed default whatsapp settings if empty
        cursor.execute("SELECT COUNT(*) FROM whatsapp_settings")
        if cursor.fetchone()[0] == 0:
            default_wa_settings = [
                ("auto_dispatch_enabled", "0"),  # Default OFF: strict safety protection
                ("quiet_hours_enabled", "1"),
                ("quiet_hours_start", "22:00"),
                ("quiet_hours_end", "09:00"),
                ("support_phone", "0597595059"),
                ("movie_server", "http://10.12.14.16:8082"),
                ("football_server", "http://10.12.14.16:8080"),
                ("template_reminder", "📶 *CYBERNET ACCOUNT STATUS*\nAssalamu Alaikum *[NAME]*!\n\n📦 Plan: *[PACKAGE]*\n📅 Valid Until: *[EXPIRY_DATE]*\n💰 Due Balance: *[DUE_BALANCE] SAR*\n\nPlease recharge on time to prevent service interruption. 🙏\n\n🎬 Free Movies: [MOVIES]\n⚽ Live Football: [FOOTBALL]\n\n📞 Support (24/7): [HELPLINE]"),
                ("template_receipt", "✅ *CYBERNET PAYMENT RECEIPT*\n\nCustomer : *[NAME]*\nReceipt #: `[RECEIPT_NO]`\n\n💳 *Payment Details:*\n  • Amount Paid Today : *[AMOUNT] SAR*\n  • Plan              : [PACKAGE]\n  • Service Active To : *[EXPIRY_DATE]*\n\n✨ *Account Status:* Fully Paid & Settled ✅\n\n🎁 *Free for our customers:*\n  🎬 Movies: [MOVIES]\n  ⚽ Live Football: [FOOTBALL]\n\n📞 Support (24/7): [HELPLINE]\n\nThank you for your payment! 🙏"),
                ("template_voucher", "🌐 *CyberNet Internet Voucher*\n\nHello *[NAME]*,\nHere is your internet recharge PIN:\n\n🎟️ *Voucher PIN:* `[PIN]`\n📦 *Package:* [PACKAGE]\n💰 *Amount:* [AMOUNT] SAR\n\nTo activate, enter this PIN on the WiFi popup or visit:\nhttp://10.20.30.1:8088/hotspot/login\n\n🎬 Movies: [MOVIES]\n⚽ Live Football: [FOOTBALL]\n📞 Support: [HELPLINE]"),
                ("template_expiry", "⚠️ *CyberNet Service Alert*\n\nDear *[NAME]*,\nYour internet subscription expired on *[EXPIRY_DATE]*.\nTo restore your high-speed access immediately, please recharge your plan.\n\n💳 *Due Amount:* [DUE_BALANCE] SAR\n\nContact our team or visit http://10.20.30.1:8088/hotspot/login to recharge via voucher.\nSupport: [HELPLINE]"),
                ("template_maintenance", "🛠️ *CyberNet Maintenance Announcement*\n\nDear Subscribers,\nPlease be informed that scheduled optical network optimization will take place on *[EXPIRY_DATE]* for 30 minutes.\n\nWe apologize for any temporary inconvenience and appreciate your patience!\nSupport: [HELPLINE]")
            ]
            cursor.executemany("INSERT INTO whatsapp_settings (key, value) VALUES (?, ?)", default_wa_settings)

        # Seed initial sample audit logs if empty
        cursor.execute("SELECT COUNT(*) FROM whatsapp_logs")
        if cursor.fetchone()[0] == 0:
            now_dt = datetime.now()
            t_receipt = (now_dt - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")
            t_guard = (now_dt - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            sample_logs = [
                (2, "Shajjad Khan Ofc Phone", "966597595059", "receipt", "✅ *CYBERNET PAYMENT RECEIPT*\nCustomer: Shajjad Khan\nAmount Paid: 150.00 SAR\nPlan: VIP Gigabit Ultra 100M\nStatus: Settled", "sent", None, "admin", t_receipt),
                (5, "Advance Test Postpaid", "966599990001", "reminder", "📶 *CYBERNET ACCOUNT STATUS*\nDear Advance Test Postpaid, your plan is active.", "blocked_night", "Blocked: Dispatch attempted during night quiet hours (protection active)", "system_cron", t_guard)
            ]
            cursor.executemany("""
                INSERT INTO whatsapp_logs (customer_id, customer_name, phone, message_type, message_body, status, error_message, sent_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, sample_logs)

        # 12. MikroTik Gateway Fleet Management Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS routers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER DEFAULT 8728,
            username TEXT NOT NULL DEFAULT 'admin',
            password TEXT NOT NULL DEFAULT '',
            vlan_id INTEGER DEFAULT 10,
            ssid_name TEXT DEFAULT 'CyberNet-Line1',
            uplink_type TEXT DEFAULT 'Zain 5G SIM #1',
            is_active INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            identity TEXT,
            ros_version TEXT,
            model TEXT,
            cpu_usage INTEGER DEFAULT 0,
            memory_usage INTEGER DEFAULT 0,
            uptime TEXT,
            last_status TEXT DEFAULT 'unknown',
            last_seen TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        # Seed initial primary router if empty
        cursor.execute("SELECT COUNT(*) FROM routers")
        if cursor.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            default_host = os.getenv("MIKROTIK_HOST", "10.20.30.1")
            default_user = os.getenv("MIKROTIK_USER", "admin")
            default_pass = os.getenv("MIKROTIK_PASS", "admin")
            default_port = int(os.getenv("MIKROTIK_PORT", "8728"))
            cursor.execute("""
                INSERT INTO routers (
                    name, host, port, username, password, vlan_id, ssid_name, uplink_type,
                    is_active, is_default, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """, (
                "MikroTik 1 - Master Gateway (VLAN 10)",
                default_host,
                default_port,
                default_user,
                default_pass,
                10,
                "CyberNet-Line1",
                "Zain 5G SIM #1 (Primary)",
                now_str,
                now_str
            ))

        # 11. Customer Internet Traffic & 90-Day Bandwidth Accounting Tables
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_traffic_hourly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            mac_address TEXT NOT NULL,
            device_id INTEGER NULL,
            date_str TEXT NOT NULL, -- 'YYYY-MM-DD'
            hour_int INTEGER NOT NULL, -- 0..23
            download_bytes INTEGER NOT NULL DEFAULT 0,
            upload_bytes INTEGER NOT NULL DEFAULT 0,
            total_bytes INTEGER NOT NULL DEFAULT 0,
            active_seconds INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            UNIQUE(mac_address, date_str, hour_int)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tr_hourly_cust_date ON customer_traffic_hourly(customer_id, date_str)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tr_hourly_date ON customer_traffic_hourly(date_str)")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_traffic_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            mac_address TEXT NOT NULL,
            device_id INTEGER NULL,
            date_str TEXT NOT NULL, -- 'YYYY-MM-DD'
            download_bytes INTEGER NOT NULL DEFAULT 0,
            upload_bytes INTEGER NOT NULL DEFAULT 0,
            total_bytes INTEGER NOT NULL DEFAULT 0,
            active_seconds INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
            UNIQUE(mac_address, date_str)
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tr_daily_cust_date ON customer_traffic_daily(customer_id, date_str)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tr_daily_date ON customer_traffic_daily(date_str)")

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_connection_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            mac_address TEXT NOT NULL,
            device_name TEXT,
            ip_address TEXT,
            started_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            closed_at TEXT NULL,
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            download_bytes INTEGER NOT NULL DEFAULT 0,
            upload_bytes INTEGER NOT NULL DEFAULT 0,
            total_bytes INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tr_sess_cust ON customer_connection_sessions(customer_id, started_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tr_sess_mac_active ON customer_connection_sessions(mac_address, is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_customer_devices_cust_id ON customer_devices(customer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_customer_devices_mac ON customer_devices(mac_address)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_collections_cust_id ON collections(customer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conn_requests_mac ON connection_requests(mac_address)")

        conn.commit()


def get_packages(active_only: bool = False) -> List[Dict[str, Any]]:
    """Returns all speed packages with live subscriber counts."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                p.*,
                COALESCE(p.price, p.default_price) as display_price,
                COALESCE(sub_counts.sub_count, 0) as subscribers_count
            FROM packages p
            LEFT JOIN (
                SELECT package_name, COUNT(*) as sub_count
                FROM customers
                WHERE status = 'active'
                GROUP BY package_name
            ) sub_counts ON sub_counts.package_name = p.name
        """
        if active_only:
            query += " WHERE p.is_active = 1"
        query += " ORDER BY COALESCE(p.price, p.default_price) ASC"
        
        cursor.execute(query)
        pkgs = []
        for r in cursor.fetchall():
            item = dict(r)
            # Normalize unlimited badge flag
            rl = item.get("rate_limit", "")
            item["is_unlimited"] = not rl or str(rl).strip().lower() in ("0", "0m", "0k", "0/0", "0m/0m", "unlimited", "none", "")
            pkgs.append(item)
        return pkgs


def get_customer_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE phone = ?", (phone,))
        row = cursor.fetchone()
        return dict(row) if row else None



def is_customer_expired(cust: Optional[Dict[str, Any]], today_str: Optional[str] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Evaluates whether a customer's subscription is currently expired.
    Returns (is_expired: bool, reason: str, expiry_date_str: Optional[str]).
    Rules:
    1. If no customer record: return (False, "No record", None)
    2. Active grace hold (suspension_held_until >= today) ALWAYS protects customer from being cut.
    3. Expiry / Due date: if expiry_date < today (and not on active grace), customer is EXPIRED.
    4. Explicit 'suspended' status: customer is EXPIRED / CUT.
    5. All devices under an expired customer share the customer's expiry date; device join date doesn't matter.
    """
    if not cust:
        return (False, "No customer record", None)

    if not today_str:
        today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Grace Hold check (Promise to pay)
    susp_until = cust.get("suspension_held_until")
    if susp_until and str(susp_until).strip() >= today_str:
        return (False, f"Protected by active grace hold until {susp_until}", str(susp_until).strip())

    # 2. Expiry / Due date check
    raw_exp = cust.get("expiry_date") or cust.get("due_date")
    exp_date_str = None
    if raw_exp:
        try:
            exp_date_str = str(raw_exp).split()[0].strip()
            if len(exp_date_str) == 10 and exp_date_str[4] == '-' and exp_date_str[7] == '-':
                if exp_date_str < today_str:
                    return (True, f"Subscription expired on {exp_date_str}", exp_date_str)
        except Exception:
            pass

    # 3. Explicit suspended status check
    if cust.get("status") == "suspended":
        return (True, "Subscription is suspended", exp_date_str or raw_exp)

    return (False, f"Subscription active until {exp_date_str}" if exp_date_str else "Active", exp_date_str or raw_exp)


def check_and_enforce_customer_expirations() -> List[Dict[str, Any]]:
    """
    Audits customer subscriptions against current date.
    When a customer expires (expiry_date < today without active grace hold):
    - Sets customers.status = 'suspended'
    - Sets customer_devices.status = 'blocked'
    - Collects all device MAC addresses for immediate disconnection across MikroTik fleet.
    Returns list of expired customers and their MAC addresses.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today_str = now.strftime("%Y-%m-%d")

    expired_records = []

    with get_db() as conn:
        cursor = conn.cursor()

        # Query all customers who are either active OR have approved devices that must be cut
        cursor.execute("""
            SELECT id, name, phone, status, billing_type, package_name, expiry_date, due_date, suspension_held_until,
                   connection_type, pppoe_username
            FROM customers
            WHERE status = 'active'
               OR id IN (SELECT DISTINCT customer_id FROM customer_devices WHERE status = 'approved')
        """)
        candidates = [dict(r) for r in cursor.fetchall()]

        for cust in candidates:
            cid = cust["id"]
            is_exp, reason, exp_date = is_customer_expired(cust, today_str=today_str)
            if is_exp:
                # Find all devices for this customer
                cursor.execute("SELECT mac_address, status FROM customer_devices WHERE customer_id = ?", (cid,))
                dev_rows = cursor.fetchall()
                macs = [d["mac_address"].upper() for d in dev_rows if d["mac_address"]]
                has_approved_dev = any(d["status"] == "approved" for d in dev_rows)

                if cust["status"] == "active" or has_approved_dev:
                    cursor.execute("UPDATE customers SET status = 'suspended', updated_at = ? WHERE id = ?", (now_str, cid))
                    cursor.execute("UPDATE customer_devices SET status = 'blocked' WHERE customer_id = ?", (cid,))
                    cursor.execute("SELECT id FROM customer_suspensions WHERE customer_id = ? AND resumed_at IS NULL", (cid,))
                    if not cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO customer_suspensions (customer_id, suspended_at, reason, created_at)
                            VALUES (?, ?, 'Automated expiration cutoff', ?)
                        """, (cid, now_str, now_str))
                    expired_records.append({
                        "customer_id": cid,
                        "name": cust["name"],
                        "phone": cust["phone"],
                        "expiry_date": exp_date,
                        "reason": reason,
                        "macs": macs,
                        "connection_type": cust.get("connection_type") or "hotspot",
                        "pppoe_username": cust.get("pppoe_username") or ""
                    })

        conn.commit()

    return expired_records


def get_customer_by_mac(mac: str) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*, d.mac_address, d.status as device_status
            FROM customer_devices d
            JOIN customers c ON d.customer_id = c.id
            WHERE UPPER(d.mac_address) = UPPER(?) AND d.status = 'approved'
        """, (mac,))
        row = cursor.fetchone()
        if not row:
            return None
        cust = dict(row)
        is_exp, reason, exp_date = is_customer_expired(cust)
        cust["is_expired"] = is_exp
        cust["expiry_reason"] = reason
        if is_exp:
            cust["status"] = "expired"
        return cust



def create_or_update_request(phone: str, mac: str, ip: Optional[str], device_model: Optional[str]) -> Tuple[Dict[str, Any], bool, bool]:
    """
    Processes incoming hotspot submission from phone.
    Returns (request_dict, is_already_approved, is_secondary).
    Strictly forbids randomized MAC addresses (Device MAC required).
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mac_upper = mac.strip().upper()
    phone_clean = phone.strip()

    # Reject randomized MAC addresses
    if is_randomized_mac(mac_upper):
        raise ValueError(f"Randomized MAC address '{mac_upper}' detected. CyberNet requires physical Device MAC for connection.")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if MAC is already approved
        existing_device = get_customer_by_mac(mac_upper)
        if existing_device:
            is_exp, reason, exp_date = is_customer_expired(existing_device)
            if is_exp or existing_device.get("is_expired") or existing_device.get("status") == "expired":
                existing_device["status"] = "expired"
                existing_device["is_expired"] = True
                existing_device["expiry_date"] = exp_date or existing_device.get("expiry_date") or existing_device.get("due_date")
                return (existing_device, False, False)
            elif existing_device.get("status") == "active":
                return (existing_device, True, False)

        # Check if phone belongs to an existing customer
        existing_cust = get_customer_by_phone(phone_clean)
        is_secondary = 1 if existing_cust else 0
        customer_id = existing_cust["id"] if existing_cust else None

        # Filter out router-internal NAT IP
        clean_ip = ip if (ip and not ip.startswith("10.20.30.") and ip != "127.0.0.1") else None

        # Check for existing pending request with same MAC
        cursor.execute("SELECT id, ip_address, device_model FROM connection_requests WHERE UPPER(mac_address) = ? AND status = 'pending'", (mac_upper,))
        existing_req = cursor.fetchone()

        if existing_req:
            req_id = existing_req["id"]
            final_ip = clean_ip if clean_ip else existing_req["ip_address"]
            final_model = device_model if device_model else existing_req["device_model"]
            cursor.execute("""
                UPDATE connection_requests
                SET phone = ?, ip_address = ?, device_model = ?, customer_id = ?, is_secondary = ?, updated_at = ?
                WHERE id = ?
            """, (phone_clean, final_ip, final_model, customer_id, is_secondary, now, req_id))
        else:
            cursor.execute("""
                INSERT INTO connection_requests (phone, mac_address, ip_address, device_model, status, customer_id, is_secondary, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """, (phone_clean, mac_upper, clean_ip, device_model, customer_id, is_secondary, now, now))
            req_id = cursor.lastrowid

        conn.commit()

        cursor.execute("SELECT * FROM connection_requests WHERE id = ?", (req_id,))
        req = dict(cursor.fetchone())
        return (req, False, bool(is_secondary))


def get_request_status_by_mac_and_phone(mac: str, phone: str = "") -> Dict[str, Any]:
    mac_upper = mac.strip().upper()
    phone_clean = phone.strip() if phone else ""
    if is_randomized_mac(mac_upper):
        return {
            "status": "random_mac_blocked",
            "is_random_mac": True,
            "can_connect": False,
            "message": "Connection blocked: Randomized MAC detected. Please change Wi-Fi settings to 'Device MAC' to connect."
        }

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. First check if device MAC is approved directly
        cust = get_customer_by_mac(mac_upper)
        if cust:
            is_exp, reason, exp_date = is_customer_expired(cust)
            if is_exp or cust.get("is_expired") or cust.get("status") == "expired":
                exp_display = exp_date or cust.get("expiry_date") or cust.get("due_date") or "N/A"
                return {
                    "status": "expired",
                    "expiry_date": exp_display,
                    "phone": cust.get("phone"),
                    "name": cust.get("name"),
                    "message": f"Your internet subscription expired on {exp_display}. Please renew your plan to restore internet access."
                }
            if cust.get("status") == "active":
                return {"status": "approved", "message": f"Device authorized. Welcome {cust['name']}!"}

        # 2. Check if phone belongs to an existing customer who is expired
        if phone_clean:
            cust_by_phone = get_customer_by_phone(phone_clean)
            if cust_by_phone:
                is_exp, reason, exp_date = is_customer_expired(cust_by_phone)
                if is_exp or cust_by_phone.get("status") == "suspended":
                    exp_display = exp_date or cust_by_phone.get("expiry_date") or cust_by_phone.get("due_date") or "N/A"
                    return {
                        "status": "expired",
                        "expiry_date": exp_display,
                        "phone": cust_by_phone.get("phone"),
                        "name": cust_by_phone.get("name"),
                        "message": f"Subscriber account for {cust_by_phone.get('name')} expired on {exp_display}. Renewal required to connect new devices."
                    }

        # 3. Check latest connection request
        cursor.execute("""
            SELECT * FROM connection_requests
            WHERE UPPER(mac_address) = ?
            ORDER BY id DESC LIMIT 1
        """, (mac_upper,))
        row = cursor.fetchone()
        if not row:
            return {"status": "none", "message": "No pending request."}

        req = dict(row)
        if req["status"] == "approved":
            # If historical request says approved, but get_customer_by_mac was None or inactive,
            # this device was deleted from customer_devices or customer is suspended/deleted!
            return {
                "status": "revoked",
                "is_secondary": bool(req.get("is_secondary")),
                "message": "Device access has been revoked or removed. Please contact administrator."
            }

        return {
            "status": req["status"],
            "is_secondary": bool(req["is_secondary"]),
            "message": "Awaiting admin approval."
        }


def parse_clean_device_model(raw: Optional[str]) -> str:
    if not raw or not raw.strip():
        return "Mobile Client"
    raw_str = raw.strip()
    if not ("Mozilla/" in raw_str or "AppleWebKit" in raw_str or "Version/" in raw_str):
        return raw_str[:35]
    ua = raw_str
    if "iPhone" in ua:
        return "Apple iPhone"
    if "iPad" in ua:
        return "Apple iPad"
    if any(k in ua for k in ["Redmi Note 14", "24090RA29", "24094RAD4", "24115RA8E", "24116RN10", "24090RA28", "24108PCE4"]):
        return "Redmi Note 14"
    if "Redmi" in ua:
        m = re.search(r"Redmi[^\s;)]*", ua)
        return m.group(0) if m else "Xiaomi Redmi"
    if "POCO" in ua:
        m = re.search(r"POCO[^\s;)]*", ua)
        return m.group(0) if m else "Xiaomi POCO"
    if "Xiaomi" in ua:
        return "Xiaomi Phone"
    if "SM-S928" in ua:
        return "Samsung Galaxy S24 Ultra"
    if "SM-" in ua:
        m = re.search(r"SM-[A-Z0-9]+", ua)
        if m:
            return f"Samsung ({m.group(0)})"
        return "Samsung Galaxy"
    if "Android" in ua:
        m = re.search(r";\s*([^;]+?)\s*Build/", ua)
        if m:
            model = m.group(1).strip()
            if not model.lower().startswith("android"):
                return model[:30]
        return "Android Phone"
    if "Windows" in ua:
        return "Windows PC"
    if "Macintosh" in ua or "Mac OS" in ua:
        return "Apple Mac"
    if "Linux" in ua:
        return "Linux Device"
    return "Mobile Client"


def get_pending_requests() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, c.name as existing_customer_name, c.notes as existing_customer_notes, c.billing_type as existing_billing_type,
                   c.package_name as existing_package_name, c.expiry_date as existing_expiry_date,
                   c.due_date as existing_due_date, c.suspension_held_until as existing_suspension_held_until,
                   c.status as existing_customer_status, c.speed_limit as existing_speed_limit,
                   c.monthly_fee as existing_monthly_fee, c.max_devices as customer_max_devices,
                   (SELECT COUNT(*) FROM customer_devices cd WHERE cd.customer_id = c.id AND cd.status = 'approved') as current_device_count
            FROM connection_requests r
            LEFT JOIN customers c ON (r.customer_id = c.id OR (r.customer_id IS NULL AND r.phone = c.phone))
            WHERE r.status = 'pending'
            ORDER BY r.id DESC
        """)
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            r["is_random_mac"] = is_randomized_mac(r.get("mac_address", ""))
            r["device_model"] = parse_clean_device_model(r.get("device_model", ""))
            r["existing_customer_notes"] = r.get("existing_customer_notes") or r.get("notes") or ""
            if r.get("existing_customer_name") or r.get("customer_id"):
                r["is_secondary"] = 1
                cust_data = {
                    "status": r.get("existing_customer_status"),
                    "expiry_date": r.get("existing_expiry_date"),
                    "due_date": r.get("existing_due_date"),
                    "suspension_held_until": r.get("existing_suspension_held_until")
                }
                is_exp, reason, exp_str = is_customer_expired(cust_data)
                r["is_customer_expired"] = is_exp
                r["customer_expiry_reason"] = reason
                r["customer_expiry_date"] = exp_str or r.get("existing_expiry_date") or r.get("existing_due_date") or ""
            else:
                r["is_secondary"] = 0
                r["is_customer_expired"] = False
                r["customer_expiry_reason"] = ""
                r["customer_expiry_date"] = ""
        return rows


def get_approved_devices() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, c.phone, c.name as customer_name, c.billing_type, c.package_name, c.monthly_fee,
                   c.status as customer_status, c.expiry_date, c.max_devices, c.speed_limit, c.notes,
                   p.rate_limit as package_rate_limit,
                   COALESCE(NULLIF(c.speed_limit, ''), p.rate_limit) as effective_speed_limit
            FROM customer_devices d
            JOIN customers c ON d.customer_id = c.id
            LEFT JOIN packages p ON c.package_name = p.name
            WHERE d.status = 'approved' AND c.status = 'active'
            ORDER BY d.id DESC
        """)
        rows = [dict(row) for row in cursor.fetchall()]
        for r in rows:
            r["is_random_mac"] = is_randomized_mac(r.get("mac_address", ""))
        return rows


def get_request_by_id(req_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM connection_requests WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def approve_connection(
    req_id: int,
    name: str,
    billing_type: str = "prepaid",
    package_name: Optional[str] = None,
    monthly_fee: float = 0.0,
    collected_today: float = 0.0,
    due_day: int = 1,
    due_date: Optional[str] = None,
    max_devices: int = 1,
    speed_limit: Optional[str] = None,
    advance_mode: str = "credit",
    is_secondary: bool = False,
    join_date: Optional[str] = None,
    billing_start_date: Optional[str] = None,
    notes: Optional[str] = "",
    connection_type: str = "hotspot",
    pppoe_username: Optional[str] = None,
    pppoe_password: Optional[str] = None,
    pppoe_profile: Optional[str] = None,
    pppoe_remote_ip: Optional[str] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Approves a pending request:
    1. For existing active customers (secondary/extra devices):
       - DOES NOT reset or overwrite billing type, package, monthly fee, or due/expiry dates.
       - DOES NOT record false collections when no extra payment is collected.
       - Ensures customer remains active, auto-expands device limit if needed, and binds the device.
    2. For new customers (initial subscription setup):
       - Sets up billing type, package, fee, due date, payment collection, and binds the device.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    clean_collected = float(collected_today or 0.0)
    monthly_fee = float(monthly_fee or 0.0)
    clean_limit = max(1, int(max_devices or 1))
    clean_speed = speed_limit.strip() if speed_limit and speed_limit.strip() else None

    with get_db() as conn:
        cursor = conn.cursor()

        # Get request
        cursor.execute("SELECT * FROM connection_requests WHERE id = ?", (req_id,))
        req_row = cursor.fetchone()
        if not req_row:
            raise ValueError(f"Request #{req_id} not found.")
        req = dict(req_row)

        phone = req["phone"].strip()
        mac = req["mac_address"].upper()
        ip = req["ip_address"]

        # Enforce Device MAC - forbid approving randomized MACs
        if is_randomized_mac(mac):
            raise ValueError(f"Cannot approve connection for request #{req_id}: MAC '{mac}' is a randomized MAC address. Customer must connect using physical Device MAC.")

        # Check if customer already exists
        cursor.execute("SELECT * FROM customers WHERE phone = ?", (phone,))
        cust_row = cursor.fetchone()

        is_existing = cust_row is not None
        is_secondary_req = bool(is_secondary or req.get("is_secondary") or is_existing)

        if is_existing and is_secondary_req:
            # =========================================================================
            # CASE A: Existing Customer (Extra Device Authorization)
            # Billing is already done! Preserve all subscription parameters.
            # Expiration is customer-centric: devices inherit customer expiry date.
            # =========================================================================
            cust = dict(cust_row)
            customer_id = cust["id"]
            existing_max = int(cust.get("max_devices") or 1)

            # Check if customer is currently expired
            today_str = now.strftime("%Y-%m-%d")
            is_exp, exp_reason, exp_date = is_customer_expired(cust, today_str=today_str)

            # Count current approved devices
            cursor.execute("SELECT COUNT(*) FROM customer_devices WHERE customer_id = ? AND status = 'approved'", (customer_id,))
            current_dev_cnt = cursor.fetchone()[0] or 0

            # Ensure max_devices accommodates this device
            new_max_devices = max(existing_max, clean_limit)
            if current_dev_cnt >= new_max_devices:
                new_max_devices = current_dev_cnt + 1

            update_name = name.strip() if (name and not name.startswith("Customer 05")) else cust["name"]

            # Expiration and status resolution:
            # If admin passed an explicit future due_date, extend validity
            if due_date and str(due_date).split()[0] >= today_str:
                new_due_date = str(due_date).split()[0]
                cust_status = "active"
                dev_status = "approved"
                cursor.execute("""
                    UPDATE customers
                    SET name = ?, status = 'active', max_devices = ?, due_date = ?, expiry_date = ?, updated_at = ?
                    WHERE id = ?
                """, (update_name, new_max_devices, new_due_date, new_due_date, now_str, customer_id))
            elif is_exp and clean_collected == 0:
                # Expired customer and no payment collected: keep suspended/cut
                cust_status = "suspended"
                dev_status = "blocked"
                cursor.execute("""
                    UPDATE customers
                    SET name = ?, status = 'suspended', max_devices = ?, updated_at = ?
                    WHERE id = ?
                """, (update_name, new_max_devices, now_str, customer_id))
            else:
                cust_status = "active"
                dev_status = "approved"
                if clean_collected > 0:
                    existing_credit = float(cust.get("credit_balance") or 0.0)
                    new_credit = round(existing_credit + clean_collected, 2)
                    cursor.execute("""
                        UPDATE customers
                        SET name = ?, status = 'active', max_devices = ?, credit_balance = ?, updated_at = ?
                        WHERE id = ?
                    """, (update_name, new_max_devices, new_credit, now_str, customer_id))

                    cursor.execute("""
                        INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
                        VALUES (?, ?, ?, ?, ?, 'Admin')
                    """, (customer_id, clean_collected, cust.get("billing_type", "postpaid"), f"Additional device payment / credit deposit ({clean_collected:.2f} SAR)", now_str))
                else:
                    cursor.execute("""
                        UPDATE customers
                        SET name = ?, status = 'active', max_devices = ?, updated_at = ?
                        WHERE id = ?
                    """, (update_name, new_max_devices, now_str, customer_id))

            # Insert or update customer_devices
            cursor.execute("SELECT id FROM customer_devices WHERE UPPER(mac_address) = ?", (mac,))
            dev_row = cursor.fetchone()
            if dev_row:
                cursor.execute("""
                    UPDATE customer_devices
                    SET customer_id = ?, ip_address = ?, device_name = ?, status = ?, approved_at = ?
                    WHERE id = ?
                """, (customer_id, ip, req.get("device_model", "Mobile Phone"), dev_status, now_str, dev_row["id"]))
            else:
                cursor.execute("""
                    INSERT INTO customer_devices (customer_id, mac_address, ip_address, device_name, status, approved_at, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (customer_id, mac, ip, req.get("device_model", "Mobile Phone"), dev_status, now_str, now_str))

            if join_date and join_date.strip():
                cursor.execute("UPDATE customers SET join_date = ? WHERE id = ?", (join_date.strip(), customer_id))
            if billing_start_date and billing_start_date.strip():
                cursor.execute("UPDATE customers SET billing_start_date = ? WHERE id = ?", (billing_start_date.strip(), customer_id))
            if notes is not None and notes.strip():
                cursor.execute("UPDATE customers SET notes = ? WHERE id = ?", (notes.strip(), customer_id))

            # Mark request as approved
            cursor.execute("""
                UPDATE connection_requests
                SET status = 'approved', customer_id = ?, notes = COALESCE(NULLIF(?, ''), notes), updated_at = ?
                WHERE id = ?
            """, (customer_id, (notes.strip() if notes else None), now_str, req_id))

            conn.commit()

            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            saved_cust = dict(cursor.fetchone())
            saved_cust["mac_address"] = mac
            saved_cust["ip_address"] = ip
            saved_cust["device_status"] = dev_status
            saved_cust["is_expired"] = (cust_status == "suspended") or (dev_status == "blocked")
            saved_cust["credit_balance"] = round(float(saved_cust.get("credit_balance") or 0.0), 2)
            return saved_cust

        else:
            # =========================================================================
            # CASE B: Brand New Customer (Initial Setup)
            # =========================================================================
            today_str = now.strftime("%Y-%m-%d")
            final_join_date = join_date.strip() if join_date and join_date.strip() else today_str
            final_billing_start = billing_start_date.strip() if billing_start_date and billing_start_date.strip() else final_join_date

            final_billing_type = (billing_type or "prepaid").strip().lower()
            if clean_collected == 0.0:
                final_billing_type = "postpaid"
            elif clean_collected >= monthly_fee and monthly_fee > 0:
                final_billing_type = "prepaid"

            if due_date and due_date.strip():
                final_due_date = due_date.strip()
            else:
                try:
                    j_day = int(final_join_date.split("-")[2])
                    now_day = now.day
                    if now_day <= j_day:
                        target_month = now.month
                        target_year = now.year
                    else:
                        target_month = now.month + 1
                        target_year = now.year
                        if target_month > 12:
                            target_month = 1
                            target_year += 1
                    max_d = calendar.monthrange(target_year, target_month)[1]
                    final_due_date = f"{target_year:04d}-{target_month:02d}-{min(j_day, max_d):02d}"
                except Exception:
                    final_due_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

            credit_to_add = 0.0
            col_notes = ""

            if clean_collected > 0 and monthly_fee > 0:
                if clean_collected > monthly_fee:
                    if advance_mode == "months":
                        covered_months = int(clean_collected // monthly_fee)
                        surplus_credit = round(clean_collected - (covered_months * monthly_fee), 2)
                        try:
                            base_dt = datetime.strptime(final_due_date, "%Y-%m-%d")
                        except Exception:
                            base_dt = now
                        extra_days = (covered_months - 1) * 30 if covered_months > 1 else 0
                        final_due_date = (base_dt + timedelta(days=extra_days)).strftime("%Y-%m-%d")
                        credit_to_add = surplus_credit
                        col_notes = f"Advance payment: {clean_collected:.2f} SAR ({covered_months} months covered until {final_due_date}, +{surplus_credit:.2f} SAR credit)"
                    else:
                        credit_to_add = round(clean_collected - monthly_fee, 2)
                        col_notes = f"Advance payment: {clean_collected:.2f} SAR ({monthly_fee:.2f} SAR 1st cycle, +{credit_to_add:.2f} SAR added to Credit Balance)"
                elif clean_collected == monthly_fee:
                    col_notes = f"Initial activation payment for {package_name} ({clean_collected:.2f} SAR)"
                else:
                    credit_to_add = clean_collected
                    col_notes = f"Initial payment deposit: {clean_collected:.2f} SAR credited to balance"
            elif clean_collected > 0:
                credit_to_add = clean_collected
                col_notes = f"Initial credit deposit: {clean_collected:.2f} SAR"

            expiry_date = final_due_date
            try:
                due_day = int(final_due_date.split("-")[2])
            except Exception:
                pass

            final_notes = notes.strip() if notes and notes.strip() else ""
            new_credit = round(credit_to_add, 2)
            final_conn_type = "pppoe" if connection_type and connection_type.strip().lower() == "pppoe" else (req.get("connection_type") or "hotspot")
            final_pppoe_user = pppoe_username.strip() if pppoe_username and pppoe_username.strip() else (req.get("pppoe_username") or (phone.strip() if final_conn_type == "pppoe" else ""))
            final_pppoe_pass = pppoe_password.strip() if pppoe_password and pppoe_password.strip() else (req.get("pppoe_password") or ("" if final_conn_type != "pppoe" else "cyber" + phone.strip()[-4:]))
            final_pppoe_prof = pppoe_profile.strip() if pppoe_profile and pppoe_profile.strip() else ""
            final_pppoe_ip = pppoe_remote_ip.strip() if pppoe_remote_ip and pppoe_remote_ip.strip() else ""

            cursor.execute("""
                INSERT INTO customers (
                    phone, name, billing_type, package_name, monthly_fee,
                    collected_today, due_day, due_date, status, expiry_date,
                    max_devices, speed_limit, credit_balance, join_date, billing_start_date,
                    notes, connection_type, pppoe_username, pppoe_password, pppoe_profile, pppoe_remote_ip,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                phone, name, final_billing_type, package_name or "Standard", monthly_fee,
                clean_collected, due_day, final_due_date, expiry_date,
                clean_limit, clean_speed, new_credit, final_join_date, final_billing_start,
                final_notes, final_conn_type, final_pppoe_user, final_pppoe_pass, final_pppoe_prof, final_pppoe_ip,
                now_str, now_str
            ))
            customer_id = cursor.lastrowid

            cursor.execute("SELECT id FROM customer_devices WHERE UPPER(mac_address) = ?", (mac,))
            dev_row = cursor.fetchone()
            if dev_row:
                cursor.execute("""
                    UPDATE customer_devices
                    SET customer_id = ?, ip_address = ?, device_name = ?, status = 'approved', approved_at = ?
                    WHERE id = ?
                """, (customer_id, ip, req.get("device_model", "Mobile Phone"), now_str, dev_row["id"]))
            else:
                cursor.execute("""
                    INSERT INTO customer_devices (customer_id, mac_address, ip_address, device_name, status, approved_at, created_at)
                    VALUES (?, ?, ?, ?, 'approved', ?, ?)
                """, (customer_id, mac, ip, req.get("device_model", "Mobile Phone"), now_str, now_str))

            if clean_collected > 0:
                cursor.execute("""
                    INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
                    VALUES (?, ?, ?, ?, ?, 'Admin')
                """, (customer_id, clean_collected, final_billing_type, col_notes or f"Activation payment for {package_name}", now_str))

            cursor.execute("""
                UPDATE connection_requests
                SET status = 'approved', customer_id = ?, notes = ?, updated_at = ?
                WHERE id = ?
            """, (customer_id, final_notes, now_str, req_id))

            conn.commit()

            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            saved_cust = dict(cursor.fetchone())
            saved_cust["mac_address"] = mac
            saved_cust["ip_address"] = ip
            saved_cust["credit_balance"] = round(float(saved_cust.get("credit_balance") or 0.0), 2)
            return saved_cust


def reject_connection(req_id: int) -> bool:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE connection_requests
            SET status = 'rejected', updated_at = ?
            WHERE id = ?
        """, (now_str, req_id))
        conn.commit()
        return cursor.rowcount > 0


def revoke_customer_device(mac: str) -> Optional[Dict[str, Any]]:
    """
    Revokes a device:
    1. Sets device status = 'blocked'
    2. Sets connection request = 'revoked'
    3. Sets customer status = 'suspended'
    Returns device and customer details for network cut-off.
    """
    mac_clean = mac.strip().upper()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()

        # Get device info
        cursor.execute("""
            SELECT d.*, c.phone, c.name, c.id as cust_id
            FROM customer_devices d
            JOIN customers c ON d.customer_id = c.id
            WHERE UPPER(d.mac_address) = ?
        """, (mac_clean,))
        row = cursor.fetchone()
        if not row:
            return None
        info = dict(row)

        # Update statuses
        cursor.execute("UPDATE customer_devices SET status = 'blocked' WHERE UPPER(mac_address) = ?", (mac_clean,))
        cursor.execute("UPDATE connection_requests SET status = 'revoked', updated_at = ? WHERE UPPER(mac_address) = ?", (now_str, mac_clean))

        # Check if customer has any other approved devices
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM customer_devices 
            WHERE customer_id = ? AND status = 'approved' AND UPPER(mac_address) != ?
        """, (info["cust_id"], mac_clean))
        remaining = cursor.fetchone()["count"]
        if remaining == 0:
            cursor.execute("UPDATE customers SET status = 'suspended', updated_at = ? WHERE id = ?", (now_str, info["cust_id"]))
        else:
            cursor.execute("UPDATE customers SET updated_at = ? WHERE id = ?", (now_str, info["cust_id"]))

        conn.commit()
        return info


# =========================================================
# Step 3: Customer Directory Operations
# =========================================================

def get_all_customers(reseller_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Returns registered customers with device counts, payment stats,
    reseller partner metadata, and computed validity/days remaining.
    Optionally scoped to a specific reseller partner.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    with get_db() as conn:
        cursor = conn.cursor()

        where_sql = ""
        params = []
        if reseller_id is not None:
            where_sql = "WHERE c.reseller_id = ?"
            params.append(reseller_id)

        query = f"""
            SELECT 
                c.*,
                COALESCE(u_res.username, '') as reseller_username,
                COALESCE(u_res.shop_name, '') as reseller_shop_name,
                COUNT(DISTINCT CASE WHEN d.status = 'approved' THEN d.id END) as active_devices_count,
                COALESCE(SUM(col.amount), 0.0) as total_paid
            FROM customers c
            LEFT JOIN admin_users u_res ON c.reseller_id = u_res.id
            LEFT JOIN customer_devices d ON d.customer_id = c.id
            LEFT JOIN collections col ON col.customer_id = c.id
            {where_sql}
            GROUP BY c.id
            ORDER BY c.id DESC
        """
        rows = cursor.execute(query, params).fetchall()

        # Preload packages to resolve default speed rates
        cursor.execute("SELECT name, rate_limit, default_price FROM packages")
        pkg_map = {row["name"]: dict(row) for row in cursor.fetchall()}

        # Preload approved devices for customer list
        cursor.execute("""
            SELECT id, customer_id, mac_address, ip_address, device_name, status, approved_at, created_at
            FROM customer_devices
            WHERE status = 'approved'
            ORDER BY id ASC
        """)
        dev_rows = cursor.fetchall()
        cust_dev_map: Dict[int, List[Dict[str, Any]]] = {}
        for dr in dev_rows:
            cid = dr["customer_id"]
            if cid not in cust_dev_map:
                cust_dev_map[cid] = []
            cust_dev_map[cid].append(dict(dr))

        customers = []
        for r in rows:
            item = dict(r)
            item["join_date"] = item.get("join_date") or item.get("billing_start_date") or (item.get("created_at")[:10] if item.get("created_at") else today_str)
            item["billing_start_date"] = item.get("billing_start_date") or item.get("join_date") or (item.get("created_at")[:10] if item.get("created_at") else today_str)
            item["devices"] = cust_dev_map.get(item["id"], [])
            
            # Days remaining calculation
            expiry = item.get("expiry_date") or item.get("due_date")
            if expiry:
                try:
                    exp_dt = datetime.strptime(expiry.split()[0], "%Y-%m-%d")
                    delta = (exp_dt.date() - now.date()).days
                    item["days_remaining"] = delta
                    item["is_expired"] = delta < 0
                except Exception:
                    item["days_remaining"] = None
                    item["is_expired"] = False
            else:
                item["days_remaining"] = None
                item["is_expired"] = False

            # Speed resolution
            pkg_info = pkg_map.get(item.get("package_name"), {})
            item["package_rate_limit"] = pkg_info.get("rate_limit")
            item["effective_speed"] = item.get("speed_limit") or pkg_info.get("rate_limit") or "Unlimited"
            item["is_speed_custom"] = bool(item.get("speed_limit"))
            item["credit_balance"] = round(float(item.get("credit_balance") or 0.0), 2)

            # Grace hold / suspension hold check
            susp_until = item.get("suspension_held_until")
            if susp_until and susp_until >= today_str:
                item["is_grace_held"] = True
                item["grace_until"] = susp_until
                item["tier_badge"] = "grace"
                item["tier_label"] = f"Grace Hold ({susp_until})"
            else:
                item["is_grace_held"] = False

            customers.append(item)
        return customers


def get_customer_profile(customer_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns complete customer profile: personal details, bound devices,
    reseller partner metadata, effective speed, credit balance, and payment ledger history.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Customer row with reseller details
        cursor.execute("""
            SELECT c.*,
                   COALESCE(u_res.username, '') as reseller_username,
                   COALESCE(u_res.shop_name, '') as reseller_shop_name
            FROM customers c
            LEFT JOIN admin_users u_res ON c.reseller_id = u_res.id
            WHERE c.id = ?
        """, (customer_id,))
        cust_row = cursor.fetchone()
        if not cust_row:
            return None
        cust = dict(cust_row)
        cust["join_date"] = cust.get("join_date") or cust.get("billing_start_date") or (cust.get("created_at")[:10] if cust.get("created_at") else datetime.now().strftime("%Y-%m-%d"))
        cust["billing_start_date"] = cust.get("billing_start_date") or cust.get("join_date") or (cust.get("created_at")[:10] if cust.get("created_at") else datetime.now().strftime("%Y-%m-%d"))
        cust["credit_balance"] = round(float(cust.get("credit_balance") or 0.0), 2)

        # Lookup package speed
        cursor.execute("SELECT rate_limit FROM packages WHERE name = ?", (cust.get("package_name"),))
        pkg_row = cursor.fetchone()
        pkg_rate = pkg_row["rate_limit"] if pkg_row else None
        cust["package_rate_limit"] = pkg_rate
        cust["effective_speed"] = cust.get("speed_limit") or pkg_rate or "Unlimited"
        cust["is_speed_custom"] = bool(cust.get("speed_limit"))

        # Associated devices
        cursor.execute("""
            SELECT * FROM customer_devices 
            WHERE customer_id = ? 
            ORDER BY id DESC
        """, (customer_id,))
        cust["devices"] = [dict(r) for r in cursor.fetchall()]

        # Days remaining and collection eligibility
        now = datetime.now()
        expiry = cust.get("due_date") or cust.get("expiry_date")
        if expiry:
            try:
                exp_dt = datetime.strptime(expiry.split()[0], "%Y-%m-%d")
                delta = (exp_dt.date() - now.date()).days
                cust["days_remaining"] = delta
                cust["is_expired"] = delta < 0
                cust["is_due"] = delta <= 0 or cust.get("status") == "suspended"
                cust["is_due_soon"] = (0 < delta <= 3) and cust.get("status") != "suspended"
            except Exception:
                cust["days_remaining"] = None
                cust["is_expired"] = False
                cust["is_due"] = False
                cust["is_due_soon"] = False
        else:
            cust["days_remaining"] = None
            cust["is_expired"] = False
            cust["is_due"] = True
        # Grace hold resolution
        today_str = now.strftime("%Y-%m-%d")
        susp_until = cust.get("suspension_held_until")
        if susp_until and susp_until >= today_str:
            cust["is_grace_held"] = True
            cust["grace_until"] = susp_until
            cust["tier_badge"] = "grace"
            cust["tier_label"] = f"Grace Hold ({susp_until})"
        else:
            cust["is_grace_held"] = False

        # Payment history
        cursor.execute("""
            SELECT * FROM collections 
            WHERE customer_id = ? 
            ORDER BY id DESC
        """, (customer_id,))
        cust["collections"] = [dict(r) for r in cursor.fetchall()]

        return cust


def create_customer(
    phone: str,
    name: str,
    billing_type: str,
    package_name: str,
    monthly_fee: float,
    due_date: Optional[str] = None,
    due_day: int = 1,
    mac_address: Optional[str] = None,
    max_devices: int = 1,
    speed_limit: Optional[str] = None,
    initial_payment: float = 0.0,
    advance_mode: str = "credit",
    reseller_id: Optional[int] = None,
    join_date: Optional[str] = None,
    billing_start_date: Optional[str] = None,
    notes: Optional[str] = "",
    connection_type: str = "hotspot",
    pppoe_username: Optional[str] = None,
    pppoe_password: Optional[str] = None,
    pppoe_profile: Optional[str] = None,
    pppoe_remote_ip: Optional[str] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """Manually creates a new customer with custom speed, fee, due date, device limit, advance credit handling, and optional reseller attribution."""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    clean_payment = float(initial_payment or 0.0)
    monthly_fee = float(monthly_fee or 0.0)
    final_notes = notes.strip() if notes and notes.strip() else ""

    # Auto-register join_date and billing_start_date
    today_str = now.strftime("%Y-%m-%d")
    final_join_date = join_date.strip() if join_date and join_date.strip() else today_str
    final_billing_start = billing_start_date.strip() if billing_start_date and billing_start_date.strip() else final_join_date

    # Dynamic Lifecycle Auto-Switching:
    # 0 SAR initial payment -> POSTPAID (deferred billing)
    # Payment >= monthly fee -> PREPAID (service pre-funded)
    final_billing_type = (billing_type or "prepaid").strip().lower()
    if clean_payment == 0.0:
        final_billing_type = "postpaid"
    elif clean_payment >= monthly_fee and monthly_fee > 0:
        final_billing_type = "prepaid"

    # Due date / Expiry
    if due_date and due_date.strip():
        final_due_date = due_date.strip()
    else:
        try:
            j_day = int(final_join_date.split("-")[2])
            now_day = now.day
            if now_day <= j_day:
                target_month = now.month
                target_year = now.year
            else:
                target_month = now.month + 1
                target_year = now.year
                if target_month > 12:
                    target_month = 1
                    target_year += 1
            max_d = calendar.monthrange(target_year, target_month)[1]
            final_due_date = f"{target_year:04d}-{target_month:02d}-{min(j_day, max_d):02d}"
        except Exception:
            final_due_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    credit_to_add = 0.0
    col_notes = ""

    # Advance payment calculation
    if clean_payment > 0 and monthly_fee > 0:
        if clean_payment > monthly_fee:
            if advance_mode == "months":
                covered_months = int(clean_payment // monthly_fee)
                surplus_credit = round(clean_payment - (covered_months * monthly_fee), 2)
                try:
                    base_dt = datetime.strptime(final_due_date, "%Y-%m-%d")
                except Exception:
                    base_dt = now
                extra_days = (covered_months - 1) * 30 if covered_months > 1 else 0
                final_due_date = (base_dt + timedelta(days=extra_days)).strftime("%Y-%m-%d")
                credit_to_add = surplus_credit
                col_notes = f"Advance payment: {clean_payment:.2f} SAR ({covered_months} months covered until {final_due_date}, +{surplus_credit:.2f} SAR credit)"
            else:
                credit_to_add = round(clean_payment - monthly_fee, 2)
                col_notes = f"Advance payment: {clean_payment:.2f} SAR ({monthly_fee:.2f} SAR 1st cycle, +{credit_to_add:.2f} SAR added to Credit Balance)"
        elif clean_payment == monthly_fee:
            col_notes = f"Initial activation payment for {package_name} ({clean_payment:.2f} SAR)"
        else:
            credit_to_add = clean_payment
            col_notes = f"Initial payment deposit: {clean_payment:.2f} SAR credited to balance"
    elif clean_payment > 0:
        credit_to_add = clean_payment
        col_notes = f"Initial credit deposit: {clean_payment:.2f} SAR"

    expiry_date = final_due_date
    try:
        due_day = int(final_due_date.split("-")[2])
    except Exception:
        pass

    clean_limit = max(1, int(max_devices or 1))
    clean_speed = speed_limit.strip() if speed_limit and speed_limit.strip() else None

    final_conn_type = "pppoe" if connection_type and connection_type.strip().lower() == "pppoe" else "hotspot"
    final_pppoe_user = pppoe_username.strip() if pppoe_username and pppoe_username.strip() else (phone.strip() if final_conn_type == "pppoe" else "")
    final_pppoe_pass = pppoe_password.strip() if pppoe_password and pppoe_password.strip() else ("" if final_conn_type != "pppoe" else "cyber" + phone.strip()[-4:])
    final_pppoe_prof = pppoe_profile.strip() if pppoe_profile and pppoe_profile.strip() else ""
    final_pppoe_ip = pppoe_remote_ip.strip() if pppoe_remote_ip and pppoe_remote_ip.strip() else ""

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO customers (
                phone, name, billing_type, package_name, monthly_fee,
                collected_today, due_day, due_date, status, expiry_date,
                max_devices, speed_limit, credit_balance, reseller_id,
                join_date, billing_start_date, notes, connection_type,
                pppoe_username, pppoe_password, pppoe_profile, pppoe_remote_ip,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            phone.strip(), name.strip(), final_billing_type, package_name, monthly_fee,
            clean_payment, due_day, final_due_date, expiry_date,
            clean_limit, clean_speed, credit_to_add, reseller_id,
            final_join_date, final_billing_start, final_notes, final_conn_type,
            final_pppoe_user, final_pppoe_pass, final_pppoe_prof, final_pppoe_ip,
            now_str, now_str
        ))
        customer_id = cursor.lastrowid

        # Bind MAC if provided
        if mac_address and mac_address.strip():
            mac_clean = mac_address.strip().upper()
            if is_randomized_mac(mac_clean):
                raise ValueError(f"Randomized MAC address '{mac_clean}' is not permitted. CyberNet requires physical Device MAC.")
            cursor.execute("""
                INSERT INTO customer_devices (customer_id, mac_address, ip_address, device_name, status, approved_at, created_at)
                VALUES (?, ?, NULL, 'Manual Entry', 'approved', ?, ?)
            """, (customer_id, mac_clean, now_str, now_str))

        # Record payment if provided
        if clean_payment > 0:
            cursor.execute("""
                INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
                VALUES (?, ?, ?, ?, ?, 'Admin')
            """, (customer_id, clean_payment, final_billing_type, col_notes or f"Initial registration payment for {package_name}", now_str))

        conn.commit()

        return get_customer_profile(customer_id)


def update_customer_details(
    customer_id: int,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    billing_type: Optional[str] = None,
    package_name: Optional[str] = None,
    monthly_fee: Optional[float] = None,
    due_date: Optional[str] = None,
    speed_limit: Optional[str] = None,
    max_devices: Optional[int] = None,
    status: Optional[str] = None,
    credit_balance: Optional[float] = None,
    reseller_id: Optional[int] = -1,
    billing_start_date: Optional[str] = None,
    join_date: Optional[str] = None,
    suspension_held_until: Optional[str] = -1,
    suspension_hold_reason: Optional[str] = -1,
    notes: Optional[str] = -1,
    connection_type: Optional[str] = None,
    pppoe_username: Optional[str] = -1,
    pppoe_password: Optional[str] = -1,
    pppoe_profile: Optional[str] = -1,
    pppoe_remote_ip: Optional[str] = -1,
    **kwargs: Any
) -> Optional[Dict[str, Any]]:
    """
    Updates any customer fields: monthly rate, payment due date, custom speed limit,
    billing type, device limit, package name, name, phone, status, credit balance, reseller attribution,
    join date, billing start date, suspension grace hold, and notes/room number.
    Automatically keeps prepaid expiry_date and due_day in sync.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        cust = cursor.fetchone()
        if not cust:
            return None
        current = dict(cust)

        new_name = name.strip() if name and name.strip() else current["name"]
        new_phone = phone.strip() if phone and phone.strip() else current["phone"]
        new_btype = billing_type.strip().lower() if billing_type and billing_type.strip() else current["billing_type"]
        new_pkg = package_name.strip() if package_name and package_name.strip() else current["package_name"]
        new_fee = float(monthly_fee) if monthly_fee is not None else float(current["monthly_fee"])
        new_status = status.strip() if status and status.strip() else current["status"]
        new_max_devices = max(1, int(max_devices)) if max_devices is not None else int(current.get("max_devices") or 1)
        new_credit = round(max(0.0, float(credit_balance)), 2) if credit_balance is not None else round(float(current.get("credit_balance") or 0.0), 2)
        final_reseller_id = current.get("reseller_id") if reseller_id == -1 else reseller_id
        new_notes = current.get("notes") or "" if notes == -1 else (notes.strip() if notes else "")
        new_conn_type = connection_type.strip().lower() if connection_type and connection_type.strip() else current.get("connection_type", "hotspot")
        new_pppoe_user = current.get("pppoe_username", "") if pppoe_username == -1 else (pppoe_username.strip() if pppoe_username else "")
        new_pppoe_pass = current.get("pppoe_password", "") if pppoe_password == -1 else (pppoe_password.strip() if pppoe_password else "")
        new_pppoe_prof = current.get("pppoe_profile", "") if pppoe_profile == -1 else (pppoe_profile.strip() if pppoe_profile else "")
        new_pppoe_ip = current.get("pppoe_remote_ip", "") if pppoe_remote_ip == -1 else (pppoe_remote_ip.strip() if pppoe_remote_ip else "")

        # Billing start date & join date & suspension hold
        new_bstart = billing_start_date.strip() if billing_start_date and billing_start_date.strip() else current.get("billing_start_date")
        new_join_date = join_date.strip() if join_date and join_date.strip() else current.get("join_date")
        if not new_join_date:
            new_join_date = new_bstart or (current.get("created_at")[:10] if current.get("created_at") else datetime.now().strftime("%Y-%m-%d"))
        if not new_bstart:
            new_bstart = new_join_date
        new_susp_held = current.get("suspension_held_until") if suspension_held_until == -1 else suspension_held_until
        new_susp_reason = current.get("suspension_hold_reason") if suspension_hold_reason == -1 else suspension_hold_reason

        # Speed limit: if explicitly passed, update it (empty string or "0" or "unlimited" means cleared/unlimited)
        if speed_limit is not None:
            new_speed = speed_limit.strip() if speed_limit.strip() else None
        else:
            new_speed = current.get("speed_limit")

        # Due date & expiry date
        if due_date and due_date.strip():
            new_due_date = due_date.strip()
            new_expiry_date = new_due_date
            try:
                new_due_day = int(new_due_date.split("-")[2])
            except Exception:
                new_due_day = current.get("due_day") or 1
        else:
            new_due_date = current.get("due_date")
            new_expiry_date = current.get("expiry_date")
            if new_join_date:
                try:
                    new_due_day = int(new_join_date.split("-")[2])
                except Exception:
                    new_due_day = current.get("due_day") or 1
            else:
                new_due_day = current.get("due_day") or 1

        cursor.execute("""
            UPDATE customers
            SET name = ?, phone = ?, billing_type = ?, package_name = ?,
                monthly_fee = ?, due_date = ?, due_day = ?, expiry_date = ?,
                speed_limit = ?, max_devices = ?, status = ?, credit_balance = ?, reseller_id = ?,
                join_date = ?, billing_start_date = ?, suspension_held_until = ?, suspension_hold_reason = ?,
                notes = ?, connection_type = ?, pppoe_username = ?, pppoe_password = ?,
                pppoe_profile = ?, pppoe_remote_ip = ?, updated_at = ?
            WHERE id = ?
        """, (
            new_name, new_phone, new_btype, new_pkg,
            new_fee, new_due_date, new_due_day, new_expiry_date,
            new_speed, new_max_devices, new_status, new_credit, final_reseller_id,
            new_join_date, new_bstart, new_susp_held, new_susp_reason,
            new_notes, new_conn_type, new_pppoe_user, new_pppoe_pass,
            new_pppoe_prof, new_pppoe_ip, now_str,
            customer_id
        ))

        # Handle suspension lifecycle if status changed
        if new_status != current.get("status"):
            if new_status == "suspended":
                cursor.execute("SELECT id FROM customer_suspensions WHERE customer_id = ? AND resumed_at IS NULL", (customer_id,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO customer_suspensions (customer_id, suspended_at, reason, created_at)
                        VALUES (?, ?, 'Admin profile status update', ?)
                    """, (customer_id, now_str, now_str))
            elif new_status == "active":
                cursor.execute("""
                    UPDATE customer_suspensions
                    SET resumed_at = ?
                    WHERE customer_id = ? AND resumed_at IS NULL
                """, (now_str, customer_id))

        conn.commit()

        return get_customer_profile(customer_id)


def update_customer(
    customer_id: int,
    name: str,
    phone: str,
    billing_type: str,
    package_name: str,
    monthly_fee: float,
    due_date: Optional[str] = None,
    due_day: int = 1,
    status: str = "active",
    max_devices: Optional[int] = None,
    speed_limit: Optional[str] = None,
    credit_balance: Optional[float] = None,
    billing_start_date: Optional[str] = None,
    join_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Legacy wrapper forwarding to update_customer_details."""
    return update_customer_details(
        customer_id=customer_id,
        name=name,
        phone=phone,
        billing_type=billing_type,
        package_name=package_name,
        monthly_fee=monthly_fee,
        due_date=due_date,
        speed_limit=speed_limit,
        max_devices=max_devices,
        status=status,
        credit_balance=credit_balance,
        billing_start_date=billing_start_date,
        join_date=join_date
    )


def update_customer_device_limit(customer_id: int, max_devices: int) -> bool:
    """Updates the allowed concurrent devices for a customer."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE customers SET max_devices = ?, updated_at = ? WHERE id = ?", (max(1, int(max_devices)), now_str, customer_id))
        conn.commit()
        return True


def toggle_customer_status(customer_id: int) -> Tuple[str, List[str]]:
    """
    Toggles customer between 'active' and 'suspended'.
    Returns (new_status, list_of_approved_mac_addresses).
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Customer #{customer_id} not found.")

        new_status = "suspended" if row["status"] == "active" else "active"
        new_device_status = "blocked" if new_status == "suspended" else "approved"

        cursor.execute("UPDATE customers SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_str, customer_id))
        cursor.execute("UPDATE customer_devices SET status = ? WHERE customer_id = ?", (new_device_status, customer_id))

        if new_status == "suspended":
            cursor.execute("""
                INSERT INTO customer_suspensions (customer_id, suspended_at, reason, created_at)
                VALUES (?, ?, 'Manual admin toggle', ?)
            """, (customer_id, now_str, now_str))
        else:
            cursor.execute("""
                UPDATE customer_suspensions
                SET resumed_at = ?
                WHERE customer_id = ? AND resumed_at IS NULL
            """, (now_str, customer_id))

        cursor.execute("SELECT mac_address FROM customer_devices WHERE customer_id = ?", (customer_id,))
        macs = [r["mac_address"].upper() for r in cursor.fetchall()]

        conn.commit()
        return (new_status, macs)


def add_customer_device(customer_id: int, mac_address: str, device_name: str = "Client Device") -> Dict[str, Any]:
    """Adds a new MAC device to an existing customer and marks connection requests approved."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mac_clean = mac_address.strip().upper()

    if is_randomized_mac(mac_clean):
        raise ValueError(f"Randomized MAC address '{mac_clean}' is not permitted. CyberNet requires physical Device MAC.")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO customer_devices (customer_id, mac_address, ip_address, device_name, status, approved_at, created_at)
            VALUES (?, ?, NULL, ?, 'approved', ?, ?)
        """, (customer_id, mac_clean, device_name, now_str, now_str))
        cursor.execute("""
            UPDATE connection_requests
            SET status = 'approved', customer_id = ?, updated_at = ?
            WHERE UPPER(mac_address) = ?
        """, (customer_id, now_str, mac_clean))
        conn.commit()
        dev_id = cursor.lastrowid
        cursor.execute("SELECT * FROM customer_devices WHERE id = ?", (dev_id,))
        return dict(cursor.fetchone())


def remove_customer_device(device_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Removes a device, revokes its connection requests, and returns (mac, ip) for unbinding."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mac_address, ip_address FROM customer_devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        if not row:
            return None, None
        mac = row["mac_address"].upper()
        ip = row["ip_address"]

        cursor.execute("DELETE FROM customer_devices WHERE id = ?", (device_id,))
        cursor.execute("""
            UPDATE connection_requests
            SET status = 'revoked', updated_at = ?
            WHERE UPPER(mac_address) = ?
        """, (now_str, mac))
        conn.commit()
        return mac, ip


def delete_customer_permanently(customer_id: int) -> Tuple[bool, List[str], str, str, str]:
    """
    Permanently deletes a customer and all associated devices, payment collections,
    and disassociates ONUs, revokes connection requests, and disassociates WhatsApp logs.
    Returns (success, list_of_mac_addresses, customer_name, customer_phone, pppoe_username).
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, phone, pppoe_username FROM customers WHERE id = ?", (customer_id,))
        cust = cursor.fetchone()
        if not cust:
            return False, [], "", "", ""

        cust_name = cust["name"]
        cust_phone = cust["phone"]
        cust_pppoe_user = cust.get("pppoe_username") or ""

        # 1. Fetch all MAC addresses of devices registered to this customer
        cursor.execute("SELECT mac_address FROM customer_devices WHERE customer_id = ?", (customer_id,))
        mac_rows = cursor.fetchall()
        macs = [r["mac_address"].upper() for r in mac_rows if r["mac_address"]]

        # 2. Delete all bound devices
        cursor.execute("DELETE FROM customer_devices WHERE customer_id = ?", (customer_id,))

        # 3. Delete collections / ledger records for this customer
        cursor.execute("DELETE FROM collections WHERE customer_id = ?", (customer_id,))

        # 4. Revoke and disassociate connection requests
        cursor.execute("UPDATE connection_requests SET status = 'revoked', customer_id = NULL, updated_at = ? WHERE customer_id = ?", (now_str, customer_id))
        for m in macs:
            cursor.execute("UPDATE connection_requests SET status = 'revoked', updated_at = ? WHERE UPPER(mac_address) = ?", (now_str, m))

        # 5. Disassociate assigned ONUs
        cursor.execute("UPDATE onus SET customer_id = NULL WHERE customer_id = ?", (customer_id,))

        # 6. Disassociate WhatsApp logs
        cursor.execute("UPDATE whatsapp_logs SET customer_id = NULL WHERE customer_id = ?", (customer_id,))

        # 7. Delete customer record
        cursor.execute("DELETE FROM customers WHERE id = ?", (customer_id,))

        conn.commit()
        return True, macs, cust_name, cust_phone, cust_pppoe_user


def get_all_pppoe_customers(active_only: bool = False) -> List[Dict[str, Any]]:
    """Returns all customers configured with connection_type == 'pppoe'."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM customers WHERE connection_type = 'pppoe'"
        if active_only:
            query += " AND status = 'active'"
        query += " ORDER BY id ASC"
        return [dict(r) for r in cursor.execute(query).fetchall()]



def record_customer_payment(
    customer_id: int,
    amount: float,
    notes: str = "Cash Payment",
    extend_days: int = 30,
    advance_mode: str = "credit"
) -> Dict[str, Any]:
    """
    Records a payment in collections ledger, marks customer active,
    extends their due/expiry date, and credits any advance/surplus payment to credit_balance.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    clean_amt = float(amount or 0.0)

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT expiry_date, due_date, billing_type, monthly_fee, credit_balance FROM customers WHERE id = ?", (customer_id,))
        cust_row = cursor.fetchone()
        if not cust_row:
            raise ValueError(f"Customer #{customer_id} not found.")
        cust = dict(cust_row)

        monthly_fee = float(cust.get("monthly_fee") or 0.0)
        current_credit = float(cust.get("credit_balance") or 0.0)
        current_billing_type = (cust.get("billing_type") or "prepaid").lower()

        credit_inc = 0.0
        actual_days = int(extend_days or 30)

        # Dynamic Lifecycle Auto-Switching between Prepaid and Postpaid:
        # 1. Zero payment with day extension -> auto-switches to POSTPAID (deferred billing)
        # 2. Paid money -> pre-funded service, auto-switches to PREPAID
        new_billing_type = current_billing_type
        if clean_amt == 0.0:
            new_billing_type = "postpaid"
            actual_days = int(extend_days or 30)
            if current_billing_type != "postpaid":
                rec_note = (notes or "Service Validity Extension") + " [Zero payment: Auto-switched to POSTPAID]"
            else:
                rec_note = (notes or "Service Validity Extension") + " [Extended on credit (Postpaid)]"
            new_credit = current_credit
        else:
            new_billing_type = "prepaid"
            switch_tag = " [Auto-switched to PREPAID]" if current_billing_type != "prepaid" else ""
            if monthly_fee > 0:
                if clean_amt >= monthly_fee:
                    covered_months = int(clean_amt // monthly_fee)
                    surplus = round(clean_amt - (covered_months * monthly_fee), 2)
                    actual_days = covered_months * 30
                    new_credit = round(current_credit + surplus, 2)
                    if covered_months > 1:
                        rec_note = (notes or "Advance Payment") + f" [Advance: {covered_months} months (+{actual_days} days), +{surplus:.2f} SAR surplus credited]{switch_tag}"
                    elif surplus > 0:
                        rec_note = (notes or "Advance Payment") + f" [1 month (+30 days), +{surplus:.2f} SAR surplus credited]{switch_tag}"
                    else:
                        rec_note = (notes or "Full Cycle Payment") + switch_tag
                else:
                    # clean_amt < monthly_fee: check if combined with existing credit covers 1+ cycles
                    comb_total = round(current_credit + clean_amt, 2)
                    if comb_total >= monthly_fee:
                        covered_months = int(comb_total // monthly_fee)
                        actual_days = covered_months * 30
                        new_credit = round(comb_total - (covered_months * monthly_fee), 2)
                        rec_note = (notes or "Payment + Credit Settlement") + f" [Auto-settled: {covered_months} month(s) (+{actual_days} days), {new_credit:.2f} SAR remaining credit]{switch_tag}"
                    else:
                        actual_days = 0
                        new_credit = comb_total
                        rec_note = (notes or "Credit Deposit") + f" [+{clean_amt:.2f} SAR added to Credit Balance. Balance: {new_credit:.2f}/{monthly_fee:.2f} SAR]{switch_tag}"
            else:
                actual_days = int(extend_days or 30)
                new_credit = current_credit
                rec_note = (notes or "Cash Payment") + switch_tag

        # 1. Insert collection
        cursor.execute("""
            INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
            VALUES (?, ?, 'recharge', ?, ?, 'Admin')
        """, (customer_id, clean_amt, rec_note, now_str))

        # 2. Update customer expiry / due date & credit_balance & billing_type
        current_exp = cust["expiry_date"] or cust["due_date"]
        try:
            base_dt = datetime.strptime(current_exp, "%Y-%m-%d")
            calc_base = max(base_dt, now)
        except Exception:
            calc_base = now

        if actual_days > 0:
            new_expiry = (calc_base + timedelta(days=actual_days)).strftime("%Y-%m-%d")
        else:
            new_expiry = current_exp or now.strftime("%Y-%m-%d")
        try:
            new_due_day = int(new_expiry.split("-")[2])
        except Exception:
            new_due_day = 1

        cursor.execute("""
            UPDATE customers
            SET expiry_date = ?, due_date = ?, due_day = ?, credit_balance = ?, billing_type = ?, status = 'active', updated_at = ?
            WHERE id = ?
        """, (new_expiry, new_expiry, new_due_day, new_credit, new_billing_type, now_str, customer_id))

        # Unblock any suspended customer devices
        cursor.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))

        conn.commit()
        return {
            "customer_id": customer_id,
            "amount": clean_amt,
            "billing_type": new_billing_type,
            "previous_billing_type": current_billing_type,
            "switched": (new_billing_type != current_billing_type),
            "new_expiry_date": new_expiry,
            "new_credit_balance": new_credit,
            "recorded_at": now_str
        }


def apply_customer_credit(
    customer_id: int,
    amount: Optional[float] = None,
    extend_days: int = 30
) -> Dict[str, Any]:
    """
    Applies existing credit balance to renew or extend the customer's service.
    Deducts credit from customer's credit_balance, extends due/expiry date,
    and logs a collection record as credit settlement.
    Automatically sets/keeps customer as PREPAID.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Customer #{customer_id} not found.")
        cust = dict(row)

        current_credit = float(cust.get("credit_balance") or 0.0)
        monthly_fee = float(cust.get("monthly_fee") or 0.0)
        current_billing_type = (cust.get("billing_type") or "prepaid").lower()
        new_billing_type = "prepaid"

        if current_credit <= 0:
            raise ValueError("Customer has no credit balance available.")

        # Determine deduction amount: either passed amount or monthly_fee or available credit
        if amount is not None and float(amount) > 0:
            deduct_amt = min(float(amount), current_credit)
        else:
            deduct_amt = min(monthly_fee if monthly_fee > 0 else 30.0, current_credit)

        new_credit = round(current_credit - deduct_amt, 2)

        # Extend due / expiry date
        current_exp = cust["expiry_date"] or cust["due_date"]
        try:
            base_dt = datetime.strptime(current_exp, "%Y-%m-%d")
            calc_base = max(base_dt, now)
        except Exception:
            calc_base = now

        new_expiry = (calc_base + timedelta(days=extend_days)).strftime("%Y-%m-%d")
        try:
            new_due_day = int(new_expiry.split("-")[2])
        except Exception:
            new_due_day = cust.get("due_day") or 1

        # 1. Update customer credit balance, expiry, billing_type, and status
        cursor.execute("""
            UPDATE customers
            SET credit_balance = ?, expiry_date = ?, due_date = ?, due_day = ?, billing_type = ?, status = 'active', updated_at = ?
            WHERE id = ?
        """, (new_credit, new_expiry, new_expiry, new_due_day, new_billing_type, now_str, customer_id))

        # 2. Unblock customer devices if suspended
        cursor.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))

        # 3. Log to collections ledger
        cursor.execute("""
            INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
            VALUES (?, ?, 'credit_deduction', ?, ?, 'Admin')
        """, (
            customer_id,
            deduct_amt,
            f"Settled from Account Credit (-{deduct_amt:.2f} SAR). Remaining Credit: {new_credit:.2f} SAR",
            now_str
        ))

        conn.commit()

        return {
            "customer_id": customer_id,
            "billing_type": new_billing_type,
            "previous_billing_type": current_billing_type,
            "switched": (new_billing_type != current_billing_type),
            "applied_credit": deduct_amt,
            "remaining_credit": new_credit,
            "new_expiry_date": new_expiry,
            "status": "active"
        }


# =========================================================
# Grace Period, Daily Accrual & Month Settlement Engine
# (Suspension Hold & Month-by-Month is_settled Waiver)
# =========================================================

def record_customer_promise(
    customer_id: int,
    days: int = 0,
    promise_date: Optional[str] = None,
    note: str = "",
    created_by: str = "Admin"
) -> Dict[str, Any]:
    """
    Holds customer suspension on MikroTik while allowing daily billing debt to accrue.
    Sets suspension_held_until in customers table and logs to customer_promises.
    Unblocks devices on MikroTik so customer remains active.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today = now.date()

    if promise_date and promise_date.strip():
        target_date_str = promise_date.strip()[:10]
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            calc_days = max(1, (target_date - today).days)
        except Exception:
            calc_days = max(1, days or 20)
            target_date_str = (now + timedelta(days=calc_days)).strftime("%Y-%m-%d")
    else:
        calc_days = max(1, days or 20)
        target_date_str = (now + timedelta(days=calc_days)).strftime("%Y-%m-%d")

    target_month_year = target_date_str[:7]
    hold_reason = note.strip() if note and note.strip() else f"Suspension hold requested ({calc_days} days grace)"

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, phone, monthly_fee, status FROM customers WHERE id = ?", (customer_id,))
        cust = cursor.fetchone()
        if not cust:
            raise ValueError(f"Customer #{customer_id} not found.")

        # 1. Cancel previous pending promises for this customer
        cursor.execute("""
            UPDATE customer_promises
            SET status = 'cancelled', updated_at = ?
            WHERE customer_id = ? AND status = 'pending'
        """, (now_str, customer_id))

        # 2. Insert new promise record
        cursor.execute("""
            INSERT INTO customer_promises (customer_id, month_year, days, promise_date, note, status, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
        """, (customer_id, target_month_year, calc_days, target_date_str, hold_reason, created_by, now_str, now_str))
        promise_id = cursor.lastrowid

        # 3. Update customer table: hold suspension and ensure status is active
        cursor.execute("""
            UPDATE customers
            SET suspension_held_until = ?, suspension_hold_reason = ?, status = 'active', updated_at = ?
            WHERE id = ?
        """, (target_date_str, hold_reason, now_str, customer_id))

        # 4. Unblock any blocked devices in DB
        cursor.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))
        conn.commit()

    return {
        "success": True,
        "promise_id": promise_id,
        "customer_id": customer_id,
        "days": calc_days,
        "promise_date": target_date_str,
        "note": hold_reason,
        "created_at": now_str
    }


def cancel_customer_promise(customer_id: int, reason: str = "Cancelled by admin") -> Dict[str, Any]:
    """
    Cancels any active grace / suspension hold for the customer.
    Reverts suspension_held_until to NULL.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE customer_promises
            SET status = 'cancelled', updated_at = ?
            WHERE customer_id = ? AND status = 'pending'
        """, (now_str, customer_id))
        cursor.execute("""
            UPDATE customers
            SET suspension_held_until = NULL, suspension_hold_reason = NULL, updated_at = ?
            WHERE id = ?
        """, (now_str, customer_id))
        conn.commit()

    return {"success": True, "customer_id": customer_id, "message": "Suspension hold cancelled"}


def get_customer_billing_breakdown(customer_id: int) -> Dict[str, Any]:
    """
    Calculates detailed month-by-month billing cycles, unpaid debt,
    accrued daily grace amounts, settled months, and waiver history.
    Follows the exact accounting model of billing_reminder:
    - Monthly rate divided by 30 gives daily rate.
    - Each elapsed cycle owes expected monthly fee.
    - Active grace hold accrues elapsed days up to promise date.
    - Settled months (is_settled=1) permanently close cycle debt.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today = now.date()
    today_str = today.strftime("%Y-%m-%d")
    current_month_str = today.strftime("%Y-%m")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, phone, billing_type, package_name, monthly_fee, due_day, due_date,
                   expiry_date, status, credit_balance, created_at,
                   join_date, billing_start_date, suspension_held_until, suspension_hold_reason
            FROM customers WHERE id = ?
        """, (customer_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Customer #{customer_id} not found.")
        cust = dict(row)

        # Preload active promise if any
        cursor.execute("""
            SELECT id, month_year, days, promise_date, note, status, created_at
            FROM customer_promises
            WHERE customer_id = ? AND status = 'pending'
            ORDER BY id DESC LIMIT 1
        """, (customer_id,))
        promise_row = cursor.fetchone()
        promise_data = dict(promise_row) if promise_row else None

        # Collections by month
        cursor.execute("""
            SELECT id, month_year, amount, is_settled, waived_amount, notes, collected_at, collected_by
            FROM collections
            WHERE customer_id = ?
            ORDER BY month_year ASC, id ASC
        """, (customer_id,))
        col_rows = cursor.fetchall()

    monthly_fee = float(cust.get("monthly_fee") or 30.0)
    if monthly_fee <= 0:
        monthly_fee = 30.0
    daily_rate = round(monthly_fee / 30.0, 4)

    # Collections map
    colls_by_month: Dict[str, Dict[str, Any]] = {}
    total_cash_collected = 0.0
    for cr in col_rows:
        amt = float(cr["amount"] or 0.0)
        settled = int(cr["is_settled"] or 0)
        waived = float(cr["waived_amount"] or 0.0)
        my = cr["month_year"] or (cr["collected_at"][:7] if cr["collected_at"] else current_month_str)
        if my not in colls_by_month:
            colls_by_month[my] = {"total": 0.0, "settled": 0, "waived": 0.0, "records": []}
        colls_by_month[my]["total"] += amt
        if settled == 1:
            colls_by_month[my]["settled"] = 1
        colls_by_month[my]["waived"] += waived
        colls_by_month[my]["records"].append(dict(cr))
        if amt > 0:
            total_cash_collected += amt

    # Determine start date
    start_str = cust.get("billing_start_date")
    if not start_str:
        start_str = cust.get("join_date") or (cust.get("created_at")[:10] if cust.get("created_at") else today_str)
    try:
        start_date = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
    except Exception:
        start_date = today

    # Active grace hold info
    susp_until = cust.get("suspension_held_until")
    has_active_promise = bool(susp_until and susp_until >= today_str)
    promise_date_str = susp_until if has_active_promise else (promise_data.get("promise_date") if promise_data else None)

    # Determine target end month: up to current month, or promise month if future
    max_month_date = today
    if promise_date_str:
        try:
            p_dt = datetime.strptime(promise_date_str[:10], "%Y-%m-%d").date()
            if p_dt > max_month_date:
                max_month_date = p_dt
        except Exception:
            pass

    # Determine billing day and effective start date matching billing_reminder
    billing_day = int(cust.get("due_day") or cust.get("billing_day") or 1)

    def get_effective_billing_start(b_date_str: str, bd: int) -> date:
        if not b_date_str:
            return date(today.year, today.month, 1)
        try:
            dt = datetime.strptime(b_date_str[:10], "%Y-%m-%d").date()
        except Exception:
            return date(today.year, today.month, 1)
        j_day = dt.day
        j_year = dt.year
        j_month = dt.month
        dim = calendar.monthrange(j_year, j_month)[1]
        if j_day <= bd:
            return date(j_year, j_month, min(bd, dim))
        else:
            nm = j_month + 1
            ny = j_year
            if nm > 12:
                nm = 1
                ny += 1
            ndim = calendar.monthrange(ny, nm)[1]
            return date(ny, nm, min(bd, ndim))

    eff_start = get_effective_billing_start(start_str, billing_day)
    months_seq: List[str] = []
    cur_d = eff_start
    i_cnt = 0
    while cur_d <= today and i_cnt < 60:
        i_cnt += 1
        months_seq.append(cur_d.strftime("%Y-%m"))
        ny = cur_d.year
        nm = cur_d.month + 1
        if nm > 12:
            nm = 1
            ny += 1
        dim = calendar.monthrange(ny, nm)[1]
        safe_day = min(billing_day, dim)
        cur_d = date(ny, nm, safe_day)

    # If customer has active suspension hold (grace promise) extending into future months, include it
    if has_active_promise and promise_date_str:
        p_m = promise_date_str[:7]
        if p_m not in months_seq:
            months_seq.append(p_m)

    # Also include any months present in collections that might not be in sequence
    for my in colls_by_month.keys():
        if my not in months_seq:
            months_seq.append(my)
    months_seq.sort()

    unpaid_cycles = []
    settled_cycles = []
    total_owed = 0.0

    for m in months_seq:
        try:
            m_dt = datetime.strptime(m + "-01", "%Y-%m-%d").date()
            m_label = m_dt.strftime("%B %Y")
        except Exception:
            m_label = m

        dim = calendar.monthrange(m_dt.year, m_dt.month)[1]
        p = colls_by_month.get(m, {"total": 0.0, "settled": 0, "waived": 0.0, "records": []})
        paid = round(p["total"], 2)
        is_settled = (p["settled"] == 1)

        # Expected fee calculation:
        is_grace_month = False
        grace_days = 0
        expected_fee = monthly_fee

        if has_active_promise and promise_date_str and promise_date_str.startswith(m):
            # Target promise day in this month
            try:
                p_day = int(promise_date_str.split("-")[2])
                grace_days = min(p_day, 30)
                expected_fee = round(grace_days * daily_rate, 2)
                is_grace_month = True
            except Exception:
                expected_fee = monthly_fee
        elif m > current_month_str:
            # Future month not covered by promise
            expected_fee = monthly_fee

        # If already marked settled in ledger, the cycle is solved!
        if is_settled:
            settled_cycles.append({
                "month": m,
                "label": m_label,
                "expected_fee": expected_fee,
                "paid": paid,
                "waived": round(p["waived"], 2),
                "rem_due": 0.0,
                "is_settled": True,
                "is_grace": is_grace_month,
                "status": "Settled & Closed"
            })
        else:
            rem_due = max(0.0, round(expected_fee - paid, 2))
            if rem_due > 0.05:
                total_owed += rem_due
                unpaid_cycles.append({
                    "month": m,
                    "label": m_label,
                    "expected_fee": expected_fee,
                    "paid": paid,
                    "waived": 0.0,
                    "rem_due": rem_due,
                    "is_settled": False,
                    "is_grace": is_grace_month,
                    "grace_days": grace_days,
                    "status": "Unpaid" if paid == 0 else "Partially Paid"
                })
            else:
                # Paid up in full even without explicit settle flag
                settled_cycles.append({
                    "month": m,
                    "label": m_label,
                    "expected_fee": expected_fee,
                    "paid": paid,
                    "waived": 0.0,
                    "rem_due": 0.0,
                    "is_settled": True,
                    "is_grace": is_grace_month,
                    "status": "Fully Paid"
                })

    # Summary Promise object
    promise_info = None
    if has_active_promise or promise_data:
        p_date = promise_date_str or (promise_data.get("promise_date") if promise_data else "")
        delta_d = 0
        if p_date:
            try:
                delta_d = (datetime.strptime(p_date[:10], "%Y-%m-%d").date() - today).days
            except Exception:
                pass
        promise_info = {
            "active": has_active_promise,
            "promise_date": p_date,
            "days_remaining": delta_d,
            "note": cust.get("suspension_hold_reason") or (promise_data.get("note") if promise_data else ""),
            "accrued_daily_rate": round(daily_rate, 2),
            "id": promise_data.get("id") if promise_data else None
        }

    return {
        "customer_id": customer_id,
        "customer_name": cust["name"],
        "phone": cust["phone"],
        "monthly_fee": monthly_fee,
        "daily_rate": round(daily_rate, 2),
        "join_date": cust.get("join_date") or start_str,
        "billing_start_date": start_str,
        "credit_balance": round(float(cust.get("credit_balance") or 0.0), 2),
        "total_due": round(total_owed, 2),
        "total_paid_lifetime": round(total_cash_collected, 2),
        "has_active_promise": has_active_promise,
        "promise": promise_info,
        "unpaid_cycles": unpaid_cycles,
        "settled_cycles": settled_cycles
    }


def get_customer_unpaid_months(customer_id: int) -> List[Dict[str, Any]]:
    """
    Returns unpaid billing cycles for customer in billing_reminder format:
    [{ "month": "2026-09", "month_name": "September 2026", "due": 30.0, "fee": 30.0, "paid": 0.0 }]
    """
    breakdown = get_customer_billing_breakdown(customer_id)
    unpaid = []
    for u in breakdown.get("unpaid_cycles", []):
        unpaid.append({
            "month": u["month"],
            "month_name": u.get("label") or u["month"],
            "due": round(float(u.get("rem_due", 0.0)), 2),
            "fee": round(float(u.get("expected_fee", 0.0)), 2),
            "paid": round(float(u.get("paid", 0.0)), 2),
            "is_grace": bool(u.get("is_grace", False)),
            "grace_days": int(u.get("grace_days", 0))
        })
    return unpaid


def settle_customer_cycles(
    customer_id: int,
    settlement_items: List[Dict[str, Any]],
    collected_by: str = "Admin",
    notes: str = ""
) -> Dict[str, Any]:
    """
    Processes month-by-month settlement with partial or zero payments.
    When settle=True, the month is permanently marked is_settled=1 and the
    remainder difference is recorded as waived discount.
    Advances customer due/expiry date and fulfills any pending promises.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        cust_row = cursor.fetchone()
        if not cust_row:
            raise ValueError(f"Customer #{customer_id} not found.")
        cust = dict(cust_row)

        monthly_fee = float(cust.get("monthly_fee") or 30.0)
        daily_rate = round(monthly_fee / 30.0, 4)

        recorded_records = []
        total_collected = 0.0
        total_waived = 0.0
        settled_months_list = []

        for item in settlement_items:
            month = item.get("month", "").strip()[:7]
            if not month:
                continue
            amt = round(max(0.0, float(item.get("amount") or 0.0)), 2)
            should_settle = bool(item.get("settle", True))

            # Prior payments for this month
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0.0) as paid_sum
                FROM collections
                WHERE customer_id = ? AND month_year = ?
            """, (customer_id, month))
            prev_paid = float(cursor.fetchone()["paid_sum"] or 0.0)
            total_month_paid = prev_paid + amt

            # Check if this was a grace hold month
            expected_fee = monthly_fee
            susp_until = cust.get("suspension_held_until")
            if susp_until and susp_until.startswith(month):
                try:
                    p_day = int(susp_until.split("-")[2])
                    expected_fee = round(min(p_day, 30) * daily_rate, 2)
                except Exception:
                    expected_fee = monthly_fee

            # Settlement logic
            if should_settle:
                is_settled_val = 1
                waived = max(0.0, round(expected_fee - total_month_paid, 2))
                settled_months_list.append(month)
                desc = f"Settled {month}: {amt:.2f} SAR collected"
                if waived > 0.05:
                    desc += f" ({waived:.2f} SAR waived discount)"
            else:
                if total_month_paid >= (expected_fee - 0.05):
                    is_settled_val = 1
                    settled_months_list.append(month)
                    desc = f"Fully paid {month}: {amt:.2f} SAR"
                else:
                    is_settled_val = 0
                    rem_pending = max(0.0, expected_fee - total_month_paid)
                    desc = f"Partial payment for {month}: {amt:.2f} SAR ({rem_pending:.2f} SAR remaining pending)"
                waived = 0.0

            if notes and notes.strip():
                desc += f" - {notes.strip()}"

            # Only record if money was collected or a settlement occurred
            if amt > 0 or (should_settle and (waived > 0.01 or prev_paid > 0 or is_settled_val == 1)):
                cursor.execute("""
                    INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by, month_year, is_settled, waived_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (customer_id, amt, 'settle' if is_settled_val else 'recharge', desc, now_str, collected_by, month, is_settled_val, waived))

                recorded_records.append({
                    "month": month,
                    "amount": amt,
                    "is_settled": is_settled_val,
                    "waived": waived,
                    "note": desc
                })
            total_collected += amt
            total_waived += waived

        # Restore customer status and devices if any payment was collected
        if total_collected > 0:
            cursor.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))
            cursor.execute("UPDATE customers SET status = 'active', updated_at = ? WHERE id = ?", (now_str, customer_id))
            cursor.execute("""
                UPDATE customer_suspensions
                SET resumed_at = ?
                WHERE customer_id = ? AND resumed_at IS NULL
            """, (now_str, customer_id))

        # If any months were settled, fulfill any pending promises and advance due date
        if settled_months_list:
            cursor.execute("""
                UPDATE customer_promises
                SET status = 'fulfilled', updated_at = ?
                WHERE customer_id = ? AND status = 'pending'
            """, (now_str, customer_id))

            # Compute new expiry/due date:
            # Sort settled months and take the latest month + 1 month
            last_settled = sorted(settled_months_list)[-1]
            try:
                ly, lm = int(last_settled[:4]), int(last_settled[5:7])
                # Advance 1 month
                nm = lm + 1
                ny = ly
                if nm > 12:
                    nm = 1
                    ny += 1
                dim = calendar.monthrange(ny, nm)[1]

                # Preserve original due day (e.g. 30th for 30-day cycle)
                old_due_date = cust.get("due_date") or cust.get("expiry_date")
                if old_due_date:
                    orig_day = int(old_due_date.split("-")[2])
                elif cust.get("join_date"):
                    orig_day = int(cust["join_date"].split("-")[2])
                elif cust.get("billing_start_date"):
                    orig_day = int(cust["billing_start_date"].split("-")[2])
                else:
                    orig_day = int(cust.get("due_day") or 1)

                due_day = min(orig_day, dim)
                new_due_date = f"{ny:04d}-{nm:02d}-{due_day:02d}"
            except Exception:
                new_due_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

            cursor.execute("""
                UPDATE customers
                SET due_date = ?, expiry_date = ?, status = 'active',
                    suspension_held_until = NULL, suspension_hold_reason = NULL,
                    updated_at = ?
                WHERE id = ?
            """, (new_due_date, new_due_date, now_str, customer_id))

            # Unblock customer devices
            cursor.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))

        conn.commit()

    return {
        "success": True,
        "customer_id": customer_id,
        "total_collected": round(total_collected, 2),
        "total_waived": round(total_waived, 2),
        "settled_months": settled_months_list,
        "records": recorded_records
    }


# =========================================================
# Step 4: Packages & Limits Operations
# =========================================================

def get_package_by_id(pkg_id: int) -> Optional[Dict[str, Any]]:
    """Returns a single package by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*,
                   COALESCE(p.price, p.default_price) as display_price,
                   COALESCE(sub_counts.sub_count, 0) as subscribers_count
            FROM packages p
            LEFT JOIN (
                SELECT package_name, COUNT(*) as sub_count
                FROM customers
                WHERE status = 'active'
                GROUP BY package_name
            ) sub_counts ON sub_counts.package_name = p.name
            WHERE p.id = ?
        """, (pkg_id,))
        row = cursor.fetchone()
        if not row:
            return None
        item = dict(row)
        rl = item.get("rate_limit", "")
        item["is_unlimited"] = not rl or str(rl).strip().lower() in ("0", "0m", "0k", "0/0", "0m/0m", "unlimited", "none", "")
        return item


def create_package(
    name: str,
    price: float,
    rate_limit: Optional[str] = "0",
    package_type: str = "hotspot",
    cost_price: float = 0.0,
    validity_days: int = 30,
    shared_users: int = 1,
    mikrotik_profile: Optional[str] = None,
    description: Optional[str] = "",
    is_active: int = 1
) -> Dict[str, Any]:
    """Creates a new speed package."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_name = name.strip()
    
    # Rate limit normalization: if empty or 0, record as "0"
    clean_rate = rate_limit.strip() if rate_limit else "0"
    if clean_rate.lower() in ("unlimited", "none", ""):
        clean_rate = "0"

    # Profile slug
    if not mikrotik_profile or not mikrotik_profile.strip():
        slug = clean_name.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-")
        slug = "".join(c for c in slug if c.isalnum() or c in ("-", "_"))
        clean_profile = slug or "default"
    else:
        clean_profile = mikrotik_profile.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO packages (
                name, rate_limit, default_price, price, cost_price, validity_days,
                shared_users, mikrotik_profile, type, description, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            clean_name, clean_rate, price, price, cost_price, validity_days,
            shared_users, clean_profile, package_type, description, is_active, now_str, now_str
        ))
        conn.commit()
        pkg_id = cursor.lastrowid
        return get_package_by_id(pkg_id)


def update_package(
    pkg_id: int,
    name: str,
    price: float,
    rate_limit: Optional[str] = "0",
    package_type: str = "hotspot",
    cost_price: float = 0.0,
    validity_days: int = 30,
    shared_users: int = 1,
    mikrotik_profile: Optional[str] = None,
    description: Optional[str] = "",
    is_active: int = 1
) -> Optional[Dict[str, Any]]:
    """Updates an existing package."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_name = name.strip()

    clean_rate = rate_limit.strip() if rate_limit else "0"
    if clean_rate.lower() in ("unlimited", "none", ""):
        clean_rate = "0"

    if not mikrotik_profile or not mikrotik_profile.strip():
        slug = clean_name.lower().replace(" ", "-").replace("(", "").replace(")", "").replace("/", "-")
        slug = "".join(c for c in slug if c.isalnum() or c in ("-", "_"))
        clean_profile = slug or "default"
    else:
        clean_profile = mikrotik_profile.strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE packages
            SET name = ?, rate_limit = ?, default_price = ?, price = ?, cost_price = ?,
                validity_days = ?, shared_users = ?, mikrotik_profile = ?, type = ?,
                description = ?, is_active = ?, updated_at = ?
            WHERE id = ?
        """, (
            clean_name, clean_rate, price, price, cost_price,
            validity_days, shared_users, clean_profile, package_type,
            description, is_active, now_str, pkg_id
        ))
        conn.commit()
        return get_package_by_id(pkg_id)


def delete_package(pkg_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Deletes package if no active customers are assigned."""
    pkg = get_package_by_id(pkg_id)
    if not pkg:
        return False, "Package not found.", None

    if pkg.get("subscribers_count", 0) > 0:
        return False, f"Cannot delete: {pkg['subscribers_count']} active subscriber(s) are currently on this package. Deactivate it instead.", pkg

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM packages WHERE id = ?", (pkg_id,))
        conn.commit()
        return True, f"Package '{pkg['name']}' deleted.", pkg


def toggle_package_active(pkg_id: int) -> Tuple[bool, int]:
    """Toggles package active status."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM packages WHERE id = ?", (pkg_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Package not found")
        new_state = 0 if row["is_active"] == 1 else 1
        cursor.execute("UPDATE packages SET is_active = ?, updated_at = ? WHERE id = ?", (new_state, now_str, pkg_id))
        conn.commit()
        return True, new_state


# =========================================================
# Operations & Financial Dashboard Metrics Aggregator
# (Merging billing_reminder & ispbilling intelligence)
# =========================================================

def get_dashboard_metrics(
    month_str: Optional[str] = None,
    online_macs: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Computes unified Operations & Financial metrics:
    - 6 Top KPIs (Online Live, Active/Capacity, Collected SAR, Outstanding Due, Collection %, Expiring Accounts)
    - Capacity progress gauge & connectivity metrics
    - Will-suspend / Expiring countdown tiers (today/overdue, in 3d, in 7d, in 15d)
    - Priority action queue of expiring/due accounts with direct collect eligibility
    - Staff performance audit breakdown table
    - Recent collections feed
    - Month selector history
    """
    now = datetime.now()
    curr_month = now.strftime("%Y-%m-%d")[:7]
    target_month = (month_str.strip() if month_str and month_str.strip() else curr_month)

    try:
        dt_month = datetime.strptime(target_month, "%Y-%m")
        month_label = dt_month.strftime("%B %Y")
    except Exception:
        target_month = curr_month
        month_label = now.strftime("%B %Y")

    online_mac_set = {m.strip().upper() for m in (online_macs or []) if m and m.strip()}

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Available Months for Selector Dropdown
        cursor.execute("SELECT DISTINCT strftime('%Y-%m', collected_at) as m FROM collections WHERE collected_at IS NOT NULL AND length(collected_at) >= 7 ORDER BY m DESC")
        db_months = [r["m"] for r in cursor.fetchall() if r["m"]]
        if curr_month not in db_months:
            db_months.insert(0, curr_month)

        available_months = []
        for m in db_months:
            try:
                m_dt = datetime.strptime(m, "%Y-%m")
                lbl = m_dt.strftime("%B %Y")
                if m == curr_month:
                    lbl += " (Current)"
                available_months.append({"value": m, "label": lbl, "is_selected": (m == target_month)})
            except Exception:
                pass

        # 2. Customers and Devices Analysis
        cursor.execute("SELECT * FROM customers ORDER BY id DESC")
        all_custs = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM customer_devices WHERE status = 'approved'")
        all_devices = [dict(r) for r in cursor.fetchall()]
        for dev in all_devices:
            dev["is_random_mac"] = is_randomized_mac(dev.get("mac_address", ""))

        # Map devices by customer_id
        cust_devices_map: Dict[int, List[Dict[str, Any]]] = {}
        for dev in all_devices:
            cid = dev["customer_id"]
            if cid not in cust_devices_map:
                cust_devices_map[cid] = []
            cust_devices_map[cid].append(dev)

        total_customers = len(all_custs)
        active_customers = [c for c in all_custs if c.get("status") == "active"]
        suspended_customers = [c for c in all_custs if c.get("status") == "suspended"]

        # Online Device matching
        total_approved_devices = len(all_devices)
        online_approved_devices = 0
        online_customer_ids = set()

        for dev in all_devices:
            mac = dev.get("mac_address", "").upper()
            if mac in online_mac_set:
                online_approved_devices += 1
                online_customer_ids.add(dev["customer_id"])

        connectivity_rate = (
            round((online_approved_devices / total_approved_devices * 100), 1)
            if total_approved_devices > 0 else 0.0
        )
        active_subscribers_online = len(online_customer_ids)

        # 3. Expiration Tiers & Priority Action Queue
        tier_counts = {
            "total": 0,
            "overdue": 0,
            "today": 0,
            "today_overdue": 0,
            "in_3d": 0,
            "in_7d": 0,
            "in_15d": 0
        }

        priority_queue = []
        due_customers_count = 0
        outstanding_sar = 0.0

        for c in all_custs:
            cid = c["id"]
            c["devices"] = cust_devices_map.get(cid, [])
            c["devices_count"] = len(c["devices"])
            c["primary_mac"] = c["devices"][0]["mac_address"] if c["devices"] else None
            c["primary_mac_is_random"] = is_randomized_mac(c["primary_mac"]) if c["primary_mac"] else False
            c["is_online"] = (cid in online_customer_ids)
            c["credit_balance"] = round(float(c.get("credit_balance") or 0.0), 2)
            c["monthly_fee"] = round(float(c.get("monthly_fee") or 0.0), 2)

            expiry = c.get("due_date") or c.get("expiry_date")
            days_rem = None
            is_expired = False
            is_due = False
            tier = "active"
            tier_badge = "active"
            tier_label = "Active"

            today_str = now.strftime("%Y-%m-%d")
            susp_until = c.get("suspension_held_until")
            if susp_until and susp_until >= today_str:
                tier = "grace"
                tier_badge = "grace"
                tier_label = f"Grace Hold ({susp_until})"
                is_due = True
                c["is_grace_held"] = True
                c["grace_until"] = susp_until
            elif c.get("status") == "suspended":
                tier = "overdue"
                tier_badge = "suspended"
                tier_label = "SUSPENDED"
                is_due = True
                is_expired = True
                days_rem = -999
            elif expiry:
                try:
                    exp_dt = datetime.strptime(expiry.split()[0], "%Y-%m-%d")
                    delta = (exp_dt.date() - now.date()).days
                    days_rem = delta
                    is_expired = (delta < 0)

                    if delta < 0:
                        tier = "overdue"
                        tier_badge = "overdue"
                        tier_label = f"Overdue (-{abs(delta)}d)"
                        is_due = True
                    elif delta == 0:
                        tier = "today"
                        tier_badge = "today"
                        tier_label = "Due Today"
                        is_due = True
                    elif 1 <= delta <= 3:
                        tier = "in_3d"
                        tier_badge = "in_3d"
                        tier_label = f"In {delta} day{'s' if delta > 1 else ''}"
                        is_due = True  # Eligible for renewal
                    elif 4 <= delta <= 7:
                        tier = "in_7d"
                        tier_badge = "in_7d"
                        tier_label = f"In {delta} days"
                        is_due = False
                    elif 8 <= delta <= 15:
                        tier = "in_15d"
                        tier_badge = "in_15d"
                        tier_label = f"In {delta} days"
                        is_due = False
                    else:
                        tier = "active"
                        tier_badge = "active"
                        tier_label = f"{delta} days left"
                        is_due = False
                except Exception:
                    tier = "overdue"
                    tier_badge = "overdue"
                    tier_label = "Invalid Date"
                    is_due = True
            else:
                tier = "overdue"
                tier_badge = "overdue"
                tier_label = "No Due Date"
                is_due = True

            c["days_remaining"] = days_rem
            c["is_expired"] = is_expired
            c["is_due"] = is_due
            c["tier"] = tier
            c["tier_badge"] = tier_badge
            c["tier_label"] = tier_label

            if is_due:
                due_customers_count += 1
                outstanding_sar += c["monthly_fee"]

            # Count tiers
            if tier in ("overdue", "today", "in_3d", "in_7d", "in_15d"):
                if tier == "overdue":
                    tier_counts["overdue"] += 1
                elif tier == "today":
                    tier_counts["today"] += 1
                elif tier == "in_3d":
                    tier_counts["in_3d"] += 1
                elif tier == "in_7d":
                    tier_counts["in_7d"] += 1
                elif tier == "in_15d":
                    tier_counts["in_15d"] += 1

                priority_queue.append(c)

        tier_counts["today_overdue"] = tier_counts["overdue"] + tier_counts["today"]
        tier_counts["total"] = (
            tier_counts["today_overdue"] +
            tier_counts["in_3d"] +
            tier_counts["in_7d"] +
            tier_counts["in_15d"]
        )

        # Sort Priority Queue:
        # Priority: overdue/suspended (0) -> today (1) -> in_3d (2) -> in_7d (3) -> in_15d (4)
        def priority_sort_key(item):
            t = item["tier"]
            order = {"overdue": 0, "today": 1, "in_3d": 2, "in_7d": 3, "in_15d": 4}.get(t, 5)
            rem = item["days_remaining"] if item["days_remaining"] is not None else -9999
            return (order, rem)

        priority_queue.sort(key=priority_sort_key)

        # 4. Financial Statistics for Target Month
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as total_collected,
                   COUNT(*) as tx_count
            FROM collections
            WHERE strftime('%Y-%m', collected_at) = ? AND amount > 0
        """, (target_month,))
        fin_row = cursor.fetchone()
        collected_month_sar = round(float(fin_row["total_collected"] or 0.0), 2)
        collections_count = int(fin_row["tx_count"] or 0)

        # Outstanding & Collection Target
        outstanding_sar = round(outstanding_sar, 2)
        target_revenue_sar = round(collected_month_sar + outstanding_sar, 2)
        collection_rate = (
            round((collected_month_sar / target_revenue_sar * 100), 1)
            if target_revenue_sar > 0 else 100.0
        )

        # 5. Dashboard subscriber capacity limit (defaults to 1,500 subscribers, configurable via ISP_CAPACITY_LIMIT)
        try:
            configured_capacity = max(1000, int(os.getenv('ISP_CAPACITY_LIMIT', '1500')))
        except (TypeError, ValueError):
            configured_capacity = 1500

        # Dynamically auto-scale capacity if total active subscribers approach or exceed configured limit
        capacity_limit = max(configured_capacity, max(1000, ((len(active_customers) // 500) + 1) * 500))
        capacity_percent = min(100.0, round((len(active_customers) / capacity_limit * 100), 1))
        capacity_limit_formatted = f"{capacity_limit:,}"

        # 6. Staff Performance Breakdown for Target Month
        cursor.execute("""
            SELECT collected_by,
                   COUNT(*) as tx_count,
                   COALESCE(SUM(amount), 0.0) as total_amount,
                   COALESCE(AVG(amount), 0.0) as avg_amount
            FROM collections
            WHERE strftime('%Y-%m', collected_at) = ? AND amount > 0
            GROUP BY collected_by
            ORDER BY total_amount DESC
        """, (target_month,))
        staff_rows = cursor.fetchall()
        staff_performance = []
        for s in staff_rows:
            tot = round(float(s["total_amount"] or 0.0), 2)
            share = round((tot / collected_month_sar * 100), 1) if collected_month_sar > 0 else 0.0
            staff_performance.append({
                "collector_name": s["collected_by"] or "Admin",
                "tx_count": int(s["tx_count"] or 0),
                "total_amount": tot,
                "avg_amount": round(float(s["avg_amount"] or 0.0), 2),
                "share_percent": share
            })

        # 7. Recent Collections Feed (Last 12 transactions)
        cursor.execute("""
            SELECT col.*, c.name as customer_name, c.phone as customer_phone
            FROM collections col
            LEFT JOIN customers c ON col.customer_id = c.id
            ORDER BY col.id DESC
            LIMIT 12
        """)
        recent_collections = [dict(r) for r in cursor.fetchall()]

        return {
            "target_month": target_month,
            "month_label": month_label,
            "available_months": available_months,
            "total_subscribers": total_customers,
            "active_subscribers": len(active_customers),
            "suspended_count": len(suspended_customers),
            "capacity_limit": capacity_limit,
            "capacity_limit_formatted": capacity_limit_formatted,
            "capacity_percent": capacity_percent,
            "total_approved_devices": total_approved_devices,
            "online_devices": online_approved_devices,
            "connectivity_rate": connectivity_rate,
            "active_subscribers_online": active_subscribers_online,
            "collected_month_sar": collected_month_sar,
            "collections_count": collections_count,
            "outstanding_sar": outstanding_sar,
            "due_customers_count": due_customers_count,
            "target_revenue_sar": target_revenue_sar,
            "collection_rate": collection_rate,
            "expiring_tiers": tier_counts,
            "priority_queue": priority_queue,
            "all_customers": all_custs,
            "staff_performance": staff_performance,
            "recent_collections": recent_collections
        }


def get_date_range_report(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Generates custom date range financial & collection report (from billing_reminder).
    """
    clean_start = (start_date.strip() if start_date else "")[:10]
    clean_end = (end_date.strip() if end_date else "")[:10]

    with get_db() as conn:
        cursor = conn.cursor()

        # Ledger records in date range
        cursor.execute("""
            SELECT col.*, c.name as customer_name, c.phone as customer_phone, c.package_name
            FROM collections col
            LEFT JOIN customers c ON col.customer_id = c.id
            WHERE date(col.collected_at) >= date(?) AND date(col.collected_at) <= date(?)
            ORDER BY col.collected_at DESC, col.id DESC
        """, (clean_start, clean_end))
        items = [dict(r) for r in cursor.fetchall()]

        # Totals
        total_collected = sum(float(i.get("amount") or 0.0) for i in items if float(i.get("amount") or 0.0) > 0)
        unique_customers = len({i["customer_id"] for i in items if i.get("customer_id")})
        tx_count = len([i for i in items if float(i.get("amount") or 0.0) > 0])
        avg_tx = round(total_collected / tx_count, 2) if tx_count > 0 else 0.0

        # Staff breakdown for range
        cursor.execute("""
            SELECT collected_by,
                   COUNT(*) as tx_count,
                   COALESCE(SUM(amount), 0.0) as total_amount
            FROM collections
            WHERE date(collected_at) >= date(?) AND date(collected_at) <= date(?) AND amount > 0
            GROUP BY collected_by
            ORDER BY total_amount DESC
        """, (clean_start, clean_end))
        staff = [dict(r) for r in cursor.fetchall()]

        return {
            "start_date": clean_start,
            "end_date": clean_end,
            "total_collected": round(total_collected, 2),
            "tx_count": tx_count,
            "unique_customers": unique_customers,
            "avg_transaction": avg_tx,
            "items": items,
            "staff_breakdown": staff
        }


# =========================================================
# Step 5: OLT & Fiber PON Plant Management
# =========================================================

def get_all_olts() -> List[Dict[str, Any]]:
    """Returns list of all OLT chassis with live ONU counts and telemetry."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM olts ORDER BY id ASC")
        olts = [dict(r) for r in cursor.fetchall()]

        for olt in olts:
            oid = olt["id"]
            cursor.execute("SELECT COUNT(*) as tot, SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as onl FROM onus WHERE olt_id = ?", (oid,))
            counts = cursor.fetchone()
            olt["total_onus"] = int(counts["tot"] or 0)
            olt["online_onus"] = int(counts["onl"] or 0)
            olt["offline_onus"] = olt["total_onus"] - olt["online_onus"]

            cursor.execute("SELECT COUNT(*) FROM unconfigured_onus WHERE olt_id = ? AND status = 'unassigned'", (oid,))
            olt["unconfigured_count"] = int(cursor.fetchone()[0] or 0)
        return olts


def get_olt_details(olt_id: int) -> Optional[Dict[str, Any]]:
    """Returns detailed OLT chassis info including PON ports rack visualizer data."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM olts WHERE id = ?", (olt_id,))
        row = cursor.fetchone()
        if not row:
            return None
        olt = dict(row)

        # PON Ports breakdown
        pon_count = int(olt.get("pon_ports_count") or 4)
        ports = []
        for p in range(1, pon_count + 1):
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_onus,
                    SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_onus,
                    AVG(rx_power) as avg_rx
                FROM onus 
                WHERE olt_id = ? AND pon_port = ?
            """, (olt_id, p))
            p_stat = cursor.fetchone()
            tot = int(p_stat["total_onus"] or 0)
            onl = int(p_stat["online_onus"] or 0)
            ports.append({
                "port_number": p,
                "name": f"PON {p}",
                "total_onus": tot,
                "online_onus": onl,
                "max_capacity": 128,
                "utilization_percent": min(100.0, round((tot / 128) * 100, 1)),
                "tx_power_dbm": "+2.5 dBm",
                "avg_rx_dbm": round(float(p_stat["avg_rx"] or -19.0), 1) if tot > 0 else "—",
                "status": "up" if tot > 0 else "idle"
            })
        olt["ports"] = ports

        # Uplink Ports (ge1, ge2, ge3)
        olt["uplink_ports"] = [
            {"name": "ge1 (Copper)", "type": "1000Base-T", "status": "up", "speed": "1 Gbps", "comment": "MikroTik ether4 (192.168.200.1 / VLAN 10 Untagged)"},
            {"name": "ge2 (Copper)", "type": "1000Base-T", "status": "idle", "speed": "1 Gbps", "comment": "Copper Uplink 2 (VLAN 30 Untagged)"},
            {"name": "ge3 (SFP Optical)", "type": "1G SFP Optical (850nm)", "status": "up", "speed": "1 Gbps", "comment": "MikroTik sfp1 Hotspot (10.50.0.1/22 / VLAN 20 Untagged)"}
        ]

        return olt


def get_onus(
    olt_id: Optional[int] = None,
    pon_port: Optional[int] = None,
    status_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Returns filtered ONUs / ONTs with linked customer and optical signal telemetry."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT 
                onu.*,
                o.name as olt_name, o.model as olt_model, o.brand as olt_brand,
                c.name as customer_name, c.phone as customer_phone, c.billing_type as customer_billing_type,
                c.package_name as customer_package, c.status as customer_account_status
            FROM onus onu
            JOIN olts o ON onu.olt_id = o.id
            LEFT JOIN customers c ON onu.customer_id = c.id
            WHERE 1=1
        """
        params = []
        if olt_id:
            query += " AND onu.olt_id = ?"
            params.append(olt_id)
        if pon_port:
            query += " AND onu.pon_port = ?"
            params.append(pon_port)
        if status_filter and status_filter.lower() != "all":
            if status_filter == "good":
                query += " AND onu.rx_power >= -24.0"
            elif status_filter == "warning":
                query += " AND onu.rx_power < -24.0 AND onu.rx_power >= -27.0"
            elif status_filter == "critical":
                query += " AND onu.rx_power < -27.0"
            elif status_filter == "unassigned":
                query += " AND onu.customer_id IS NULL"
            else:
                query += " AND onu.status = ?"
                params.append(status_filter)

        query += " ORDER BY onu.pon_port ASC, onu.onu_id ASC"
        cursor.execute(query, tuple(params))
        
        onus = []
        for r in cursor.fetchall():
            item = dict(r)
            rx = float(item.get("rx_power") or -20.0)
            
            # Optical Signal Health Evaluation
            if rx >= -24.0:
                item["signal_quality"] = "good"
                item["signal_badge"] = "Good"
                item["signal_color"] = "#34d399"
            elif rx >= -27.0:
                item["signal_quality"] = "warning"
                item["signal_badge"] = "High Loss"
                item["signal_color"] = "#fbbf24"
            else:
                item["signal_quality"] = "critical"
                item["signal_badge"] = "Critical Attenuation"
                item["signal_color"] = "#f87171"

            item["distance_km"] = round(int(item.get("distance_m") or 0) / 1000, 2)
            onus.append(item)

        return onus


def get_unconfigured_onus(olt_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Returns newly discovered optical ONUs waiting for technician authorization."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT u.*, o.name as olt_name, o.model as olt_model
            FROM unconfigured_onus u
            JOIN olts o ON u.olt_id = o.id
            WHERE u.status = 'unassigned'
        """
        params = []
        if olt_id:
            query += " AND u.olt_id = ?"
            params.append(olt_id)
        query += " ORDER BY u.discovered_at DESC"
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]


def get_olt_kpis(olt_id: Optional[int] = None) -> Dict[str, Any]:
    """Computes high-level optical health and inventory KPIs for an OLT."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM onus WHERE 1=1"
        params = []
        if olt_id:
            query += " AND olt_id = ?"
            params.append(olt_id)

        cursor.execute(query, tuple(params))
        all_onus = [dict(r) for r in cursor.fetchall()]

        total_onus = len(all_onus)
        online_onus = len([x for x in all_onus if x.get("status") == "online"])
        offline_onus = total_onus - online_onus
        los_onus = len([x for x in all_onus if x.get("status") in ("los", "loss_of_signal")])

        good_sig = len([x for x in all_onus if float(x.get("rx_power") or 0) >= -24.0])
        warn_sig = len([x for x in all_onus if -27.0 <= float(x.get("rx_power") or 0) < -24.0])
        crit_sig = len([x for x in all_onus if float(x.get("rx_power") or 0) < -27.0])

        avg_rx = round(sum(float(x.get("rx_power") or 0) for x in all_onus) / total_onus, 1) if total_onus > 0 else -19.5
        online_pct = round((online_onus / total_onus * 100), 1) if total_onus > 0 else 0.0

        # Unconfigured count
        unconf_query = "SELECT COUNT(*) FROM unconfigured_onus WHERE status = 'unassigned'"
        unconf_params = []
        if olt_id:
            unconf_query += " AND olt_id = ?"
            unconf_params.append(olt_id)
        cursor.execute(unconf_query, tuple(unconf_params))
        unconfigured_count = int(cursor.fetchone()[0] or 0)

        return {
            "total_onus": total_onus,
            "online_onus": online_onus,
            "offline_onus": offline_onus,
            "los_onus": los_onus,
            "online_percent": online_pct,
            "good_signal_count": good_sig,
            "warning_signal_count": warn_sig,
            "critical_signal_count": crit_sig,
            "avg_rx_power": avg_rx,
            "unconfigured_count": unconfigured_count
        }


def register_onu(
    olt_id: int,
    pon_port: int,
    serial_number: str,
    name: str,
    customer_id: Optional[int] = None,
    onu_model: Optional[str] = "1GE+1FE+WiFi GPON ONT",
    mode: str = "Routing",
    vlan_id: int = 100,
    mac_address: Optional[str] = None
) -> Dict[str, Any]:
    """Registers and authorizes an ONU/ONT on a PON port."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_sn = serial_number.strip().upper()
    clean_mac = mac_address.strip().upper() if mac_address and mac_address.strip() else None

    with get_db() as conn:
        cursor = conn.cursor()

        # Find next ONU ID for this PON port
        cursor.execute("SELECT COALESCE(MAX(onu_id), 0) + 1 FROM onus WHERE olt_id = ? AND pon_port = ?", (olt_id, pon_port))
        next_onu_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO onus (
                olt_id, pon_port, onu_id, customer_id, serial_number, mac_address,
                name, onu_model, mode, status, rx_power, tx_power, distance_m, vlan_id,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'online', -19.2, 2.2, 750, ?, ?, ?)
        """, (
            olt_id, pon_port, next_onu_id, customer_id, clean_sn, clean_mac,
            name.strip(), onu_model, mode, vlan_id, now_str, now_str
        ))
        new_id = cursor.lastrowid

        # Mark as assigned in unconfigured_onus if present
        cursor.execute("UPDATE unconfigured_onus SET status = 'assigned' WHERE serial_number = ?", (clean_sn,))

        conn.commit()

        cursor.execute("SELECT * FROM onus WHERE id = ?", (new_id,))
        return dict(cursor.fetchone())


def update_onu(
    onu_id: int,
    name: Optional[str] = None,
    customer_id: Optional[int] = None,
    vlan_id: Optional[int] = None,
    mode: Optional[str] = None,
    status: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Updates configuration or customer assignment for an ONU."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM onus WHERE id = ?", (onu_id,))
        row = cursor.fetchone()
        if not row:
            return None

        current = dict(row)
        new_name = name.strip() if name and name.strip() else current["name"]
        new_vlan = int(vlan_id) if vlan_id is not None else current["vlan_id"]
        new_mode = mode if mode else current["mode"]
        new_status = status if status else current["status"]
        new_cust = customer_id if customer_id is not None else current["customer_id"]

        cursor.execute("""
            UPDATE onus
            SET name = ?, customer_id = ?, vlan_id = ?, mode = ?, status = ?, updated_at = ?
            WHERE id = ?
        """, (new_name, new_cust, new_vlan, new_mode, new_status, now_str, onu_id))
        conn.commit()

        cursor.execute("SELECT * FROM onus WHERE id = ?", (onu_id,))
        return dict(cursor.fetchone())


def delete_onu(onu_id: int) -> bool:
    """Deletes an ONU from inventory."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM onus WHERE id = ?", (onu_id,))
        conn.commit()
        return True


def reboot_onu(onu_id: int) -> Dict[str, Any]:
    """Triggers OMCI restart simulation for an ONU."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE onus SET last_status_change = ?, updated_at = ? WHERE id = ?", (now_str, now_str, onu_id))
        conn.commit()
        return {"success": True, "onu_id": onu_id, "rebooted_at": now_str}


def create_olt(
    name: str,
    ip_address: str,
    brand: str = "VSOL",
    model: str = "GPON-4P",
    pon_type: str = "GPON",
    pon_ports_count: int = 4,
    uplink_ports_count: int = 4,
    port: int = 161,
    snmp_community: str = "public",
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """Adds a new OLT chassis to CyberNet OS."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO olts (
                name, model, brand, ip_address, port, pon_type, pon_ports_count,
                uplink_ports_count, status, uptime, cpu_usage, memory_usage, temperature,
                snmp_community, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'online', 'Just Provisioned', 12, 30, 36, ?, ?, ?, ?)
        """, (
            name.strip(), model.strip(), brand.strip(), ip_address.strip(), port,
            pon_type.strip(), pon_ports_count, uplink_ports_count, snmp_community.strip(),
            notes or "", now_str, now_str
        ))
        conn.commit()
        new_id = cursor.lastrowid
        return get_olt_details(new_id)


def get_onu_uptime_ledger(olt_id: Optional[int] = None, onu_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Returns event history of uptime, outages, loss of signal, and power events."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT l.*, o.name as onu_name, o.serial_number, o.pon_port, o.onu_id as onu_idx,
                   c.name as customer_name, c.phone as customer_phone
            FROM onu_uptime_ledger l
            JOIN onus o ON l.onu_id = o.id
            LEFT JOIN customers c ON o.customer_id = c.id
            WHERE 1=1
        """
        params = []
        if olt_id:
            query += " AND o.olt_id = ?"
            params.append(olt_id)
        if onu_id:
            query += " AND l.onu_id = ?"
            params.append(onu_id)
        query += " ORDER BY l.id DESC"
        cursor.execute(query, tuple(params))
        return [dict(r) for r in cursor.fetchall()]


def get_olt_active_errors(olt_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Returns all active errors, fiber cuts (LOS), and degraded optical signals."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT o.*, c.name as customer_name, c.phone as customer_phone
            FROM onus o
            LEFT JOIN customers c ON o.customer_id = c.id
            WHERE (o.status != 'online' OR o.error_severity IN ('warning', 'critical') OR o.rx_power < -25.0)
        """
        params = []
        if olt_id:
            query += " AND o.olt_id = ?"
            params.append(olt_id)
        query += " ORDER BY CASE WHEN o.error_severity = 'critical' OR o.status = 'los' THEN 0 WHEN o.error_severity = 'warning' THEN 1 ELSE 2 END, o.rx_power ASC"
        cursor.execute(query, tuple(params))
        errors = []
        for r in cursor.fetchall():
            item = dict(r)
            rx = float(item.get("rx_power") or 0.0)
            status = item.get("status")
            item["distance_km"] = round(int(item.get("distance_m") or 0) / 1000, 2)
            
            if status == "los" or rx <= -30.0:
                item["diag_title"] = "Optical Loss of Signal (LOS / Fiber Break)" if status == "los" else f"Critical Low Optical Signal ({rx:.1f} dBm)"
                item["diag_severity"] = "critical"
                item["diag_badge"] = "CRITICAL FIBER BREAK" if status == "los" else "CRITICAL LOW SIGNAL"
                item["diag_solution"] = "Inspect drop cable, optical splitter port, or customer fiber wall socket."
                item["signal_color"] = "#f87171"
            elif rx <= -27.0:
                item["diag_title"] = f"Severe Optical Attenuation ({rx:.1f} dBm)"
                item["diag_severity"] = "critical"
                item["diag_badge"] = "CRITICAL ATTENUATION"
                item["diag_solution"] = "Fiber bend or dirty connector. Clean SC/APC connector with fiber pen."
                item["signal_color"] = "#f87171"
            elif rx < -25.0:
                item["diag_title"] = f"High Optical Loss ({rx:.1f} dBm)"
                item["diag_severity"] = "warning"
                item["diag_badge"] = "HIGH LOSS WARNING"
                item["diag_solution"] = "Check fiber patch cord for tight bends or splitter insertion loss."
                item["signal_color"] = "#fbbf24"
            elif status in ("power_off", "dying_gasp"):
                item["diag_title"] = "Subscriber Power Disconnected (Dying Gasp)"
                item["diag_severity"] = "warning"
                item["diag_badge"] = "POWER OFF"
                item["diag_solution"] = "Customer premise ONT is turned off or power adapter unplugged."
                item["signal_color"] = "#fbbf24"
            else:
                item["diag_title"] = item.get("last_error") or "Unknown Warning"
                item["diag_severity"] = "warning"
                item["diag_badge"] = "WARNING"
                item["diag_solution"] = "Monitor optical link stability."
                item["signal_color"] = "#fbbf24"

            errors.append(item)
        return errors


def update_onu_name(onu_id: int, new_name: str) -> Optional[Dict[str, Any]]:
    """Simple rename of an ONU."""
    clean_name = new_name.strip()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE onus SET name = ?, updated_at = ? WHERE id = ?", (clean_name, now_str, onu_id))
        conn.commit()
        cursor.execute("SELECT * FROM onus WHERE id = ?", (onu_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def sync_olt_live_telemetry(
    olt_id: int,
    onus_data: List[Dict[str, Any]],
    chassis_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Synchronizes real hardware telemetry from OLT and connected ONUs.
    - Updates ONU Rx power, link status ('online', 'offline', 'dying_gasp'), distance, errors.
    - Appends events to onu_uptime_ledger if link state changes or critical events occur.
    - Updates chassis status, temperature, CPU, memory, and updated_at.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Update chassis if chassis_info provided
        if chassis_info:
            cursor.execute("""
                UPDATE olts
                SET updated_at = ?,
                    status = COALESCE(?, status),
                    temperature = COALESCE(?, temperature),
                    cpu_usage = COALESCE(?, cpu_usage),
                    memory_usage = COALESCE(?, memory_usage),
                    uptime = COALESCE(?, uptime)
                WHERE id = ?
            """, (
                now_str,
                chassis_info.get("status", "online"),
                chassis_info.get("temperature"),
                chassis_info.get("cpu_usage"),
                chassis_info.get("memory_usage"),
                chassis_info.get("uptime"),
                olt_id
            ))
        else:
            cursor.execute("UPDATE olts SET updated_at = ? WHERE id = ?", (now_str, olt_id))

        # 2. Map existing ONUs by onu_id / index
        cursor.execute("SELECT * FROM onus WHERE olt_id = ?", (olt_id,))
        existing_rows = {r["onu_id"]: dict(r) for r in cursor.fetchall()}

        updated_count = 0
        new_events_count = 0

        for item in onus_data:
            idx = int(item.get("id") or item.get("onu_id") or 0)
            if idx <= 0:
                continue

            rx = float(item.get("rx_power") or -20.0)
            status = str(item.get("status") or "online").lower()
            phase = str(item.get("phase") or "").lower()
            sn = str(item.get("serial") or item.get("serial_number") or "").strip()
            name = str(item.get("name") or "").strip()
            model = str(item.get("model") or item.get("onu_model") or "").strip()
            dist = int(item.get("distance_m") or 100)

            # Determine diagnostic error and severity
            if phase == "dyinggasp" or status in ("dying_gasp", "power_off"):
                status = "dying_gasp"
                err = "🚨 Dying Gasp Outage (Customer Power Loss)"
                sev = "critical"
            elif phase == "offline" or status in ("offline", "los"):
                status = "offline"
                err = "🚨 Critical Fiber Break (LOS / Signal Disconnected)"
                sev = "critical"
            elif rx <= -30.0:
                err = f"Critical Low Optical Power ({rx:.2f} dBm < -30 dBm limit)"
                sev = "critical"
            elif rx <= -25.0:
                err = f"High Optical Loss ({rx:.2f} dBm > -25 dBm limit)"
                sev = "warning"
            else:
                err = "None (Normal Operation)"
                sev = "normal"

            prev = existing_rows.get(idx)
            if prev:
                prev_id = prev["id"]
                prev_status = prev.get("status")
                prev_sev = prev.get("error_severity")

                # Check for state transition -> log event
                if prev_status != status or (sev == "critical" and prev_sev != "critical"):
                    event_type = "warning" if sev == "warning" else ("offline" if status in ("offline", "dying_gasp") else ("online" if status == "online" else "warning"))
                    reason = err
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, ?, ?, 'Just now', ?, ?)
                    """, (prev_id, event_type, now_str, reason, rx))
                    new_events_count += 1
                elif prev_status in ("offline", "dying_gasp") and status == "online":
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, 'recovered', ?, 'Recovered', 'Optical link recovered & operating normally', ?)
                    """, (prev_id, now_str, rx))
                    new_events_count += 1

                # Preserve existing custom name if item has generic or empty name
                final_name = prev.get("name") if (not name or name.startswith("ONU ")) else name
                final_model = model if model else prev.get("onu_model")
                final_sn = sn if sn else prev.get("serial_number")

                cursor.execute("""
                    UPDATE onus
                    SET status = ?,
                        rx_power = ?,
                        distance_m = ?,
                        last_error = ?,
                        error_severity = ?,
                        name = COALESCE(?, name),
                        onu_model = COALESCE(?, onu_model),
                        serial_number = COALESCE(?, serial_number),
                        updated_at = ?
                    WHERE id = ?
                """, (
                    status, rx, dist, err, sev,
                    final_name, final_model, final_sn,
                    now_str, prev_id
                ))
                updated_count += 1
            else:
                cursor.execute("""
                    INSERT INTO onus (
                        olt_id, pon_port, onu_id, customer_id, serial_number, mac_address,
                        name, onu_model, mode, status, rx_power, tx_power, distance_m, vlan_id,
                        uptime, last_error, error_severity, flaps_count, availability_pct,
                        created_at, updated_at
                    )
                    VALUES (
                        ?, 1, ?, NULL, ?, NULL,
                        ?, ?, 'Routing', ?, ?, 2.3, ?, 10,
                        '18d 4h 12m', ?, ?, 0, 99.8,
                        ?, ?
                    )
                """, (
                    olt_id, idx, sn or f"GPON000000{idx:02d}",
                    name or f"ONU {idx}", model or "VSOL V711 (XPON HGU)",
                    status, rx, dist, err, sev,
                    now_str, now_str
                ))
                updated_count += 1

        conn.commit()

        # Get latest statistics
        cursor.execute("SELECT COUNT(*) as tot, SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as onl FROM onus WHERE olt_id = ?", (olt_id,))
        stat = cursor.fetchone()
        tot = int(stat["tot"] or 0)
        onl = int(stat["onl"] or 0)

        cursor.execute("SELECT COUNT(*) FROM onus WHERE olt_id = ? AND (status != 'online' OR error_severity != 'normal')", (olt_id,))
        err_cnt = int(cursor.fetchone()[0] or 0)

        return {
            "success": True,
            "olt_id": olt_id,
            "total_onus": tot,
            "online_onus": onl,
            "offline_onus": tot - onl,
            "active_errors": err_cnt,
            "new_events_logged": new_events_count,
            "updated_at": now_str
        }


# =========================================================================
# WHATSAPP MESSAGING & AUDIT LEDGER HELPERS
# =========================================================================
def get_whatsapp_settings() -> Dict[str, str]:
    """Retrieves all WhatsApp system configuration key-values."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM whatsapp_settings")
        return {r["key"]: r["value"] for r in cursor.fetchall()}


def update_whatsapp_settings(updates: Dict[str, str]) -> Dict[str, str]:
    """Updates one or more WhatsApp configuration keys."""
    with get_db() as conn:
        cursor = conn.cursor()
        for k, v in updates.items():
            cursor.execute("""
                INSERT INTO whatsapp_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (str(k), str(v)))
        conn.commit()
    return get_whatsapp_settings()


def log_whatsapp_message(
    phone: str,
    message_body: str,
    message_type: str = "manual",
    status: str = "sent",
    error_message: Optional[str] = None,
    customer_id: Optional[int] = None,
    customer_name: Optional[str] = None,
    sent_by: str = "admin"
) -> int:
    """Records an outgoing or blocked WhatsApp dispatch to the permanent audit ledger."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO whatsapp_logs (
                customer_id, customer_name, phone, message_type,
                message_body, status, error_message, sent_by, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (customer_id, customer_name, phone, message_type, message_body, status, error_message, sent_by, now_str))
        conn.commit()
        return cursor.lastrowid


def get_whatsapp_logs(
    limit: int = 100,
    status_filter: str = "all",
    search: str = ""
) -> List[Dict[str, Any]]:
    """Retrieves historical WhatsApp outbox logs with optional filtering."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT l.*, c.name as resolved_customer_name
            FROM whatsapp_logs l
            LEFT JOIN customers c ON l.customer_id = c.id
            WHERE 1=1
        """
        params = []
        if status_filter and status_filter != "all":
            query += " AND l.status = ?"
            params.append(status_filter)
        if search:
            query += " AND (l.phone LIKE ? OR l.customer_name LIKE ? OR l.message_body LIKE ?)"
            s_pat = f"%{search}%"
            params.extend([s_pat, s_pat, s_pat])

        query += " ORDER BY l.id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = []
        for r in cursor.fetchall():
            item = dict(r)
            item["display_name"] = item.get("resolved_customer_name") or item.get("customer_name") or "Direct Number"
            rows.append(item)
        return rows


def get_due_customers_for_whatsapp() -> List[Dict[str, Any]]:
    """
    Returns active subscribers with overdue, expiring, or pending monthly bills,
    formatted specifically for the WhatsApp reminder assistant.
    """
    all_custs = get_all_customers()
    due_list = []
    for c in all_custs:
        b_type = c.get("billing_type", "prepaid")
        is_exp = c.get("is_expired", False)
        days_rem = c.get("days_remaining")
        credit = c.get("credit_balance", 0.0)
        fee = float(c.get("monthly_fee", 0.0))

        is_due = False
        effective_due = fee

        if b_type == "postpaid":
            is_due = True
            effective_due = max(0.0, fee - credit) if credit < fee else fee
        elif is_exp or (days_rem is not None and days_rem <= 3):
            is_due = True
            effective_due = fee
        elif c.get("status") in ("suspended", "expired"):
            is_due = True
            effective_due = fee

        if is_due:
            c["effective_due"] = round(effective_due, 2)
            c["customer_type"] = b_type
            c["building"] = c.get("building") or "HQ / Plant"
            c["apartment"] = c.get("apartment") or "1"
            c["room"] = c.get("room") or "1"
            due_list.append(c)

    due_list.sort(key=lambda x: x["effective_due"], reverse=True)
    return due_list


get_customers = get_all_customers


# =========================================================================
# MIKROTIK MULTI-ROUTER FLEET HELPERS
# =========================================================================
def get_all_routers(active_only: bool = False) -> List[Dict[str, Any]]:
    """Retrieves all registered MikroTik routers in the fleet."""
    with get_db() as conn:
        cursor = conn.cursor()
        q = "SELECT * FROM routers"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY is_default DESC, id ASC"
        cursor.execute(q)
        return [dict(r) for r in cursor.fetchall()]


def get_router_by_id(router_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a specific router by primary key."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routers WHERE id = ?", (router_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_router(
    name: str,
    host: str,
    port: int = 8728,
    username: str = "admin",
    password: str = "",
    vlan_id: Optional[int] = 10,
    ssid_name: Optional[str] = "CyberNet-WiFi",
    uplink_type: Optional[str] = "Zain SIM",
    is_active: int = 1
) -> Dict[str, Any]:
    """Adds a new MikroTik hardware router to the fleet."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO routers (
                name, host, port, username, password, vlan_id, ssid_name,
                uplink_type, is_active, is_default, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            name.strip(), host.strip(), port, username.strip(), password,
            vlan_id or 10, ssid_name.strip() if ssid_name else "",
            uplink_type.strip() if uplink_type else "",
            1 if is_active else 0, now_str, now_str
        ))
        conn.commit()
        rid = cursor.lastrowid
        cursor.execute("SELECT * FROM routers WHERE id = ?", (rid,))
        return dict(cursor.fetchone())


def update_router(
    router_id: int,
    name: str,
    host: str,
    port: int = 8728,
    username: str = "admin",
    password: Optional[str] = None,
    vlan_id: Optional[int] = None,
    ssid_name: Optional[str] = None,
    uplink_type: Optional[str] = None,
    is_active: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Updates configuration for an existing router."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM routers WHERE id = ?", (router_id,))
        existing = cursor.fetchone()
        if not existing:
            return None
        existing = dict(existing)

        pwd = password if (password is not None and password != "") else existing["password"]
        act = is_active if is_active is not None else existing["is_active"]
        vlan = vlan_id if vlan_id is not None else existing["vlan_id"]
        ssid = ssid_name if ssid_name is not None else existing["ssid_name"]
        uplink = uplink_type if uplink_type is not None else existing["uplink_type"]

        cursor.execute("""
            UPDATE routers SET
                name = ?, host = ?, port = ?, username = ?, password = ?,
                vlan_id = ?, ssid_name = ?, uplink_type = ?, is_active = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            name.strip(), host.strip(), port, username.strip(), pwd,
            vlan, ssid, uplink, act, now_str, router_id
        ))
        conn.commit()
        cursor.execute("SELECT * FROM routers WHERE id = ?", (router_id,))
        return dict(cursor.fetchone())


def delete_router(router_id: int) -> bool:
    """Removes a router from the fleet."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM routers WHERE id = ?", (router_id,))
        conn.commit()
        return cursor.rowcount > 0


def update_router_telemetry(
    router_id: int,
    identity: Optional[str] = None,
    model: Optional[str] = None,
    ros_version: Optional[str] = None,
    cpu_usage: Optional[int] = None,
    memory_usage: Optional[int] = None,
    uptime: Optional[str] = None,
    last_status: str = "online"
):
    """Caches live telemetry metrics for a router in the fleet."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE routers SET
                identity = COALESCE(?, identity),
                model = COALESCE(?, model),
                ros_version = COALESCE(?, ros_version),
                cpu_usage = COALESCE(?, cpu_usage),
                memory_usage = COALESCE(?, memory_usage),
                uptime = COALESCE(?, uptime),
                last_status = ?,
                last_seen = ?
            WHERE id = ?
        """, (identity, model, ros_version, cpu_usage, memory_usage, uptime, last_status, now_str, router_id))
        conn.commit()


def get_collections_hub_data(
    period: str = "month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search_query: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves comprehensive balance sheet metrics, due customer queues,
    and filtered collection transactions for the Collections & Ledger Hub.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    today_str = now.strftime("%Y-%m-%d")
    current_month = now.strftime("%Y-%m")

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Today's collections
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as total, COUNT(*) as tx_count
            FROM collections
            WHERE date(collected_at) = date('now', 'localtime') AND amount > 0
        """)
        today_row = cursor.fetchone()
        today_collected = round(float(today_row["total"] or 0.0), 2)
        today_tx_count = int(today_row["tx_count"] or 0)

        # 2. Month-to-Date collections
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as total, COUNT(*) as tx_count
            FROM collections
            WHERE strftime('%Y-%m', collected_at) = ? AND amount > 0
        """, (current_month,))
        month_row = cursor.fetchone()
        month_collected = round(float(month_row["total"] or 0.0), 2)
        month_tx_count = int(month_row["tx_count"] or 0)

        # 3. Customer Credit Liabilities (Total credit held across all customer wallets)
        cursor.execute("""
            SELECT COALESCE(SUM(credit_balance), 0.0) as total_credit,
                   COUNT(CASE WHEN credit_balance > 0 THEN 1 END) as credit_holders_count
            FROM customers
        """)
        credit_row = cursor.fetchone()
        total_credit_held = round(float(credit_row["total_credit"] or 0.0), 2)
        credit_holders_count = int(credit_row["credit_holders_count"] or 0)

        # 4. Due Customers & Accounts Receivable
        all_customers = get_all_customers()
        due_customers_queue = []
        for c in all_customers:
            days_rem = c.get("days_remaining")
            status = c.get("status", "active")
            is_grace = bool(c.get("is_grace_held"))
            is_due = (days_rem is not None and days_rem <= 3) or (status == "suspended") or is_grace
            if is_due:
                fee = float(c.get("monthly_fee") or 0.0)
                wallet_credit = float(c.get("credit_balance") or 0.0)
                net_needed = max(0.0, round(fee - wallet_credit, 2))
                c_copy = dict(c)
                if is_grace:
                    daily_r = round(fee / 30.0, 4)
                    try:
                        p_day = int(str(c.get("suspension_held_until", "")).split("-")[2])
                        accrued_amt = round(min(p_day, 30) * daily_r, 2)
                    except Exception:
                        accrued_amt = fee
                    net_needed = max(0.0, round((fee + accrued_amt) - wallet_credit, 2))
                    c_copy["accrued_grace_amount"] = accrued_amt
                c_copy["net_due_amount"] = net_needed
                c_copy["can_settle_from_credit"] = (wallet_credit >= fee and fee > 0)
                due_customers_queue.append(c_copy)

        def due_sort_key(item):
            # Grace hold (0), Suspended (1), expired (2), due today (3), due soon (4)
            if item.get("is_grace_held"):
                return (0, 0)
            if item.get("status") == "suspended":
                return (1, item.get("days_remaining") or 0)
            d = item.get("days_remaining")
            if d is not None and d < 0:
                return (2, d)
            if d == 0:
                return (3, 0)
            return (4, d or 999)

        due_customers_queue.sort(key=due_sort_key)
        outstanding_receivable = round(sum(item["net_due_amount"] for item in due_customers_queue), 2)
        due_count = len(due_customers_queue)

        projected_monthly_revenue = round(sum(float(c.get("monthly_fee") or 0.0) for c in all_customers if c.get("status") == "active"), 2)
        total_cycle_revenue = round(month_collected + outstanding_receivable, 2)
        collection_efficiency = round((month_collected / total_cycle_revenue * 100), 1) if total_cycle_revenue > 0 else 100.0

        # 5. Filtered Ledger Records
        where_clauses = ["1=1"]
        params = []

        if period == "today":
            where_clauses.append("date(col.collected_at) = date('now', 'localtime')")
        elif period == "yesterday":
            where_clauses.append("date(col.collected_at) = date('now', 'localtime', '-1 day')")
        elif period == "week":
            where_clauses.append("date(col.collected_at) >= date('now', 'localtime', 'weekday 0', '-7 days')")
        elif period == "month":
            where_clauses.append("strftime('%Y-%m', col.collected_at) = ?")
            params.append(current_month)
        elif period == "custom" and start_date and end_date:
            where_clauses.append("date(col.collected_at) >= date(?) AND date(col.collected_at) <= date(?)")
            params.extend([start_date.strip()[:10], end_date.strip()[:10]])
        # "all" has no date constraint

        if search_query and search_query.strip():
            sq = f"%{search_query.strip().lower()}%"
            where_clauses.append("(lower(c.name) LIKE ? OR c.phone LIKE ? OR lower(col.notes) LIKE ? OR lower(col.collected_by) LIKE ?)")
            params.extend([sq, sq, sq, sq])

        where_sql = " AND ".join(where_clauses)

        cursor.execute(f"""
            SELECT col.*, c.name as customer_name, c.phone as customer_phone, c.package_name, c.monthly_fee as current_monthly_fee
            FROM collections col
            LEFT JOIN customers c ON col.customer_id = c.id
            WHERE {where_sql}
            ORDER BY col.id DESC
            LIMIT 300
        """, tuple(params))
        ledger_records = [dict(r) for r in cursor.fetchall()]

        filtered_total = round(sum(float(r.get("amount") or 0.0) for r in ledger_records if float(r.get("amount") or 0.0) > 0), 2)
        filtered_tx_count = len(ledger_records)

        # Minimal customer list for the Express Collect search selector
        all_customers_minimal = [
            {
                "id": c["id"],
                "name": c["name"],
                "phone": c["phone"],
                "package_name": c.get("package_name") or "Standard",
                "monthly_fee": float(c.get("monthly_fee") or 0.0),
                "credit_balance": float(c.get("credit_balance") or 0.0),
                "due_date": c.get("due_date") or c.get("expiry_date") or "",
                "days_remaining": c.get("days_remaining"),
                "status": c.get("status", "active"),
                "is_grace_held": c.get("is_grace_held", False),
                "suspension_held_until": c.get("suspension_held_until")
            }
            for c in all_customers
        ]

        return {
            "balance_sheet": {
                "today_collected": today_collected,
                "today_tx_count": today_tx_count,
                "month_collected": month_collected,
                "month_tx_count": month_tx_count,
                "outstanding_receivable": outstanding_receivable,
                "due_customers_count": due_count,
                "total_credit_held": total_credit_held,
                "credit_holders_count": credit_holders_count,
                "projected_monthly_revenue": projected_monthly_revenue,
                "collection_efficiency": collection_efficiency,
                "total_subscribers": len(all_customers),
                "current_month_label": now.strftime("%B %Y")
            },
            "due_queue": due_customers_queue,
            "ledger": ledger_records,
            "filtered_total": filtered_total,
            "filtered_tx_count": filtered_tx_count,
            "period": period,
            "customers_dropdown": all_customers_minimal
        }


def get_collection_by_id(collection_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single collection transaction with customer details."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT col.*, cust.name as customer_name, cust.phone as customer_phone
            FROM collections col
            LEFT JOIN customers cust ON col.customer_id = cust.id
            WHERE col.id = ?
        """, (collection_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_collection(
    collection_id: int,
    amount: float,
    notes: str,
    collected_at: Optional[str] = None,
    collected_by: Optional[str] = None,
    billing_type: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Updates amount, notes, timestamp, collector, or billing type of a collection record."""
    clean_amt = round(float(amount or 0.0), 2)
    clean_notes = (notes or "").strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM collections WHERE id = ?", (collection_id,))
        old = cursor.fetchone()
        if not old:
            return None

        final_at = collected_at.strip() if (collected_at and collected_at.strip()) else old["collected_at"]
        final_by = collected_by.strip() if (collected_by and collected_by.strip()) else old["collected_by"]
        final_type = billing_type.strip() if (billing_type and billing_type.strip()) else old["billing_type"]
        month_yr = final_at[:7] if len(final_at) >= 7 else old["month_year"]

        cursor.execute("""
            UPDATE collections
            SET amount = ?, notes = ?, collected_at = ?, collected_by = ?, billing_type = ?, month_year = ?
            WHERE id = ?
        """, (clean_amt, clean_notes, final_at, final_by, final_type, month_yr, collection_id))
        conn.commit()

        cursor.execute("""
            SELECT col.*, cust.name as customer_name, cust.phone as customer_phone
            FROM collections col
            LEFT JOIN customers cust ON col.customer_id = cust.id
            WHERE col.id = ?
        """, (collection_id,))
        return dict(cursor.fetchone())


def delete_collection(collection_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Permanently deletes a collection entry and adjusts customer collected_today if applicable."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT col.*, cust.name as customer_name, cust.phone as customer_phone
            FROM collections col
            LEFT JOIN customers cust ON col.customer_id = cust.id
            WHERE col.id = ?
        """, (collection_id,))
        row = cursor.fetchone()
        if not row:
            return False, None
        col = dict(row)

        cust_id = col.get("customer_id")
        amt = float(col.get("amount") or 0.0)

        # If customer had collected_today set from this payment, adjust collected_today
        if cust_id and amt > 0:
            cursor.execute("SELECT collected_today, credit_balance FROM customers WHERE id = ?", (cust_id,))
            cust_row = cursor.fetchone()
            if cust_row:
                curr_collected = float(cust_row["collected_today"] or 0.0)
                if curr_collected > 0:
                    new_collected = max(0.0, round(curr_collected - amt, 2))
                    cursor.execute("UPDATE customers SET collected_today = ? WHERE id = ?", (new_collected, cust_id))

        cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        conn.commit()
        return True, col


# =========================================================
# Reseller Partner Operations & Wallet Ledger
# =========================================================


def topup_reseller_wallet(
    reseller_id: int,
    amount: float,
    notes: Optional[str] = None,
    created_by: str = "Admin"
) -> Tuple[bool, str, float]:
    """
    Tops up a reseller's prepaid wallet balance.
    Logs transaction in reseller_wallet_ledger.
    Returns (success, message, new_balance).
    """
    clean_amt = float(amount or 0.0)
    if clean_amt <= 0:
        return False, "Top-up amount must be greater than 0.", 0.0

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, wallet_balance, is_active FROM admin_users WHERE id = ? AND role = 'reseller'", (reseller_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Reseller partner not found.", 0.0

        reseller = dict(row)
        if not reseller.get("is_active", 1):
            return False, "This reseller partner account is suspended.", float(reseller.get("wallet_balance") or 0.0)

        balance_before = float(reseller.get("wallet_balance") or 0.0)
        balance_after = round(balance_before + clean_amt, 2)

        # Update wallet
        cursor.execute("UPDATE admin_users SET wallet_balance = ?, updated_at = ? WHERE id = ?", (balance_after, now_str, reseller_id))

        # Log ledger entry
        cursor.execute("""
            INSERT INTO reseller_wallet_ledger (
                reseller_id, type, amount, balance_before, balance_after,
                customer_id, description, created_by, created_at
            )
            VALUES (?, 'topup', ?, ?, ?, NULL, ?, ?, ?)
        """, (
            reseller_id, clean_amt, balance_before, balance_after,
            notes or f"Prepaid wallet credit top-up (+{clean_amt:.2f} SAR)",
            created_by or "Admin", now_str
        ))
        conn.commit()

        return True, f"Successfully credited {clean_amt:.2f} SAR. New balance: {balance_after:.2f} SAR", balance_after


def reseller_recharge_customer(
    reseller_id: int,
    customer_id: int,
    months: int = 1,
    notes: Optional[str] = None,
    operator_username: Optional[str] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Reseller Fast Recharge POS operation:
    1. Validates reseller wallet balance.
    2. Applies partner discount according to commission_rate.
    3. Deducts net cost from reseller's wallet.
    4. Automatically extends customer's due/expiry date and reactivates subscriber.
    5. Records entry in reseller_wallet_ledger and customer collections audit ledger.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    clean_months = max(1, int(months or 1))

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Fetch reseller
        cursor.execute("SELECT id, username, full_name, role, is_active, wallet_balance, commission_rate, shop_name FROM admin_users WHERE id = ?", (reseller_id,))
        r_row = cursor.fetchone()
        if not r_row:
            return False, "Reseller not found.", {}
        reseller = dict(r_row)

        if not reseller.get("is_active", 1):
            return False, "Reseller account is deactivated.", {}

        # 2. Fetch customer
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        c_row = cursor.fetchone()
        if not c_row:
            return False, f"Customer #{customer_id} not found.", {}
        cust = dict(c_row)

        # Check reseller assignment (or auto-assign if customer was unassigned)
        current_reseller = cust.get("reseller_id")
        if current_reseller and current_reseller != reseller_id and reseller.get("role") == "reseller":
            return False, "This subscriber belongs to another agency/partner.", {}

        monthly_fee = float(cust.get("monthly_fee") or 0.0)
        if monthly_fee <= 0:
            monthly_fee = 30.0  # Default plan fee fallback

        gross_amount = round(monthly_fee * clean_months, 2)
        commission_rate = float(reseller.get("commission_rate") or 0.0)
        # Net deduction with partner commission discount
        discount_factor = max(0.0, min(1.0, 1.0 - (commission_rate / 100.0)))
        net_deduction = round(gross_amount * discount_factor, 2)

        wallet_balance = float(reseller.get("wallet_balance") or 0.0)
        if wallet_balance < net_deduction:
            return False, f"Insufficient wallet balance ({wallet_balance:.2f} SAR). Need {net_deduction:.2f} SAR to recharge {clean_months} month(s).", {
                "wallet_balance": wallet_balance,
                "required_amount": net_deduction
            }

        balance_after = round(wallet_balance - net_deduction, 2)

        # 3. Deduct from reseller wallet
        cursor.execute("UPDATE admin_users SET wallet_balance = ?, updated_at = ? WHERE id = ?", (balance_after, now_str, reseller_id))

        # 4. Record in reseller wallet ledger
        ledger_desc = f"Recharge for {cust['name']} ({cust['phone']}) - {clean_months} month(s) [{gross_amount:.2f} SAR fee, {commission_rate:.1f}% discount = {net_deduction:.2f} SAR deducted]"
        cursor.execute("""
            INSERT INTO reseller_wallet_ledger (
                reseller_id, type, amount, balance_before, balance_after,
                customer_id, description, created_by, created_at
            )
            VALUES (?, 'recharge_deduction', ?, ?, ?, ?, ?, ?, ?)
        """, (
            reseller_id, net_deduction, wallet_balance, balance_after,
            customer_id, ledger_desc, operator_username or reseller.get("username") or "Reseller", now_str
        ))

        # 5. Extend customer expiry & due date
        added_days = clean_months * 30
        current_exp = cust.get("expiry_date") or cust.get("due_date")
        try:
            base_dt = datetime.strptime(current_exp.split()[0], "%Y-%m-%d")
            calc_base = max(base_dt, now)
        except Exception:
            calc_base = now

        new_expiry = (calc_base + timedelta(days=added_days)).strftime("%Y-%m-%d")
        try:
            new_due_day = int(new_expiry.split("-")[2])
        except Exception:
            new_due_day = cust.get("due_day") or 1

        cursor.execute("""
            UPDATE customers
            SET expiry_date = ?, due_date = ?, due_day = ?, status = 'active',
                billing_type = 'prepaid', reseller_id = ?, updated_at = ?
            WHERE id = ?
        """, (new_expiry, new_expiry, new_due_day, reseller_id, now_str, customer_id))

        # 6. Unblock customer devices
        cursor.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))

        # 7. Record in master collections ledger
        shop_label = reseller.get("shop_name") or reseller.get("username")
        col_notes = f"[Reseller: {shop_label}] {notes or 'Prepaid Cycle Renewal'} ({clean_months} mo until {new_expiry})"
        cursor.execute("""
            INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
            VALUES (?, ?, 'prepaid', ?, ?, ?)
        """, (
            customer_id, gross_amount, col_notes, now_str,
            operator_username or reseller.get("username") or "Reseller"
        ))

        conn.commit()

        return True, f"Recharge confirmed! Line active until {new_expiry}. Deducted {net_deduction:.2f} SAR.", {
            "customer_id": customer_id,
            "customer_name": cust.get("name"),
            "customer_phone": cust.get("phone"),
            "months": clean_months,
            "gross_amount": gross_amount,
            "commission_rate": commission_rate,
            "net_deduction": net_deduction,
            "wallet_balance": balance_after,
            "new_expiry_date": new_expiry,
            "recorded_at": now_str
        }


def get_reseller_wallet_ledger(
    reseller_id: Optional[int] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Fetches wallet ledger entries with reseller and customer names."""
    with get_db() as conn:
        cursor = conn.cursor()
        where_sql = ""
        params = []
        if reseller_id is not None:
            where_sql = "WHERE l.reseller_id = ?"
            params.append(reseller_id)
        params.append(limit)

        cursor.execute(f"""
            SELECT 
                l.*,
                COALESCE(u.username, '') as reseller_username,
                COALESCE(u.shop_name, '') as reseller_shop_name,
                COALESCE(c.name, '') as customer_name,
                COALESCE(c.phone, '') as customer_phone
            FROM reseller_wallet_ledger l
            LEFT JOIN admin_users u ON l.reseller_id = u.id
            LEFT JOIN customers c ON l.customer_id = c.id
            {where_sql}
            ORDER BY l.id DESC
            LIMIT ?
        """, params)
        return [dict(r) for r in cursor.fetchall()]


def get_reseller_stats(reseller_id: int) -> Dict[str, Any]:
    """Calculates summary KPIs for a specific reseller."""
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")
    today_prefix = now.strftime("%Y-%m-%d")

    with get_db() as conn:
        cursor = conn.cursor()

        # Reseller info
        cursor.execute("SELECT id, username, full_name, wallet_balance, commission_rate, shop_name, phone FROM admin_users WHERE id = ?", (reseller_id,))
        res_row = cursor.fetchone()
        reseller = dict(res_row) if res_row else {}

        # Customers
        cursor.execute("SELECT COUNT(*) as total, COUNT(CASE WHEN status = 'active' THEN 1 END) as active FROM customers WHERE reseller_id = ?", (reseller_id,))
        c_stats = dict(cursor.fetchone() or {})

        # Sales month
        cursor.execute("""
            SELECT COALESCE(SUM(col.amount), 0.0) as month_sales, COUNT(*) as month_tx
            FROM collections col
            JOIN customers c ON col.customer_id = c.id
            WHERE c.reseller_id = ? AND col.collected_at LIKE ?
        """, (reseller_id, f"{month_prefix}%"))
        m_sales = dict(cursor.fetchone() or {})

        # Sales today
        cursor.execute("""
            SELECT COALESCE(SUM(col.amount), 0.0) as today_sales, COUNT(*) as today_tx
            FROM collections col
            JOIN customers c ON col.customer_id = c.id
            WHERE c.reseller_id = ? AND col.collected_at LIKE ?
        """, (reseller_id, f"{today_prefix}%"))
        t_sales = dict(cursor.fetchone() or {})

        return {
            "reseller": reseller,
            "total_customers": c_stats.get("total", 0),
            "active_customers": c_stats.get("active", 0),
            "month_sales": float(m_sales.get("month_sales", 0.0)),
            "month_tx_count": int(m_sales.get("month_tx", 0)),
            "today_sales": float(t_sales.get("today_sales", 0.0)),
            "today_tx_count": int(t_sales.get("today_tx", 0)),
            "wallet_balance": float(reseller.get("wallet_balance", 0.0)),
            "commission_rate": float(reseller.get("commission_rate", 0.0))
        }


# =========================================================
# Step 8: Customer Internet Traffic & 90-Day Bandwidth Audit
# =========================================================

def format_bytes_display(b: Any) -> str:
    try:
        n = float(b or 0)
        if n >= 1024 ** 3:
            return f"{n / (1024 ** 3):.2f} GB"
        elif n >= 1024 ** 2:
            return f"{n / (1024 ** 2):.1f} MB"
        elif n >= 1024:
            return f"{n / 1024:.0f} KB"
        return f"{int(n)} B"
    except Exception:
        return "0 B"


def format_seconds_display(sec: Any) -> str:
    try:
        s = int(sec or 0)
        if s <= 0:
            return "0m"
        hours = s // 3600
        minutes = (s % 3600) // 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    except Exception:
        return "0m"


def clean_device_friendly_name(stored_name: Optional[str], dhcp_host_name: Optional[str] = None) -> str:
    """Provides a human-friendly device label instead of user-agent strings."""
    if dhcp_host_name and dhcp_host_name.strip() and dhcp_host_name not in ("*", "—", "unknown"):
        clean_dhcp = dhcp_host_name.strip().replace("-", " ")
        if not stored_name or "Mozilla" in stored_name or "AppleWebKit" in stored_name:
            return clean_dhcp

    if not stored_name or not stored_name.strip():
        return dhcp_host_name or "Client Device"

    name = stored_name.strip()
    if "Mozilla" in name or "AppleWebKit" in name:
        if "iPhone" in name:
            return "Apple iPhone"
        if "iPad" in name:
            return "Apple iPad"
        if "Android" in name:
            return "Android Device"
        if "Macintosh" in name or "Mac OS" in name:
            return "Apple Mac"
        if "Windows" in name:
            return "Windows PC"
        if "Linux" in name:
            return "Linux Device"
        return "Mobile Device"

    if len(name) > 28:
        return name[:26] + "…"
    return name


def record_device_traffic_delta(
    mac_address: str,
    download_bytes: int,
    upload_bytes: int,
    active_seconds: int = 60,
    ip_address: Optional[str] = None
) -> bool:
    """
    Persistently records incremental traffic delta for a client MAC address.
    Updates customer_traffic_hourly, customer_traffic_daily, and active connection sessions.
    """
    if not mac_address:
        return False
    mac_clean = mac_address.strip().upper()
    total_bytes = max(0, download_bytes) + max(0, upload_bytes)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    hour_int = now.hour
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()

        # Find customer & device mapping
        cursor.execute("""
            SELECT id, customer_id, device_name 
            FROM customer_devices 
            WHERE UPPER(mac_address) = ? AND status = 'approved'
            LIMIT 1
        """, (mac_clean,))
        dev_row = cursor.fetchone()

        customer_id = None
        device_id = None
        device_name = "Client Device"

        if dev_row:
            device_id = dev_row["id"]
            customer_id = dev_row["customer_id"]
            device_name = dev_row["device_name"] or "Client Device"
        else:
            # Check connection requests if linked to a customer
            cursor.execute("""
                SELECT customer_id, device_model 
                FROM connection_requests 
                WHERE UPPER(mac_address) = ? AND customer_id IS NOT NULL
                LIMIT 1
            """, (mac_clean,))
            req_row = cursor.fetchone()
            if req_row and req_row["customer_id"]:
                customer_id = req_row["customer_id"]
                device_name = req_row["device_model"] or "Client Device"

        if not customer_id:
            return False

        # 1. Upsert Hourly Table
        cursor.execute("""
            INSERT INTO customer_traffic_hourly
            (customer_id, mac_address, device_id, date_str, hour_int, download_bytes, upload_bytes, total_bytes, active_seconds, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac_address, date_str, hour_int) DO UPDATE SET
                download_bytes = download_bytes + excluded.download_bytes,
                upload_bytes = upload_bytes + excluded.upload_bytes,
                total_bytes = total_bytes + excluded.total_bytes,
                active_seconds = active_seconds + excluded.active_seconds,
                updated_at = excluded.updated_at
        """, (
            customer_id, mac_clean, device_id, date_str, hour_int,
            max(0, download_bytes), max(0, upload_bytes), total_bytes,
            max(0, active_seconds), now_str
        ))

        # 2. Upsert Daily Table
        cursor.execute("""
            INSERT INTO customer_traffic_daily
            (customer_id, mac_address, device_id, date_str, download_bytes, upload_bytes, total_bytes, active_seconds, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mac_address, date_str) DO UPDATE SET
                download_bytes = download_bytes + excluded.download_bytes,
                upload_bytes = upload_bytes + excluded.upload_bytes,
                total_bytes = total_bytes + excluded.total_bytes,
                active_seconds = active_seconds + excluded.active_seconds,
                updated_at = excluded.updated_at
        """, (
            customer_id, mac_clean, device_id, date_str,
            max(0, download_bytes), max(0, upload_bytes), total_bytes,
            max(0, active_seconds), now_str
        ))

        # 3. Connection Session Tracking
        cursor.execute("""
            SELECT id, duration_seconds 
            FROM customer_connection_sessions 
            WHERE UPPER(mac_address) = ? AND is_active = 1
            ORDER BY id DESC LIMIT 1
        """, (mac_clean,))
        active_sess = cursor.fetchone()

        if active_sess:
            cursor.execute("""
                UPDATE customer_connection_sessions
                SET last_seen_at = ?,
                    duration_seconds = duration_seconds + ?,
                    download_bytes = download_bytes + ?,
                    upload_bytes = upload_bytes + ?,
                    total_bytes = total_bytes + ?,
                    ip_address = COALESCE(?, ip_address)
                WHERE id = ?
            """, (
                now_str, max(0, active_seconds), max(0, download_bytes), max(0, upload_bytes),
                total_bytes, ip_address, active_sess["id"]
            ))
        else:
            # Start new live connection session
            cursor.execute("""
                INSERT INTO customer_connection_sessions
                (customer_id, mac_address, device_name, ip_address, started_at, last_seen_at, duration_seconds, download_bytes, upload_bytes, total_bytes, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                customer_id, mac_clean, device_name, ip_address,
                now_str, now_str, max(0, active_seconds),
                max(0, download_bytes), max(0, upload_bytes), total_bytes
            ))

        conn.commit()
        return True


def close_device_session(mac_address: str) -> bool:
    """Closes active connection session when device disconnects from router."""
    if not mac_address:
        return False
    mac_clean = mac_address.strip().upper()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE customer_connection_sessions
            SET is_active = 0, closed_at = COALESCE(last_seen_at, ?)
            WHERE UPPER(mac_address) = ? AND is_active = 1
        """, (now_str, mac_clean))
        conn.commit()
        return cursor.rowcount > 0


def purge_old_traffic_logs(days_to_keep: int = 90) -> int:
    """Purges historical traffic logs and closed sessions older than days_to_keep."""
    cutoff_date = (datetime.now().date() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
    cutoff_datetime = f"{cutoff_date} 00:00:00"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM customer_traffic_hourly WHERE date_str < ?", (cutoff_date,))
        deleted_hourly = cursor.rowcount
        cursor.execute("DELETE FROM customer_traffic_daily WHERE date_str < ?", (cutoff_date,))
        deleted_daily = cursor.rowcount
        cursor.execute("DELETE FROM customer_connection_sessions WHERE is_active = 0 AND started_at < ?", (cutoff_datetime,))
        deleted_sessions = cursor.rowcount
        conn.commit()
        return deleted_hourly + deleted_daily + deleted_sessions


def get_customer_usage_analytics(
    customer_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns comprehensive 90-day bandwidth and internet usage audit for a customer:
    - Executive summary KPI metrics
    - 24-hour distribution (hourly bars)
    - Day-by-day table records with visual intensity
    - Per-device MAC breakdown
    - Timestamped session audit logs
    """
    now = datetime.now()
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (now.date() - timedelta(days=30)).strftime("%Y-%m-%d")

    # Ensure start <= end
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    with get_db() as conn:
        cursor = conn.cursor()

        # Customer basic profile
        cursor.execute("""
            SELECT id, name, phone, package_name, monthly_fee, speed_limit, billing_type, status, due_date, expiry_date, max_devices, join_date, billing_start_date
            FROM customers WHERE id = ?
        """, (customer_id,))
        cust_row = cursor.fetchone()
        if not cust_row:
            return {}
        customer = dict(cust_row)

        # Approved devices
        cursor.execute("""
            SELECT id, mac_address, device_name, ip_address, status, created_at
            FROM customer_devices WHERE customer_id = ? AND status = 'approved'
            ORDER BY id ASC
        """, (customer_id,))
        approved_devices = [dict(d) for d in cursor.fetchall()]

        # 1. Summary Totals
        cursor.execute("""
            SELECT 
                COALESCE(SUM(download_bytes), 0) as total_down,
                COALESCE(SUM(upload_bytes), 0) as total_up,
                COALESCE(SUM(total_bytes), 0) as total_bytes,
                COALESCE(SUM(active_seconds), 0) as total_sec,
                COUNT(DISTINCT date_str) as days_with_traffic
            FROM customer_traffic_daily
            WHERE customer_id = ? AND date_str >= ? AND date_str <= ?
        """, (customer_id, start_date, end_date))
        tot_row = dict(cursor.fetchone() or {})

        total_down = int(tot_row.get("total_down", 0))
        total_up = int(tot_row.get("total_up", 0))
        total_bytes = int(tot_row.get("total_bytes", 0))
        total_sec = int(tot_row.get("total_sec", 0))

        # Calculate number of days in range
        try:
            d_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            d_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            range_days = max(1, (d_end - d_start).days + 1)
        except Exception:
            range_days = 30

        daily_avg_bytes = total_bytes // range_days if range_days > 0 else 0

        # Percentages
        down_percent = round((total_down / total_bytes * 100), 1) if total_bytes > 0 else 0.0
        up_percent = round((total_up / total_bytes * 100), 1) if total_bytes > 0 else 0.0

        # Peak Hour
        cursor.execute("""
            SELECT hour_int, SUM(total_bytes) as hr_total
            FROM customer_traffic_hourly
            WHERE customer_id = ? AND date_str >= ? AND date_str <= ?
            GROUP BY hour_int
            ORDER BY hr_total DESC
            LIMIT 1
        """, (customer_id, start_date, end_date))
        peak_hr_row = cursor.fetchone()
        peak_hour_int = peak_hr_row["hour_int"] if peak_hr_row else 20
        peak_hour_bytes = peak_hr_row["hr_total"] if peak_hr_row else 0
        peak_hour_label = f"{peak_hour_int:02d}:00 - {((peak_hour_int + 1) % 24):02d}:00"

        # Peak Day
        cursor.execute("""
            SELECT date_str, SUM(total_bytes) as day_total
            FROM customer_traffic_daily
            WHERE customer_id = ? AND date_str >= ? AND date_str <= ?
            GROUP BY date_str
            ORDER BY day_total DESC
            LIMIT 1
        """, (customer_id, start_date, end_date))
        peak_day_row = cursor.fetchone()
        peak_day_str = peak_day_row["date_str"] if peak_day_row else (now.strftime("%Y-%m-%d"))
        peak_day_bytes = peak_day_row["day_total"] if peak_day_row else 0
        try:
            peak_day_name = datetime.strptime(peak_day_str, "%Y-%m-%d").strftime("%A, %b %d")
        except Exception:
            peak_day_name = peak_day_str

        # 2. Hourly Distribution (0..23)
        cursor.execute("""
            SELECT 
                hour_int,
                COALESCE(SUM(download_bytes), 0) as down,
                COALESCE(SUM(upload_bytes), 0) as up,
                COALESCE(SUM(total_bytes), 0) as total
            FROM customer_traffic_hourly
            WHERE customer_id = ? AND date_str >= ? AND date_str <= ?
            GROUP BY hour_int
        """, (customer_id, start_date, end_date))
        hr_map = {r["hour_int"]: dict(r) for r in cursor.fetchall()}

        max_hr_total = max([h.get("total", 0) for h in hr_map.values()] + [1])

        hourly_dist = []
        for h in range(24):
            data = hr_map.get(h, {"down": 0, "up": 0, "total": 0})
            h_tot = data["total"]
            hourly_dist.append({
                "hour": h,
                "hour_label": f"{h:02d}:00",
                "download_bytes": data["down"],
                "upload_bytes": data["up"],
                "total_bytes": h_tot,
                "formatted_down": format_bytes_display(data["down"]),
                "formatted_up": format_bytes_display(data["up"]),
                "formatted_total": format_bytes_display(h_tot),
                "is_peak": (h == peak_hour_int and h_tot > 0),
                "height_percent": round((h_tot / max_hr_total * 100), 1) if max_hr_total > 0 else 0
            })

        # 3. Daily Records (sorted date DESC)
        cursor.execute("""
            SELECT 
                date_str,
                COALESCE(SUM(download_bytes), 0) as down,
                COALESCE(SUM(upload_bytes), 0) as up,
                COALESCE(SUM(total_bytes), 0) as total,
                COALESCE(SUM(active_seconds), 0) as active_sec,
                COUNT(DISTINCT mac_address) as dev_count
            FROM customer_traffic_daily
            WHERE customer_id = ? AND date_str >= ? AND date_str <= ?
            GROUP BY date_str
            ORDER BY date_str DESC
        """, (customer_id, start_date, end_date))
        daily_rows = cursor.fetchall()
        max_day_total = max([r["total"] for r in daily_rows] + [1])

        daily_records = []
        for r in daily_rows:
            d_str = r["date_str"]
            try:
                dt = datetime.strptime(d_str, "%Y-%m-%d")
                d_formatted = dt.strftime("%b %d, %Y")
                day_name = dt.strftime("%a")
                is_weekend = dt.weekday() in (4, 5)
            except Exception:
                d_formatted = d_str
                day_name = "—"
                is_weekend = False

            d_tot = r["total"]
            daily_records.append({
                "date_str": d_str,
                "date_formatted": d_formatted,
                "day_name": day_name,
                "is_weekend": is_weekend,
                "download_bytes": r["down"],
                "upload_bytes": r["up"],
                "total_bytes": d_tot,
                "formatted_down": format_bytes_display(r["down"]),
                "formatted_up": format_bytes_display(r["up"]),
                "formatted_total": format_bytes_display(d_tot),
                "active_seconds": r["active_sec"],
                "formatted_active_time": format_seconds_display(r["active_sec"]),
                "dev_count": r["dev_count"],
                "is_peak": (d_str == peak_day_str and d_tot > 0),
                "intensity_percent": round((d_tot / max_day_total * 100), 1) if max_day_total > 0 else 0
            })

        # 4. Device Breakdown
        cursor.execute("""
            SELECT 
                d.mac_address,
                COALESCE(SUM(d.download_bytes), 0) as down,
                COALESCE(SUM(d.upload_bytes), 0) as up,
                COALESCE(SUM(d.total_bytes), 0) as total,
                COALESCE(SUM(d.active_seconds), 0) as sec
            FROM customer_traffic_daily d
            WHERE d.customer_id = ? AND d.date_str >= ? AND d.date_str <= ?
            GROUP BY d.mac_address
            ORDER BY total DESC
        """, (customer_id, start_date, end_date))
        dev_usage_rows = cursor.fetchall()

        dev_meta_map = {d["mac_address"].upper(): d for d in approved_devices}

        device_breakdown = []
        for r in dev_usage_rows:
            mac = r["mac_address"].upper()
            meta = dev_meta_map.get(mac, {})
            d_tot = r["total"]
            share_pct = round((d_tot / total_bytes * 100), 1) if total_bytes > 0 else 0.0

            raw_name = meta.get("device_name") or "Client Device"
            friendly = clean_device_friendly_name(raw_name)

            device_breakdown.append({
                "mac_address": mac,
                "device_id": meta.get("id"),
                "device_name": raw_name,
                "friendly_name": friendly,
                "ip_address": meta.get("ip_address") or "—",
                "download_bytes": r["down"],
                "upload_bytes": r["up"],
                "total_bytes": d_tot,
                "formatted_down": format_bytes_display(r["down"]),
                "formatted_up": format_bytes_display(r["up"]),
                "formatted_total": format_bytes_display(d_tot),
                "active_seconds": r["sec"],
                "formatted_active_time": format_seconds_display(r["sec"]),
                "share_percent": share_pct
            })

        seen_macs = {r["mac_address"].upper() for r in dev_usage_rows}
        for d in approved_devices:
            m = d["mac_address"].upper()
            if m not in seen_macs:
                device_breakdown.append({
                    "mac_address": m,
                    "device_id": d["id"],
                    "device_name": d.get("device_name") or "Client Device",
                    "friendly_name": clean_device_friendly_name(d.get("device_name")),
                    "ip_address": d.get("ip_address") or "—",
                    "download_bytes": 0,
                    "upload_bytes": 0,
                    "total_bytes": 0,
                    "formatted_down": "0 B",
                    "formatted_up": "0 B",
                    "formatted_total": "0 B",
                    "active_seconds": 0,
                    "formatted_active_time": "0m",
                    "share_percent": 0.0
                })

        # 5. Recent Sessions (last 30)
        cursor.execute("""
            SELECT id, mac_address, device_name, ip_address, started_at, last_seen_at, closed_at,
                   duration_seconds, download_bytes, upload_bytes, total_bytes, is_active
            FROM customer_connection_sessions
            WHERE customer_id = ?
            ORDER BY id DESC
            LIMIT 30
        """, (customer_id,))
        sess_rows = cursor.fetchall()
        session_logs = []
        for s in sess_rows:
            item = dict(s)
            item["formatted_down"] = format_bytes_display(item["download_bytes"])
            item["formatted_up"] = format_bytes_display(item["upload_bytes"])
            item["formatted_total"] = format_bytes_display(item["total_bytes"])
            item["formatted_duration"] = format_seconds_display(item["duration_seconds"])
            item["friendly_name"] = clean_device_friendly_name(item.get("device_name"))
            session_logs.append(item)

        return {
            "customer": customer,
            "period": {
                "start_date": start_date,
                "end_date": end_date,
                "days_count": range_days
            },
            "summary": {
                "total_download_bytes": total_down,
                "total_upload_bytes": total_up,
                "total_bytes": total_bytes,
                "total_active_seconds": total_sec,
                "formatted_down": format_bytes_display(total_down),
                "formatted_up": format_bytes_display(total_up),
                "formatted_total": format_bytes_display(total_bytes),
                "formatted_active_time": format_seconds_display(total_sec),
                "down_percent": down_percent,
                "up_percent": up_percent,
                "daily_avg_bytes": daily_avg_bytes,
                "formatted_daily_avg": format_bytes_display(daily_avg_bytes),
                "peak_hour": {
                    "hour": peak_hour_int,
                    "label": peak_hour_label,
                    "total_bytes": peak_hour_bytes,
                    "formatted_total": format_bytes_display(peak_hour_bytes)
                },
                "peak_day": {
                    "date_str": peak_day_str,
                    "formatted_name": peak_day_name,
                    "total_bytes": peak_day_bytes,
                    "formatted_total": format_bytes_display(peak_day_bytes)
                }
            },
            "hourly_distribution": hourly_dist,
            "daily_records": daily_records,
            "device_breakdown": device_breakdown,
            "recent_sessions": session_logs
        }


def seed_historical_usage_if_empty():
    """
    Disabled: only real live traffic from MikroTik accounting collector will be populated.
    """
    return


def clear_all_traffic_history() -> Dict[str, int]:
    """
    Truncates all recorded internet usage, daily rollups, hourly tables, and connection sessions.
    Returns counts of deleted records.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM customer_traffic_hourly")
        h_cnt = cursor.rowcount
        cursor.execute("DELETE FROM customer_traffic_daily")
        d_cnt = cursor.rowcount
        cursor.execute("DELETE FROM customer_connection_sessions")
        s_cnt = cursor.rowcount
        conn.commit()
        return {
            "hourly_deleted": h_cnt,
            "daily_deleted": d_cnt,
            "sessions_deleted": s_cnt
        }


# ============================================================
# DEDICATED CUSTOMER BALANCE SHEET & FINANCIAL LEDGER ENGINE
# Native CyberNet OS (isp_v2.db) subscriber accounts
# Replicates and modernizes portal.php?page=balance
# ============================================================

def normalize_saudi_phone_number(raw: Optional[str]) -> str:
    """Normalizes Saudi mobile to international 9665xxxxxxxx format."""
    if not raw:
        return ""
    digits = re.sub(r"[^0-9]", "", str(raw).strip())
    if digits.startswith("0") and len(digits) == 10:
        return "966" + digits[1:]
    elif digits.startswith("5") and len(digits) == 9:
        return "966" + digits
    return digits


def get_balance_sheet_data(
    status_filter: str = "all",
    search_query: Optional[str] = None,
    source: Optional[str] = None
) -> Dict[str, Any]:
    """
    Returns real-time CyberNet OS subscriber balance sheet data.
    Matches the exact accounting rules of CyberNet billing_reminder (portal.php?page=balance):
    - Billable days from start date to yesterday inclusive
    - Daily rate = fee / 30
    - Total owed = round(billable_days * daily_rate, 2)
    - Total paid = sum(collections.amount)
    - Balance = round(total_paid - total_owed, 2)
    - Status: CREDIT (> 0), SETTLED (== 0), OWING (< 0)
    - Sorted by highest debt owing first (most negative balance), then alphabetically by name.
    Strictly for CyberNet OS existing customers. No duplicates, no external database.
    """
    status_filter = (status_filter or "all").strip().lower()
    q = (search_query or "").strip().lower()

    today = date.today()
    yesterday = today - timedelta(days=1)

    rows: List[Dict[str, Any]] = []
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        col_rows = cur.execute("""
            SELECT customer_id, COALESCE(SUM(amount), 0.0) as total, COUNT(*) as count
            FROM collections
            WHERE amount > 0
            GROUP BY customer_id
        """).fetchall()
        colls_by_cid = {int(r["customer_id"]): float(r["total"] or 0.0) for r in col_rows}
        colls_count_by_cid = {int(r["customer_id"]): int(r["count"] or 0) for r in col_rows}

        # Load suspensions for all subscribers
        try:
            susp_rows = cur.execute("""
                SELECT customer_id, suspended_at, resumed_at
                FROM customer_suspensions
                ORDER BY id ASC
            """).fetchall()
        except Exception:
            susp_rows = []

        susp_by_cid: Dict[int, List[Tuple[date, Optional[date]]]] = {}
        for s in susp_rows:
            scid = int(s["customer_id"])
            try:
                s_d = datetime.strptime(str(s["suspended_at"])[:10], "%Y-%m-%d").date()
                r_d = datetime.strptime(str(s["resumed_at"])[:10], "%Y-%m-%d").date() if s["resumed_at"] else None
                susp_by_cid.setdefault(scid, []).append((s_d, r_d))
            except Exception:
                pass

        custs = cur.execute("""
            SELECT id, name, phone, notes, monthly_fee, billing_start_date, join_date, status, credit_balance, due_day
            FROM customers
            WHERE status != 'deleted'
            ORDER BY id ASC
        """).fetchall()

        for c in custs:
            cid = int(c["id"])
            raw_fee = c["monthly_fee"]
            fee = float(raw_fee) if raw_fee is not None else 30.0
            daily_rate = round(fee / 30.0, 4) if fee > 0 else 0.0

            start_str = c["billing_start_date"] or c["join_date"] or today.strftime("%Y-%m-%d")
            try:
                start_d = datetime.strptime(str(start_str)[:10], "%Y-%m-%d").date()
            except Exception:
                start_d = today

            cust_susp = list(susp_by_cid.get(cid, []))
            is_currently_suspended = (str(c["status"]).strip().lower() == "suspended")
            if is_currently_suspended and not any(r_d is None for _, r_d in cust_susp):
                cust_susp.append((today, None))

            billable = 0
            cur_d = start_d
            while cur_d <= yesterday:
                in_susp = False
                for s_start, s_end in cust_susp:
                    if s_end is None:
                        if cur_d >= s_start:
                            in_susp = True
                            break
                    else:
                        if s_start <= cur_d <= s_end:
                            in_susp = True
                            break
                if not in_susp:
                    billable += 1
                cur_d += timedelta(days=1)

            owed = round(billable * daily_rate, 2) if fee > 0 else 0.0
            paid = round(colls_by_cid.get(cid, 0.0), 2)
            bal = round(paid - owed, 2)
            st = "CREDIT" if bal > 0 else ("SETTLED" if bal == 0 else "OWING")

            phone_str = str(c["phone"] or "").strip()
            norm_mob = normalize_saudi_phone_number(phone_str)

            rows.append({
                "id": cid,
                "name": str(c["name"] or f"Subscriber #{cid}").strip(),
                "mobile": phone_str,
                "norm_phone": norm_mob,
                "room": str(c["notes"] or "").strip(),
                "monthly_fee": fee,
                "daily_rate": daily_rate,
                "billing_start_date": str(start_str)[:10],
                "billable_days": billable,
                "total_owed": owed,
                "total_paid": paid,
                "balance": bal,
                "status": st,
                "is_suspended": is_currently_suspended,
                "payments_count": colls_count_by_cid.get(cid, 0),
                "reminders_enabled": 1
            })

    # Sort highest debt owing first (most negative balance), then alphabetically by name
    rows.sort(key=lambda x: (x["balance"], x["name"].lower()))

    # Compute summary stats across all active CyberNet customers
    grand_owed = round(sum(r["total_owed"] for r in rows), 2)
    grand_paid = round(sum(r["total_paid"] for r in rows), 2)
    grand_net = round(grand_paid - grand_owed, 2)
    owing_count = sum(1 for r in rows if r["balance"] < 0)
    settled_count = sum(1 for r in rows if r["balance"] == 0)
    credit_count = sum(1 for r in rows if r["balance"] > 0)
    total_active = len(rows)
    total_debt_amount = round(sum(abs(r["balance"]) for r in rows if r["balance"] < 0), 2)
    total_credit_amount = round(sum(r["balance"] for r in rows if r["balance"] > 0), 2)

    status_counts = {
        "all": total_active,
        "owing": owing_count,
        "settled": settled_count,
        "credit": credit_count
    }

    # Filter by status if specified
    filtered_rows = rows
    if status_filter == "owing":
        filtered_rows = [r for r in filtered_rows if r["balance"] < 0]
    elif status_filter == "settled":
        filtered_rows = [r for r in filtered_rows if r["balance"] == 0]
    elif status_filter == "credit":
        filtered_rows = [r for r in filtered_rows if r["balance"] > 0]

    # Filter by search query if specified
    if q:
        tokens = [t for t in q.split() if t]
        def row_matches(r: Dict[str, Any]) -> bool:
            searchable = f"{r['name']} {r['mobile']} {r['norm_phone']} {r['room']}".lower()
            return all(
                tok in searchable or (
                    tok.isdigit() and len(tok) >= 2 and (
                        (tok.startswith('05') and ('966' + tok[1:]) in searchable) or
                        (tok.startswith('9665') and ('0' + tok[3:]) in searchable) or
                        (tok.startswith('5') and (('0' + tok in searchable) or ('966' + tok in searchable)))
                    )
                )
                for tok in tokens
            )
        filtered_rows = [r for r in filtered_rows if row_matches(r)]

    return {
        "summary": {
            "grand_owed": grand_owed,
            "grand_paid": grand_paid,
            "grand_net": grand_net,
            "owing_count": owing_count,
            "settled_count": settled_count,
            "credit_count": credit_count,
            "total_active": total_active,
            "total_debt_amount": total_debt_amount,
            "total_credit_amount": total_credit_amount
        },
        "status_counts": status_counts,
        "rows": filtered_rows,
        "status_filter": status_filter,
        "search_query": search_query or ""
    }


def get_balance_customer_history(customer_id: int, source: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns full billing cycle details, rate breakdown, and collection receipts history
    for a CyberNet OS subscriber.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        c = cur.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not c:
            raise ValueError(f"Subscriber #{customer_id} not found in CyberNet database.")

        col_rows = cur.execute("""
            SELECT id, month_year, amount, is_settled, waived_amount, notes,
                   collected_at as collected_date, collected_by as collector
            FROM collections
            WHERE customer_id = ?
            ORDER BY collected_at DESC, id DESC
        """, (customer_id,)).fetchall()
        collections = [dict(cr) for cr in col_rows]

        raw_fee = c["monthly_fee"]
        fee = float(raw_fee) if raw_fee is not None else 30.0
        daily_rate = round(fee / 30.0, 4) if fee > 0 else 0.0

        start_str = c["billing_start_date"] or c["join_date"] or today.strftime("%Y-%m-%d")
        try:
            start_d = datetime.strptime(str(start_str)[:10], "%Y-%m-%d").date()
        except Exception:
            start_d = today

        # Load suspensions for this customer
        try:
            susp_rows = cur.execute("""
                SELECT id, suspended_at, resumed_at, reason
                FROM customer_suspensions
                WHERE customer_id = ?
                ORDER BY id ASC
            """, (customer_id,)).fetchall()
            suspensions_data = [
                {
                    "id": s["id"],
                    "suspended_at": str(s["suspended_at"])[:10],
                    "resumed_at": str(s["resumed_at"])[:10] if s["resumed_at"] else None,
                    "reason": str(s["reason"] or "Suspended")
                }
                for s in susp_rows
            ]
        except Exception:
            suspensions_data = []

        is_currently_suspended = (str(c["status"]).strip().lower() == "suspended")
        cust_susp: List[Tuple[date, Optional[date]]] = []
        for s in suspensions_data:
            try:
                s_d = datetime.strptime(s["suspended_at"], "%Y-%m-%d").date()
                r_d = datetime.strptime(s["resumed_at"], "%Y-%m-%d").date() if s["resumed_at"] else None
                cust_susp.append((s_d, r_d))
            except Exception:
                pass
        if is_currently_suspended and not any(r_d is None for _, r_d in cust_susp):
            cust_susp.append((today, None))

        billable = 0
        cur_d = start_d
        while cur_d <= yesterday:
            in_susp = False
            for s_start, s_end in cust_susp:
                if s_end is None:
                    if cur_d >= s_start:
                        in_susp = True
                        break
                else:
                    if s_start <= cur_d <= s_end:
                        in_susp = True
                        break
            if not in_susp:
                billable += 1
            cur_d += timedelta(days=1)

        total_owed = round(billable * daily_rate, 2) if fee > 0 else 0.0
        total_paid = round(sum(float(cr["amount"] or 0.0) for cr in collections if float(cr["amount"] or 0.0) > 0), 2)
        balance = round(total_paid - total_owed, 2)
        status_label = "CREDIT" if balance > 0 else ("SETTLED" if balance == 0 else "OWING")

        return {
            "customer": {
                "id": c["id"],
                "name": c["name"],
                "mobile": c["phone"],
                "norm_phone": normalize_saudi_phone_number(c["phone"]),
                "room": str(c["notes"] or "").strip(),
                "monthly_fee": fee,
                "daily_rate": daily_rate,
                "billing_start_date": str(start_str)[:10],
                "status": c["status"],
                "is_suspended": is_currently_suspended
            },
            "metrics": {
                "billable_days": billable,
                "total_owed": total_owed,
                "total_paid": total_paid,
                "balance": balance,
                "status": status_label,
                "owes_amount": abs(balance) if balance < 0 else 0.0,
                "is_suspended": is_currently_suspended
            },
            "suspensions": suspensions_data,
            "vacation_holds": suspensions_data,
            "collections": collections
        }


def record_balance_collection(
    customer_id: int,
    amount: float,
    source: Optional[str] = None,
    payment_type: str = "cash",
    collector: str = "Admin",
    notes: str = "",
    month_year: Optional[str] = None
) -> Dict[str, Any]:
    """
    Records collection payment directly into CyberNet OS ledger.
    - Adds record to collections table
    - Restores customer status to active and marks devices approved
    - Updates expiry/due date if monthly fee is covered
    """
    clean_amt = round(float(amount or 0.0), 2)
    if clean_amt <= 0:
        raise ValueError("Collection amount must be greater than 0.00 SAR.")

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    month_str = month_year or now.strftime("%Y-%m")

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT id, name, phone, notes, monthly_fee, expiry_date, due_date, status FROM customers WHERE id = ?", (customer_id,))
        cust_row = cur.fetchone()
        if not cust_row:
            raise ValueError(f"Customer #{customer_id} not found in database.")

        cust = dict(cust_row)
        cust_name = cust.get("name") or f"Subscriber #{customer_id}"

        # 1. Insert collection record
        col_notes = notes.strip() if notes and notes.strip() else f"Balance Sheet Collection ({payment_type})"
        cur.execute("""
            INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by, month_year, is_settled, waived_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0.0)
        """, (customer_id, clean_amt, payment_type or "cash", col_notes, now_str, collector or "Admin", month_str))
        col_id = cur.lastrowid

        # 2. Reactivate customer and devices if previously suspended / blocked
        cur.execute("UPDATE customer_devices SET status = 'approved' WHERE customer_id = ?", (customer_id,))

        # 3. Advance expiry/due date if payment covers monthly cycle
        monthly_fee = float(cust.get("monthly_fee") or 30.0)
        if monthly_fee > 0 and clean_amt >= monthly_fee:
            days_to_add = int(clean_amt // monthly_fee) * 30
            current_exp = cust.get("expiry_date") or cust.get("due_date")
            try:
                base_dt = datetime.strptime(str(current_exp)[:10], "%Y-%m-%d")
                calc_base = max(base_dt, now)
            except Exception:
                calc_base = now
            new_exp = (calc_base + timedelta(days=days_to_add)).strftime("%Y-%m-%d")
            try:
                new_due_day = int(new_exp.split("-")[2])
            except Exception:
                new_due_day = 1
            cur.execute("""
                UPDATE customers
                SET status = 'active', expiry_date = ?, due_date = ?, due_day = ?, updated_at = ?
                WHERE id = ?
            """, (new_exp, new_exp, new_due_day, now_str, customer_id))
        else:
            cur.execute("""
                UPDATE customers
                SET status = 'active', updated_at = ?
                WHERE id = ?
            """, (now_str, customer_id))

        # Close open suspension for this customer if reactivated
        cur.execute("""
            UPDATE customer_suspensions
            SET resumed_at = ?
            WHERE customer_id = ? AND resumed_at IS NULL
        """, (now_str, customer_id))

        conn.commit()

        return {
            "success": True,
            "collection_id": col_id,
            "customer_id": customer_id,
            "customer_name": cust_name,
            "amount": clean_amt,
            "payment_type": payment_type,
            "collected_at": now_str,
            "message": f"Successfully collected {clean_amt:.2f} SAR for {cust_name}!"
        }


def get_monthly_reconciliation(month_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Computes end-of-month financial reconciliation and collector breakdown
    strictly for the calendar month (1st day 00:00:00 to last day 23:59:59).
    Matches the executive reporting requirements of CyberNet OS.
    """
    today = date.today()
    if not month_str or not month_str.strip():
        month_str = today.strftime("%Y-%m")
    else:
        month_str = month_str.strip()[:7]

    try:
        y, m = int(month_str[:4]), int(month_str[5:7])
    except Exception:
        y, m = today.year, today.month
        month_str = f"{y:04d}-{m:02d}"

    dim = calendar.monthrange(y, m)[1]
    start_ts = f"{month_str}-01 00:00:00"
    end_ts = f"{month_str}-{dim:02d} 23:59:59"
    month_label = datetime(y, m, 1).strftime("%B %Y")

    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 1. Total collections within this calendar month window
        stats_row = cur.execute("""
            SELECT COALESCE(SUM(amount), 0.0) as total_amount,
                   COUNT(*) as total_transactions,
                   COUNT(DISTINCT customer_id) as paying_subscribers
            FROM collections
            WHERE collected_at >= ? AND collected_at <= ? AND amount > 0
        """, (start_ts, end_ts)).fetchone()

        total_amount = float(stats_row["total_amount"] or 0.0)
        total_tx = int(stats_row["total_transactions"] or 0)
        paying_subs = int(stats_row["paying_subscribers"] or 0)

        # 2. Total active customers in fleet
        total_active_custs = cur.execute("SELECT COUNT(*) FROM customers WHERE status != 'deleted'").fetchone()[0]
        pending_subs = max(0, total_active_custs - paying_subs)

        # 3. Collections by Staff / Collector
        staff_rows = cur.execute("""
            SELECT collected_by as collector,
                   COUNT(*) as count,
                   COALESCE(SUM(amount), 0.0) as total,
                   COALESCE(AVG(amount), 0.0) as average
            FROM collections
            WHERE collected_at >= ? AND collected_at <= ? AND amount > 0
            GROUP BY collected_by
            ORDER BY total DESC, count DESC
        """, (start_ts, end_ts)).fetchall()

        staff_breakdown = [
            {
                "collector": str(r["collector"] or "System"),
                "count": int(r["count"] or 0),
                "total": round(float(r["total"] or 0.0), 2),
                "average": round(float(r["average"] or 0.0), 2)
            }
            for r in staff_rows
        ]

        # 4. Collections by Payment Method (Cash, Alinma, STC Pay, etc.)
        method_rows = cur.execute("""
            SELECT billing_type as method,
                   COUNT(*) as count,
                   COALESCE(SUM(amount), 0.0) as total
            FROM collections
            WHERE collected_at >= ? AND collected_at <= ? AND amount > 0
            GROUP BY billing_type
            ORDER BY total DESC
        """, (start_ts, end_ts)).fetchall()

        method_breakdown = [
            {
                "method": str(r["method"] or "Cash").title(),
                "count": int(r["count"] or 0),
                "total": round(float(r["total"] or 0.0), 2)
            }
            for r in method_rows
        ]

        # 5. Full itemized collection records for this calendar month
        tx_rows = cur.execute("""
            SELECT c.id, c.customer_id, cu.name as customer_name, cu.phone as mobile, cu.notes as room,
                   c.amount, c.billing_type, c.collected_at, c.collected_by, c.month_year, c.is_settled, c.notes
            FROM collections c
            LEFT JOIN customers cu ON c.customer_id = cu.id
            WHERE c.collected_at >= ? AND c.collected_at <= ? AND c.amount > 0
            ORDER BY c.collected_at DESC, c.id DESC
        """, (start_ts, end_ts)).fetchall()

        transactions = [
            {
                "id": int(r["id"]),
                "customer_id": int(r["customer_id"]),
                "customer_name": str(r["customer_name"] or f"Subscriber #{r['customer_id']}"),
                "mobile": str(r["mobile"] or ""),
                "room": str(r["room"] or ""),
                "amount": round(float(r["amount"] or 0.0), 2),
                "billing_type": str(r["billing_type"] or "cash"),
                "collected_at": str(r["collected_at"] or ""),
                "collected_by": str(r["collected_by"] or "Admin"),
                "month_year": str(r["month_year"] or month_str),
                "is_settled": int(r["is_settled"] or 0),
                "notes": str(r["notes"] or "")
            }
            for r in tx_rows
        ]

        # Generate list of past 12 calendar months for selector
        months_available = []
        cur_m = datetime(today.year, today.month, 1)
        for _ in range(12):
            m_val = cur_m.strftime("%Y-%m")
            m_lbl = cur_m.strftime("%B %Y")
            months_available.append({"value": m_val, "label": m_lbl, "is_selected": (m_val == month_str)})
            prev_m = cur_m.month - 1
            prev_y = cur_m.year
            if prev_m == 0:
                prev_m = 12
                prev_y -= 1
            cur_m = datetime(prev_y, prev_m, 1)

        return {
            "month": month_str,
            "month_label": month_label,
            "start_date": f"{month_str}-01",
            "end_date": f"{month_str}-{dim:02d}",
            "total_collected": round(total_amount, 2),
            "total_transactions": total_tx,
            "paying_subscribers": paying_subs,
            "pending_subscribers": pending_subs,
            "total_active_subscribers": total_active_custs,
            "staff_breakdown": staff_breakdown,
            "method_breakdown": method_breakdown,
            "transactions": transactions,
            "months_available": months_available
        }


