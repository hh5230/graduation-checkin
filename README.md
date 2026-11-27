# Graduation Ceremony QR Check-in & Stage Management

毕业典礼 QR Code 签到及舞台管理系统。每位参与者拥有专属二维码，工作人员用手机浏览器扫码完成签到与上台流程；多台设备同时操作时，数据一致性由 PostgreSQL 事务与锁保证，状态变化通过 Socket.IO 实时同步到所有设备。

- 后端：Python 3.12 · Flask 3 · Flask-SQLAlchemy (SQLAlchemy 2) · psycopg 3 · Flask-SocketIO
- 数据库：PostgreSQL 16（唯一业务数据来源）
- Redis 7：Socket.IO 消息队列 + 统计缓存（不保存业务状态）
- 前端：Jinja2 模板 + 原生 JS/CSS（移动优先、中英文切换）、html5-qrcode 摄像头扫码
- 详细设计 / API 契约：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 1. 架构说明

```
 手机/电脑浏览器 (Entry / Stage / Admin / Dashboard / Display)
        │  REST (JSON)                 ▲ Socket.IO 推送
        ▼                              │
 ┌──────────────── Flask app ─────────────────────────┐
 │ api/*  薄控制层：鉴权装饰器、参数解析               │
 │ services/*  业务逻辑：状态机、条件更新、锁、审计     │
 │ realtime.py  commit 之后广播事件                     │
 │ errors.py / i18n.py  统一 JSON 错误 + 中英文文案      │
 └───────┬─────────────────────────────┬───────────────┘
         ▼                             ▼
   PostgreSQL 16                   Redis 7
   participants / users /          Socket.IO message_queue
   audit_logs（约束+索引）          stats:v1 统计缓存 (TTL)
```

| 目录 | 说明 |
|---|---|
| `app/api/` | REST 蓝图：auth / participants / checkin / stage / stats |
| `app/services/` | 业务逻辑（签到、入队、呼叫、完成、统计、二维码） |
| `app/models.py` | ORM 模型、序列化、`init_database()` |
| `app/auth.py` | 登录态与角色校验（API 返回 401/403，页面跳转登录/403 页） |
| `app/realtime.py` | Socket.IO 连接鉴权与提交后广播 |
| `app/templates/`, `app/static/` | 页面、JS、CSS、`i18n/zh.json` / `en.json` |
| `db/schema.sql` | 权威 DDL（幂等） |
| `scripts/` | `init_db.py` 初始化、`seed.py` 测试数据、`concurrency_test.py` 多设备并发验证 |
| `tests/` | pytest（真实 PostgreSQL 测试库） |

### 状态机（后端强制）
```
registered ──签到──▶ checked_in ──入队──▶ queued ──呼叫──▶ on_stage ──完成──▶ completed
```
任何其他跳转都会被拒绝（`NOT_CHECKED_IN` / `ALREADY_QUEUED` / `INVALID_STATE` …）。编辑资料不能修改状态。

### 页面
| 路径 | 角色 | 功能 |
|---|---|---|
| `/login` | 公开 | 登录 |
| `/claim` | 公开 | **学生自助领取二维码**：输入编号 + 登记邮箱，显示/下载自己的二维码（补充需求） |
| `/admin` | admin | 参与者新增/编辑/查询/搜索/状态筛选、二维码查看/打印/重新生成 |
| `/entry` | staff/admin | Entry Counter：扫码或手动输入编号 → 显示资料 → 确认签到 |
| `/stage` | staff/admin | Stage Counter：扫码入队、队列、呼叫下一位、完成上台 |
| `/display` | staff/admin | 舞台全屏大屏，实时显示当前上台者 |
| `/dashboard` | staff/admin | 六项实时统计 |

---

## 2. 安装与运行

前置：Docker Desktop、Python 3.11+（开发使用 3.12）。

```bash
# 1) 启动 PostgreSQL(5434) 和 Redis(6380)
docker compose up -d

# 2) Python 环境
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # 如需修改端口/密钥

# 3) 初始化数据库（建表 + 默认账号，可重复执行）并导入 30 条测试数据
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/seed.py            # --reset 可清空参与者后重新导入

# 4) 启动服务
.venv/bin/python run.py                      # http://localhost:5001
```

> 端口说明：开发机上 5432/5433/6379 已被其他服务占用，因此 compose 映射为 **5434 / 6380**，可在 `docker-compose.yml` 与 `.env` 中修改。

### 手机访问与摄像头
浏览器只允许在 **HTTPS 或 localhost** 下调用摄像头。手机通过局域网 IP（`http://192.168.x.x:5001`）访问时摄像头会被浏览器禁止，可选：
1. 使用 HTTPS 隧道（如 `cloudflared tunnel --url http://localhost:5001` 或 `ngrok http 5001`），手机打开隧道地址；
2. Android Chrome 可在 `chrome://flags/#unsafely-treat-insecure-origin-as-secure` 中加入局域网地址；
3. 摄像头不可用时，页面会提示并可使用 **手动输入编号**（功能完全等价）。

---

