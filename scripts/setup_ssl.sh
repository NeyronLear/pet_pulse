#!/bin/sh
# usage: setup_ssl.sh DOMAIN EMAIL APP_DIR   (запускать от root)
set -eu
DOMAIN=$1; EMAIL=$2; APP_DIR=$3

command -v certbot >/dev/null || { apt-get update -qq && apt-get install -y -qq certbot; }

# хуки продления: на время пр
H=/etc/letsencrypt/renewal-hooks
mkdir -p $H/pre $H/post
printf '#!/bin/sh\ncd %s && docker compose stop nginx\n' "$APP_DIR" > $H/pre/nginx.sh
printf '#!/bin/sh\ncd %s && docker compose start nginx\n' "$APP_DIR" > $H/post/nginx.sh
chmod +x $H/pre/nginx.sh $H/post/nginx.sh

# выпуск только если сертификата ещё нет
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  (cd "$APP_DIR" && docker compose stop nginx) || true
  certbot certonly --standalone -d "$DOMAIN" --email "$EMAIL" \
    --agree-tos --no-eff-email --non-interactive
fi