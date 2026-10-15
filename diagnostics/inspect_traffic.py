import sqlite3
import os
import sys
from datetime import datetime, timedelta

db_path = '/home/sk/isp_v2/isp_v2.db' if os.path.exists('/home/sk/isp_v2/isp_v2.db') else ('/home/tserver/isp_v2/isp_v2.db' if os.path.exists('/home/tserver/isp_v2/isp_v2.db') else 'isp_v2.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print(f"Connected to database: {db_path}")

print("\n=== RECENT 10 RECORDS IN customer_traffic_hourly ===")
c.execute("SELECT id, customer_id, mac_address, date_str, hour_int, download_bytes, upload_bytes, updated_at FROM customer_traffic_hourly ORDER BY id DESC LIMIT 10")
for r in c.fetchall():
    print(dict(r))

print("\n=== TOP 5 BY download_bytes ALL TIME ===")
c.execute("SELECT h.id, h.customer_id, c.name, h.date_str, h.hour_int, h.download_bytes, h.upload_bytes, h.total_bytes FROM customer_traffic_hourly h JOIN customers c ON h.customer_id = c.id ORDER BY h.download_bytes DESC LIMIT 5")
for r in c.fetchall():
    d_bytes = r['download_bytes']
    print(f"{r['name']} ({r['date_str']} hr {r['hour_int']}) -> {d_bytes} bytes = {d_bytes / (1024*1024*1024):.2f} GB ({d_bytes / (1024*1024):.2f} MB)")

print("\n=== TODAY TOTALS BY CUSTOMER ===")
today_str = datetime.now().strftime("%Y-%m-%d")
c.execute("""
    SELECT c.id, c.name, SUM(h.download_bytes) as d_sum, SUM(h.upload_bytes) as u_sum, SUM(h.total_bytes) as t_sum
    FROM customer_traffic_hourly h
    JOIN customers c ON h.customer_id = c.id
    WHERE h.date_str = ?
    GROUP BY c.id
    ORDER BY d_sum DESC
    LIMIT 10
""", (today_str,))
rows = c.fetchall()
print(f"Found {len(rows)} customers with traffic today ({today_str}):")
for r in rows:
    d = r['d_sum']
    print(f"#{r['id']} {r['name']}: {d} bytes | {d / (1024*1024*1024):.2f} GB | {d / (1024*1024):.2f} MB")

print("\n=== TESTING get_live_top_bandwidth_consumers() ===")
sys.path.insert(0, '/home/sk/isp_v2')
from main import get_live_top_bandwidth_consumers
data = get_live_top_bandwidth_consumers(limit=10, window_hours=1, sort_by="speed")
print("Cutoff:", data.get("window_cutoff"))
print("Fleet 1h Download:", data.get("total_fleet_window_download"))
print("Fleet 1h Upload:", data.get("total_fleet_window_upload"))
print("Fleet 1h Total:", data.get("total_fleet_window_bytes"))
peak = data.get("peak_consumer")
print("Peak Consumer:", f"{peak['name']} ({peak['room']}) - {peak['live_speed_formatted']}" if peak else "None")
print("\nConsumers:")
for c in data.get("consumers", []):
    print(f"#{c['rank']} {c['name']} ({c['room']}) -> Live: {c['live_speed_formatted']} ({c['live_speed_mbps']} Mbps) | 1h: {c['window_download_formatted']} | Today: {c['today_download_formatted']} | Router: {c['router_name']}")




