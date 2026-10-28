#!/bin/bash
set -e
# Starts or restarts the dedicated ispv2_whatsapp container with persistence and upstream bug-patch
CONTAINER_NAME="ispv2_whatsapp"
DATA_DIR="/home/tserver/isp_v2/whatsapp_data"

if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container ${CONTAINER_NAME} exists. Ensuring it is active..."
    docker start "${CONTAINER_NAME}" || true
else
    echo "Creating and starting ${CONTAINER_NAME}..."
    docker run -d \
      --name "${CONTAINER_NAME}" \
      --restart always \
      -p 127.0.0.1:2790:2785 \
      -p 127.0.0.1:2890:2886 \
      -v "${DATA_DIR}:/app/data" \
      -v "${DATA_DIR}/whatsapp-web-js.adapter.js:/app/dist/engine/adapters/whatsapp-web-js.adapter.js" \
      ghcr.io/rmyndharis/openwa:latest
fi
