#!/bin/sh
set -e

CERT=/etc/nginx/certs/server.crt
KEY=/etc/nginx/certs/server.key
OUT=/etc/nginx/conf.d/default.conf
VARS='${WEBAPP_PORT} ${INGESTION_PORT} ${API_KEY}'

if [ -f "$CERT" ] && [ -f "$KEY" ]; then
    echo "TLS certificates found — starting in HTTPS mode on port ${WEBAPP_PORT}"
    envsubst "$VARS" < /etc/nginx/conf-templates/nginx-https.conf.tmpl > "$OUT"
else
    echo "No TLS certificates — starting in HTTP mode on port ${WEBAPP_PORT}"
    envsubst "$VARS" < /etc/nginx/conf-templates/nginx-http.conf.tmpl > "$OUT"
fi
