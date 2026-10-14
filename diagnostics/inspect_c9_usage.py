import sys
sys.path.insert(0, '/home/sk/isp_v2')
import database

analytics = database.get_customer_usage_analytics(9)
print("Summary:", analytics.get("summary"))
print("Devices in breakdown:", len(analytics.get("device_breakdown", [])))
for d in analytics.get("device_breakdown", []):
    print(" - Device:", d.get("device_name"), "MAC:", d.get("mac_address"), "Total:", d.get("formatted_total"))
