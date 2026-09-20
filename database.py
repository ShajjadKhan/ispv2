"""
Database module for CyberNet OS v2.
Manages customers, devices, connection requests, and billing records using SQLite.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

DB_PATH = os.getenv("DB_PATH", "/home/tserver/isp_v2/isp_v2.db")

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

        # Seed initial OLT and ONUs if none exist
        cursor.execute("SELECT COUNT(*) FROM olts")
        if cursor.fetchone()[0] == 0:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO olts (name, model, brand, ip_address, port, pon_type, pon_ports_count, uplink_ports_count, status, uptime, cpu_usage, memory_usage, temperature, snmp_community, notes, created_at, updated_at)
                VALUES ('Core Hub OLT 1', 'V1600G1-B', 'VSOL', '10.20.30.2', 161, 'GPON', 4, 4, 'online', '18d 4h 12m', 16, 38, 39, 'public', 'Main Optical Distribution Hub (4 PON Ports, Class C+ SFP)', ?, ?)
            """, (now_str, now_str))
            olt_id = cursor.lastrowid

            # Seed sample ONUs linked to existing customers
            cursor.execute("SELECT id FROM customers WHERE id = 2")
            if cursor.fetchone():
                cursor.execute("""
                    INSERT INTO onus (olt_id, pon_port, onu_id, customer_id, serial_number, mac_address, name, onu_model, mode, status, rx_power, tx_power, distance_m, vlan_id, created_at, updated_at)
                    VALUES (?, 1, 1, 2, 'VSOL1A2B3C4D', '3C:38:24:0F:69:74', 'Shajjad Khan Office ONT', 'VSOL V2804RE (4GE+WiFi)', 'Routing', 'online', -18.6, 2.3, 420, 100, ?, ?)
                """, (olt_id, now_str, now_str))

            cursor.execute("SELECT id FROM customers WHERE id = 3")
            if cursor.fetchone():
                cursor.execute("""
                    INSERT INTO onus (olt_id, pon_port, onu_id, customer_id, serial_number, mac_address, name, onu_model, mode, status, rx_power, tx_power, distance_m, vlan_id, created_at, updated_at)
                    VALUES (?, 1, 2, 3, 'HWTC5E6F7A8B', '11:22:33:44:55', 'Ahmed Al-Mansoor Residence ONT', 'Huawei HG8546M (1GE+3FE+WiFi)', 'Routing', 'online', -21.4, 2.1, 1150, 100, ?, ?)
                """, (olt_id, now_str, now_str))

            cursor.execute("SELECT id FROM customers WHERE id = 5")
            if cursor.fetchone():
                cursor.execute("""
                    INSERT INTO onus (olt_id, pon_port, onu_id, customer_id, serial_number, mac_address, name, onu_model, mode, status, rx_power, tx_power, distance_m, vlan_id, created_at, updated_at)
                    VALUES (?, 2, 1, 5, 'ZTEG9C8B7A6F', NULL, 'Advance Test Postpaid Fiber ONT', 'ZTE F670L (Dual Band AC)', 'Routing', 'online', -25.8, 1.9, 1840, 100, ?, ?)
                """, (olt_id, now_str, now_str))

            cursor.execute("SELECT id FROM customers WHERE id = 6")
            if cursor.fetchone():
                cursor.execute("""
                    INSERT INTO onus (olt_id, pon_port, onu_id, customer_id, serial_number, mac_address, name, onu_model, mode, status, rx_power, tx_power, distance_m, vlan_id, created_at, updated_at)
                    VALUES (?, 3, 1, 6, 'FHTT4D3C2B1A', 'E0:D5:5E:AA:BB:CC', 'Sultan Villa ONT', 'FiberHome AN5506-04-F', 'Routing', 'online', -28.4, 1.8, 2310, 100, ?, ?)
                """, (olt_id, now_str, now_str))

            cursor.execute("""
                INSERT INTO unconfigured_onus (olt_id, pon_port, serial_number, vendor, rx_power, discovered_at, status)
                VALUES (?, 1, 'HWTC99887766', 'Huawei', -17.8, ?, 'unassigned')
            """, (olt_id, now_str))

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

        # Seed initial uptime ledger entries if empty
        cursor.execute("SELECT COUNT(*) FROM onu_uptime_ledger")
        if cursor.fetchone()[0] == 0:
            now_dt = datetime.now()
            cursor.execute("SELECT id, serial_number, name FROM onus")
            seeded_onus = [dict(r) for r in cursor.fetchall()]
            for o in seeded_onus:
                oid = o["id"]
                sn = o["serial_number"]
                if "VSOL" in sn:
                    t1 = (now_dt - timedelta(days=18, hours=4)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, 'online', ?, '18d 4h 12m', 'Optical link synchronized & stable (Class C+)', -18.6)
                    """, (oid, t1))
                    cursor.execute("""
                        UPDATE onus SET uptime = '18d 4h 12m', status = 'online', last_error = 'None (Normal Operation)', error_severity = 'normal', flaps_count = 0, availability_pct = 100.0, last_online_at = ? WHERE id = ?
                    """, (t1, oid))
                elif "HWTC" in sn:
                    t1 = (now_dt - timedelta(days=6, hours=11)).strftime("%Y-%m-%d %H:%M:%S")
                    t_glitch = (now_dt - timedelta(days=6, hours=11, minutes=4)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, 'dying_gasp', ?, '4m', 'Subscriber power glitch (dying gasp detected)', -21.4)
                    """, (oid, t_glitch))
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, 'online', ?, '6d 11h 45m', 'Power restored - Optical link UP', -21.4)
                    """, (oid, t1))
                    cursor.execute("""
                        UPDATE onus SET uptime = '6d 11h 45m', status = 'online', last_error = 'None (Brief power glitch 6d ago, recovered)', error_severity = 'normal', flaps_count = 1, availability_pct = 99.8, last_online_at = ? WHERE id = ?
                    """, (t1, oid))
                elif "ZTEG" in sn:
                    t_warn = (now_dt - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
                    t_up = (now_dt - timedelta(days=2, hours=19)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, 'warning', ?, 'Ongoing (8h)', 'Optical attenuation warning (-25.8 dBm > -24dBm limit)', -25.8)
                    """, (oid, t_warn))
                    cursor.execute("""
                        UPDATE onus SET uptime = '2d 19h 30m', status = 'online', last_error = 'High Optical Loss (-25.8 dBm > -24dBm limit)', error_severity = 'warning', flaps_count = 2, availability_pct = 98.6, last_online_at = ? WHERE id = ?
                    """, (t_up, oid))
                elif "FHTT" in sn:
                    t_los = (now_dt - timedelta(minutes=48)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO onu_uptime_ledger (onu_id, event_type, event_time, duration_str, reason, rx_power)
                        VALUES (?, 'los', ?, '48m (Active Cut)', 'Loss of Signal (LOS) - Optical RX power dropped to -34.0 dBm (Physical fiber break)', -34.0)
                    """, (oid, t_los))
                    cursor.execute("""
                        UPDATE onus SET uptime = 'Offline (48m)', status = 'los', rx_power = -34.0, last_error = 'Critical Fiber Break (LOS / Signal Disconnected)', error_severity = 'critical', flaps_count = 3, availability_pct = 92.4, last_offline_at = ? WHERE id = ?
                    """, (t_los, oid))

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
        return dict(row) if row else None


def create_or_update_request(phone: str, mac: str, ip: Optional[str], device_model: Optional[str]) -> Tuple[Dict[str, Any], bool, bool]:
    """
    Processes incoming hotspot submission from phone.
    Returns (request_dict, is_already_approved, is_secondary)
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mac_upper = mac.strip().upper()
    phone_clean = phone.strip()

    with get_db() as conn:
        cursor = conn.cursor()

        # Check if MAC is already approved
        existing_device = get_customer_by_mac(mac_upper)
        if existing_device and existing_device["status"] == "active":
            return (existing_device, True, False)

        # Check if phone belongs to an existing customer
        existing_cust = get_customer_by_phone(phone_clean)
        is_secondary = 1 if existing_cust else 0
        customer_id = existing_cust["id"] if existing_cust else None

        # Check for existing pending request with same MAC
        cursor.execute("SELECT id FROM connection_requests WHERE UPPER(mac_address) = ? AND status = 'pending'", (mac_upper,))
        existing_req = cursor.fetchone()

        if existing_req:
            req_id = existing_req["id"]
            cursor.execute("""
                UPDATE connection_requests
                SET phone = ?, ip_address = ?, device_model = ?, customer_id = ?, is_secondary = ?, updated_at = ?
                WHERE id = ?
            """, (phone_clean, ip, device_model, customer_id, is_secondary, now, req_id))
        else:
            cursor.execute("""
                INSERT INTO connection_requests (phone, mac_address, ip_address, device_model, status, customer_id, is_secondary, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """, (phone_clean, mac_upper, ip, device_model, customer_id, is_secondary, now, now))
            req_id = cursor.lastrowid

        conn.commit()

        cursor.execute("SELECT * FROM connection_requests WHERE id = ?", (req_id,))
        req = dict(cursor.fetchone())
        return (req, False, bool(is_secondary))


def get_request_status_by_mac_and_phone(mac: str, phone: str) -> Dict[str, Any]:
    mac_upper = mac.strip().upper()
    with get_db() as conn:
        cursor = conn.cursor()

        # First check if device MAC is approved directly
        cust = get_customer_by_mac(mac_upper)
        if cust and cust["status"] == "active":
            return {"status": "approved", "message": f"Device authorized. Welcome {cust['name']}!"}

        # Check latest connection request
        cursor.execute("""
            SELECT * FROM connection_requests
            WHERE UPPER(mac_address) = ?
            ORDER BY id DESC LIMIT 1
        """, (mac_upper,))
        row = cursor.fetchone()
        if not row:
            return {"status": "none", "message": "No pending request."}

        req = dict(row)
        return {
            "status": req["status"],
            "is_secondary": bool(req["is_secondary"]),
            "message": "Connection approved!" if req["status"] == "approved" else "Awaiting admin approval."
        }


def get_pending_requests() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.*, c.name as existing_customer_name, c.billing_type as existing_billing_type,
                   c.max_devices as customer_max_devices,
                   (SELECT COUNT(*) FROM customer_devices cd WHERE cd.customer_id = c.id AND cd.status = 'approved') as current_device_count
            FROM connection_requests r
            LEFT JOIN customers c ON r.customer_id = c.id
            WHERE r.status = 'pending'
            ORDER BY r.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_approved_devices() -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.*, c.phone, c.name as customer_name, c.billing_type, c.package_name, c.monthly_fee, c.status as customer_status, c.expiry_date, c.max_devices
            FROM customer_devices d
            JOIN customers c ON d.customer_id = c.id
            WHERE d.status = 'approved' AND c.status = 'active'
            ORDER BY d.id DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_request_by_id(req_id: int) -> Optional[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM connection_requests WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def approve_connection(
    req_id: int,
    name: str,
    billing_type: str,
    package_name: str,
    monthly_fee: float,
    collected_today: float = 0.0,
    due_day: int = 1,
    due_date: Optional[str] = None,
    max_devices: int = 1,
    speed_limit: Optional[str] = None,
    advance_mode: str = "credit"
) -> Dict[str, Any]:
    """
    Approves a pending request:
    1. Creates or updates customer with manual fee, due date, speed limit, device limit, and credit balance.
    2. If customer pays in advance (e.g. 100 SAR for a 30 SAR monthly fee), registers 30 SAR for cycle
       and automatically saves the remainder (+70 SAR) into customer credit balance.
    3. Binds MAC to customer.
    4. Records payment in collections ledger.
    5. Marks connection request as approved.
    """
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    clean_collected = float(collected_today or 0.0)
    monthly_fee = float(monthly_fee or 0.0)
    clean_limit = max(1, int(max_devices or 1))
    clean_speed = speed_limit.strip() if speed_limit and speed_limit.strip() else None

    # Dynamic Lifecycle Auto-Switching:
    # 0 SAR collected upfront -> POSTPAID (deferred billing)
    # Payment >= monthly fee -> PREPAID (service pre-funded)
    final_billing_type = (billing_type or "prepaid").strip().lower()
    if clean_collected == 0.0:
        final_billing_type = "postpaid"
    elif clean_collected >= monthly_fee and monthly_fee > 0:
        final_billing_type = "prepaid"

    # Base due date / expiry calculation
    if due_date and due_date.strip():
        final_due_date = due_date.strip()
    else:
        final_due_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    credit_to_add = 0.0
    col_notes = ""

    # Advance payment calculation
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
                # Default "credit" mode: 1st cycle covered, remaining extra money is held as customer credit
                credit_to_add = round(clean_collected - monthly_fee, 2)
                col_notes = f"Advance payment: {clean_collected:.2f} SAR ({monthly_fee:.2f} SAR 1st cycle, +{credit_to_add:.2f} SAR added to Credit Balance)"
        elif clean_collected == monthly_fee:
            col_notes = f"Initial activation payment for {package_name} ({clean_collected:.2f} SAR)"
        else:
            # Partial deposit
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

    with get_db() as conn:
        cursor = conn.cursor()

        # Get request
        cursor.execute("SELECT * FROM connection_requests WHERE id = ?", (req_id,))
        req_row = cursor.fetchone()
        if not req_row:
            raise ValueError(f"Request #{req_id} not found.")
        req = dict(req_row)

        phone = req["phone"]
        mac = req["mac_address"].upper()
        ip = req["ip_address"]

        # 1. Upsert customer
        cursor.execute("SELECT id, credit_balance FROM customers WHERE phone = ?", (phone,))
        cust_row = cursor.fetchone()

        if cust_row:
            customer_id = cust_row["id"]
            existing_credit = float(cust_row["credit_balance"] or 0.0)
            new_credit = round(existing_credit + credit_to_add, 2)
            cursor.execute("""
                UPDATE customers
                SET name = ?, billing_type = ?, package_name = ?, monthly_fee = ?,
                    collected_today = ?, due_day = ?, due_date = ?, status = 'active',
                    expiry_date = ?, max_devices = ?, speed_limit = ?, credit_balance = ?, updated_at = ?
                WHERE id = ?
            """, (name, final_billing_type, package_name, monthly_fee, clean_collected, due_day, final_due_date, expiry_date, clean_limit, clean_speed, new_credit, now_str, customer_id))
        else:
            new_credit = round(credit_to_add, 2)
            cursor.execute("""
                INSERT INTO customers (phone, name, billing_type, package_name, monthly_fee, collected_today, due_day, due_date, status, expiry_date, max_devices, speed_limit, credit_balance, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """, (phone, name, final_billing_type, package_name, monthly_fee, clean_collected, due_day, final_due_date, expiry_date, clean_limit, clean_speed, new_credit, now_str, now_str))
            customer_id = cursor.lastrowid

        # 2. Insert or update customer_devices
        cursor.execute("SELECT id FROM customer_devices WHERE UPPER(mac_address) = ?", (mac,))
        dev_row = cursor.fetchone()
        if dev_row:
            cursor.execute("""
                UPDATE customer_devices
                SET customer_id = ?, ip_address = ?, status = 'approved', approved_at = ?
                WHERE id = ?
            """, (customer_id, ip, now_str, dev_row["id"]))
        else:
            cursor.execute("""
                INSERT INTO customer_devices (customer_id, mac_address, ip_address, device_name, status, approved_at, created_at)
                VALUES (?, ?, ?, ?, 'approved', ?, ?)
            """, (customer_id, mac, ip, req.get("device_model", "Mobile Phone"), now_str, now_str))

        # 3. If payment collected today > 0, log collection
        if clean_collected > 0:
            cursor.execute("""
                INSERT INTO collections (customer_id, amount, billing_type, notes, collected_at, collected_by)
                VALUES (?, ?, ?, ?, ?, 'Admin')
            """, (customer_id, clean_collected, final_billing_type, col_notes or f"Activation payment for {package_name}", now_str))

        # 4. Mark request approved
        cursor.execute("""
            UPDATE connection_requests
            SET status = 'approved', customer_id = ?, updated_at = ?
            WHERE id = ?
        """, (customer_id, now_str, req_id))

        conn.commit()

        # Return combined result
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        cust = dict(cursor.fetchone())
        cust["mac_address"] = mac
        cust["ip_address"] = ip
        cust["credit_balance"] = round(float(cust.get("credit_balance") or 0.0), 2)
        return cust


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
        cursor.execute("UPDATE customers SET status = 'suspended', updated_at = ? WHERE id = ?", (now_str, info["cust_id"]))

        conn.commit()
        return info


# =========================================================
# Step 3: Customer Directory Operations
# =========================================================

def get_all_customers() -> List[Dict[str, Any]]:
    """
    Returns all registered customers with device counts, payment stats,
    and computed validity/days remaining.
    """
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                c.*,
                COUNT(DISTINCT CASE WHEN d.status = 'approved' THEN d.id END) as active_devices_count,
                COALESCE(SUM(col.amount), 0.0) as total_paid
            FROM customers c
            LEFT JOIN customer_devices d ON d.customer_id = c.id
            LEFT JOIN collections col ON col.customer_id = c.id
            GROUP BY c.id
            ORDER BY c.id DESC
        """)
        # Preload packages to resolve default speed rates
        cursor.execute("SELECT name, rate_limit, default_price FROM packages")
        pkg_map = {row["name"]: dict(row) for row in cursor.fetchall()}

        customers = []
        for r in cursor.fetchall() if False else cursor.execute("SELECT c.*, COUNT(DISTINCT CASE WHEN d.status = 'approved' THEN d.id END) as active_devices_count, COALESCE(SUM(col.amount), 0.0) as total_paid FROM customers c LEFT JOIN customer_devices d ON d.customer_id = c.id LEFT JOIN collections col ON col.customer_id = c.id GROUP BY c.id ORDER BY c.id DESC").fetchall():
            item = dict(r)
            
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

            customers.append(item)
        return customers


def get_customer_profile(customer_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns complete customer profile: personal details, all bound devices,
    effective speed, credit balance, and payment ledger history.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Customer row
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        cust_row = cursor.fetchone()
        if not cust_row:
            return None
        cust = dict(cust_row)
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
    advance_mode: str = "credit"
) -> Dict[str, Any]:
    """Manually creates a new customer with custom speed, fee, due date, device limit, and advance credit handling."""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    clean_payment = float(initial_payment or 0.0)
    monthly_fee = float(monthly_fee or 0.0)

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

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO customers (phone, name, billing_type, package_name, monthly_fee, collected_today, due_day, due_date, status, expiry_date, max_devices, speed_limit, credit_balance, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
        """, (phone.strip(), name.strip(), final_billing_type, package_name, monthly_fee, clean_payment, due_day, final_due_date, expiry_date, clean_limit, clean_speed, credit_to_add, now_str, now_str))
        customer_id = cursor.lastrowid

        # Bind MAC if provided
        if mac_address and mac_address.strip():
            mac_clean = mac_address.strip().upper()
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
    credit_balance: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Updates any customer fields: monthly rate, payment due date, custom speed limit,
    billing type, device limit, package name, name, phone, status, and credit balance.
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
            new_due_day = current.get("due_day") or 1

        cursor.execute("""
            UPDATE customers
            SET name = ?, phone = ?, billing_type = ?, package_name = ?,
                monthly_fee = ?, due_date = ?, due_day = ?, expiry_date = ?,
                speed_limit = ?, max_devices = ?, status = ?, credit_balance = ?, updated_at = ?
            WHERE id = ?
        """, (
            new_name, new_phone, new_btype, new_pkg,
            new_fee, new_due_date, new_due_day, new_expiry_date,
            new_speed, new_max_devices, new_status, new_credit, now_str,
            customer_id
        ))
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
    credit_balance: Optional[float] = None
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
        credit_balance=credit_balance
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

        cursor.execute("SELECT mac_address FROM customer_devices WHERE customer_id = ?", (customer_id,))
        macs = [r["mac_address"].upper() for r in cursor.fetchall()]

        conn.commit()
        return (new_status, macs)


def add_customer_device(customer_id: int, mac_address: str, device_name: str = "Client Device") -> Dict[str, Any]:
    """Adds a new MAC device to an existing customer."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mac_clean = mac_address.strip().upper()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO customer_devices (customer_id, mac_address, ip_address, device_name, status, approved_at, created_at)
            VALUES (?, ?, NULL, ?, 'approved', ?, ?)
        """, (customer_id, mac_clean, device_name, now_str, now_str))
        conn.commit()
        dev_id = cursor.lastrowid
        cursor.execute("SELECT * FROM customer_devices WHERE id = ?", (dev_id,))
        return dict(cursor.fetchone())


