#!/bin/bash
set -euo pipefail
revision=${1:?revision required}
[[ "$revision" =~ ^[a-f0-9]{7,40}$ ]]
release=/var/oled/radar/releases/$revision
test ! -e "$release"
previous=$(readlink -f /var/oled/radar/current)
systemctl start radar-backup.service
install -d -m 0750 -o root -g radar "$release"
tar -xf /home/opc/radar-final.tar -C "$release"
chown -R root:radar "$release"
find "$release" -type d -exec chmod 0750 {} +
find "$release" -type f -exec chmod 0640 {} +
cp -p /etc/nginx/conf.d/radar.conf "/var/oled/radar/admin-backups/radar-before-$revision.conf"
install -m 0644 "$release/deploy/radar-cloudflare.inc" /etc/nginx/radar-cloudflare.inc
install -m 0644 "$release/deploy/radar-proxy.inc" /etc/nginx/radar-proxy.inc
install -m 0644 "$release/deploy/radar.nginx.conf" /etc/nginx/conf.d/radar.conf
restorecon -F /etc/nginx/radar-cloudflare.inc /etc/nginx/radar-proxy.inc /etc/nginx/conf.d/radar.conf
if ! nginx -t; then
    cp -p "/var/oled/radar/admin-backups/radar-before-$revision.conf" /etc/nginx/conf.d/radar.conf
    exit 1
fi
install -m 0644 "$release/deploy/radar.service" /etc/systemd/system/radar.service
ln -sfn "$release" /var/oled/radar/current
systemctl daemon-reload
systemctl restart radar
systemctl reload nginx
if ! curl --retry 3 --retry-delay 1 --retry-connrefused --fail --silent --resolve radar.clasure.com.br:443:127.0.0.1 https://radar.clasure.com.br/login >/dev/null; then
    ln -sfn "$previous" /var/oled/radar/current
    systemctl restart radar
    echo 'Health check failed: previous application revision restored.' >&2
    exit 1
fi
echo "RADAR active revision $revision"
