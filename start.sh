#!/bin/bash
pkill -f 'port 9911' 2>/dev/null || true
sleep 1
cd /home/tserver/isp_v2
nohup /home/tserver/ispbilling/venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 9911 > uvicorn_9911.log 2>&1 &