def remove_customer_device(device_id: int) -> Optional[str]:
    """Removes a device and returns its MAC for unbinding."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT mac_address FROM customer_devices WHERE id = ?", (device_id,))
        row = cursor.fetchone()
        if not row:
            return None
        mac = row["mac_address"].upper()

        cursor.execute("DELETE FROM customer_devices WHERE id = ?", (device_id,))
        conn.commit()
        return mac


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

            if c.get("status") == "suspended":
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

        # 5. Capacity Limit (Base 100 users)
        capacity_limit = 100
        capacity_percent = min(100.0, round((len(active_customers) / capacity_limit * 100), 1))

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
                "max_capacity": 64,
                "utilization_percent": min(100.0, round((tot / 64) * 100, 1)),
                "tx_power_dbm": "+2.5 dBm",
                "avg_rx_dbm": round(float(p_stat["avg_rx"] or -19.0), 1) if tot > 0 else "—",
                "status": "up" if tot > 0 else "idle"
            })
        olt["ports"] = ports

        # Uplink SFP Ports
        olt["uplink_ports"] = [
            {"name": "GE 1 (Uplink)", "type": "1000Base-T", "status": "up", "speed": "1 Gbps", "comment": "Core MikroTik hAP lite (ether1)"},
            {"name": "GE 2 (Uplink)", "type": "1000Base-T", "status": "down", "speed": "—", "comment": "Redundant Uplink Link"},
            {"name": "10GE SFP+ 1", "type": "10G SFP+ Optical", "status": "up", "speed": "10 Gbps", "comment": "Backbone Optical Trunk"},
            {"name": "10GE SFP+ 2", "type": "10G SFP+ Optical", "status": "down", "speed": "—", "comment": "Standby Ring Link"}
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
            WHERE (o.status != 'online' OR o.error_severity IN ('warning', 'critical') OR o.rx_power < -24.0)
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
            
            if status == "los" or rx <= -30.0:
                item["diag_title"] = "Optical Loss of Signal (LOS / Fiber Break)"
                item["diag_severity"] = "critical"
                item["diag_badge"] = "CRITICAL FIBER CUT"
                item["diag_solution"] = "Inspect drop cable, optical splitter port, or customer fiber wall socket."
            elif rx < -27.0:
                item["diag_title"] = f"Severe Optical Attenuation ({rx:.1f} dBm)"
                item["diag_severity"] = "critical"
                item["diag_badge"] = "CRITICAL ATTENUATION"
                item["diag_solution"] = "Fiber bend or dirty connector. Clean SC/APC connector with fiber pen."
            elif rx < -24.0:
                item["diag_title"] = f"High Optical Loss ({rx:.1f} dBm)"
                item["diag_severity"] = "warning"
                item["diag_badge"] = "HIGH LOSS WARNING"
                item["diag_solution"] = "Check fiber patch cord for tight bends or splitter insertion loss."
            elif status in ("power_off", "dying_gasp"):
                item["diag_title"] = "Subscriber Power Disconnected (Dying Gasp)"
                item["diag_severity"] = "warning"
                item["diag_badge"] = "POWER OFF"
                item["diag_solution"] = "Customer premise ONT is turned off or power adapter unplugged."
            else:
                item["diag_title"] = item.get("last_error") or "Unknown Warning"
                item["diag_severity"] = "warning"
                item["diag_badge"] = "WARNING"
                item["diag_solution"] = "Monitor optical link stability."

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



