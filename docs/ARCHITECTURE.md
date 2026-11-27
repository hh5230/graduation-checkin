# 架构与接口契约（Claude 制定，Codex 必须遵守，不得擅自修改）

> 本文件是唯一的设计依据。实现中如发现契约有问题，在交付说明里写明，不要自行改动契约。

## 1. 功能清单（逐项对应原始需求 §1.2）

| # | 需求 | 实现位置 | 角色 |
|---|---|---|---|
| F1 | 管理员登录 | `/login` 页 + `POST /api/auth/login` | admin |
| F2 | 新增/编辑/查询参与者（姓名、邮箱、唯一编号） | `/admin` 页 + `/api/participants*` | admin |
| F3 | 每位参与者独立 QR Code | `GET /api/participants/<id>/qr.png`（QR 内容=不可猜测 token） | admin |
| F4 | 查看签到状态、上台状态 | `/admin` 列表的状态列 + 时间/操作人 | admin |
| F5 | 搜索 + 按状态筛选 | `GET /api/participants?q=&status=` | admin |
| F6 | 工作人员登录 | 同 F1，role=staff | staff |
| F7 | 手机浏览器摄像头扫码（无须 App） | `/entry` 页，html5-qrcode | staff/admin |
| F8 | 扫码后显示资料，工作人员确认签到 | `GET /api/lookup` → 确认按钮 → `POST /api/checkin` | staff/admin |
| F9 | 记录签到时间与操作人 | `participants.checked_in_at / checked_in_by` + `audit_logs` | — |
| F10 | 防重复签到 | 条件 UPDATE，`409 ALREADY_CHECKED_IN`（含首次时间、操作人） | — |
| F11 | 无效二维码/异常处理 | `INVALID_QR`、`PARTICIPANT_NOT_FOUND`、摄像头权限失败提示等 | — |
| F12 | 手动输入参与者编号 | `/entry`、`/stage` 均有输入框，`code` 参数 | staff/admin |
| F13 | 舞台扫同一个 QR | `/stage` 页扫码 → `POST /api/stage/queue` | staff/admin |
| F14 | 仅已签到者可入队 | 条件 UPDATE `WHERE status='checked_in'`，否则 `NOT_CHECKED_IN` | — |
| F15 | 防重复入队 | 同上，`ALREADY_QUEUED` | — |
| F16 | 队列按加入时间排序 | `ORDER BY queued_at, id` | — |
| F17 | 呼叫下一位 | `POST /api/stage/call-next`（事务 + advisory lock + SKIP LOCKED） | staff/admin |
| F18 | 确认完成上台 | `POST /api/stage/complete` | staff/admin |
| F19 | 独立全屏舞台显示页 | `/display` | staff/admin 登录的大屏 |
| F20 | 切换后自动更新 | Socket.IO `stage_updated` 事件 | — |
| F21 | Dashboard 六项统计 | `/dashboard` + `GET /api/stats` + Socket.IO `stats_updated` | staff/admin |
| T1 | 中英文切换 | 前端 `static/i18n/{zh,en}.json` + 后端错误文案 zh/en | — |

## 2. 技术栈与目录

- Python 3.12, Flask 3, Flask-SQLAlchemy 3 (SQLAlchemy 2), psycopg 3, Flask-SocketIO 5（async_mode=`threading` + simple-websocket）
- PostgreSQL 16（docker, host 端口 **5434**），Redis 7（docker, host 端口 **6380**）。本机已有 5432/5433/6379 占用，所以用非默认端口。
- 前端：Jinja2 模板 + 原生 JS + CSS，移动优先；html5-qrcode（CDN：`https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js`）；socket.io 客户端（CDN：`https://cdn.socket.io/4.7.5/socket.io.min.js`）

