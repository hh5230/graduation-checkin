#!/usr/bin/env bash
# Generate a private root CA + a server certificate for an IP address.
# Phones install ca.crt once; after that https://<IP>:<PORT> is trusted
# (secure context => camera / getUserMedia allowed).
#
# Usage: deploy/gen_certs.sh <server-ip> [out-dir]
set -euo pipefail

IP="${1:?usage: gen_certs.sh <server-ip> [out-dir]}"
OUT="${2:-/opt/graduation-checkin/certs}"
mkdir -p "$OUT"
cd "$OUT"
umask 077

# 1) Root CA (10 years). Must be CA:TRUE so iOS lists it under
#    Settings > General > About > Certificate Trust Settings.
if [[ ! -f ca.key ]]; then
  openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
    -keyout ca.key -out ca.crt \
    -subj "/CN=Graduation Checkin Local CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign"
fi

# 2) Server cert for the IP. Apple requires: SAN (CN is ignored),
#    EKU serverAuth, SHA-256, validity <= 825 days (we use 397).
cat > server.ext <<EOF
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:${IP}
EOF
openssl req -newkey rsa:2048 -sha256 -nodes \
  -keyout server.key -out server.csr -subj "/CN=${IP}"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 397 -sha256 -extfile server.ext -out server.crt
rm -f server.csr server.ext

chmod 600 ca.key server.key
chmod 644 ca.crt server.crt
openssl verify -CAfile ca.crt server.crt
openssl x509 -in server.crt -noout -subject -ext subjectAltName -dates
