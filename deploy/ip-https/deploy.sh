#!/usr/bin/env bash
set -euo pipefail

cd /opt/graduation-checkin
account=grad-checkin
unit=graduation-checkin.service
if (( EUID != 0 )); then
    echo "Run the deployment as root (sudo bash deploy/deploy.sh)." >&2
    exit 1
fi
for file in .env certs/ca.crt certs/server.crt certs/server.key; do
    if [[ ! -s "$file" ]]; then
        echo "Missing or empty $PWD/$file" >&2
        exit 1
    fi
done

# Keep the signing key out of the recursive ownership change, even momentarily.
find . -xdev \( -path ./certs -o -path ./.env \) -prune -o -exec chown -h "$account:$account" -- {} +
chown root:"$account" certs
chmod 750 certs
if [[ -e certs/ca.key ]]; then
    chmod 600 certs/ca.key
    chown root:root certs/ca.key
fi
chmod 600 .env certs/server.key
chown "$account:$account" .env certs/server.key
chown root:"$account" certs/ca.crt certs/server.crt
chmod 644 certs/ca.crt certs/server.crt

as_service() {
    runuser -u "$account" -- "$@"
}
if [[ ! -x .venv/bin/python ]]; then
    as_service python3.12 -m venv .venv
fi
as_service .venv/bin/python -m pip install -r requirements.txt

# Use the same .env as systemd, even if the operator's shell has a different DB.
run_app() {
    as_service env -i PATH=/usr/local/bin:/usr/bin:/bin .venv/bin/python "$@"
}
port=$(run_app - <<'PY'
from dotenv import dotenv_values
from urllib.parse import urlsplit
from sqlalchemy.engine import make_url

env = dotenv_values(".env")
database = make_url(env["DATABASE_URL"]) if env.get("DATABASE_URL") else None
if database is None or database.get_backend_name() != "postgresql" or not database.database:
    raise SystemExit("Set DATABASE_URL to the dedicated graduation PostgreSQL database in .env")
redis = urlsplit(env.get("REDIS_URL") or "")
if redis.hostname not in {"127.0.0.1", "localhost"} or redis.port != 6391:
    raise SystemExit("Set REDIS_URL to the dedicated Redis at 127.0.0.1:6391")
if env.get("SESSION_COOKIE_SECURE", "").strip().lower() not in {"1", "yes", "true"} or env.get("SOCKETIO_ASYNC_MODE") != "gevent":
    raise SystemExit("Set SESSION_COOKIE_SECURE=1 and SOCKETIO_ASYNC_MODE=gevent in .env")
print(int(env.get("PORT", "5000")))
PY
)
run_app scripts/init_db.py
run_app scripts/seed.py

install -o root -g root -m 644 "deploy/ip-https/$unit" "/etc/systemd/system/$unit"
systemctl daemon-reload
systemctl enable "$unit"
systemctl restart "$unit"
for ((attempt=1; attempt<=20; attempt++)); do
    if systemctl is-active --quiet "$unit" &&
        health=$(curl --noproxy '*' -kfsS --max-time 3 "https://127.0.0.1:$port/api/health") &&
        run_app -c 'import json, sys; h = json.load(sys.stdin); sys.exit(h.get("ok") is not True or h.get("data") != {"db": "ok", "redis": "ok"})' <<< "$health"; then
        echo "$health"
        exit 0
    fi
    sleep 1
done
echo "HTTPS health check failed. Inspect journalctl -u $unit -n 50." >&2
exit 1
