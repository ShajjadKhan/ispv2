import requests
import json
import base64
import os
import sys

SESSION_ID = "8cc17322-a9d3-4b88-89ac-d4d95fb57ff4"
API_URL = "http://127.0.0.1:2785"
API_KEY = "dev-admin-key"
HEADERS = {"x-api-key": API_KEY, "Content-Type": "application/json"}
TARGET_PHONE = "966597595059"
TARGET_CHAT_ID = f"{TARGET_PHONE}@c.us"

def check_contact():
    check_url = f"{API_URL}/api/sessions/{SESSION_ID}/contacts/check/{TARGET_PHONE}"
    res = requests.get(check_url, headers=HEADERS)
    print(f"Check Contact: {res.status_code} -> {res.text}")
    return res.json() if res.status_code == 200 else None

def send_document_base64(filepath, filename, mimetype, caption=""):
    url = f"{API_URL}/api/sessions/{SESSION_ID}/messages/send-document"
    with open(filepath, "rb") as f:
        b64_data = base64.b64encode(f.read()).decode("utf-8")
    
    payload = {
        "chatId": TARGET_CHAT_ID,
        "base64": b64_data,
        "filename": filename,
        "mimetype": mimetype,
        "caption": caption
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    print(f"Send Document ({filename}): {res.status_code} -> {res.text}")
    return res

def send_document_url(url, filename, mimetype, caption=""):
    endpoint = f"{API_URL}/api/sessions/{SESSION_ID}/messages/send-document"
    payload = {
        "chatId": TARGET_CHAT_ID,
        "url": url,
        "filename": filename,
        "mimetype": mimetype,
        "caption": caption
    }
    res = requests.post(endpoint, headers=HEADERS, json=payload)
    print(f"Send Document URL ({filename}): {res.status_code} -> {res.text}")
    return res

def send_text(text):
    url = f"{API_URL}/api/sessions/{SESSION_ID}/messages/send-text"
    payload = {
        "chatId": TARGET_CHAT_ID,
        "text": text
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    print(f"Send Text: {res.status_code} -> {res.text}")
    return res


def send_executive_summary():
    summary_text = """🚀 *CyberNet OS v2 - UI/UX, Accessibility & Responsive Audit Delivered*

Assalamu Alaikum Shajjad Bhai,
The comprehensive UI/UX, Accessibility, and Mobile Responsiveness Audit Report for *CyberNet OS v2* has been generated and dispatched to your WhatsApp in all 3 requested formats:

📁 *Delivered Documents:*
1️⃣ *PDF Document:* `CyberNet_OS_v2_UI_UX_Audit_Report.pdf` (Executive styling, tables, metrics)
2️⃣ *Markdown (.md):* `CyberNet_OS_v2_UI_UX_Audit_Report.md` (For AI agents & developers)
3️⃣ *Plain Text (.txt):* `CyberNet_OS_v2_UI_UX_Audit_Report.txt` (Universal viewing)

🌐 *Direct High-Speed Download Links:*
• *PDF:* https://isp.shajjadkhan.com/downloads/UI_UX_ACCESSIBILITY_AUDIT_REPORT.pdf
• *Markdown:* https://isp.shajjadkhan.com/downloads/UI_UX_ACCESSIBILITY_AUDIT_REPORT.md
• *Plain Text:* https://isp.shajjadkhan.com/downloads/UI_UX_ACCESSIBILITY_AUDIT_REPORT.txt

🎯 *Key Audit Highlights (16 Actionable Findings):*
• *Mobile Card Deck Conversion:* Completed on Dashboard & Approvals (zero horizontal scrolling).
• *Remaining Tables:* 6 pages mapped for pure CSS card-deck transform (Collections, Packages, Resellers, Reseller Portal, OLT, WhatsApp).
• *Touch Targets:* 44px minimum target sizes for mobile thumb comfort.
• *Captive Portal:* Arabic/English toggle, numeric keypad defaults, and 16px iOS auto-zoom fix.
• *WCAG 2.1 AA:* Contrast elevated, focus-visible rings, and ARIA screen reader live regions.

Everything is synced and ready for the next Antigravity agent to begin Phase 1 execution."""

    return send_text(summary_text)

if __name__ == "__main__":
    send_executive_summary()