## 3. 默认账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | 管理员（全部功能） |
| staff1 | staff123 | 工作人员 |
| staff2 | staff123 | 工作人员 |

测试参与者编号：`G2026001` – `G2026030`（二维码在管理后台查看）。

---

## 4. API 列表

统一响应：成功 `{"ok": true, "data": ...}`；失败 `{"ok": false, "error": {"code", "message", "details"}}`。`X-Lang: zh|en` 控制错误文案语言。写操作要求 `Content-Type: application/json`。

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| GET | `/api/health` | 公开 | DB / Redis 健康检查 |
| POST | `/api/auth/login` | 公开 | 登录 `{username, password}` |
| POST | `/api/auth/logout` | 登录 | 登出 |
| GET | `/api/auth/me` | 登录 | 当前用户 |
| GET | `/api/participants?q=&status=&page=&per_page=` | admin | 列表、搜索、状态筛选、分页 |
| POST | `/api/participants` | admin | 新增 `{participant_code, name, email}` |
| GET | `/api/participants/<id>` | admin | 详情 |
| PATCH | `/api/participants/<id>` | admin | 编辑（不能改状态） |
| POST | `/api/participants/<id>/regenerate-qr` | admin | 重新生成二维码（旧码失效） |
| GET | `/api/participants/<id>/qr.png` | admin | 二维码 PNG |
| POST | `/api/public/claim` | 公开 + IP 限流 | 学生领取二维码 `{participant_code, email}`，两者同时匹配才返回 |
| GET | `/api/lookup?token=` / `?code=` | staff/admin | 扫码/手动查询参与者 |
| POST | `/api/checkin` | staff/admin | 签到 `{token}` 或 `{code}` |
| POST | `/api/stage/queue` | staff/admin | 入队 `{token}` 或 `{code}` |
| GET | `/api/stage/state` | staff/admin | 当前上台 + 队列 + 最近完成 |
| POST | `/api/stage/call-next` | staff/admin | 呼叫下一位 `{complete_current?: bool}` |
| POST | `/api/stage/complete` | staff/admin | 完成上台 `{participant_id?}` |
| GET | `/api/stats` | staff/admin | 六项统计 |

错误码：`UNAUTHORIZED`(401) `INVALID_CREDENTIALS`(401) `FORBIDDEN`(403) `VALIDATION_ERROR`(400) `UNSUPPORTED_MEDIA_TYPE`(415) `NOT_FOUND` `PARTICIPANT_NOT_FOUND` `INVALID_QR`(404) `DUPLICATE_CODE` `DUPLICATE_EMAIL` `ALREADY_CHECKED_IN` `NOT_CHECKED_IN` `ALREADY_QUEUED` `INVALID_STATE` `QUEUE_EMPTY` `STAGE_BUSY` `NOTHING_ON_STAGE`(409) `CLAIM_NOT_FOUND`(404) `RATE_LIMITED`(429) `INTERNAL_ERROR`(500)。

Socket.IO 事件：`participant_updated`、`stage_updated`、`stats_updated`（仅已登录连接可接收）。

---

## 5. 并发与一致性设计

| 场景 | 机制 | 效果 |
|---|---|---|
| 重复签到 | `UPDATE participants SET status='checked_in' ... WHERE <token/code> AND status='registered' RETURNING id` | PostgreSQL 行锁使并发 UPDATE 串行；后到者重新评估 WHERE 得 0 行 → `409 ALREADY_CHECKED_IN`，并返回首次签到时间与操作人 |
| 未签到入队 / 重复入队 | `UPDATE ... WHERE status='checked_in'`；0 行时按当前状态返回 `NOT_CHECKED_IN` / `ALREADY_QUEUED` / `INVALID_STATE` | 队列状态在参与者行上，一人一行，天然不会重复 |
| 呼叫下一位 | 单事务：`pg_advisory_xact_lock` 串行化舞台操作 → 已有人在台上则 `STAGE_BUSY` → `SELECT ... ORDER BY queued_at, id LIMIT 1 FOR UPDATE SKIP LOCKED` → 置为 on_stage | 多设备同时点击只推进一人 |
| 同一时刻最多一人上台 | 部分唯一索引 `uq_one_on_stage ON participants((true)) WHERE status='on_stage'` | 数据库兜底，即使绕过应用也无法出现两人 on_stage |
| 完成上台 | 同一 advisory lock + `UPDATE ... WHERE status='on_stage' [AND id=:expected]` | 重复点击只成功一次（`NOTHING_ON_STAGE`） |
| 状态与时间一致 | CHECK 约束：status ≥ checked_in ⇒ checked_in_at 非空，等等 | 数据库拒绝不一致数据 |
| 唯一性 | `participant_code` UNIQUE、`lower(email)` UNIQUE、`qr_token` UNIQUE | 并发新增时由约束兜底，映射为 `DUPLICATE_*` |
| 审计 | 每次状态变更在**同一事务**写 `audit_logs`（动作、操作人、时间） | 业务与审计要么都成功要么都回滚 |
| 实时同步 | `commit()` 之后才通过 Socket.IO（Redis message_queue）广播；客户端（重）连时从 REST 拉全量 | 不会广播未提交数据；断线后自动补偿 |
| 时间来源 | 使用数据库 `now()` / `clock_timestamp()` | 多台设备/服务器时间不一致不影响排序 |

