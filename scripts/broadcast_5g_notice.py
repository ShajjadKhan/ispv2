#!/usr/bin/env python3
"""
CyberNet OS v2 - 4-Language 5G Migration Broadcast Dispatcher
Dispatches the unified 4-language announcement (English, Bangla, Arabic, Hindi)
to all active subscribers with anti-ban pacing delays and audit logging.
"""

import os
import sys
import time
import json
import random
import signal
import logging
import argparse
from datetime import datetime

# Adjust path to import isp_v2 core modules
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import database
import whatsapp_service

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("broadcast_5g")

STATE_FILE = os.path.join(SCRIPT_DIR, "broadcast_5g_sent.json")

BROADCAST_MESSAGE = """📢 *CYBERNET HIGH-SPEED NETWORK NOTICE*
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 *ENGLISH*
Dear Valued Subscribers,
To experience ultra-fast internet speeds and low-latency gaming/streaming, we strongly advise connecting your devices to our high-performance *5GHz Wi-Fi* networks:
⚡ *CyberNet 5G*
⚡ *Game Network 5G*
⚡ *Free WiFi 5G*

⚠️ *Important Notice:* Please *avoid* connecting to older 2.4 GHz signals (*CyberNet Free WiFi* / *GameNetwork*) due to frequency congestion and slower speeds.
🔄 All subscribers are requested to reconnect and re-register your devices on our *New Upgraded Server* as soon as possible.

📞 *Support & Helplines:*
• Shajjad Khan: +966 59 759 5059
• Riyadh Hossain: +966 55 203 6454
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇧🇩 *বাংলা (BANGLA)*
সম্মানিত গ্রাহকবৃন্দ,
সর্বোচ্চ ইন্টারনেট স্পিড ও নিরবচ্ছিন্ন গেমিং/স্ট্রিমিং অভিজ্ঞতার জন্য আপনাদের সকল ডিভাইসে আমাদের দ্রুতগতির *5GHz Wi-Fi* নেটওয়ার্ক ব্যবহারের জন্য বিশেষ অনুরোধ করা হচ্ছে:
⚡ *CyberNet 5G*
⚡ *Game Network 5G*
⚡ *Free WiFi 5G*

⚠️ *জরুরি সতর্কতা:* ধীরগতি ও অতিরিক্ত সিগন্যাল জ্যাম এড়াতে পুরনো 2.4 GHz সিগন্যাল (*CyberNet Free WiFi* / *GameNetwork*) ব্যবহার করা থেকে বিরত থাকুন।
🔄 সকল সম্মানিত গ্রাহককে অতি দ্রুত আমাদের *নতুন আপগ্রেডেড সার্ভারে* পুনরায় ডিভাইস রেজিস্ট্রেশন করার জন্য অনুরোধ করা হচ্ছে।

📞 *হেল্পলাইন ও সাপোর্ট:*
• সাজ্জাদ খান: +966 59 759 5059
• রিয়াদ হোসেন: +966 55 203 6454
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇸🇦 *العربية (ARABIC)*
عملاؤنا الأعزاء،
للحصول على أعلى سرعات الإنترنت وأفضل تجربة سلسة للألعاب والبث المباشر، نوصي بشدة بربط أجهزتكم بشبكات الـ *5GHz* فائقة السرعة:
⚡ *CyberNet 5G*
⚡ *Game Network 5G*
⚡ *Free WiFi 5G*

⚠️ *تنبيه هام:* يُرجى *تجنب* الاتصال بترددات 2.4 GHz القديمة (*CyberNet Free WiFi* / *GameNetwork*) نظراً للازدحام الشديد وبطء السرعة.
🔄 نرجو من جميع المشتركين إعادة تسجيل أجهزتهم على *السيرفر الجديد المطور* في أقرب وقت ممكن.

📞 *أرقام الدعم الفني والمساعدة:*
• سجاد خان: 0597595059 966+
• رياض حسين: 0552036454 966+
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🇮🇳 *हिन्दी (HINDI)*
प्रिय सम्मानीय ग्राहक,
सुपर-फास्ट इंटरनेट स्पीड और बेहतरीन गेमिंग व लाइव स्ट्रीमिंग अनुभव के लिए अपने डिवाइस को हमारे *5GHz Wi-Fi* नेटवर्क से कनेक्ट करें:
⚡ *CyberNet 5G*
⚡ *Game Network 5G*
⚡ *Free WiFi 5G*

⚠️ *ज़रूरी सूचना:* धीमी स्पीड और नेटवर्क जाम से बचने के लिए पुराने 2.4 GHz सिग्नल (*CyberNet Free WiFi* / *GameNetwork*) से कनेक्ट न करें।
🔄 सभी ग्राहकों से अनुरोध है कि जल्द से जल्द *नए अपग्रेडेड सर्वर* पर अपने डिवाइस को दोबारा रजिस्टर करें।

📞 *हेल्पलाइन और सहायता:*
• सज्जाद खान: +966 59 759 5059
• रियाद हुसैन: +966 55 203 6454
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CyberNet High-Speed Fiber Network"""


