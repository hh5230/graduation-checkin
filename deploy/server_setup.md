# 签到服务部署

上传代码包时排除本地 `.venv/`、`.env` 和 `certs/`。解压到 `/opt/graduation-checkin`，保留服务器已有的配置和证书。虚拟环境在服务器使用 Python 3.12 创建。以下命令在该目录执行。

1. 确认系统账号及同名组 `grad-checkin` 已存在，专用单元 `graduation-checkin-redis.service` 监听 `127.0.0.1:6391`。将 `DATABASE_URL` 设置为签到系统专用 PostgreSQL 库的连接串，使用有权建表的专用数据库账号。
2. 在 `.env` 写入每行一个静态 `KEY=value`，填写 `SECRET_KEY`、`DATABASE_URL`，并设置以下生产值。Gunicorn 直接提供 HTTPS/WSS，开放服务器 TCP 5000。

   ```dotenv
   REDIS_URL=redis://127.0.0.1:6391/0
   PORT=5000
   SESSION_COOKIE_SECURE=1
   SOCKETIO_ASYNC_MODE=gevent
   CA_CERT_PATH=/opt/graduation-checkin/certs/ca.crt
   ```

3. 首次签发证书时，用手机实际访问的服务器 IP 运行 `sudo bash deploy/gen_certs.sh <服务器IP>`。已有配套证书可直接沿用。手机从 `https://<服务器IP>:5000/ca.crt` 下载并信任根证书。Gunicorn 默认读取 `certs/server.crt` 和 `certs/server.key`，可用 `CERT_FILE` 和 `KEY_FILE` 指定其他可读路径。
4. 上传完成后运行 `sudo bash deploy/deploy.sh`。需要指定 Python 镜像时运行 `sudo env PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash deploy/deploy.sh`。脚本设置权限，安装依赖，执行 `init_db.py` 和 `seed.py`，启用并重启 `graduation-checkin.service`，等到 HTTPS 健康检查的 PostgreSQL 和 Redis 均为 `ok`。

服务账号拥有应用代码、`.env` 和 `server.key`，后两者权限为 600。`certs/` 为 `root:grad-checkin`、750，两个公钥证书为 644，留在服务器的 `ca.key` 为 `root:root`、600。使用自定义证书路径时也应为服务账号设置相应读取权限。

`scripts/init_db.py` 每次部署都会校准三个初始账号，包括恢复契约中的默认密码并启用账号。请将此行为纳入生产凭据管理。

运行状态用 `systemctl status graduation-checkin.service` 查看，日志用 `journalctl -u graduation-checkin.service -n 50` 查看。本机可用 `curl -kfsS https://127.0.0.1:5000/api/health` 复查。
