"""Temporary HTTPS probe server for checking the certificate and the phone camera.

Not part of the app. Usage:
  python3 deploy/https_probe.py --port 5000 --certs /opt/graduation-checkin/certs
Pages:
  /        secure-context + camera test
  /ca.crt  root CA for phones to install
"""
import argparse
import http.server
import ssl
from pathlib import Path

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HTTPS Camera Check</title>
<style>body{font-family:-apple-system,system-ui,sans-serif;margin:16px;background:#F6F3F8;color:#2B2230}
.card{background:#fff;border-radius:14px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px #0001}
.ok{color:#1E7B45;font-weight:700}.bad{color:#B42318;font-weight:700}
button,a.btn{display:inline-block;background:#4A1D4F;color:#fff;border:0;border-radius:10px;padding:12px 16px;
font-size:16px;text-decoration:none}video{width:100%;border-radius:12px;margin-top:12px;background:#000}</style></head>
<body><h2>HTTPS / 摄像头检测</h2>
<div class="card">安全上下文 isSecureContext：<span id="sc"></span><br>
摄像头接口 mediaDevices：<span id="md"></span></div>
<div class="card"><button id="go">打开摄像头测试</button><p id="msg"></p><video id="v" playsinline muted></video></div>
<div class="card">首次使用请安装根证书：<br><br><a class="btn" href="/ca.crt">下载根证书 ca.crt</a></div>
<script>
const f=(el,ok)=>{el.textContent=ok?'是':'否';el.className=ok?'ok':'bad'};
f(sc,window.isSecureContext);f(md,!!(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia));
go.onclick=async()=>{try{const s=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});
v.srcObject=s;await v.play();msg.textContent='摄像头已打开 ✅';msg.className='ok'}
catch(e){msg.textContent='失败：'+e.name+' '+e.message;msg.className='bad'}};
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--certs", default="/opt/graduation-checkin/certs")
    args = ap.parse_args()
    certs = Path(args.certs)
    ca_bytes = (certs / "ca.crt").read_bytes()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/ca.crt":
                body, ctype = ca_bytes, "application/x-x509-ca-cert"
                extra = {"Content-Disposition": 'attachment; filename="graduation-ca.crt"'}
            else:
                body, ctype, extra = PAGE.encode(), "text/html; charset=utf-8", {}
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in extra.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certs / "server.crt", certs / "server.key")
    srv = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), H)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f"https probe on :{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
