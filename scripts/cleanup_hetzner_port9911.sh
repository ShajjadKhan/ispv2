#!/bin/bash
# Autonomous Watchdog: Clean up zombie port 9911 forwards on Hetzner VPS
SSH_KEY="/home/tserver/.ssh/id_hetzner_tunnel"
REMOTE="shajjad@135.181.39.96"

if [ ! -f "$SSH_KEY" ]; then
    exit 0
fi

# Check if port 9911 is listening on Hetzner
IS_LISTENING=$(ssh -i "$SSH_KEY" -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new "$REMOTE" "ss -tulpn | grep 9911 || true" 2>/dev/null)

if [ -n "$IS_LISTENING" ]; then
    # Test if 9911 responds to HTTP GET
    HTTP_CODE=$(ssh -i "$SSH_KEY" -o ConnectTimeout=4 "$REMOTE" "curl -s -o /dev/null -w '%{http_code}' -m 2 http://127.0.0.1:9911/login || echo '000'" 2>/dev/null)
    if [ "$HTTP_CODE" != "200" ]; then
        echo "[cleanup] Port 9911 returned HTTP $HTTP_CODE (zombie session). Clearing stale sshd sessions on Hetzner..."
        ssh -i "$SSH_KEY" -o ConnectTimeout=4 "$REMOTE" "pkill -u shajjad -f 'sshd-session: shajjad$' || true" 2>/dev/null || true
        sleep 1
    else
        echo "[cleanup] Port 9911 is healthy (HTTP $HTTP_CODE)."
    fi
else
    echo "[cleanup] Port 9911 is completely free."
fi
exit 0