```
app/
  __init__.py        create_app(config_name) 工厂；注册蓝图、错误处理、socketio、CLI
  config.py          Config / TestConfig，读取 .env
  extensions.py      db = SQLAlchemy(), socketio = SocketIO(), redis_client 封装
  models.py          User, Participant, AuditLog（与 db/schema.sql 完全一致）
  errors.py          ApiError(code, http_status, details) + 统一 JSON 错误处理
  i18n.py            后端错误文案 {code: {zh, en}}，get_lang(request)
  auth.py            login_required / role_required 装饰器（API 返回 401/403 JSON；页面重定向/403 页）
  realtime.py        broadcast_state_change(...)：提交后广播；socket connect 鉴权
  services/
    participants.py  CRUD、搜索、token 生成、lookup
    checkin.py       签到（条件 UPDATE）
    stage.py         入队、呼叫下一位、完成、队列查询（事务 + 锁）
    stats.py         统计（PG 计算 + Redis 缓存）
    qr.py            生成 QR PNG
  api/               auth.py, participants.py, checkin.py, stage.py, stats.py （蓝图，薄控制层）
  views.py           页面路由
  templates/         base.html, login.html, admin.html, entry.html, stage.html, display.html, dashboard.html, error.html
  static/css/app.css
  static/js/         api.js(fetch 封装), i18n.js, scanner.js(扫码封装), realtime.js, admin.js, entry.js, stage.js, display.js, dashboard.js
  static/i18n/       zh.json, en.json
db/schema.sql        权威 DDL（幂等，可重复执行）
scripts/init_db.py   执行 schema.sql + 创建默认账号（幂等）
scripts/seed.py      导入测试参与者（幂等，按编号 upsert）
scripts/concurrency_test.py  对运行中的服务发起并发签到/入队/呼叫，验证只有一次成功
tests/               pytest（使用独立测试库 graduation_test）
run.py               socketio.run(app, host=0.0.0.0, port=5001)
```

## 3. 数据库设计（PostgreSQL 是唯一业务数据来源）

完整 DDL 见 `db/schema.sql`。要点：

- `users`：`id`, `username UNIQUE`, `password_hash`（werkzeug pbkdf2/scrypt）, `display_name`, `role CHECK IN ('admin','staff')`, `is_active`, `created_at`
- `participants`：
  - `participant_code VARCHAR(32) UNIQUE`（人类可读编号，如 `G2026001`，手动输入用）
  - `email` 唯一：`UNIQUE INDEX ON lower(email)`（大小写不敏感）
  - `qr_token VARCHAR(64) UNIQUE`：`secrets.token_urlsafe(24)`，QR 只编码此 token，绝不编码自增 id
  - `status CHECK IN ('registered','checked_in','queued','on_stage','completed')`
  - 审计列：`checked_in_at/by`, `queued_at/by`, `called_at/by`, `completed_at/by`（by → users.id）
  - CHECK 约束保证状态与时间戳一致（例如 status≥checked_in ⇒ checked_in_at NOT NULL）
  - **部分唯一索引** `uq_one_on_stage ON participants ((true)) WHERE status='on_stage'` → 数据库层面保证同一时刻最多一人 on_stage
  - 队列索引 `ix_queue ON participants (queued_at, id) WHERE status='queued'`
  - 搜索索引：`status`、`lower(name)`
- `audit_logs`：`participant_id`, `action CHECK IN ('create','update','check_in','enqueue','call','complete','regenerate_qr')`, `operator_id`, `created_at`, `details JSONB`。每次状态变化与业务 UPDATE 在**同一事务**写入。
- 队列建模：队列状态直接存在 participants 行上（一人一行 ⇒ 不可能重复入队；配合条件 UPDATE 状态校验）。

## 4. 状态机（后端强制）

```
registered --check_in--> checked_in --enqueue--> queued --call_next--> on_stage --complete--> completed
```
任何其他跳转一律拒绝（`INVALID_STATE` 或更具体的错误码）。编辑参与者资料不能修改 status。

## 5. 并发与一致性方案

| 操作 | 实现 | 并发结果 |
|---|---|---|
| 签到 | `UPDATE participants SET status='checked_in', checked_in_at=now(), checked_in_by=:uid, updated_at=now() WHERE id=:id AND status='registered' RETURNING id` | 只有 1 个事务影响 1 行；其余 0 行 → 重新查询，返回 `ALREADY_CHECKED_IN`（附首次 `checked_in_at`、`checked_in_by_name`） |
| 入队 | `UPDATE ... SET status='queued', queued_at=clock_timestamp(), queued_by=:uid WHERE id=:id AND status='checked_in'` | 0 行时按当前状态返回 `NOT_CHECKED_IN` / `ALREADY_QUEUED` / `INVALID_STATE` |
| 呼叫下一位 | 单事务：`SELECT pg_advisory_xact_lock(<STAGE_LOCK_KEY>)` 串行化舞台操作 → 若已有 on_stage 返回 `STAGE_BUSY` → `SELECT ... WHERE status='queued' ORDER BY queued_at, id LIMIT 1 FOR UPDATE SKIP LOCKED` → 无则 `QUEUE_EMPTY` → UPDATE 为 on_stage | 多设备同时点击只推进一人；部分唯一索引兜底（IntegrityError 映射为 `STAGE_BUSY`） |
| 完成上台 | 单事务 + 同一 advisory lock；`UPDATE ... SET status='completed' WHERE status='on_stage' [AND id=:expected_id]` | 重复点击第二次返回 `NOTHING_ON_STAGE` |

