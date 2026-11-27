#!/usr/bin/env bash
# Run ON THE SERVER (as root) from /opt/graduation-checkin after uploading the code:
#   tar --exclude=.venv --exclude=.env --exclude=.git -cf - . | ssh root@SERVER 'tar xf - -C /opt/graduation-checkin'
#   ssh root@SERVER 'bash /opt/graduation-checkin/deploy/deploy.sh'
# Prerequisites (one-time, see README §7): .env (600), PostgreSQL db/user grad_checkin,
# Redis on 127.0.0.1, graduation-checkin-nginx.service + Let's Encrypt certificate.
set -euo pipefail
cd /opt/graduation-checkin
account=grad-checkin
unit=graduation-checkin.service
INDEX=${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
[[ -s .env ]] || { echo "missing .env" >&2; exit 1; }
id "$account" >/dev/null 2>&1 || useradd --system --home "$PWD" --shell /usr/sbin/nologin "$account"

find . -xdev -name '._*' -delete
chown -R "$account:$account" .
chmod 600 .env

[[ -x .venv/bin/python ]] || runuser -u "$account" -- "${PYTHON:-python3}" -m venv .venv
runuser -u "$account" -- .venv/bin/pip install -q -i "$INDEX" -r requirements.txt

run_app() { runuser -u "$account" -- env -i PATH=/usr/bin:/bin .venv/bin/python "$@"; }
run_app scripts/init_db.py
run_app scripts/seed.py

install -o root -g root -m 644 "deploy/$unit" "/etc/systemd/system/$unit"
systemctl daemon-reload
systemctl enable "$unit" >/dev/null
systemctl restart "$unit"
for i in $(seq 1 30); do
  if health=$(curl -fsS --max-time 3 http://127.0.0.1:5000/api/health 2>/dev/null); then
    echo "local health: $health"; exit 0
  fi
  sleep 1
done
echo "health check failed; see: journalctl -u $unit -n 50" >&2
exit 1
