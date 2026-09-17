# File Service — 轻量图片文件存储微服务

> 服务端口：**9094** ｜ 技术栈与工程规范严格对齐 `mservice-fastapi-user` / `mservice-fastapi-metastorage`

为 CaloPlan 提供图片文件存储：**JWT 鉴权上传**（防接口滥用），**公开 URL 访问**（随机 UUID 文件名即访问凭证）。存储层通过 `StorageProvider` 抽象，当前实现本地磁盘，未来可无缝替换为 COS / OSS / S3。

## 相关项目（CaloPlan 全家桶）

CaloPlan 全栈项目统一托管在 GitHub Organization [caloplan](https://github.com/caloplan)：

| 类型 | 项目 | 与本项目关系 |
| --- | --- | --- |
| 前端 | [coloplan-v2](https://github.com/caloplan/coloplan-v2) | 客户端（图片上传链路） |
| SDK | [caloplan-core](https://github.com/caloplan/caloplan-core) | 业务核心（兄弟模块） |
| SDK | [caloplan-user](https://github.com/caloplan/caloplan-user) | 用户模块（兄弟模块） |
| SDK | [caloplan-chat](https://github.com/caloplan/caloplan-chat) | AI 对话 SDK（图片识别链路） |
| SDK | [caloplan-cache](https://github.com/caloplan/caloplan-cache) | 通用缓存（兄弟模块） |
| 服务 | [fastapi-chat-service](https://github.com/caloplan/fastapi-chat-service) | AI 对话微服务（兄弟服务） |
| 服务（本仓库） | [fastapi-file-service](https://github.com/caloplan/fastapi-file-service) | 图片文件存储微服务 |
| 服务 | [mservice-fastapi-user](https://github.com/caloplan/mservice-fastapi-user) | 认证 / 用户微服务（JWT 签发方） |
| 服务 | [mservice-fastapi-metastorage](https://github.com/caloplan/mservice-fastapi-metastorage) | 元数据微服务（兄弟服务） |

本服务只校验 `mservice-fastapi-user` 签发的 JWT，不签发令牌；供 `coloplan-v2` 等前端上传图片使用。

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI（异步） |
| 数据验证 | Pydantic v2 + pydantic-settings |
| JWT 校验 | python-jose + cryptography（消费 user-service 令牌，RS256） |
| HTTP 客户端 | httpx（拉取 user-service JWKS） |
| 日志 | RotatingFileHandler 轮转 |
| 测试 | pytest + pytest-asyncio + httpx |
| 容器化 | Docker + docker-compose |

> 无数据库、无删除/分片上传、无用户文件管理——刻意保持轻量。

## 目录结构

```
fastapi-file-service/
├── app/
│   ├── main.py                    # 应用入口（lifespan 初始化存储目录）
│   ├── core/
│   │   ├── config.py              # Settings（含 USER_SERVICE_URL / 存储与文件限制配置）
│   │   ├── security.py            # JWKS 获取/缓存 + JWT 校验（消费 user-service 令牌）
│   │   └── dependencies.py        # 认证依赖（get_current_user）
│   ├── schemas/
│   │   └── file.py                # 上传响应 {key, url}
│   ├── storage/
│   │   ├── base.py                # StorageProvider 抽象接口
│   │   ├── local.py               # LocalStorageProvider（本地磁盘实现）
│   │   └── __init__.py            # get_storage() 单例入口
│   ├── services/
│   │   └── file_service.py        # 文件类型/大小校验、UUID 命名、存储读写
│   ├── api/v1/routes/
│   │   └── files.py               # POST /files（鉴权）、GET /files/{key}（公开）
│   └── utils/
│       └── logger.py              # 轮转日志
├── tests/
│   ├── conftest.py                # 测试 fixtures（RSA 密钥对、JWT 签发、JWKS mock、临时存储）
│   └── test_api/
│       └── test_files.py          # 上传/下载接口测试
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── docker-compose.yml
└── pytest.ini
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements-dev.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少确认 USER_SERVICE_URL 指向运行中的 user-service
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload --port 9094
```

访问 `http://localhost:9094/docs` 查看交互式 API 文档。

### 4. 健康检查

```bash
curl http://localhost:9094/health
# {"status":"healthy","service":"File Service","version":"1.0.0"}
```

## API 端点

前缀 `/api/v1`，服务端口 9094。上传需认证，下载公开。

| 方法 | 端点 | 功能 | 权限 |
|------|------|------|------|
| POST | `/files` | 上传图片到**默认目录**（`STORAGE_CATEGORIES` 第一个，默认 image） | **需 JWT** |
| POST | `/files/{dir}` | 上传图片到**指定目录**（dir 必须在白名单中） | **需 JWT** |
| GET | `/files/{dir}/{key}` | 按目录 + key 获取图片 | **公开** |
| GET | `/health` | 健康检查 | 公开 |
| GET | `/` | 服务信息 | 公开 |

### 上传示例

```bash
# 上传到默认目录（image）
curl -X POST http://localhost:9094/api/v1/files \
  -H "Authorization: Bearer <token>" \
  -F "file=@avatar.png;type=image/png"
# 201 → {"key":"image/<32位uuidhex>.png","url":"http://localhost:9094/api/v1/files/image/<key>"}

# 上传到指定目录（如 avatar，需先加入 STORAGE_CATEGORIES）
curl -X POST http://localhost:9094/api/v1/files/avatar \
  -H "Authorization: Bearer <token>" \
  -F "file=@avatar.png;type=image/png"
```

### 下载示例

```bash
curl http://localhost:9094/api/v1/files/image/<key> -o avatar.png
```

## 认证与权限

本服务**不签发令牌**，只校验 user-service 签发的 JWT（与 metastorage 完全一致）：

1. 读取 JWT Header 中的 `kid`；
2. 本地 JWKS 缓存命中则用对应公钥验证（RS256）；
3. 未命中或缓存过期则从 `http://user-service:8000/.well-known/jwks.json` 强制刷新后再验证；
4. 兼容 user-service 的密钥轮换（多 kid）。

JWKS 缓存带 TTL（`JWKS_CACHE_TTL_SECONDS`，默认 3600 秒）。

- `POST /files` 要求 `Authorization: Bearer <access_token>`（`type=access`），仅用于防止接口被滥用，不区分用户权限、不落库；
- `GET /files/{key}` **无需鉴权**——文件名是随机 UUID，不可枚举，即访问凭证。

## 文件规则

| 规则 | 默认值 | 说明 |
|------|--------|------|
| 存储目录 | `["image"]`（`STORAGE_CATEGORIES`） | 白名单：上传/下载按目录路由，目录不在列表中返回 **422**（下载 404） |
| 允许扩展名 | `.jpg` / `.jpeg` / `.png` / `.webp` | 不支持返回 **415** |
| 允许 MIME | `image/jpeg` / `image/png` / `image/webp` | 不匹配返回 **415** |
| 单文件大小 | 5MB（`MAX_FILE_SIZE`） | 超过返回 **413** |
| 文件名 | `uuid4().hex + 扩展名` | 避免文件名冲突与路径注入 |
| key 格式 | `{目录}/{uuid}.{ext}` | 如 `image/3f2a…c9.png` |

安全要点：

- **目录白名单路由**：`POST /files/{dir}` 的 dir 与 `GET /files/{dir}/{key}` 的 dir 均须在 `STORAGE_CATEGORIES` 中，未配置的目录一律拒绝（上传 422 / 下载 404）；
- **路径注入防护**：文件名严格校验为 `[0-9a-f]{32}.(jpg|jpeg|png|webp)`，目录白名单 + `StorageProvider` 路径越界兜底，`../../etc/passwd` 之类一律 404；
- **超大文件防护**：读取时上限 `MAX_FILE_SIZE + 1` 字节，不会将超大文件整体读入内存；
- **原子写入**：先写临时文件再替换，避免进程中断留下半截文件。

## 存储层抽象

`app/storage/base.py` 定义 `StorageProvider` 接口（`save` / `open` / `exists`），路由与 Service 只依赖接口，不接触文件系统：

- 当前实现：`LocalStorageProvider`（保存到 `STORAGE_DIR`，默认 `storage/`）；
- 未来替换：实现 `StorageProvider`（如 COS / OSS / S3），在 `app/storage/__init__.py` 的 `get_storage()` 中更换实现类即可，业务代码零改动。

## 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `APP_NAME` | File Service | 应用名 |
| `APP_VERSION` | 1.0.0 | 版本号 |
| `APP_ENV` | development | 运行环境 |
| `HOST` | 0.0.0.0 | 监听地址 |
| `PORT` | 9094 | 服务端口 |
| `USER_SERVICE_URL` | http://localhost:8000 | user-service 地址（拉取 JWKS） |
| `JWKS_CACHE_TTL_SECONDS` | 3600 | JWKS 缓存 TTL（秒） |
| `ALGORITHM` | RS256 | JWT 签名算法 |
| `STORAGE_DIR` | storage | 本地存储根目录 |
| `STORAGE_CATEGORIES` | ["image"] | 允许的存储目录分类（白名单，第一个为默认目录） |
| `MAX_FILE_SIZE` | 5242880 | 单文件大小上限（字节，5MB） |
| `ALLOWED_CONTENT_TYPES` | ["image/jpeg","image/png","image/webp"] | 允许的 MIME 类型 |
| `ALLOWED_EXTENSIONS` | [".jpg",".jpeg",".png",".webp"] | 允许的文件扩展名 |
| `LOG_LEVEL` | INFO | 日志级别 |
| `LOG_FILE` | logs/file_service.log | 日志文件路径 |
| `LOG_MAX_BYTES` | 10485760 | 单日志文件最大字节 |
| `LOG_BACKUP_COUNT` | 5 | 日志轮转保留份数 |
| `ALLOWED_ORIGINS` | ["http://localhost:3000","http://localhost:9094"] | CORS 允许来源 |

## Docker 部署

```bash
docker-compose up -d --build
```

- 服务名：`file-service`，端口映射 `9094:9094`；
- 数据卷：`./storage:/app/storage`（上传图片持久化）、`./logs:/app/logs`；
- `USER_SERVICE_URL` 默认指向 Docker 同网络内的 `http://user-service:8000`，若 user-service 在外部需修改；
- 健康检查探测 `/health`，每 30 秒一次，超时 10 秒，重试 3 次。

## 测试

```bash
pytest tests/ -v
```

测试覆盖（12 项）：
- 鉴权：无 token / 伪造 token 上传 → 401
- 上传成功：png / jpeg / webp / 大写扩展名，返回 `{key, url}` 且文件落盘、可下载还原
- 校验失败：非法扩展名 → 415、MIME 不匹配 → 415、超过 5MB → 413
- 下载：不存在 → 404、非法 key（路径注入等）→ 404、公开访问无需 token

测试通过 mock JWKS 拉取、使用测试 RSA 密钥对签发 JWT、使用临时存储目录，无需真实运行 user-service。

## 与 user-service 的 JWT 对接说明

1. 用户通过 user-service 的 `POST /api/v1/auth/login` 获取 JWT（payload 携带 `sub / user_id / service_name / role / type`）；
2. 上传时请求头携带 `Authorization: Bearer <token>`，本服务从 user-service 拉取 JWKS 公钥验证签名（RS256），兼容密钥轮换；
3. 下载无需任何凭证，直接访问随机 UUID URL。