- 所有业务时间使用数据库时间（`now()` / `clock_timestamp()`），不用应用服务器时间。
- `call-next` 可选参数 `{"complete_current": true}`：在同一事务内先完成当前上台者再呼叫下一位（方便现场单键操作）。默认 false。
- 广播必须在 `db.session.commit()` **之后**发出；事务失败不广播。

## 6. Redis 用途（辅助，不存业务状态）

1. Flask-SocketIO `message_queue=REDIS_URL`：多进程/多实例之间广播（也允许外部脚本通过 `SocketIO(message_queue=...)` 推送）。
2. 统计缓存：key `stats:v1`，TTL 10 秒；任何状态变化提交后 `DEL stats:v1`。Redis 不可用时降级为直接查 PG（记录 warning，不影响业务）。
3. `GET /api/health` 返回 `{db: "ok", redis: "ok"|"error"}`。

## 7. 身份认证与权限

- Flask 签名 session cookie（`HttpOnly`，`SameSite=Lax`），session 存 `user_id`；每次请求从 DB 读取用户并校验 `is_active`。
- 角色：
  - `admin`：全部功能。
  - `staff`：签到、舞台操作、lookup、Dashboard、Display；**不能**访问参与者列表/新增/编辑/QR 图片（403）。
- API：未登录 → 401 `UNAUTHORIZED`；角色不足 → 403 `FORBIDDEN`。
- 页面：未登录 → 302 到 `/login?next=...`；角色不足 → 403 错误页。
- Socket.IO：`connect` 时校验 session 中已登录，否则拒绝连接（`return False`）。
- 写操作 API 要求 `Content-Type: application/json`（降低 CSRF 风险：跨站表单无法发 JSON）。

## 8. API 契约

### 8.1 通用格式
- 成功：`{"ok": true, "data": <payload>}`
- 失败：`{"ok": false, "error": {"code": "ALREADY_CHECKED_IN", "message": "<按语言本地化>", "details": {...}}}`
- 语言：请求头 `X-Lang: zh|en` 优先，其次 cookie `lang`，其次 `Accept-Language`，默认 `zh`。
- 时间：ISO 8601 带时区（UTC，如 `2026-11-27T12:00:00+00:00`）。

### 8.2 Participant 序列化（所有接口统一）
```json
{
  "id": 1, "participant_code": "G2026001", "name": "张三", "email": "a@example.com",
  "status": "checked_in",
  "checked_in_at": "...", "checked_in_by": {"id": 2, "name": "Staff One"},
  "queued_at": null, "queued_by": null,
  "called_at": null, "called_by": null,
  "completed_at": null, "completed_by": null,
  "created_at": "...", "updated_at": "..."
}
```
`qr_token` 只在 admin 接口（列表/详情）中返回字段 `qr_token`；staff 接口不返回。

### 8.3 错误码

| code | HTTP | 场景 | details |
|---|---|---|---|
| `UNAUTHORIZED` | 401 | 未登录 / 会话失效 | — |
| `INVALID_CREDENTIALS` | 401 | 用户名或密码错误 | — |
| `FORBIDDEN` | 403 | 角色无权限 | — |
| `VALIDATION_ERROR` | 400 | 参数缺失/格式错 | `{fields: {name: "required"}}` |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 写操作非 JSON | — |
| `NOT_FOUND` | 404 | 路由/资源不存在 | — |
| `PARTICIPANT_NOT_FOUND` | 404 | 编号不存在 | `{code}` |
| `INVALID_QR` | 404 | token 格式非法或不存在 | — |
| `DUPLICATE_CODE` | 409 | 编号重复 | — |
| `DUPLICATE_EMAIL` | 409 | 邮箱重复 | — |
| `ALREADY_CHECKED_IN` | 409 | 重复签到 | `{checked_in_at, checked_in_by: {id,name}, participant}` |
| `NOT_CHECKED_IN` | 409 | 未签到就入队 | `{participant}` |
| `ALREADY_QUEUED` | 409 | 重复入队（status=queued） | `{queued_at, participant, position}` |
| `INVALID_STATE` | 409 | 其他非法状态跳转（如已 on_stage/completed 再入队） | `{status, participant}` |
| `QUEUE_EMPTY` | 409 | 呼叫下一位时队列为空 | — |
| `STAGE_BUSY` | 409 | 已有人在台上，需先完成 | `{current}` |
| `NOTHING_ON_STAGE` | 409 | 完成时无人在台上 / expected_id 不匹配 | — |
| `INTERNAL_ERROR` | 500 | 未预期异常（不泄露堆栈） | — |

### 8.4 接口列表

