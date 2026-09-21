# CyberNet OS v2 - ISP Operations & Management System

A high-performance, clean, reality-based ISP Billing & Operational Management Engine designed for MikroTik RouterOS gateways, Optical Line Terminals (OLT), and customer communications.

## Key Features

- 🌐 **MikroTik Gateway Operations**: Live CPU/Memory telemetry, active hotspot leases, interface traffic rates, dynamic firewall address lists, and profile syncing.
- ⚡ **OLT & Fiber PON Diagnostics**: Real-time connected ONU monitor, optical power levels (dBm), distance calculations, fiber break / LOS detection, and session uptime ledger.
- 📱 **Hotspot Approvals & Device Management**: Captive portal requests, MAC auto-binding, multi-device limits, and instant access provisioning.
- 🛡️ **Strict Device MAC Enforcement & Randomized MAC Shield**:
  - Automatically identifies Locally Administered Addresses (LAA, IEEE 802 bit-1) used by iOS Private Wi-Fi, Android Randomized MAC, and Windows Random Hardware Addresses.
  - Hard-blocks connection submissions and status polling from phones with randomized MACs.
  - Automatically pushes active block rules to MikroTik (`/ip/hotspot/ip-binding type=blocked`).
  - Interactive mobile captive portal guide instructing customers how to switch to "Device MAC" on iOS and Android.
  - Live admin & reseller UI indicators (`[✓ DEVICE MAC]` vs `[⚠️ RANDOM MAC]`) with approval safeguards.
  - Ready-to-deploy MikroTik template (`mikrotik_hotspot/login.html`) and RouterOS policy rules (`mikrotik_hotspot/random_mac_policy.rsc`).
- 👥 **Customer Directory & Hybrid Billing**: Auto-transition between Prepaid and Postpaid billing, advance balance settlement, and collection ledgers.
- 📦 **Bandwidth Packages & Limits**: Dynamic rate limiting (upload/download speed caps) and shared user control.
- 💬 **WhatsApp Operations & Safety Hub**:
  - OpenWA gateway integration (`:2785`)
  - Master Automated Dispatch Safety Switch (Safe mode by default)
  - Night Quiet Hours Shield (10:00 PM – 09:00 AM) to protect customer sleep
  - Realistic Dark Mode WhatsApp preview bubble with dynamic placeholder tag rendering
  - Immutable delivery and outbox audit ledger (`whatsapp_logs`)

## Architecture & Quick Start

- **Framework**: FastAPI + Jinja2 + Vanilla Modern CSS (Dark Aesthetic)
- **Database**: SQLite3 (`isp_v2.db`)
- **Default Port**: `9911`

```bash
# Start the production service
bash start.sh
```
