import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database

metrics = database.get_dashboard_metrics()
print("EXPIRING_TIERS:", metrics.get("expiring_tiers"))
print("SUSPENDED_COUNT:", metrics.get("suspended_count"))
print("ACTIVE_COUNT:", metrics.get("active_subscribers"))
print("WILL_SUSPEND_COUNT:", metrics.get("expiring_tiers", {}).get("will_suspend"))