def load_sent_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"sent_phones": {}, "last_updated": None}


def save_sent_state(state):
    state["last_updated"] = datetime.now().isoformat()
    temp = STATE_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(temp, STATE_FILE)


def main():
    parser = argparse.ArgumentParser(description="CyberNet 4-Language 5G Migration Broadcast Dispatcher")
    parser.add_argument("--preview", action="store_true", help="Print message and recipient statistics without sending")
    parser.add_argument("--test-admin", action="store_true", help="Send single test dispatch to admin (0597595059)")
    parser.add_argument("--broadcast", action="store_true", help="Execute real fleet broadcast to all active subscribers")
    parser.add_argument("--delay", type=float, default=8.0, help="Base delay in seconds between messages (default: 8.0s)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate broadcast without hitting WhatsApp network")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of messages to dispatch (0 = all)")
    args = parser.parse_args()

    print("=" * 60)
    print("🚀 CyberNet OS v2 - 4-Language 5G Migration Broadcast Engine")
    print("=" * 60)

    # 1. Preview Mode
    if args.preview:
        print("\n--- 4-LANGUAGE BROADCAST MESSAGE TEMPLATE ---")
        print(BROADCAST_MESSAGE)
        print("---------------------------------------------")

        all_custs = database.get_all_customers()
        active_recipients = [
            c for c in all_custs
            if c.get("status") != "deleted"
            and c.get("reminders_enabled", 1) == 1
            and c.get("phone")
            and len(whatsapp_service.format_phone(c.get("phone"))) >= 9
        ]
        state = load_sent_state()
        already_sent = state.get("sent_phones", {})
        pending = [c for c in active_recipients if whatsapp_service.format_phone(c.get("phone")) not in already_sent]

        print(f"\n📊 Fleet Audience Statistics:")
        print(f"  • Total Active Subscribers: {len(active_recipients)}")
        print(f"  • Already Dispatched (State Cache): {len(already_sent)}")
        print(f"  • Pending To Dispatch: {len(pending)}")
        print(f"  • Estimated Duration (@ {args.delay}s pacing): ~{round((len(pending) * args.delay) / 60, 1)} minutes\n")
        return

    # 2. Test Admin Mode
    if args.test_admin:
        admin_phone = "0597595059"
        clean_admin = whatsapp_service.format_phone(admin_phone)
        print(f"\n📲 Dispatching Test Broadcast to Admin Phone: {clean_admin}...")
        ok, err = whatsapp_service.send_whatsapp_raw(clean_admin, BROADCAST_MESSAGE)
        if ok:
            database.log_whatsapp_message(
                phone=clean_admin,
                message_body=BROADCAST_MESSAGE,
                message_type="test_broadcast_5g",
                status="sent",
                error_message=None,
                customer_id=None,
                customer_name="Shajjad Khan (Admin Test)",
                sent_by="admin"
            )
            print("✅ TEST DISPATCH SUCCESSFUL! Delivered to WhatsApp.")
        else:
            print(f"❌ TEST DISPATCH FAILED: {err}")
        return

    # 3. Fleet Broadcast Mode
    if args.broadcast or args.dry_run:
        all_custs = database.get_all_customers()
        active_recipients = [
            c for c in all_custs
            if c.get("status") != "deleted"
            and c.get("reminders_enabled", 1) == 1
            and c.get("phone")
            and len(whatsapp_service.format_phone(c.get("phone"))) >= 9
        ]

        state = load_sent_state()
        sent_dict = state.setdefault("sent_phones", {})

        # Deduplicate by clean phone number
        seen_phones = set()
        queue = []
        for c in active_recipients:
            cp = whatsapp_service.format_phone(c.get("phone"))
            if cp in seen_phones:
                continue
            seen_phones.add(cp)
            if cp not in sent_dict:
                queue.append((c, cp))

        if args.limit > 0:
            queue = queue[:args.limit]

        total_pending = len(queue)
        print(f"\n🎯 Targets Identified: {len(active_recipients)} total, {len(sent_dict)} previously sent.")
        print(f"📦 Active Queue: {total_pending} subscribers ready to dispatch.")

        if total_pending == 0:
            print("🎉 All subscribers have already received this broadcast! Nothing to do.")
            return

        print(f"⏱️ Safety Pacing: {args.delay}s (+ randomized jitter) between dispatches to protect account.")
        print("🚨 Press Ctrl+C at any time to pause safely. State is saved after every message.\n")

        interrupted = False
        def handle_sigint(sig, frame):
            nonlocal interrupted
            print("\n⚠️ Pause requested! Completing current item and cleanly exiting...")
            interrupted = True

        signal.signal(signal.SIGINT, handle_sigint)

        success_count = 0
        fail_count = 0

        for idx, (cust, clean_phone) in enumerate(queue, 1):
            if interrupted:
                break

            name = cust.get("name") or "Subscriber"
            room = cust.get("room") or "—"
            c_id = cust.get("id")

            progress_pct = round((idx / total_pending) * 100, 1)
            print(f"[{idx}/{total_pending}] ({progress_pct}%) -> {name} ({clean_phone}, R:{room})... ", end="", flush=True)

            if args.dry_run:
                time.sleep(0.5)
                print("SIMULATED (dry-run)")
                success_count += 1
                continue

            # Live Send
            ok, err = whatsapp_service.send_whatsapp_raw(clean_phone, BROADCAST_MESSAGE)
            status_str = "sent" if ok else "failed"

            database.log_whatsapp_message(
                phone=clean_phone,
                message_body=BROADCAST_MESSAGE,
                message_type="broadcast_5g",
                status=status_str,
                error_message=err,
                customer_id=c_id,
                customer_name=name,
                sent_by="admin"
            )

            if ok:
                print("✅ SENT")
                sent_dict[clean_phone] = {
                    "customer_id": c_id,
                    "name": name,
                    "timestamp": datetime.now().isoformat()
                }
                save_sent_state(state)
                success_count += 1
            else:
                print(f"❌ FAILED ({err})")
                fail_count += 1

            # Pacing delay with gentle jitter (e.g. 7.5s - 9.0s)
            if idx < total_pending and not interrupted:
                jitter = random.uniform(args.delay - 0.5, args.delay + 1.2)
                time.sleep(max(3.0, jitter))

        print("\n" + "=" * 60)
        print("🏁 BATCH RUN SUMMARY:")
        print(f"  • Successfully Sent : {success_count}")
        print(f"  • Failed Dispatches : {fail_count}")
        print(f"  • Remaining In Queue: {total_pending - (success_count + fail_count)}")
        print(f"  • Progress Saved At : {STATE_FILE}")
        print("=" * 60)


if __name__ == "__main__":
    main()
