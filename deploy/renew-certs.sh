#!/bin/sh
# Renew Let's Encrypt certificates (only those expiring within 30 days) and reload nginx.
# Installed on the server as a daily cron job:
#   17 4 * * * /opt/prontopay/deploy/renew-certs.sh >> /var/log/prontopay-certs.log 2>&1
cd /opt/prontopay || exit 1
echo "=== $(date -u) ==="
docker compose --env-file .env.prod -f docker-compose.prod.yml run --rm --entrypoint certbot certbot renew --webroot -w /var/www/certbot --non-interactive
docker exec prontopay-nginx nginx -s reload
