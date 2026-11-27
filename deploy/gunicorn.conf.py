import os
from pathlib import Path

bind = os.getenv("BIND", f"0.0.0.0:{os.getenv('PORT', '5000')}")
workers = 1
worker_class = "gevent"
timeout = 60
graceful_timeout = 20
accesslog = "-"
errorlog = "-"

cert = Path(os.getenv("CERT_FILE", "/opt/graduation-checkin/certs/server.crt"))
key = Path(os.getenv("KEY_FILE", "/opt/graduation-checkin/certs/server.key"))
if os.getenv("GUNICORN_TLS") != "0" and cert.is_file() and key.is_file():
    certfile = str(cert)
    keyfile = str(key)
