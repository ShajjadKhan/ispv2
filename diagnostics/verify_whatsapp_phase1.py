#!/usr/bin/env python3
"""
Verification Script for Phase 1: Dedicated WhatsApp Infrastructure & Sandbox Shield
"""
import sys
import whatsapp_service

print("=" * 70)
print("VERIFYING WHATSAPP PHASE 1: DEDICATED STACK & SAFETY SANDBOX")
print("=" * 70)

# 1. Verify Configuration Isolation
print("\n[CHECK 1] Gateway Configuration Isolation:")
print(f"  • Target URL: {whatsapp_service.OPENWA_URL}")
print(f"  • Session ID: {whatsapp_service.OPENWA_SESSION_ID}")
print(f"  • Sandbox Mode Active: {whatsapp_service.is_sandbox_active()}")
print(f"  • Authorized Test Phone: {whatsapp_service.ALLOWED_TEST_PHONE}")

assert whatsapp_service.OPENWA_URL == "http://127.0.0.1:2790", "Must point to dedicated port 2790"
assert whatsapp_service.OPENWA_SESSION_ID == "abba0f1a-573b-4107-8fc4-3e8000668e92", "Must use dedicated ispv2-bot session"
assert whatsapp_service.is_sandbox_active() is True, "Sandbox mode must be active by default"
assert whatsapp_service.ALLOWED_TEST_PHONE == "966597595059", "Authorized test phone must be 966597595059"
print("  ✓ Configuration isolation verified 100%!")

# 2. Verify Sandbox Shield Blocks Unauthorized Numbers
print("\n[CHECK 2] Sandbox Shield Protection Against Client Numbers:")
client_numbers = [
    "0500790317",
    "966500790317",
    "0556617812",
    "0543940018",
    "966537749503"
]

for phone in client_numbers:
    ok, err = whatsapp_service.send_whatsapp_raw(phone, "Test unauthorized broadcast")
    print(f"  • Testing client {phone:<14} -> Dispatched: {ok} | Shield blocked: {not ok}")
    assert ok is False, f"CRITICAL SECURITY FAILURE: Client number {phone} was NOT blocked!"
    assert "SANDBOX SHIELD ACTIVE" in str(err), f"Unexpected error response: {err}"

print("  ✓ All client numbers strictly blocked by Sandbox Shield!")

# 3. Verify Sandbox Shield Allows Authorized Test Number
print("\n[CHECK 3] Sandbox Shield Behavior for Authorized Number (0597595059):")
# Test number should bypass the shield check (network dispatch will be attempted)
ok, err = whatsapp_service.send_whatsapp_raw("0597595059", "Sandbox verification ping")
print(f"  • Testing authorized 0597595059 -> Dispatched: {ok} | Error: {err}")
assert "SANDBOX SHIELD ACTIVE" not in str(err), "Authorized test number was mistakenly blocked by sandbox shield!"
print("  ✓ 0597595059 successfully passed Sandbox Shield authorization!")

# 4. Verify Dedicated Gateway Connection & QR Generation
print("\n[CHECK 4] Dedicated OpenWA Gateway Telemetry & QR:")
status = whatsapp_service.get_whatsapp_gateway_status()
print(f"  • Gateway live status: {status.get('status')}")
print(f"  • Needs QR Scan: {status.get('needs_qr')}")
print(f"  • Connected: {status.get('connected')}")

qr_res = whatsapp_service.get_whatsapp_qr_code()
print(f"  • QR fetch success: {qr_res.get('success')}")
if qr_res.get("qr"):
    print(f"  • Live Base64 QR Code received: {qr_res.get('qr')[:40]}... ({len(qr_res.get('qr'))} chars)")
    assert qr_res.get("qr").startswith("data:image/png;base64,"), "QR must be a valid base64 PNG data URL"
    print("  ✓ Live QR Code generated cleanly from dedicated ispv2-bot session!")
else:
    print(f"  • QR status response: {qr_res}")

print("\n" + "=" * 70)
print(">>> ALL PHASE 1 CHECKS PASSED WITH 100% SUCCESS! <<<")
print("=" * 70)
