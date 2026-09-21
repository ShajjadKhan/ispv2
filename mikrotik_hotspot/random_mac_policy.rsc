# ==============================================================================
# CyberNet OS v2 - MikroTik RouterOS Randomized MAC Blocking & Hotspot Policy
# ==============================================================================
# In IEEE 802, locally administered (randomized/private) MAC addresses have
# bit 1 of the first octet set to 1.
# Hex mask: 02:00:00:00:00:00 / 02:00:00:00:00:00
#
# 1. Hotspot IP-Binding Policy:
# CyberNet automatically manages /ip/hotspot/ip-binding.
# When a client connects with Device MAC and is approved:
#   /ip hotspot ip-binding add mac-address=XX:XX:XX:XX:XX:XX type=bypassed
# When a client attempts to connect with a Randomized MAC:
#   CyberNet immediately pushes a block rule:
#   /ip hotspot ip-binding add mac-address=XX:XX:XX:XX:XX:XX type=blocked comment="Blocked: Randomized MAC"
#
# 2. RouterOS Bridge Filter (Hardware Level Drop for Forward Traffic):
# If you want MikroTik to drop all forwarding internet traffic from randomized MACs:
#
# /interface bridge filter
# add chain=forward action=drop mac-protocol=ip src-mac-address=02:00:00:00:00:00/02:00:00:00:00:00 comment="CyberNet: Drop Forward from Randomized MACs"
#
# 3. Installing Captive Portal on MikroTik:
# Upload login.html from the mikrotik_hotspot directory to the /hotspot/ directory on MikroTik Files.
# Ensure your Hotspot Server Profile has:
#   /ip hotspot profile set [find] html-directory=hotspot login-by=http-chap,http-pap,cookie
# ==============================================================================
