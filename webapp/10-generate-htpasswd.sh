#!/bin/sh
set -e
if [ -z "$WEB_USERNAME" ] || [ -z "$WEB_PASSWORD" ]; then
  echo "ERROR: WEB_USERNAME and WEB_PASSWORD must be set" >&2
  exit 1
fi
printf '%s:%s\n' "$WEB_USERNAME" "$(openssl passwd -apr1 "$WEB_PASSWORD")" > /etc/nginx/.htpasswd
echo "htpasswd generated for user: $WEB_USERNAME"