| 方法 | 路径 | 角色 | 请求 | 成功响应 data |
|---|---|---|---|---|
| GET | `/api/health` | 公开 | — | `{db, redis}` |
| POST | `/api/auth/login` | 公开 | `{username, password}` | `{user: {id, username, display_name, role}}` |
| POST | `/api/auth/logout` | 登录 | — | `{}` |
| GET | `/api/auth/me` | 登录 | — | `{user}` |
| GET | `/api/participants` | admin | query: `q`(姓名/邮箱/编号 模糊, ILIKE), `status`, `page`(默认1), `per_page`(默认20,最大100) | `{items: [P], total, page, per_page}`，按 `id` 升序 |
| POST | `/api/participants` | admin | `{participant_code, name, email}` | `P`（201） |
| GET | `/api/participants/<id>` | admin | — | `P` |
| PATCH | `/api/participants/<id>` | admin | `{participant_code?, name?, email?}`（不可改 status） | `P` |
| POST | `/api/participants/<id>/regenerate-qr` | admin | — | `P`（旧二维码失效） |
| GET | `/api/participants/<id>/qr.png` | admin | — | `image/png` |
| GET | `/api/lookup` | staff/admin | query: `token` 或 `code`（二选一） | `P`（不含 qr_token） |
| POST | `/api/checkin` | staff/admin | `{token}` 或 `{code}` | `P`（status=checked_in） |
| POST | `/api/stage/queue` | staff/admin | `{token}` 或 `{code}` | `{participant: P, position: <int, 1 起>}` |
| GET | `/api/stage/state` | staff/admin | — | `{current: P\|null, queue: [P...按 queued_at,id], recent_completed: [P...最近 5 个, completed_at desc]}` |
| POST | `/api/stage/call-next` | staff/admin | `{complete_current?: bool}` | `{current: P, completed: P\|null}` |
| POST | `/api/stage/complete` | staff/admin | `{participant_id?: int}` | `{completed: P}` |
| GET | `/api/stats` | staff/admin | — | 见下 |

`/api/stats` data：
```json
{"total": 30, "checked_in": 12, "not_checked_in": 18, "waiting": 3, "on_stage": 1, "completed": 5}
```
- `total` = 全部参与者；`not_checked_in` = status='registered'；`checked_in` = status ∈ {checked_in, queued, on_stage, completed}（曾签到即计入）；`waiting` = queued；`on_stage`；`completed`。恒等式：`checked_in + not_checked_in = total`。

QR 扫描结果解析：二维码内容为 `GRAD:<token>`；前端扫描后去掉 `GRAD:` 前缀再作为 `token` 发送；后端也接受带前缀的 token（自动剥离）。不符合 `^[A-Za-z0-9_-]{16,64}$` 的 token → `INVALID_QR`。

## 9. 实时同步（Socket.IO，默认 namespace `/`）

服务端在事务提交后 emit（广播给所有已认证连接）：

| 事件 | payload | 触发 |
|---|---|---|
| `participant_updated` | `{action, participant: P}` | create/update/check_in/enqueue/call/complete/regenerate_qr |
| `stage_updated` | `{current: P\|null, queue: [P], recent_completed: [P]}`（即 `/api/stage/state` 同结构） | enqueue/call/complete |
| `stats_updated` | stats 对象 | 任何会改变统计的操作 |

客户端：收到事件直接用 payload 更新 UI；`connect`（含重连）时调用 REST 接口重新拉取完整状态，作为断线补偿。页面刷新从 API 拉取。

## 10. 中英文切换

- 前端：`static/i18n/zh.json`、`en.json` 扁平 key（如 `"entry.confirm": "确认签到"`）；元素用 `data-i18n="key"`（文本）、`data-i18n-placeholder="key"`；`i18n.js` 提供 `t(key, params)`、`setLang(lang)`（写 localStorage + cookie `lang`，重新渲染），每页右上角有 `中文 / EN` 切换按钮。
- 状态值显示通过 `status.<value>` key 翻译。
- `api.js` 每个请求带 `X-Lang` 头；后端错误 `message` 按语言返回；前端优先使用 `t('error.'+code)`，缺失时显示后端 message。

## 11. 默认账号（init_db 创建）

| 用户名 | 密码 | 角色 |
|---|---|---|
| admin | admin123 | admin |
| staff1 | staff123 | staff |
| staff2 | staff123 | staff |

## 12. 配置（.env）

`DATABASE_URL=postgresql+psycopg://grad:grad@localhost:5434/graduation`
`TEST_DATABASE_URL=postgresql+psycopg://grad:grad@localhost:5434/graduation_test`
`REDIS_URL=redis://localhost:6380/0`
`SECRET_KEY=change-me`
`PORT=5001`