学生领取接口是唯一的公开 API：编号+邮箱必须同时匹配，不匹配时统一返回 `CLAIM_NOT_FOUND`（不泄露哪一项错误），Redis 按 IP 限流（10 次/10 分钟），响应不包含邮箱、ID 与 token 明文。

二维码只编码 `GRAD:<token>`，token 为 `secrets.token_urlsafe(24)`（192 bit 随机），不暴露自增 ID，无法枚举。

---

## 6. 测试方法

_（最终验收后补充实际结果）_

```bash
# 单元/集成测试（使用 graduation_test 测试库）
.venv/bin/python scripts/init_db.py --test
.venv/bin/pytest -q

# 多设备并发测试（需先启动服务）
.venv/bin/python scripts/concurrency_test.py --base http://localhost:5001 --workers 20
```

---

## 7. 服务器部署

**访问地址：<https://36.138.220.233:5000>**（学生领取二维码：<https://36.138.220.233:5000/claim>，根证书：<https://36.138.220.233:5000/ca.crt>）

### 7.1 为什么必须 HTTPS
手机浏览器只在安全上下文（HTTPS 或 localhost）中开放摄像头接口 `getUserMedia`。因此 gunicorn 直接在 5000 端口用自建根 CA 签发的 IP 证书提供 HTTPS，Socket.IO 同源连接自动升级为 **wss**。扫码页实现三层兜底，三种方式最终都调用同一个后端 API，业务校验只在后端做一次：
1. 实时扫码（html5-qrcode，安全上下文可用时）；
2. 拍照识别（`<input type="file" accept="image/*" capture="environment">` + 前端解码，摄像头不可用/被拒时自动出现）；
3. 手动输入参与者编号。

### 7.2 手机安装证书（安卓优先）
- **方法一（快速）**：Chrome 打开 `https://36.138.220.233:5000`，出现警告时点「高级 → 继续前往」。
- **方法二（推荐，安装后不再警告）**：打开 `https://36.138.220.233:5000/ca.crt`（登录页也有「首次使用：安装根证书」链接）下载证书，然后进入 **设置 → 安全 → 更多安全设置 → 加密与凭据 → 安装证书 → CA 证书**，选择下载的文件。不同品牌菜单位置可能不同，可在设置中搜索「CA 证书」。Android 11 以后直接点击下载的文件无法安装，必须从设置里安装。
- **iOS（次要）**：下载后在「设置」中安装描述文件，再到 **通用 → 关于本机 → 证书信任设置** 中开启完全信任。

### 7.3 服务器组成（不影响已有服务）
| 组件 | 说明 |
|---|---|
| 代码目录 | `/opt/graduation-checkin`（独立 venv：`.venv`） |
| 应用服务 | `graduation-checkin.service`：gunicorn + gevent（1 worker，WebSocket），`0.0.0.0:5000` HTTPS，开机自启、崩溃自动重启 |
| Redis | 专用实例 `graduation-checkin-redis.service`，仅监听 `127.0.0.1:6391`（不复用其他项目的 Redis，避免 Pub/Sub 频道互相干扰） |
| PostgreSQL | 复用已有实例（127.0.0.1:25032），新建专用库与用户 `grad_checkin`，不触碰其他数据库 |
| 证书 | `/opt/graduation-checkin/certs/`：`ca.crt`（公开）、`server.crt/server.key`（IP 证书）、`ca.key`（权限 600，永不离开服务器、不进 Git） |
| 密钥 | `/opt/graduation-checkin/.env`（SECRET_KEY、数据库密码），权限 600，只存在于服务器 |
| 端口 | 对外仅新增 5000；nginx（80/443/8080/9443/9444/8444）及其他应用均未改动 |

### 7.4 部署步骤
服务器禁用了 scp/sftp，且短时间多次 SSH 会被重置，因此用一次 tar 管道上传、一次 SSH 执行：
```bash
# 本地：打包上传（不含 .venv/.env/.git）
tar --exclude=.venv --exclude=.env --exclude=.git --exclude='__pycache__' --exclude='._*' -cf - . \
  | ssh root@36.138.220.233 'tar xf - -C /opt/graduation-checkin'
# 服务器：安装依赖、初始化数据库、导入测试数据、安装并重启 systemd 服务、健康检查
ssh root@36.138.220.233 'cd /opt/graduation-checkin && PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple bash deploy/deploy.sh'
```

### 7.5 服务管理命令
```bash
systemctl status graduation-checkin          # 状态
systemctl restart graduation-checkin         # 重启（数据在 PostgreSQL，不丢失）
journalctl -u graduation-checkin -f          # 实时日志
systemctl status graduation-checkin-redis    # 专用 Redis
```

---

## 8. 验收结果与未完成项

_（最终验收后补充）_
